"""Lens dependencies: authorization as a data dependency.

**Each returns the value the handler needs**, rather than guarding and
returning nothing [TC-11, security-design §A]. That is the whole design:
a handler cannot compile a teacher-scoped query without ``owner_id``,
and ``owner_id`` arrives only inside a :class:`TeacherLens`. A guard
whose absence is invisible produces an endpoint that works perfectly and
authorizes nothing; a dependency that carries the scoping value cannot
be forgotten, because forgetting it means having nothing to scope on.

The route-enumeration gate U2 built matches on the dependency's **return
annotation** being a ``Lens`` subtype rather than on its name, so
renaming one of these does not defeat the check.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Protocol, cast

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.tokens import verify_access_token
from app.authz.lenses import GuardianLens, Lens, StudentLens, TeacherLens
from app.authz.resolve import LensResolver
from app.errors import AuthorizationError

__all__ = [
    "guardian_lens",
    "student_lens",
    "teacher_lens",
]


#: Where the verified account is memoized for the rest of the request.
_ACCOUNT_MEMO = "_aidlc_account_id"


class _HasState(Protocol):
    """The one attribute of a request lens resolution touches."""

    state: object


def get_session(request: Request) -> Session:
    """Return the request-scoped session.

    :param request: The incoming request
    :return: The session for this request
    """
    session: Session = request.state.session
    return session


def authenticated_account(request: Request) -> uuid.UUID:
    """Return the account this request's access token names.

    **U4 is the first Unit with an authenticated, lensed route**, so
    this is where the Bearer header first gets read. U3 shipped
    :func:`verify_access_token` and three routes that did not need it:
    two are public and the third authenticates by refresh token in the
    body.

    Resolved per request and memoized on ``request.state``, so a route
    taking two lens dependencies verifies the token once. The memo is
    request-scoped like the lens memo and for the same reason -- a
    process-level cache would be a cached authentication.

    :param request: The incoming request
    :return: The authenticated account id
    :raises AuthorizationError: The header is missing or the token is
        unverifiable, expired or malformed
    """
    memo: object = getattr(request.state, _ACCOUNT_MEMO, None)
    if isinstance(memo, uuid.UUID):
        return memo

    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthorizationError(
            code="NOT_AUTHENTICATED",
            message_key="auth.token.not_valid",
            status=401,
        )

    # verify_access_token raises AuthorizationError itself for an
    # expired, unsigned or unknown-kid token, so it is not re-wrapped:
    # doing so would flatten its 401 into this module's default 403.
    account_id = verify_access_token(token)
    setattr(request.state, _ACCOUNT_MEMO, account_id)
    return account_id


def _resolved(
    request: Request,
    session: Session,
    account_id: uuid.UUID,
) -> list[Lens]:
    """Resolve this request's lenses, memoized within the request.

    The resolver is typed against a minimal protocol rather than against
    ``Request``, so the cast here is where FastAPI's concrete type meets
    it. Resolution must stay unaware of the web framework: it is the one
    piece of authorization U3 made reusable, and importing ``Request``
    into it would tie lens resolution to HTTP.

    :param request: The request carrying the memo
    :param session: The session to query through
    :param account_id: The authenticated account
    :return: Every lens the account's data supports
    """
    carrier = cast("_HasState", request)
    return list(LensResolver(session).resolve(carrier, account_id))


def teacher_lens(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> TeacherLens:
    """Resolve the teacher lens, carrying the owner id to scope on.

    :param request: The request carrying the lens memo
    :param session: The session to query through
    :param account_id: The authenticated account
    :return: The teacher lens
    :raises AuthorizationError: This account owns no batches
    """
    for lens in _resolved(request, session, account_id):
        if isinstance(lens, TeacherLens):
            return lens
    raise AuthorizationError(
        code="NO_TEACHER_LENS",
        message_key="authz.lens.not_available",
    )


def student_lens(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> StudentLens:
    """Resolve the student lens.

    :param request: The request carrying the lens memo
    :param session: The session to query through
    :param account_id: The authenticated account
    :return: The student lens
    :raises AuthorizationError: This account holds no student seat
    """
    for lens in _resolved(request, session, account_id):
        if isinstance(lens, StudentLens):
            return lens
    raise AuthorizationError(
        code="NO_STUDENT_LENS",
        message_key="authz.lens.not_available",
    )


def guardian_lens(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> GuardianLens:
    """Resolve the guardian lens.

    ``child_enrollment_id`` may be None here: the first authenticated
    request has not selected a child yet, and the child arrives as a
    **path parameter** on later requests rather than from a client hint
    [BR5.1].

    :param request: The request carrying the lens memo
    :param session: The session to query through
    :param account_id: The authenticated account
    :return: The guardian lens
    :raises AuthorizationError: This account is nobody's recorded guardian
    """
    for lens in _resolved(request, session, account_id):
        if isinstance(lens, GuardianLens):
            return lens
    raise AuthorizationError(
        code="NO_GUARDIAN_LENS",
        message_key="authz.lens.not_available",
    )
