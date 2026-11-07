"""Platform administrator sign-in: an SMS code, then an authenticator code.

**Two factors, every time.** The SMS code proves the phone; the
authenticator code proves the app holding the secret. An SMS code alone
-- the realistic loss through a SIM swap -- reaches only the second step,
which grants nothing on its own.

**Enrollment is part of the first sign-in.** An allowlisted administrator
without a confirmed factor is given a fresh secret after the SMS step and
must type one code from it before any admin token is issued, so there is
no window in which an administrator holds a session with one factor.

**Guessing is bounded per account, not per request.** Five wrong
authenticator codes lock the factor for fifteen minutes, whichever
challenge they arrived on, and the lock and the count are committed even
though the request that tripped them fails.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final, Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.audit.log import AuthEvent, write_audit
from app.auth.mfa import (
    ADMIN_DOOR,
    LOCK_DURATION,
    MAX_FAILED_ATTEMPTS,
    check_code,
    confirm_factor,
    load_factor,
    start_enrollment,
)
from app.auth.tokens import (
    ADMIN_AUDIENCE,
    ADMIN_TOKEN_LIFETIME,
    MFA_CHALLENGE_AUDIENCE,
    MFA_CHALLENGE_LIFETIME,
    issue_scoped_token,
    verify_scoped_token,
)
from app.authz.admin import is_platform_admin
from app.errors import AuthorizationError, ValidationError

__all__ = [
    "ADMIN_OTP_PURPOSE",
    "ISSUER",
    "LOCK_DURATION",
    "MAX_FAILED_ATTEMPTS",
    "AdminSession",
    "Challenge",
    "Stage",
    "begin_mfa",
    "complete_mfa",
]

#: The SMS code's purpose, so a code sent for app sign-in cannot start an
#: admin sign-in, nor the reverse.
ADMIN_OTP_PURPOSE: Final = "admin"

#: What the authenticator app shows above the code.
ISSUER: Final = "ShikkhokPlus Admin"

# LOCK_DURATION and MAX_FAILED_ATTEMPTS are re-exported from
# ``app.auth.mfa``: the limit and the lock belong to the shared factor,
# the same at every door.

Stage = Literal["enroll", "verify"]


@dataclass(frozen=True, slots=True)
class Challenge:
    """What the SMS step hands to the authenticator step.

    :ivar token: The short-lived challenge token
    :ivar stage: ``enroll`` for a first sign-in, ``verify`` after it
    :ivar secret: The new secret, only when enrolling
    :ivar otpauth_uri: The same secret as a scannable URI, only when enrolling
    """

    token: str
    stage: Stage
    secret: str | None
    otpauth_uri: str | None


@dataclass(frozen=True, slots=True)
class AdminSession:
    """A signed-in administrator.

    :ivar access_token: The admin-audience access token
    :ivar expires_in: Its lifetime in seconds
    :ivar recovery_codes: Shown once, at enrollment; None otherwise
    """

    access_token: str
    expires_in: int
    recovery_codes: list[str] | None


def _refused() -> AuthorizationError:
    """Build the refusal for an account that is not an administrator.

    :return: The error
    """
    return AuthorizationError(
        code="NO_PLATFORM_ADMIN_LENS",
        message_key="authz.lens.not_available",
        status=403,
    )


def _phone(session: Session, account_id: uuid.UUID) -> str | None:
    """Read an account's number.

    :param session: The session to read through
    :param account_id: The account
    :return: Its phone, or None when the account is gone
    """
    phone = session.execute(
        sa.text("SELECT phone FROM account WHERE id = :a"), {"a": account_id}
    ).scalar()
    return None if phone is None else str(phone)


def begin_mfa(
    session: Session,
    account_id: uuid.UUID,
    phone: str,
    now: dt.datetime | None = None,
) -> Challenge:
    """Start the authenticator step after a verified SMS code.

    Does not commit; the route does, with the OTP spend it follows.

    :param session: The session to write through
    :param account_id: The account the SMS code authenticated
    :param phone: Its number
    :param now: The moment, or None for the clock
    :return: The challenge, carrying a fresh secret when enrolling
    :raises AuthorizationError: 403 when the number is not an administrator
    """
    if not is_platform_admin(phone):
        raise _refused()
    moment = now or dt.datetime.now(tz=dt.UTC)
    factor = load_factor(session, account_id)
    stage: Stage = "verify" if factor and factor.confirmed_at else "enroll"
    secret: str | None = None
    uri: str | None = None
    if stage == "enroll":
        secret, uri = start_enrollment(
            session, account_id, f"admin-{phone[-4:]}", ISSUER, moment
        )
    token = issue_scoped_token(
        account_id,
        MFA_CHALLENGE_AUDIENCE,
        MFA_CHALLENGE_LIFETIME,
        extra={"stage": stage},
        now=moment,
    )
    return Challenge(token=token, stage=stage, secret=secret, otpauth_uri=uri)


def complete_mfa(
    session: Session,
    challenge: str,
    code: str | None,
    recovery_code: str | None,
    correlation_id: str,
    now: dt.datetime | None = None,
) -> AdminSession:
    """Finish sign-in with an authenticator code or a recovery code.

    Does not commit on success; the route does.

    :param session: The session to write through
    :param challenge: The token from :func:`begin_mfa`
    :param code: A six-digit authenticator code
    :param recovery_code: A recovery code, only after enrollment
    :param correlation_id: Ties the audit row to the request
    :param now: The moment, or None for the clock
    :return: The admin session, with recovery codes at enrollment
    :raises AuthorizationError: 401 for a bad or expired challenge, 403
        when the number is no longer an administrator
    :raises ValidationError: The input is not one of the two kinds the
        stage accepts
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    claims = verify_scoped_token(challenge, MFA_CHALLENGE_AUDIENCE, now=moment)
    account_id = uuid.UUID(str(claims["sub"]))
    stage = str(claims.get("stage", ""))
    phone = _phone(session, account_id)
    if phone is None or not is_platform_admin(phone):
        raise _refused()
    if (code is None) == (recovery_code is None) or (
        stage == "enroll" and recovery_code is not None
    ):
        raise ValidationError(code="ADMIN_MFA_INPUT", message_key="auth.otp.not_valid")

    factor = load_factor(session, account_id)
    # The challenge's stage must match the factor's state: an enroll
    # challenge cannot confirm a factor that is already confirmed (that
    # would let a stolen SMS code re-enroll), and a verify challenge
    # cannot be spent against a factor that was reset meanwhile.
    if factor is None or (stage == "enroll") != (factor.confirmed_at is None):
        raise AuthorizationError(
            code="ADMIN_CHALLENGE_INVALID", message_key="auth.otp.expired", status=401
        )
    check_code(
        session,
        account_id,
        factor,
        code,
        recovery_code,
        ADMIN_DOOR,
        correlation_id,
        moment,
    )
    codes: list[str] | None = None
    if stage == "enroll":
        codes = confirm_factor(session, account_id, moment)
        write_audit(
            session, account_id, AuthEvent.ADMIN_MFA_ENROLLED, correlation_id, moment
        )
    write_audit(session, account_id, AuthEvent.ADMIN_SIGNED_IN, correlation_id, moment)
    token = issue_scoped_token(
        account_id, ADMIN_AUDIENCE, ADMIN_TOKEN_LIFETIME, now=moment
    )
    return AdminSession(
        access_token=token,
        expires_in=int(ADMIN_TOKEN_LIFETIME.total_seconds()),
        recovery_codes=codes,
    )
