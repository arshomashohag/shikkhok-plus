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

import sqlalchemy as sa
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.client_address import client_address
from app.auth.tokens import ADMIN_AUDIENCE, verify_access_token, verify_scoped_token
from app.authz.admin import (
    ADMIN_EDGE_HEADER,
    admin_edge_ok,
    admin_network_ok,
    is_platform_admin,
)
from app.authz.classes import resolve_class_lens, resolve_examiner_lens
from app.authz.invitations import available_invitations
from app.authz.lenses import (
    ClassTeacherLens,
    ExaminerLens,
    GuardianLens,
    InvitationLens,
    Lens,
    MembershipLens,
    PlatformAdminLens,
    StudentLens,
    TeacherLens,
)
from app.authz.resolve import LensResolver
from app.centres.memberships import available_memberships
from app.errors import AuthorizationError
from app.errors.codes import NOT_AVAILABLE

__all__ = [
    "WORKSPACE_HEADER",
    "admin_gate",
    "choose_workspace",
    "class_teacher_lens",
    "examiner_lens",
    "family_lens",
    "family_lenses",
    "guardian_lens",
    "invitation_lens",
    "membership_lens",
    "platform_admin_lens",
    "student_lens",
    "teacher_lens",
]


#: Where the verified account is memoized for the rest of the request.
_ACCOUNT_MEMO = "_aidlc_account_id"

#: The memo for the token's subject alone, before the account is looked up.
_SUBJECT_MEMO = "_aidlc_token_subject"

#: Whether the account a token names still exists. Indexed on the key.
_ACCOUNT_EXISTS = sa.text("SELECT 1 FROM account WHERE id = :account_id")
_ADMIN_STANDING = sa.text(
    "SELECT a.phone, a.email, EXISTS (SELECT 1 FROM mfa_factor f "
    "WHERE f.account_id = a.id AND f.confirmed_at IS NOT NULL) AS confirmed "
    "FROM account a WHERE a.id = :account_id"
)


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


def token_subject(request: Request) -> uuid.UUID:
    """Return the account a validly signed, unexpired token names.

    **Signature and expiry only** -- the account may no longer exist.
    Every route but one wants :func:`authenticated_account`, which also
    requires the account; this is for ``DELETE /v1/me``, which must stay
    idempotent for a token whose account it has already deleted [BR1.4].

    Memoized on ``request.state`` so the token is verified once per
    request; request-scoped, because a process-level cache would be a
    cached authentication.

    :param request: The incoming request
    :return: The token's subject
    :raises AuthorizationError: The header is missing or the token is
        unverifiable, expired or malformed
    """
    memo: object = getattr(request.state, _SUBJECT_MEMO, None)
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
    subject = verify_access_token(token)
    setattr(request.state, _SUBJECT_MEMO, subject)
    return subject


