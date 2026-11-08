"""The signed-in account's own password, phone number and email address.

Three routes, all in ``LENS_EXEMPT_AUTHENTICATED`` for the reason given
there: each acts on the authenticated account alone [0032].
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.accounts.clients import (
    CLIENT_PLATFORM_HEADER,
    CLIENT_VERSION_HEADER,
    record_client,
)
from app.accounts.contact import already_has, attach, contact_already_set
from app.accounts.passwords import change_password
from app.api.auth import (
    coarse_prefix_of,
    correlation_of,
    get_email_gateway,
    get_gateway,
    ip_prefix_of,
)
from app.api.deps import authenticated_account, get_session
from app.api.me import MeResponse, read_me
from app.auth import otp
from app.auth.ceilings import CeilingChecker, SendBudget
from app.auth.delivery import deliver_code
from app.auth.tokens import ACCESS_TOKEN_LIFETIME, issue_pair
from app.gateway.email import EmailGateway
from app.gateway.sms import SmsGateway
from app.schemas.auth import IssueResponse, TokenResponse
from app.schemas.identifier import IdentifierFields

__all__ = ["router"]

router = APIRouter(prefix="/v1/me", tags=["me"])


class PasswordChangeRequest(BaseModel):
    """Set a first password, or change the current one.

    :ivar current_password: Required when the account has a password
    :ivar new_password: The new one
    """

    model_config = ConfigDict(extra="forbid")

    current_password: str | None = Field(default=None, max_length=1024)
    new_password: str = Field(max_length=1024)


class ContactRequest(IdentifierFields):
    """Ask for a code to add a phone number or an email address.

    :ivar phone: The number to add, or None
    :ivar email: Or the address to add
    """

    model_config = ConfigDict(extra="forbid")


class ContactVerifyRequest(IdentifierFields):
    """Add the phone number or email address a code was sent to.

    :ivar phone: The number, or None
    :ivar email: Or the address
    :ivar code: The code sent to it
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=4, max_length=10)


@router.post("/password", response_model=TokenResponse)
def set_password(
    body: PasswordChangeRequest,
    request: Request,
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
) -> TokenResponse:
    """Set or change this account's password, and sign in afresh.

    Every session ends, this one included, and a new pair is returned
    for the device that made the change.

    :param body: The current password, when there is one, and the new
    :param request: The incoming request
    :param account_id: The authenticated account
    :param session: The request-scoped session
    :return: A new token pair
    :raises ValidationError: The current password is missing or wrong
    :raises ValidationError: The new password breaks the policy
    """
    correlation_id = correlation_of(request)
    change_password(
        session,
        account_id,
        body.current_password,
        body.new_password,
        ip_prefix=ip_prefix_of(request),
        coarse_prefix=coarse_prefix_of(request),
        correlation_id=correlation_id,
    )
    pair = issue_pair(session, account_id, correlation_id)
    record_client(
        session,
        account_id,
        request.headers.get(CLIENT_PLATFORM_HEADER),
        request.headers.get(CLIENT_VERSION_HEADER),
    )
    session.commit()
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=int(ACCESS_TOKEN_LIFETIME.total_seconds()),
    )


@router.post("/contact", response_model=IssueResponse)
def request_contact_code(
    body: ContactRequest,
    request: Request,
    background: BackgroundTasks,
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
    gateway: Annotated[SmsGateway, Depends(get_gateway)],
    email_gateway: Annotated[EmailGateway, Depends(get_email_gateway)],
) -> IssueResponse:
    """Send a code to a phone number or an address the account lacks.

    Sent whether or not another account holds it (see
    :mod:`app.accounts.contact`), within sign-in's per-destination and
    per-network ceilings and the daily send budgets.

    :param body: The number or address
    :param request: The incoming request
    :param background: Runs the send after the response is written
    :param account_id: The authenticated account
    :param session: The request-scoped session
    :param gateway: The configured SMS gateway
    :param email_gateway: The configured email gateway
    :return: The contentless acknowledgement
    :raises ConflictError: The account already has one of this kind
    :raises CeilingBreach: A ceiling refused the send
    """
    identifier = body.identifier
    if already_has(session, account_id, identifier):
        raise contact_already_set()
    correlation_id = correlation_of(request)
    CeilingChecker(session).check_and_consume(
        number=identifier.rate_key,
        ip_prefix=ip_prefix_of(request),
        coarse_prefix=coarse_prefix_of(request),
    )
    issued = otp.issue(session, identifier, correlation_id, purpose=otp.CONTACT_PURPOSE)
    deliver_code(
        background,
        session,
        identifier,
        issued.code,
        correlation_id,
        sms_budget=SendBudget.SIGN_IN,
        sms_gateway=gateway,
        email_gateway=email_gateway,
        otp_request_id=issued.request_id,
    )
    session.commit()
    return IssueResponse()


@router.post("/contact/verify", response_model=MeResponse)
def verify_contact(
    body: ContactVerifyRequest,
    request: Request,
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
) -> MeResponse:
    """Add the phone number or address the code proves.

    Adding a phone number links the seats and centre invitations recorded
    against it, so the response's lenses may have changed.

    :param body: The number or address, and the code
    :param request: The incoming request
    :param account_id: The authenticated account
    :param session: The request-scoped session
    :return: The account, as ``GET /v1/me`` describes it
    :raises CodeRefused: The code was refused
    :raises ConflictError: Already set, or held by another account
    """
    correlation_id = correlation_of(request)
    checker = CeilingChecker(session)
    ip_prefix = ip_prefix_of(request)
    coarse_prefix = coarse_prefix_of(request)
    checker.check_verify_allowed(ip_prefix, coarse_prefix)
    try:
        attach(session, account_id, body.identifier, body.code, correlation_id)
    except otp.CodeRefused as refusal:
        checker.record_verify_failure(ip_prefix, coarse_prefix)
        if refusal.code_died:
            checker.record_dead_code(body.identifier.rate_key)
        raise
    return read_me(account_id, session)
