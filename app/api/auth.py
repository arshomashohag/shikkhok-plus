"""The auth endpoints, wired to the taxonomy U2 shipped.

Two of the ``PUBLIC_ROUTES`` are opened here -- the issue and verify
endpoints. The deletion pair lives in :mod:`app.api.deletion`,
signup's two in :mod:`app.api.accounts`, ``/health`` in
:mod:`app.api.health`, and the staging outbox in :mod:`app.api.staging`.
The refresh route and the two logout routes [C-21] go in
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

import datetime as dt
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    Request,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.accounts.clients import (
    CLIENT_PLATFORM_HEADER,
    CLIENT_VERSION_HEADER,
    record_client,
)
from app.accounts.mfa import challenge_for, finish_sign_in, has_confirmed_factor
from app.accounts.passwords import complete_setup, grant_setup, sign_in
from app.accounts.service import complete_signup
from app.api.deps import authenticated_account
from app.audit.log import AuthEvent, write_audit
from app.auth import otp
from app.auth.ceilings import CeilingBreach, CeilingChecker, SendBudget
from app.auth.client_address import client_coarse_prefix, client_prefix
from app.auth.delivery import deliver_code
from app.auth.tokens import (
    ACCESS_TOKEN_LIFETIME,
    MFA_CHALLENGE_LIFETIME,
    issue_pair,
    revoke_all_families,
    revoke_family,
    rotate,
)
from app.gateway.email import EmailGateway, build_email_gateway
from app.gateway.null import build_gateway
from app.gateway.sms import SmsGateway
from app.schemas.auth import (
    IssueRequest,
    IssueResponse,
    MfaSignInRequest,
    PasswordSetupRequest,
    PasswordSignInRequest,
    RefreshRequest,
    TokenResponse,
    VerifyRequest,
    VerifyResponse,
)

__all__ = ["router"]

router = APIRouter(prefix="/v1/auth", tags=["auth"])


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


def get_email_gateway() -> EmailGateway:
    """Return the configured email gateway, defaulting to the null adapter.

    :return: The gateway
    """
    return build_email_gateway()


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


def coarse_prefix_of(request: Request) -> str:
    """Return the coarse per-IP bucket the /48 scopes count against [C-05].

    :param request: The incoming request
    :return: The IPv6 /48, or the IPv4 /24
    """
    return client_coarse_prefix(request)


def send_budget_for(issued: otp.IssuedCode) -> SendBudget | None:
    """Decide which daily budget a sign-in code's SMS spends, if any.

    A number with an account spends sign-in's budget; a number with only
    a signup draft spends SIGNUP's, so a stranger signing up numbers can
    never spend what existing accounts need [C-05]. A number with
    neither is not texted at all.

    :param issued: The code just issued
    :return: The budget to spend, or None when nothing is sent
    """
    if issued.account_exists:
        return SendBudget.SIGN_IN
    if issued.pending_signup:
        return SendBudget.SIGNUP
    return None


@router.post("/otp", response_model=IssueResponse)
def issue_code(
    body: IssueRequest,
    request: Request,
    background: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    gateway: Annotated[SmsGateway, Depends(get_gateway)],
    email_gateway: Annotated[EmailGateway, Depends(get_email_gateway)],
) -> IssueResponse:
    """Issue a code, returning the same response for any number or address.

    Since passwords [0032] the code this sends completes a signup,
    recovers a forgotten password or gives an account its first one; it
    never signs anyone in on its own (see ``POST /v1/auth/verify``).

    :param body: The request body
    :param request: The incoming request
    :param background: Runs the send after the response is written
    :param session: The request-scoped session
    :param gateway: The configured SMS gateway
    :param email_gateway: The configured email gateway
    :return: The contentless acknowledgement
    """
    correlation_id = correlation_of(request)
    identifier = body.identifier

    # BEFORE the gateway call, and for EVERY destination: these scopes
    # bound the caller, so an unknown one is bounded identically. A
    # breach raises CeilingBreach, a ConflictError, so non-retryable
    # [BR2.2]. The daily send budget is NOT spent here -- an unknown
    # destination receives nothing, so it must cost nothing [PA-SEC-2].
    CeilingChecker(session).check_and_consume(
        number=identifier.rate_key,
        ip_prefix=ip_prefix_of(request),
        coarse_prefix=coarse_prefix_of(request),
    )

    issued = otp.issue(session, identifier, correlation_id, purpose=otp.OTP_PURPOSE)
    budget = send_budget_for(issued)

    # **Only a destination with an account, or a signup draft, is sent
    # to.** The unknown branch keeps its OTP row (see `otp.issue`), but
    # no account can ever be reached through it -- `verify` refuses a
    # destination with no account and no draft -- so a code sent to it
    # could only fail. A draft's destination IS sent to [C-07]: this is
    # "send the code again" after signup, and the code completes it.
    #
    # **After the response, not before it** (deliver_code), so a known
    # and an unknown destination return having done the same work
    # [BR2.7]. The staging outbox entry is recorded on the same
    # condition, or it would be an existence oracle one endpoint over.
    if budget is not None:
        deliver_code(
            background,
            session,
            identifier,
            issued.code,
            correlation_id,
            sms_budget=budget,
            sms_gateway=gateway,
            email_gateway=email_gateway,
            otp_request_id=issued.request_id,
        )

    # The SAME response either way. The schema has one fixed field, so
    # there is nothing here that could differ [BR2.7].
    return IssueResponse()


@router.post("/verify", response_model=VerifyResponse)
def verify_code(
    body: VerifyRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> VerifyResponse:
    """Verify a code and grant the right to choose a password.

    **Never a session** [0032]. A verified code yields a
    ``password_setup_token``; ``POST /v1/auth/password/setup`` turns it
    into a session once a password is chosen -- with the authenticator
    code too when ``mfa_required`` -- so a code can recover an account
    and cannot sign in to one.

    **Bounded wider than one code** [C-20]. A verify arriving while the
    caller's /64, its /48 or the whole product has failed too often this
    hour is refused before its code is checked, and every failure counts
    against all three. A code guessed to death counts against its
    number's daily cool-off, which stops further codes being issued for
    it. All of it applies to a known and an unknown number alike.

    **Completes a verify-first signup** [C-07]: a right code for a number
    whose signup draft it was sent for creates the account, then signs
    it in, so both clients' existing "sign up, then type the code" flow
    is unchanged.

    :param body: The request body
    :param request: The incoming request
    :param session: The request-scoped session
    :return: The password-setup grant
    :raises CeilingBreach: A failed-verify ceiling is full
    :raises CodeRefused: The code was refused
    """
    correlation_id = correlation_of(request)
    checker = CeilingChecker(session)
    ip_prefix = ip_prefix_of(request)
    coarse_prefix = coarse_prefix_of(request)

    try:
        checker.check_verify_allowed(ip_prefix, coarse_prefix)
    except CeilingBreach:
        write_audit(session, None, AuthEvent.VERIFY_CEILING_BREACHED, correlation_id)
        session.commit()
        raise

    def complete(
        verifying: Session, otp_request_id: uuid.UUID, moment: dt.datetime
    ) -> uuid.UUID | None:
        """Create the account a signup draft bound to this code describes.

        :param verifying: The verify's own session
        :param otp_request_id: The code just verified
        :param moment: The moment of verification
        :return: The new account, or None when no draft is bound
        """
        return complete_signup(
            verifying,
            otp_request_id=otp_request_id,
            correlation_id=correlation_id,
            now=moment,
        )

    try:
        account_id = otp.verify(
            session,
            body.identifier,
            body.code,
            correlation_id,
            purpose=otp.OTP_PURPOSE,
            complete_signup=complete,
        )
    except otp.CodeRefused as refusal:
        checker.record_verify_failure(ip_prefix, coarse_prefix)
        if refusal.code_died:
            checker.record_dead_code(body.identifier.rate_key)
        raise
    grant = grant_setup(session, account_id)
    session.commit()
    return VerifyResponse(
        mfa_required=grant.mfa_required,
        password_setup_token=grant.token,
        password_setup_expires_in=grant.expires_in,
    )


@router.post("/password", response_model=VerifyResponse)
def sign_in_with_password(
    body: PasswordSignInRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> VerifyResponse:
    """Sign in with a phone number or an email address and a password.

    **One refusal for every failure** [BR2.7]: an unknown destination, an
    account with no password yet and a wrong password all answer
    ``auth.password.wrong``, after the same work. The person who has no
    password yet is pointed at the code flow by the client's static
    hint, not by a response that would say their account exists.

    Bounded per identifier and per network, with the network-wide
    failure ceilings shared with codes.

    :param body: The request body
    :param request: The incoming request
    :param session: The request-scoped session
    :return: The token pair, or the authenticator challenge
    :raises CeilingBreach: A failure ceiling is full
    :raises PasswordRefused: The sign-in was refused
    """
    correlation_id = correlation_of(request)
    account_id = sign_in(
        session,
        body.identifier,
        body.password,
        ip_prefix=ip_prefix_of(request),
        coarse_prefix=coarse_prefix_of(request),
        correlation_id=correlation_id,
    )
    # The second step [0028]: an account with an authenticator factor
    # gets a challenge for the existing POST /v1/auth/mfa, not tokens.
    if has_confirmed_factor(session, account_id):
        session.commit()
        return VerifyResponse(
            mfa_required=True,
            mfa_challenge=challenge_for(account_id),
            mfa_expires_in=int(MFA_CHALLENGE_LIFETIME.total_seconds()),
        )
    pair = issue_pair(session, account_id, correlation_id)
    record_client(
        session,
        account_id,
        request.headers.get(CLIENT_PLATFORM_HEADER),
        request.headers.get(CLIENT_VERSION_HEADER),
    )
    session.commit()
    return VerifyResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=int(ACCESS_TOKEN_LIFETIME.total_seconds()),
    )


@router.post("/password/setup", response_model=TokenResponse)
def set_up_password(
    body: PasswordSetupRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> TokenResponse:
    """Choose a password with a verified code's token, and sign in.

    Public, like ``/verify``: the person has no session yet. What bounds
    it is the token, which only a verified code yields, and which is
    spent by the password it sets. Every other session of the account
    ends: a password chosen through a code is a recovery.

    :param body: The token, the password, and the authenticator code
        when the account has one
    :param request: The incoming request
    :param session: The request-scoped session
    :return: A token pair
    :raises AuthorizationError: 401 when the token is bad, expired or spent
    :raises ValidationError: The password or the authenticator code
    """
    correlation_id = correlation_of(request)
    account_id = complete_setup(
        session,
        body.token,
        body.password,
        body.code,
        body.recovery_code,
        correlation_id,
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


@router.post("/mfa", response_model=TokenResponse)
def verify_second_step(
    body: MfaSignInRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> TokenResponse:
    """Finish signing in with an authenticator code or a recovery code.

    Public, like ``/verify``: the person has no token yet. What bounds it
    is the challenge, which only a verified SMS code yields, and the
    shared factor's lock after five wrong codes.

    :param body: The challenge and one code
    :param request: The incoming request
    :param session: The request-scoped session
    :return: The token pair
    """
    correlation_id = correlation_of(request)
    account_id = finish_sign_in(
        session, body.challenge, body.code, body.recovery_code, correlation_id
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
    # After the rotation has committed, in its own small transaction: the
    # new pair is already the account's, so a failure here must not be
    # able to undo it, and recording which app renewed is worth far less
    # than the renewal itself.
    if record_client(
        session,
        pair.account_id,
        request.headers.get(CLIENT_PLATFORM_HEADER),
        request.headers.get(CLIENT_VERSION_HEADER),
    ):
        session.commit()
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=int(ACCESS_TOKEN_LIFETIME.total_seconds()),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def log_out(
    body: RefreshRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """End the session a refresh token belongs to [C-21].

    Takes the **refresh** token, like ``/refresh`` and for the same
    reason, so it sits beside that route in
    ``LENS_EXEMPT_AUTHENTICATED``: a client whose access token has
    already expired must still be able to sign out. The whole family is
    revoked, so a copy of the live token on another device stops too.

    **Always 204, with no body**, whether the token was live, expired,
    revoked or never existed: logout is not an oracle for which tokens
    are valid, and a client retrying after a lost response is never
    shown an error.

    :param body: The refresh token to end the session of
    :param request: The incoming request
    :param session: The request-scoped session
    :param authorization: The bearer header, unused, as on ``/refresh``
    :return: An empty 204
    """
    revoke_family(session, body.refresh_token, correlation_of(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def log_out_everywhere(
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """End every session of the authenticated account [C-21].

    Lens-exempt on ``DELETE /v1/me``'s reasoning: it acts on the
    authenticated account itself and takes no id from the request, so
    there is no other account's data for a lens to scope, and an account
    holding no lens must still be able to sign out everywhere.

    :param account_id: The authenticated account
    :param request: The incoming request
    :param session: The request-scoped session
    :return: An empty 204
    """
    revoke_all_families(session, account_id, correlation_of(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
