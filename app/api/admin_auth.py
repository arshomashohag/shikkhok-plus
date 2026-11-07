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

import os
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session

from app.admin.signin import (
    ADMIN_OTP_PURPOSE,
    begin_mfa,
    complete_mfa,
)
from app.api.auth import (
    APP_HASH_ENV,
    correlation_of,
    get_gateway,
    ip_prefix_of,
)
from app.api.deps import admin_gate, get_session
from app.auth import otp
from app.auth.ceilings import CeilingChecker, SendBudget
from app.auth.delivery import send_within_budget
from app.auth.tokens import MFA_CHALLENGE_LIFETIME
from app.authz.admin import is_platform_admin
from app.gateway.outbox import record_outbox
from app.gateway.sms import SmsGateway
from app.gateway.template import render_otp_message
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
) -> IssueResponse:
    """Send an admin sign-in code, answering every number the same way.

    The sign-in ceilings apply before anything else, for every number, as
    they do for app sign-in; the code is texted after the response, so a
    send cannot be timed either.

    :param body: The number
    :param request: The incoming request
    :param background: Runs the send after the response
    :param session: The request-scoped session
    :param gateway: The SMS gateway
    :return: The contentless acknowledgement
    """
    correlation_id = correlation_of(request)
    CeilingChecker(session).check_and_consume(
        number=body.phone, ip_prefix=ip_prefix_of(request)
    )
    issued = otp.issue(session, body.phone, correlation_id, purpose=ADMIN_OTP_PURPOSE)
    if issued.account_exists and is_platform_admin(body.phone):
        message = render_otp_message(issued.code, os.environ.get(APP_HASH_ENV, ""))
        background.add_task(
            send_within_budget,
            session.get_bind(),
            gateway,
            body.phone,
            message,
            correlation_id,
            budget=SendBudget.SIGN_IN,
        )
        record_outbox(
            session, phone=body.phone, message=message, correlation_id=correlation_id
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
        body.phone,
        body.code,
        correlation_of(request),
        purpose=ADMIN_OTP_PURPOSE,
    )
    challenge = begin_mfa(session, account_id, body.phone)
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
