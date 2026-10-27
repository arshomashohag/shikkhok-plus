"""Signup, the already-added lookup, and the invitation routes.

**This is the Unit that creates an unauthenticated surface**, so the
two public routes here are the ones to read carefully
[logical-components § 4]. Neither reaches a batch, a fee, a mark or an
attendance record: the unauthenticated surface is confined to identity,
which is what keeps its blast radius the identity component rather than
the product.

Both are bounded by signup's **own** ceilings [BR2.1], counted
separately from the OTP path's. Signup and OTP have opposite disclosure
properties by design -- the OTP response is byte-identical whether or
not the number is known, while the lookup discloses that a seat exists
because that is its purpose -- and conflating their controls is how one
inherits the other's assumptions.

The four invitation routes each resolve an :class:`InvitationLens`
carrying the one seat they may touch, so the route-enumeration gate
sees them as lensed and a handler cannot widen to a second seat.
"""

from __future__ import annotations

import os
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.accounts import decisions, service
from app.api.auth import APP_HASH_ENV, correlation_of, ip_prefix_of
from app.api.deps import authenticated_account, get_session, invitation_lens
from app.audit.log import AuthEvent, write_audit
from app.auth import otp
from app.auth.ceilings import CeilingBreach, CeilingChecker
from app.authz.invitations import (
    InvitationRow,
    available_invitations,
    read_invitation,
)
from app.authz.lenses import InvitationLens
from app.gateway.null import build_gateway
from app.gateway.outbox import outbox_enabled, record_outbox
from app.gateway.sms import SmsGateway
from app.gateway.template import render_otp_message
from app.money import Money as DomainMoney
from app.money.wire import to_wire
from app.schemas.accounts import (
    AlreadyAddedResponse,
    DecisionResponse,
    InvitationResponse,
    RoleName,
    SignupRequest,
    SignupResponse,
)
from app.schemas.money import Money as WireMoney

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["accounts"])

#: The wire role names, keyed by the service enum. A mapping rather
#: than ``.value``, so the contract's vocabulary cannot drift from the
#: service's by somebody renaming an enum member.
#:
#: Typed to ``RoleName`` rather than to ``str``, so the crossing is
#: checked at compile time: a value here that the schema does not
#: declare is a mypy error rather than a response that validates
#: differently from the committed contract.
_ROLE_NAMES: dict[service.SignupRole, RoleName] = {
    service.SignupRole.TEACHER: "teacher",
    service.SignupRole.STUDENT: "student",
    service.SignupRole.GUARDIAN: "guardian",
}

_ROLES_BY_NAME = {name: role for role, name in _ROLE_NAMES.items()}


def get_gateway() -> SmsGateway:
    """Return the configured gateway, defaulting to the null adapter.

    :return: The gateway
    """
    return build_gateway()


def _to_wire(amount: DomainMoney | None) -> WireMoney | None:
    """Render a stored amount as the wire component.

    :param amount: The stored amount, or None
    :return: The wire representation, or None
    """
    if amount is None:
        return None
    return WireMoney(to_wire(amount))


def _as_response(row: InvitationRow) -> InvitationResponse:
    """Render one seat at BR1.4's width.

    :param row: The resolved invitation
    :return: The response body
    """
    # NARROWED, not cast [BR1.3]. An invitation lens is granted only
    # for a `pending` or `declined` link, so the third value is
    # unreachable here -- and `cast` would be the wrong way to say so,
    # because it asserts the claim instead of checking it. A `declined`
    # seat read as `pending` would re-ask a question the person already
    # answered, so the check is cheap insurance on a real distinction.
    decision: Literal["pending", "declined"] = (
        "declined" if row.decision == "declined" else "pending"
    )
    return InvitationResponse(
        enrollment_id=row.enrollment_id,
        batch_name=row.batch_name,
        subject=row.subject,
        fee_amount=_to_wire(row.fee_amount),
        decision=decision,
    )


@router.post(
    "/accounts",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
)
def sign_up(
    body: SignupRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    gateway: Annotated[SmsGateway, Depends(get_gateway)],
) -> SignupResponse:
    """Create an account, then send the verification code [BR4.3].

    **The ordering is the requirement, not an implementation detail**
    [AC1.11.4]. The account exists before the code is sent, so a person
    who verifies always has something to verify into; sending first
    would mean a code arriving for an account that may never be
    created.

    The ceiling is consumed **before** the account is created, for the
    reason the OTP path checks before its gateway call: a ceiling
    checked afterwards has already spent what it exists to protect.

    Public by design, and in ``PUBLIC_ROUTES``: there is no session to
    authenticate with before an account exists.

    :param body: The signup request
    :param request: The incoming request
    :param session: The request-scoped session
    :param gateway: The configured SMS gateway
    :return: The new account and the number its code went to
    :raises CeilingBreach: A signup ceiling refused this request
    :raises DuplicateNumber: The number already has an account
    """
    correlation_id = correlation_of(request)
    checker = CeilingChecker(session)

    try:
        checker.check_and_consume_signup(
            number=body.phone, ip_prefix=ip_prefix_of(request)
        )
    except CeilingBreach:
        # Recorded as a NAMED member with no scope value [NFR12.10]:
        # the value is a phone number or an IP prefix, and this log
        # carries no content. The scope KIND reaches the operator
        # through the ceiling module's own alert.
        write_audit(session, None, AuthEvent.SIGNUP_CEILING_BREACHED, correlation_id)
        raise

    created = service.create_account(
        session,
        phone=body.phone,
        role=_ROLES_BY_NAME[body.role],
        self_name=body.self_name,
        address=body.address,
    )
    write_audit(session, created.account_id, AuthEvent.ACCOUNT_CREATED, correlation_id)

    # The EXISTING OTP path, unchanged [BR2.2]. Signup does not become
    # a second authentication route: it triggers the one that carries
    # the seven abuse controls.
    issued = otp.issue(session, body.phone, correlation_id, purpose=otp.OTP_PURPOSE)
    message = render_otp_message(issued.code, os.environ.get(APP_HASH_ENV, ""))
    gateway.send(body.phone, message, correlation_id)

    # **The staging outbox, which this path was missing.** `/v1/auth/otp`
    # records here and this endpoint did not, so a person who registered
    # on a host with no SMS credentials got a 201, an account, and no way
    # to reach the code -- the outbox exists precisely so that is
    # possible before real credentials are configured.
    #
    # No `account_exists` guard, unlike the auth route. There the guard
    # stops the outbox becoming an existence oracle for a number with no
    # account; here the account was just created three statements above,
    # so it always exists and the condition could only ever be true.
    if outbox_enabled():
        record_outbox(
            session,
            phone=body.phone,
            message=message,
            correlation_id=correlation_id,
        )

    session.commit()

    return SignupResponse(account_id=created.account_id, code_sent_to=body.phone)


