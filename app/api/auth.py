"""The three auth endpoints, wired to the taxonomy U2 shipped.

Two of the eight ``PUBLIC_ROUTES`` are opened here -- the issue and
verify endpoints. The deletion pair lives in :mod:`app.api.deletion`,
signup's two in :mod:`app.api.accounts`, ``/health`` in
:mod:`app.api.health`, and the staging outbox in :mod:`app.api.staging`.
The refresh route goes in
``LENS_EXEMPT_AUTHENTICATED``, which is why U2 kept that set separate --
with one combined allowlist, whoever first hits a failing refresh route
takes the cheapest green edit and moves it to ``PUBLIC_ROUTES``, after
which nothing records that the route must stay authenticated.

**The ceilings are checked before the gateway call, never after.**
Checking afterwards spends the money the limit exists to protect. The
per-number and per-IP limits are checked on the request path, for every
number; the daily send budget is checked at the send itself, so only a
real SMS spends it (:mod:`app.auth.delivery`, [PA-SEC-2]).
"""

from __future__ import annotations

import os
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request
from sqlalchemy.orm import Session

from app.auth import otp
from app.auth.ceilings import CeilingChecker, SendBudget
from app.auth.client_address import client_prefix
from app.auth.delivery import send_within_budget
from app.auth.tokens import ACCESS_TOKEN_LIFETIME, issue_pair, rotate
from app.gateway.null import build_gateway
from app.gateway.outbox import record_outbox
from app.gateway.sms import SmsGateway
from app.gateway.template import render_otp_message
from app.schemas.auth import (
    IssueRequest,
    IssueResponse,
    RefreshRequest,
    TokenResponse,
    VerifyRequest,
)

__all__ = ["router"]

router = APIRouter(prefix="/v1/auth", tags=["auth"])

#: The SMS Retriever app hash, from configuration. Eleven characters.
APP_HASH_ENV = "SHIKKHOKPLUS_SMS_APP_HASH"


def get_session(request: Request) -> Session:
    """Return the request-scoped session.

    :param request: The incoming request
    :return: The session for this request
    """
    session: Session = request.state.session
    return session


def get_gateway() -> SmsGateway:
    """Return the configured gateway, defaulting to the null adapter.

    :return: The gateway
    """
    return build_gateway()


def correlation_of(request: Request) -> str:
    """Return this request's correlation id.

    :param request: The incoming request
    :return: The correlation id
    """
    existing: str | None = getattr(request.state, "correlation_id", None)
    return existing or str(uuid.uuid4())


def ip_prefix_of(request: Request) -> str:
    """Return the per-IP bucket every per-IP limit counts against.

    A thin name over :func:`~app.auth.client_address.client_prefix`,
    kept because signup and deletion import it from here. Which address
    is read (the trusted proxy header or the peer) and how it is reduced
    (IPv4 /24, IPv6 /64, one shared bucket for anything unparsable) are
    decided there, once, for all three routes.

    :param request: The incoming request
    :return: The prefix to count against
    """
    return client_prefix(request)


@router.post("/otp", response_model=IssueResponse)
def issue_code(
    body: IssueRequest,
    request: Request,
    background: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    gateway: Annotated[SmsGateway, Depends(get_gateway)],
) -> IssueResponse:
    """Issue a code, returning the same response for any number.

    :param body: The request body
    :param request: The incoming request
    :param background: Runs the SMS send after the response is written
    :param session: The request-scoped session
    :param gateway: The configured SMS gateway
    :return: The contentless acknowledgement
    """
    correlation_id = correlation_of(request)

    # BEFORE the gateway call, and for EVERY number: these scopes bound
    # the caller, so an unknown number is bounded identically. A breach
    # raises CeilingBreach, a ConflictError, so non-retryable [BR2.2].
    # The daily send budget is NOT spent here -- an unknown number sends
    # nothing, so it must cost nothing [PA-SEC-2].
    CeilingChecker(session).check_and_consume(
        number=body.phone, ip_prefix=ip_prefix_of(request)
    )

    issued = otp.issue(session, body.phone, correlation_id, purpose=otp.OTP_PURPOSE)

    message = render_otp_message(issued.code, os.environ.get(APP_HASH_ENV, ""))

    # **Only a number with an account is texted.** The unknown branch
    # keeps its OTP row (see `otp.issue`), but no account can ever be
    # signed in through it -- `verify` refuses a number with no account
    # -- so a code sent to it could only fail: reported from a device, a
    # student a teacher had added pressed Sign in rather than Sign up
    # and had every correct code refused.
    #
    # **After the response, not before it**, and that placement is what
    # keeps this branch from becoming a timing oracle [BR2.7]. Sending
    # inline would make the known branch slower by one gateway round
    # trip; deferred, both branches return having done the same work.
    # The daily send budget is spent INSIDE the deferred task, so it is
    # spent only by a real send and its exhaustion cannot change the
    # response either [PA-SEC-2].
    if issued.account_exists:
        background.add_task(
            send_within_budget,
            session.get_bind(),
            gateway,
            body.phone,
            message,
            correlation_id,
            budget=SendBudget.SIGN_IN,
        )

    # Records the message a staging host did NOT text, so a person can
    # read it and sign in on a device. A NO-OP unless the environment
    # permits it and an operator opted in, so this call carries no
    # environment branch of its own and production runs it to no effect.
    #
    # GUARDED ON account_exists, and that guard is the whole correctness
    # of this call. The unknown-number path does equivalent work and
    # RENDERS a message for a code nobody can ever sign in with.
    # Recording that would put an entry in the outbox for a number with
    # no account, which is an existence oracle in a new place: exactly
    # what the byte-identical response above protects, reintroduced one
    # endpoint over.
    #
    # Found by running it, not by reading it: the outbox returned a
    # perfectly ordinary-looking code for an unknown number, and that
    # code could never verify.
    if issued.account_exists:
        record_outbox(
            session,
            phone=body.phone,
            message=message,
            correlation_id=correlation_id,
        )

    # The SAME response either way. The schema has one fixed field, so
    # there is nothing here that could differ [BR2.7].
    return IssueResponse()


@router.post("/verify", response_model=TokenResponse)
def verify_code(
    body: VerifyRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> TokenResponse:
    """Verify a code and issue a token pair.

    :param body: The request body
    :param request: The incoming request
    :param session: The request-scoped session
    :return: The new token pair
    """
    correlation_id = correlation_of(request)
    account_id = otp.verify(
        session, body.phone, body.code, correlation_id, purpose=otp.OTP_PURPOSE
    )
    pair = issue_pair(session, account_id, correlation_id)
    session.commit()
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=int(ACCESS_TOKEN_LIFETIME.total_seconds()),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_tokens(
    body: RefreshRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> TokenResponse:
    """Rotate a refresh token, invalidating the family on reuse.

    Authenticated but **lens-exempt**: the caller has a token and no
    lens has been resolved yet, which is exactly why
    ``LENS_EXEMPT_AUTHENTICATED`` exists as a separate set.

    :param body: The request body
    :param request: The incoming request
    :param session: The request-scoped session
    :param authorization: The bearer header, unused but required present
    :return: The replacement pair
    """
    correlation_id = correlation_of(request)
    pair = rotate(session, body.refresh_token, correlation_id)
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=int(ACCESS_TOKEN_LIFETIME.total_seconds()),
    )