def authenticated_account(request: Request) -> uuid.UUID:
    """Return the account this request's access token names -- if it exists.

    **Authentication is the signature AND an account row.** An access
    token lives fifteen minutes and cannot be recalled, so after
    ``DELETE /v1/me`` it stayed validly signed for an account that was
    gone: reads answered 200 with every field null and ``PATCH /v1/me``
    raised a 500 updating a row that was not there. A token naming a
    deleted account now gets the same 401 as an expired one, so a client
    does what it does for any ended session: refresh, which fails because
    the refresh tokens went with the account, then sign out.

    One indexed primary-key read per request, memoized with the rest, so
    a route taking two lens dependencies pays for it once.

    :param request: The incoming request
    :return: The authenticated account id
    :raises AuthorizationError: The token is missing, unverifiable,
        expired or malformed, or names an account that no longer exists
    """
    memo: object = getattr(request.state, _ACCOUNT_MEMO, None)
    if isinstance(memo, uuid.UUID):
        return memo

    account_id = token_subject(request)
    found = (
        get_session(request)
        .execute(_ACCOUNT_EXISTS, {"account_id": account_id})
        .first()
    )
    if found is None:
        raise AuthorizationError(
            code="NOT_AUTHENTICATED",
            message_key="auth.token.not_valid",
            status=401,
        )
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
    :return: The teacher lens for the workspace this request acts on
    :raises AuthorizationError: This account manages no workspace, or
        not the one the request names
    """
    workspaces = [
        lens
        for lens in _resolved(request, session, account_id)
        if isinstance(lens, TeacherLens)
    ]
    return choose_workspace(workspaces, request.headers.get(WORKSPACE_HEADER))


#: The header a client names the workspace it acts on with [0022].
WORKSPACE_HEADER = "X-Workspace-Id"


def choose_workspace(
    workspaces: list[TeacherLens], requested: str | None
) -> TeacherLens:
    """Pick the workspace a request acts on, from those the account manages.

    **The header is a choice, never a grant** [TC-11]. It selects among
    the workspaces the account's own data already gives it, resolved by
    the same query as every lens; naming any other workspace is refused
    with the same code as naming none, so it cannot test which centres
    exist. Without the header the solo workspace comes first, which is
    what every client sent before centres existed.

    :param workspaces: The account's teacher lenses, solo first
    :param requested: The header's value, if sent
    :return: The chosen lens
    :raises AuthorizationError: No workspace, or one not in the list
    """
    if requested is None or not requested.strip():
        if workspaces:
            return workspaces[0]
    else:
        for lens in workspaces:
            if str(lens.owner_id) == requested.strip():
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


def family_lenses(
    request: Request, session: Session, account_id: uuid.UUID
) -> list[StudentLens | GuardianLens]:
    """List this account's student and guardian lenses, student first.

    A plain helper rather than a dependency: a route that serves both
    family roles takes :func:`family_lens` for authentication and asks
    this for every candidate, because an account may be a student on
    one seat and a guardian on another.

    :param request: The request carrying the lens memo
    :param session: The session to query through
    :param account_id: The authenticated account
    :return: The family lenses, possibly empty
    """
    return [
        lens
        for lens in _resolved(request, session, account_id)
        if isinstance(lens, StudentLens | GuardianLens)
    ]


def family_lens(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> StudentLens | GuardianLens:
    """Resolve a student or guardian lens, for routes serving both.

    :param request: The request carrying the lens memo
    :param session: The session to query through
    :param account_id: The authenticated account
    :return: The first family lens, student first
    :raises AuthorizationError: This account holds no accepted family seat
    """
    found = family_lenses(request, session, account_id)
    if not found:
        raise AuthorizationError(
            code="NO_FAMILY_LENS",
            message_key="authz.lens.not_available",
        )
    return found[0]


def invitation_lens(
    enrollment_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> InvitationLens:
    """Resolve the invitation lens for one seat named in the path.

    **Not memoized and not taken from the request's resolved lenses**,
    which is the one place this dependency differs from the other three
    [ADR-011, NFR20.3]. The role lenses come from the per-request
    ``_LENS_QUERY``; an invitation grant is a SET resolved by its own
    statement on this route alone, so there is nothing on
    ``request.state`` to read and nothing the hot path pays for.

    The seat arrives as a **path parameter** and the grant is checked
    against it, never the other way round: the handler cannot reach a
    second seat because the lens it is handed carries exactly one.

    The refusal does not distinguish "no such seat" from "not yours",
    for the same reason a teacher reading another's batch gets a
    not-found [NFR14.13] -- except that this one answers 403, because
    an invitation route is reached from a list the person was already
    shown, so there is no id for them to enumerate that they were not
    handed.

    :param enrollment_id: The seat, from the route path
    :param session: The session to query through
    :param account_id: The authenticated account
    :return: The invitation lens for that one seat
    :raises AuthorizationError: No unaccepted link on that seat names
        this account
    """
    for lens in available_invitations(session, account_id):
        if lens.enrollment_id == enrollment_id:
            return lens
    raise AuthorizationError(
        code="NO_INVITATION_LENS",
        message_key="authz.lens.not_available",
    )


def membership_lens(
    member_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> MembershipLens:
    """Resolve the membership lens for one centre offer named in the path.

    Resolved by its own statement and never memoized, on
    :func:`invitation_lens`'s reasoning; the path id is checked against
    the grant, so a handler cannot reach a second offer.

    :param member_id: The membership, from the route path
    :param session: The session to query through
    :param account_id: The authenticated account
    :return: The membership lens for that one offer
    :raises AuthorizationError: No unanswered, unrevoked offer with that
        id names this account
    """
    for lens in available_memberships(session, account_id):
        if lens.member_id == member_id:
            return lens
    raise AuthorizationError(
        code="NO_MEMBERSHIP_LENS",
        message_key="authz.lens.not_available",
    )


def class_teacher_lens(
    session_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> ClassTeacherLens:
    """Resolve the class-teacher lens for the one class in the path [C4].

    Resolved by its own statement and never memoized, on
    :func:`invitation_lens`'s reasoning; the class arrives as a path
    parameter and the grant is checked against it.

    :param session_id: The class, from the route path
    :param session: The session to query through
    :param account_id: The authenticated account
    :return: The lens for that one class
    """
    return resolve_class_lens(session, account_id=account_id, session_id=session_id)


def examiner_lens(
    exam_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> ExaminerLens:
    """Resolve the examiner lens for the one exam in the path [C4].

    :param exam_id: The exam, from the route path
    :param session: The session to query through
    :param account_id: The authenticated account
    :return: The lens for that one exam
    """
    return resolve_examiner_lens(session, account_id=account_id, exam_id=exam_id)


def admin_gate(request: Request) -> None:
    """Refuse any request that did not arrive through the admin hostname.

    Two independent locks, both failing closed: the ``X-Admin-Edge``
    secret only the admin CloudFront distribution adds, and the client
    address against the admin network allowlist (which that
    distribution's edge function also enforces). Either missing answers
    the same 404 as a route that does not exist, so the public API host
    does not reveal that an admin surface is behind it.

    :param request: The incoming request
    :return: None
    :raises AuthorizationError: 404 when either lock refuses
    """
    if not admin_edge_ok(request.headers.get(ADMIN_EDGE_HEADER)) or not (
        admin_network_ok(client_address(request))
    ):
        raise AuthorizationError(
            code=NOT_AVAILABLE, message_key="authz.lens.not_available", status=404
        )


def platform_admin_lens(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> PlatformAdminLens:
    """Resolve the platform administrator lens [TC-14, D-6].

    Four checks, each on every request and none memoized beyond it:

    * :func:`admin_gate` -- the request came through the admin hostname,
      from an allowed network;
    * an **admin** access token, which only the admin sign-in issues
      after an SMS code and an authenticator code; an app token is
      refused here even for an allowlisted number;
    * the account's number is still on the allowlist, so removing it
      revokes the reach at once rather than when the token lapses;
    * the account still has a confirmed authenticator factor, so a
      factor reset ends any session it began.

    :param request: The incoming request
    :param session: The session to query through
    :return: The administrator's lens
    :raises AuthorizationError: 404 off the admin hostname, 401 without a
        valid admin token, 403 when the number or factor no longer qualifies
    """
    admin_gate(request)
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthorizationError(
            code="NOT_AUTHENTICATED", message_key="auth.token.not_valid", status=401
        )
    claims = verify_scoped_token(token, ADMIN_AUDIENCE)
    account_id = uuid.UUID(str(claims["sub"]))
    row = session.execute(_ADMIN_STANDING, {"account_id": account_id}).first()
    if row is None:
        raise AuthorizationError(
            code="NOT_AUTHENTICATED", message_key="auth.token.not_valid", status=401
        )
    if not is_platform_admin(row.phone, row.email) or not row.confirmed:
        raise AuthorizationError(
            code="NO_PLATFORM_ADMIN_LENS",
            message_key="authz.lens.not_available",
            status=403,
        )
    return PlatformAdminLens(account_id=account_id)
