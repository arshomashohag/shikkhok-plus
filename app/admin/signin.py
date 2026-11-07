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
from cryptography.exceptions import InvalidTag
from sqlalchemy.orm import Session

from app.audit.log import AuthEvent, write_audit
from app.auth import totp
from app.auth.mfa_crypto import (
    EncryptedSecret,
    decrypt_secret,
    encrypt_secret,
    hash_recovery_code,
    new_recovery_codes,
    recovery_code_matches,
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
from app.errors import AuthorizationError, ConflictError, ValidationError

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

#: Wrong authenticator codes before the factor locks.
MAX_FAILED_ATTEMPTS: Final = 5

#: How long a locked factor refuses every code.
LOCK_DURATION: Final = dt.timedelta(minutes=15)

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
    confirmed = session.execute(
        sa.text(
            "SELECT confirmed_at IS NOT NULL FROM mfa_factor WHERE account_id = :a"
        ),
        {"a": account_id},
    ).scalar()
    secret: str | None = None
    uri: str | None = None
    stage: Stage = "verify" if confirmed else "enroll"
    if stage == "enroll":
        # A NEW secret on every unconfirmed attempt: an abandoned QR code
        # someone photographed stops working the next time this runs.
        secret = totp.new_secret()
        sealed = encrypt_secret(secret, account_id)
        session.execute(
            sa.text(
                "INSERT INTO mfa_factor "
                "(account_id, secret_kid, secret_ciphertext, created_at) "
                "VALUES (:a, :kid, :ct, :now) "
                "ON CONFLICT (account_id) DO UPDATE SET "
                "secret_kid = EXCLUDED.secret_kid, "
                "secret_ciphertext = EXCLUDED.secret_ciphertext, "
                "created_at = EXCLUDED.created_at, last_used_step = NULL"
            ),
            {
                "a": account_id,
                "kid": sealed.kid,
                "ct": sealed.ciphertext,
                "now": moment,
            },
        )
        uri = totp.otpauth_uri(secret, f"admin-{phone[-4:]}", ISSUER)
    token = issue_scoped_token(
        account_id,
        MFA_CHALLENGE_AUDIENCE,
        MFA_CHALLENGE_LIFETIME,
        extra={"stage": stage},
        now=moment,
    )
    return Challenge(token=token, stage=stage, secret=secret, otpauth_uri=uri)


def _fail(
    session: Session,
    account_id: uuid.UUID,
    attempts: int,
    correlation_id: str,
    moment: dt.datetime,
) -> ValidationError | ConflictError:
    """Count a wrong code, locking the factor at the limit, and commit.

    Committed HERE, before the caller raises, because the request is about
    to fail and its transaction would otherwise roll the count back --
    which would make the limit count nothing.

    :param session: The session to write through
    :param account_id: The account
    :param attempts: Wrong codes before this one
    :param correlation_id: Ties the audit row to the request
    :param moment: Now
    :return: The error for the caller to raise
    """
    locking = attempts + 1 >= MAX_FAILED_ATTEMPTS
    session.execute(
        sa.text(
            "UPDATE mfa_factor SET failed_attempts = :n, locked_until = :until "
            "WHERE account_id = :a"
        ),
        {
            "a": account_id,
            "n": 0 if locking else attempts + 1,
            "until": moment + LOCK_DURATION if locking else None,
        },
    )
    write_audit(
        session,
        account_id,
        AuthEvent.ADMIN_MFA_LOCKED if locking else AuthEvent.ADMIN_MFA_FAILED,
        correlation_id,
        occurred_at=moment,
    )
    session.commit()
    if locking:
        return ConflictError(
            code="ADMIN_MFA_LOCKED", message_key="auth.otp.no_tries_left"
        )
    return ValidationError(code="ADMIN_MFA_WRONG", message_key="auth.otp.wrong")


def _spend_recovery_code(
    session: Session, account_id: uuid.UUID, typed: str, moment: dt.datetime
) -> bool:
    """Spend one unused recovery code if the typed one matches.

    :param session: The session to write through
    :param account_id: The account
    :param typed: What the person typed
    :param moment: Now
    :return: True when a code matched and is now spent
    """
    rows = session.execute(
        sa.text(
            "SELECT id, code_hash, salt FROM mfa_recovery_code "
            "WHERE account_id = :a AND used_at IS NULL FOR UPDATE"
        ),
        {"a": account_id},
    ).all()
    for row in rows:
        if recovery_code_matches(typed, bytes(row.code_hash), bytes(row.salt)):
            session.execute(
                sa.text("UPDATE mfa_recovery_code SET used_at = :now WHERE id = :id"),
                {"now": moment, "id": row.id},
            )
            return True
    return False


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
    :raises ValidationError: The code is wrong, or the input is not one of
        the two kinds the stage accepts
    :raises ConflictError: The factor is locked
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

    factor = session.execute(
        sa.text(
            "SELECT secret_kid, secret_ciphertext, confirmed_at, last_used_step, "
            "failed_attempts, locked_until FROM mfa_factor "
            "WHERE account_id = :a FOR UPDATE"
        ),
        {"a": account_id},
    ).first()
    # The challenge's stage must match the factor's state: an enroll
    # challenge cannot confirm a factor that is already confirmed (that
    # would let a stolen SMS code re-enroll), and a verify challenge
    # cannot be spent against a factor that was reset meanwhile.
    if factor is None or (stage == "enroll") != (factor.confirmed_at is None):
        raise AuthorizationError(
            code="ADMIN_CHALLENGE_INVALID", message_key="auth.otp.expired", status=401
        )
    if factor.locked_until is not None and factor.locked_until > moment:
        raise ConflictError(
            code="ADMIN_MFA_LOCKED", message_key="auth.otp.no_tries_left"
        )

    step: int | None = None
    if code is not None:
        try:
            secret = decrypt_secret(
                EncryptedSecret(
                    kid=factor.secret_kid, ciphertext=bytes(factor.secret_ciphertext)
                ),
                account_id,
            )
        except InvalidTag as error:
            raise AuthorizationError(
                code="ADMIN_CHALLENGE_INVALID",
                message_key="auth.otp.expired",
                status=401,
            ) from error
        step = totp.matching_step(
            secret, code, factor.last_used_step, now=moment.timestamp()
        )
        if step is None:
            raise _fail(
                session, account_id, factor.failed_attempts, correlation_id, moment
            )
    elif recovery_code is not None and not _spend_recovery_code(
        session, account_id, recovery_code, moment
    ):
        raise _fail(session, account_id, factor.failed_attempts, correlation_id, moment)

    session.execute(
        sa.text(
            "UPDATE mfa_factor SET failed_attempts = 0, locked_until = NULL, "
            "last_used_step = COALESCE(:step, last_used_step), "
            "confirmed_at = COALESCE(confirmed_at, :now) WHERE account_id = :a"
        ),
        {"a": account_id, "step": step, "now": moment},
    )
    codes: list[str] | None = None
    if stage == "enroll":
        codes = new_recovery_codes()
        session.execute(
            sa.text("DELETE FROM mfa_recovery_code WHERE account_id = :a"),
            {"a": account_id},
        )
        for issued in codes:
            digest, salt = hash_recovery_code(issued)
            session.execute(
                sa.text(
                    "INSERT INTO mfa_recovery_code "
                    "(id, account_id, code_hash, salt, created_at) "
                    "VALUES (:id, :a, :h, :s, :now)"
                ),
                {
                    "id": uuid.uuid4(),
                    "a": account_id,
                    "h": digest,
                    "s": salt,
                    "now": moment,
                },
            )
        write_audit(
            session, account_id, AuthEvent.ADMIN_MFA_ENROLLED, correlation_id, moment
        )
    if recovery_code is not None:
        write_audit(
            session,
            account_id,
            AuthEvent.ADMIN_RECOVERY_CODE_USED,
            correlation_id,
            moment,
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
