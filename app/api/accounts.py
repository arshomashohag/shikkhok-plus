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

import datetime as dt
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.accounts import decisions, service
from app.api.auth import (
    coarse_prefix_of,
    correlation_of,
    get_email_gateway,
    ip_prefix_of,
)
from app.api.deps import authenticated_account, get_session, invitation_lens
from app.audit.log import AuthEvent, write_audit
from app.auth import otp, pending
from app.auth.ceilings import CeilingBreach, CeilingChecker, SendBudget
from app.auth.delivery import deliver_code
from app.authz.invitations import (
    InvitationRow,
    available_invitations,
    read_invitation,
)
from app.authz.lenses import InvitationLens
from app.gateway.email import EmailGateway
from app.gateway.null import build_gateway
from app.gateway.sms import SmsGateway
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
from app.schemas.phone import PhoneField

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
    # Narrowed the same way and for the same reason. The query emits
    # exactly these two literals from one `case`, and a `cast` would
    # assert that rather than check it -- which is the distinction the
    # comment above draws.
    role: Literal["student", "guardian"] = (
        "guardian" if row.role == "guardian" else "student"
    )
    return InvitationResponse(
        enrollment_id=row.enrollment_id,
        batch_name=row.batch_name,
        subject=row.subject,
        fee_amount=_to_wire(row.fee_amount),
        decision=decision,
        role=role,
        child_name=row.child_name,
        also_covers=row.also_covers,
    )


@router.post(
    "/accounts",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
)
def sign_up(
    body: SignupRequest,
    request: Request,
    background: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    gateway: Annotated[SmsGateway, Depends(get_gateway)],
    email_gateway: Annotated[EmailGateway, Depends(get_email_gateway)],
) -> SignupResponse:
    """Hold the signup form, then send the code that completes it [C-07].

    **Verify first, create second.** This used to create the account,
    profile, owner and centre here and answer an existing number with a
    409: an existence oracle for any phone number, and a way to squat a
    stranger's number with a name, address and role the real owner then
    inherited. Now the form is held as a draft
    (:mod:`app.auth.pending`) and the account is created only when the
    code sent to the number is verified at ``POST /v1/auth/verify`` --
    which is the call both clients already make next, so neither changes.

    **The same answer for every number.** A number with an account gets
    the same 201 and the same body shape, and the code sent to it signs
    the person in to the account they already have; a new number's code
    creates the account. The ``account_id`` reported is the draft's,
    fresh on every request, and becomes the account's id if the draft is
    completed. Both branches write a draft and a code, so the work is
    the same too [BR2.7].

    The ceiling is consumed **before** anything is written, for the
    reason the OTP path checks before its gateway call. The SMS goes
    after the response, from **signup's own** send budget [C-05], for
    an existing number too: signup can never spend what sign-in needs.

    Public by design, and in ``PUBLIC_ROUTES``: there is no session to
    authenticate with before an account exists.

    :param body: The signup request
    :param request: The incoming request
    :param background: Runs the SMS send after the response is written
    :param session: The request-scoped session
    :param gateway: The configured SMS gateway
    :param email_gateway: The configured email gateway
    :return: The draft's id and where its code went
    :raises CeilingBreach: A signup ceiling refused this request
    """
    correlation_id = correlation_of(request)
    checker = CeilingChecker(session)
    identifier = body.identifier

    try:
        checker.check_and_consume_signup(
            number=identifier.rate_key,
            ip_prefix=ip_prefix_of(request),
            coarse_prefix=coarse_prefix_of(request),
        )
    except CeilingBreach:
        # Recorded as a NAMED member with no scope value [NFR12.10]:
        # the value is a phone number or an IP prefix, and this log
        # carries no content. The scope KIND reaches the operator
        # through the ceiling module's own alert.
        write_audit(session, None, AuthEvent.SIGNUP_CEILING_BREACHED, correlation_id)
        raise

    moment = dt.datetime.now(tz=dt.UTC)
    draft_id = pending.save_draft(
        session,
        identifier=identifier,
        role=body.role,
        self_name=body.self_name,
        address_house=body.address_house,
        address_road=body.address_road,
        address_city=body.address_city,
        address_postcode=body.address_postcode,
        centre_name=body.centre_name,
        now=moment,
    )
    # Never the account id, known or not: saying which is the oracle.
    write_audit(
        session, None, AuthEvent.SIGNUP_REQUESTED, correlation_id, occurred_at=moment
    )

    # The EXISTING OTP path [BR2.2]: signup does not become a second
    # authentication route. `otp.issue` binds the draft just written to
    # the code it issues and commits both together, so a failure between
    # them leaves neither.
    issued = otp.issue(
        session, identifier, correlation_id, purpose=otp.OTP_PURPOSE, now=moment
    )

    # After the response, so a known and an unknown destination return
    # having done the same work, and a text spends signup's budget [C-05]
    # (an email spends the email budget [0032]). A skipped send kills the
    # code [C-20]. The staging outbox records it unconditionally, because
    # every signup sends: nothing there differs between destinations.
    deliver_code(
        background,
        session,
        identifier,
        issued.code,
        correlation_id,
        sms_budget=SendBudget.SIGNUP,
        sms_gateway=gateway,
        email_gateway=email_gateway,
        otp_request_id=issued.request_id,
    )

    session.commit()

    return SignupResponse(account_id=draft_id, code_sent_to=identifier.value)


@router.get("/accounts/already-added", response_model=AlreadyAddedResponse)
def lookup_already_added(
    phone: Annotated[PhoneField, Query()],
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> AlreadyAddedResponse:
    """Report whether a teacher recorded this number, and nothing more.

    **This route discloses that a seat exists, deliberately**
    [BR2.3, AC1.12.2]. That is its purpose, and it is why BR2.2's
    byte-identical requirement applies to the OTP endpoint and not to
    this one. What is bounded is the WIDTH -- never the teacher, never
    the batch, never the name [C-06] -- and the rate, through the
    lookup's own ceilings. **Never signup's** [SEC-4]: three anonymous
    lookups used to spend a number's whole daily signup allowance.

    Public, and in ``PUBLIC_ROUTES``: it is called while the signup
    form renders, before any account exists.

    :param phone: The number typed into the form, canonicalised on the
        way in like every other number, so the ceiling and the lookup
        both see one spelling
    :param request: The incoming request
    :param session: The request-scoped session
    :return: Existence and the role to lock; never a name
    :raises CeilingBreach: A lookup ceiling refused this request
    """
    CeilingChecker(session).check_and_consume_lookup(
        number=phone,
        ip_prefix=ip_prefix_of(request),
        coarse_prefix=coarse_prefix_of(request),
    )

    found = service.already_added(session, phone)
    return AlreadyAddedResponse(
        already_added=found.exists,
        # NEVER the name [C-06]. Empty rather than absent where a seat
        # exists, because the Android mapper already in the field treats
        # a seat with a null name as a broken response and shows an
        # error instead of the role-locked form. Empty locks the role
        # and pre-fills nothing, which is the behaviour wanted.
        display_name="" if found.exists else None,
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