@router.get("/accounts/already-added", response_model=AlreadyAddedResponse)
def lookup_already_added(
    phone: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> AlreadyAddedResponse:
    """Report whether a teacher recorded this number, and nothing more.

    **This route discloses that a seat exists, deliberately**
    [BR2.3, AC1.12.2]. That is its purpose, and it is why BR2.2's
    byte-identical requirement applies to the OTP endpoint and not to
    this one. What is bounded is the WIDTH -- never the teacher, never
    the batch -- and the rate, through signup's own ceilings.

    Public, and in ``PUBLIC_ROUTES``: it is called while the signup
    form renders, before any account exists.

    :param phone: The number typed into the form
    :param request: The incoming request
    :param session: The request-scoped session
    :return: Existence, the name to pre-fill and the role to lock
    :raises CeilingBreach: A signup ceiling refused this request
    """
    CeilingChecker(session).check_and_consume_signup(
        number=phone, ip_prefix=ip_prefix_of(request)
    )

    found = service.already_added(session, phone)
    return AlreadyAddedResponse(
        already_added=found.exists,
        display_name=found.display_name,
        role=_ROLE_NAMES[found.role] if found.role is not None else None,
    )


@router.get("/invitations", response_model=list[InvitationResponse])
def list_invitations(
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
) -> list[InvitationResponse]:
    """List every unaccepted seat this account holds [BR1.3, BR5.5].

    **Lens-exempt for the same reason ``GET /v1/me`` is**, and recorded
    in ``LENS_EXEMPT_AUTHENTICATED`` rather than left to infer: this is
    the route that REPORTS which invitation lenses exist, so requiring
    one would mean a person had to already know which seats they were
    offered in order to ask. Every row it returns is derived from the
    authenticated account id and it reads nothing another account could
    own.

    A **declined** seat stays in this list with its state, because its
    holder may change their mind [BR5.4, AC1.13.1]. A seat whose links
    this account holds BOTH appears once [BR5.3].

    :param account_id: The authenticated account
    :param session: The request-scoped session
    :return: One entry per unaccepted seat, oldest first
    """
    return [
        _as_response(read_invitation(session, lens=lens))
        for lens in available_invitations(session, account_id)
    ]


@router.get(
    "/invitations/{enrollment_id}",
    response_model=InvitationResponse,
)
def read_one_invitation(
    lens: Annotated[InvitationLens, Depends(invitation_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> InvitationResponse:
    """Read one unaccepted seat, at BR1.4's width.

    :param lens: The invitation lens carrying the one reachable seat
    :param session: The request-scoped session
    :return: Batch name, subject, fee and this holder's own state
    """
    return _as_response(read_invitation(session, lens=lens))


@router.post(
    "/invitations/{enrollment_id}/accept",
    response_model=DecisionResponse,
)
def accept_invitation(
    lens: Annotated[InvitationLens, Depends(invitation_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> DecisionResponse:
    """Accept this seat, from ``pending`` or from ``declined``.

    One route for both, because accepting after a decline is the same
    operation and not a second one [BR5.4, AC1.13.2]: the lens becomes
    available exactly as if the person had accepted first time.

    :param lens: The invitation lens carrying the one reachable seat
    :param session: The request-scoped session
    :return: The seat and this holder's decision
    """
    decisions.accept_seat(session, lens=lens)
    return DecisionResponse(enrollment_id=lens.enrollment_id, decision="accepted")


@router.post(
    "/invitations/{enrollment_id}/decline",
    response_model=DecisionResponse,
)
def decline_invitation(
    lens: Annotated[InvitationLens, Depends(invitation_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> DecisionResponse:
    """Decline this seat, withdrawing only this holder's own lens.

    **A guardian's decline does not stop the student's fee** [BR5.2,
    AC1.14.1a]. The seat leaves this person's enrollments and stays
    among their invitations, with an accept action [BR5.5].

    :param lens: The invitation lens carrying the one reachable seat
    :param session: The request-scoped session
    :return: The seat and this holder's decision
    """
    decisions.decline_seat(session, lens=lens)
    return DecisionResponse(enrollment_id=lens.enrollment_id, decision="declined")
