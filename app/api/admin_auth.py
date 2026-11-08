"""Platform administrator sign-in, reachable only through the admin hostname.

Three steps, each behind :func:`~app.api.deps.admin_gate` (the admin
distribution's secret header and the admin network allowlist):

1. ``POST /v1/admin/auth/otp`` -- send an SMS code. The same response
   for every number, and a code is texted **only** to an allowlisted
   number that has an account, so this route says nothing about who is
   an administrator.
2. ``POST /v1/admin/auth/verify`` -- spend the SMS code; get a challenge,
   and at a first sign-in a new authenticator secret to set up.
3. ``POST /v1/admin/auth/mfa`` -- an authenticator code (or a recovery
   code) and the challenge; get an admin access token.

**No bearer token on any of them**, so they sit in ``PUBLIC_ROUTES``: a
person signing in has nothing to authenticate with yet. "Public" there
means unauthenticated, not reachable by anyone -- the gate refuses every
request that did not come through the admin hostname from an allowed
network, before any of the work below.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session

from app.admin.signin import (
    ADMIN_OTP_PURPOSE,
    begin_mfa,
    complete_mfa,
)
from app.api.auth import (
    correlation_of,
    get_email_gateway,
    get_gateway,
    ip_prefix_of,
)
from app.api.deps import admin_gate, get_session
from app.auth import otp
from app.auth.ceilings import CeilingChecker, SendBudget
from app.auth.delivery import deliver_code
from app.auth.tokens import MFA_CHALLENGE_LIFETIME
from app.authz.admin import is_platform_admin
from app.gateway.email import EmailGateway
from app.gateway.sms import SmsGateway
from app.schemas.admin import (
    AdminChallengeResponse,
    AdminEnrollment,
    AdminMfaRequest,
    AdminOtpRequest,
    AdminSessionResponse,
    AdminVerifyRequest,
)
from app.schemas.auth import IssueResponse

__all__ = ["router"]

router = APIRouter(
    prefix="/v1/admin/auth",
    tags=["admin"],
    dependencies=[Depends(admin_gate)],
)


@router.post("/otp", response_model=IssueResponse)
def send_code(
    body: AdminOtpRequest,
    request: Request,
    background: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    gateway: Annotated[SmsGateway, Depends(get_gateway)],
    email_gateway: Annotated[EmailGateway, Depends(get_email_gateway)],
) -> IssueResponse:
    """Send an admin sign-in code, answering every destination the same way.

    The sign-in ceilings apply before anything else, for every number or
    address, as they do for app sign-in; the code is sent after the
    response, so a send cannot be timed either. An administrator named
    by email address [0032] is sent the code by email.

    :param body: The number or the address
    :param request: The incoming request
    :param background: Runs the send after the response
    :param session: The request-scoped session
    :param gateway: The SMS gateway
    :param email_gateway: The email gateway
    :return: The contentless acknowledgement
    """
    correlation_id = correlation_of(request)
    identifier = body.identifier
    CeilingChecker(session).check_and_consume(
        number=identifier.rate_key, ip_prefix=ip_prefix_of(request)
    )
    issued = otp.issue(session, identifier, correlation_id, purpose=ADMIN_OTP_PURPOSE)
    listed = (
        is_platform_admin(identifier.value)
        if identifier.is_phone
        else is_platform_admin(None, identifier.value)
    )
    if issued.account_exists and listed:
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


@router.post("/verify", response_model=AdminChallengeResponse)
def verify_code(
    body: AdminVerifyRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> AdminChallengeResponse:
    """Spend the SMS code and start the authenticator step.

    :param body: The number and the code
    :param request: The incoming request
    :param session: The request-scoped session
    :return: The challenge, with a secret to set up at a first sign-in
    """
    account_id = otp.verify(
        session,
        body.identifier,
        body.code,
        correlation_of(request),
        purpose=ADMIN_OTP_PURPOSE,
    )
    challenge = begin_mfa(session, account_id, body.identifier.value)
    session.commit()
    return AdminChallengeResponse(
        challenge=challenge.token,
        expires_in=int(MFA_CHALLENGE_LIFETIME.total_seconds()),
        stage=challenge.stage,
        enrollment=None
        if challenge.secret is None or challenge.otpauth_uri is None
        else AdminEnrollment(
            secret=challenge.secret, otpauth_uri=challenge.otpauth_uri
        ),
    )


@router.post("/mfa", response_model=AdminSessionResponse)
def finish(
    body: AdminMfaRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> AdminSessionResponse:
    """Finish signing in with an authenticator code or a recovery code.

    :param body: The challenge and one code
    :param request: The incoming request
    :param session: The request-scoped session
    :return: The admin access token, and recovery codes at a first sign-in
    """
    signed_in = complete_mfa(
        session,
        body.challenge,
        body.code,
        body.recovery_code,
        correlation_of(request),
    )
    session.commit()
    return AdminSessionResponse(
        access_token=signed_in.access_token,
        expires_in=signed_in.expires_in,
        recovery_codes=signed_in.recovery_codes,
    )
