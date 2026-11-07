"""The authenticator-app factor, shared by every sign-in that uses it.

One factor per account (``mfa_factor``), whichever door it is used at:
the admin sign-in requires it, the app sign-in requires it once the
person has turned it on, and the public deletion page requires it for an
account that has it. Enrolling, checking a code, spending a recovery
code, counting wrong guesses and locking all live here, so the three
doors cannot drift into three different rules.

**What differs per door is only what is said and recorded**: the admin
sign-in answers in its own error codes and writes ``ADMIN_*`` audit
events; the app writes ``MFA_*``. A :class:`Door` carries that
difference and nothing else.

**Guessing is bounded per account, not per request.** Five wrong codes
lock the factor for fifteen minutes at every door at once, and the count
is committed even though the request that tripped it fails.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

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
from app.errors import AuthorizationError, ConflictError, TaxonomyError, ValidationError

__all__ = [
    "ADMIN_DOOR",
    "APP_DOOR",
    "LOCK_DURATION",
    "MAX_FAILED_ATTEMPTS",
    "Door",
    "Factor",
    "check_code",
    "confirm_factor",
    "disable_factor",
    "issue_recovery_codes",
    "load_factor",
    "recovery_codes_left",
    "start_enrollment",
]

#: Wrong codes before the factor locks.
MAX_FAILED_ATTEMPTS: Final = 5

#: How long a locked factor refuses every code.
LOCK_DURATION: Final = dt.timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class Door:
    """What one sign-in path says and records; the rules are shared.

    :ivar failed_event: Audit event for a wrong code
    :ivar locked_event: Audit event when the factor locks
    :ivar recovery_event: Audit event when a recovery code is spent
    :ivar wrong: Builds the error for a wrong code
    :ivar locked: Builds the error for a locked factor
    :ivar unreadable: Builds the error when the stored secret will not
        decrypt (a rotated-out key, or a row moved between accounts)
    """

    failed_event: AuthEvent
    locked_event: AuthEvent
    recovery_event: AuthEvent
    wrong: Callable[[], TaxonomyError]
    locked: Callable[[], TaxonomyError]
    unreadable: Callable[[], TaxonomyError]


#: The admin sign-in's wording, unchanged from when it stood alone.
ADMIN_DOOR: Final = Door(
    failed_event=AuthEvent.ADMIN_MFA_FAILED,
    locked_event=AuthEvent.ADMIN_MFA_LOCKED,
    recovery_event=AuthEvent.ADMIN_RECOVERY_CODE_USED,
    wrong=lambda: ValidationError(code="ADMIN_MFA_WRONG", message_key="auth.otp.wrong"),
    locked=lambda: ConflictError(
        code="ADMIN_MFA_LOCKED", message_key="auth.otp.no_tries_left"
    ),
    unreadable=lambda: AuthorizationError(
        code="ADMIN_CHALLENGE_INVALID", message_key="auth.otp.expired", status=401
    ),
)

#: The app's wording: its own message keys, which every client shows.
APP_DOOR: Final = Door(
    failed_event=AuthEvent.MFA_FAILED,
    locked_event=AuthEvent.MFA_LOCKED,
    recovery_event=AuthEvent.MFA_RECOVERY_CODE_USED,
    wrong=lambda: ValidationError(code="MFA_CODE_WRONG", message_key="mfa.code_wrong"),
    locked=lambda: ConflictError(code="MFA_LOCKED", message_key="mfa.locked"),
    unreadable=lambda: ConflictError(
        code="MFA_UNREADABLE", message_key="mfa.code_wrong"
    ),
)


@dataclass(frozen=True, slots=True)
class Factor:
    """One account's factor row, read for update.

    :ivar sealed: The encrypted secret
    :ivar confirmed_at: When it was confirmed, or None while enrolling
    :ivar last_used_step: The newest accepted step
    :ivar failed_attempts: Wrong codes since the last right one
    :ivar locked_until: Refusing every code until then, if set
    """

    sealed: EncryptedSecret
    confirmed_at: dt.datetime | None
    last_used_step: int | None
    failed_attempts: int
    locked_until: dt.datetime | None


def load_factor(session: Session, account_id: uuid.UUID) -> Factor | None:
    """Read and lock an account's factor row.

    ``FOR UPDATE``, so two codes checked at once cannot both pass the
    replay check or both escape the attempt count.

    :param session: The session to read through
    :param account_id: The account
    :return: The factor, or None when the account has none
    """
    row = session.execute(
        sa.text(
            "SELECT secret_kid, secret_ciphertext, confirmed_at, last_used_step, "
            "failed_attempts, locked_until FROM mfa_factor "
            "WHERE account_id = :a FOR UPDATE"
        ),
        {"a": account_id},
    ).first()
    if row is None:
        return None
    return Factor(
        sealed=EncryptedSecret(
            kid=row.secret_kid, ciphertext=bytes(row.secret_ciphertext)
        ),
        confirmed_at=row.confirmed_at,
        last_used_step=row.last_used_step,
        failed_attempts=row.failed_attempts,
        locked_until=row.locked_until,
    )


def start_enrollment(
    session: Session,
    account_id: uuid.UUID,
    label: str,
    issuer: str,
    now: dt.datetime | None = None,
) -> tuple[str, str]:
    """Give an account a fresh, unconfirmed secret.

    A NEW secret every time this runs before confirmation, so an
    abandoned QR code someone photographed stops working. Never called
    for a confirmed factor; callers check first.

    :param session: The session to write through
    :param account_id: The account
    :param label: What the authenticator app shows under the issuer
    :param issuer: The service name the app shows
    :param now: The moment, or None for the clock
    :return: The base32 secret and its ``otpauth://`` URI
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
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
            "created_at = EXCLUDED.created_at, last_used_step = NULL, "
            "confirmed_at = NULL"
        ),
        {"a": account_id, "kid": sealed.kid, "ct": sealed.ciphertext, "now": moment},
    )
    return secret, totp.otpauth_uri(secret, label, issuer)


def _fail(
    session: Session,
    account_id: uuid.UUID,
    attempts: int,
    door: Door,
    correlation_id: str,
    moment: dt.datetime,
) -> TaxonomyError:
    """Count a wrong code, locking at the limit, and commit.

    Committed HERE, before the caller raises, because the request is
    about to fail and its transaction would otherwise roll the count
    back -- which would make the limit count nothing.

    :param session: The session to write through
    :param account_id: The account
    :param attempts: Wrong codes before this one
    :param door: Which sign-in path, for its wording and audit events
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
        door.locked_event if locking else door.failed_event,
        correlation_id,
        occurred_at=moment,
    )
    session.commit()
    return door.locked() if locking else door.wrong()


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


def check_code(
    session: Session,
    account_id: uuid.UUID,
    factor: Factor,
    code: str | None,
    recovery_code: str | None,
    door: Door,
    correlation_id: str,
    now: dt.datetime | None = None,
) -> None:
    """Accept an authenticator code or a recovery code, or refuse it.

    On success the attempt count and any lock clear and the accepted step
    is recorded, so the same code cannot be used again. Does not commit
    on success; the caller does, with whatever the code unlocked.

    :param session: The session to write through
    :param account_id: The account
    :param factor: Its factor, from :func:`load_factor`
    :param code: Six digits from the app
    :param recovery_code: A recovery code; only one of the two is passed
    :param door: Which sign-in path, for its wording and audit events
    :param correlation_id: Ties the audit row to the request
    :param now: The moment, or None for the clock
    :return: None
    :raises TaxonomyError: The door's wrong-code, locked or unreadable
        error, committed with the attempt count before it is raised
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    if factor.locked_until is not None and factor.locked_until > moment:
        raise door.locked()
    step: int | None = None
    if code is not None:
        try:
            secret = decrypt_secret(factor.sealed, account_id)
        except InvalidTag as error:
            raise door.unreadable() from error
        step = totp.matching_step(
            secret, code, factor.last_used_step, now=moment.timestamp()
        )
        if step is None:
            raise _fail(
                session,
                account_id,
                factor.failed_attempts,
                door,
                correlation_id,
                moment,
            )
    elif recovery_code is None or not _spend_recovery_code(
        session, account_id, recovery_code, moment
    ):
        raise _fail(
            session, account_id, factor.failed_attempts, door, correlation_id, moment
        )
    session.execute(
        sa.text(
            "UPDATE mfa_factor SET failed_attempts = 0, locked_until = NULL, "
            "last_used_step = COALESCE(:step, last_used_step) WHERE account_id = :a"
        ),
        {"a": account_id, "step": step},
    )
    if recovery_code is not None:
        write_audit(session, account_id, door.recovery_event, correlation_id, moment)


def issue_recovery_codes(
    session: Session, account_id: uuid.UUID, now: dt.datetime | None = None
) -> list[str]:
    """Replace an account's recovery codes with ten new ones.

    :param session: The session to write through
    :param account_id: The account
    :param now: The moment, or None for the clock
    :return: The codes, shown to the person once and never stored plain
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
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
    return codes


def confirm_factor(
    session: Session, account_id: uuid.UUID, now: dt.datetime | None = None
) -> list[str]:
    """Mark an enrolling factor confirmed and issue its recovery codes.

    Call only after :func:`check_code` accepted a code from it.

    :param session: The session to write through
    :param account_id: The account
    :param now: The moment, or None for the clock
    :return: The recovery codes
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    session.execute(
        sa.text(
            "UPDATE mfa_factor SET confirmed_at = COALESCE(confirmed_at, :now) "
            "WHERE account_id = :a"
        ),
        {"a": account_id, "now": moment},
    )
    return issue_recovery_codes(session, account_id, moment)


def disable_factor(session: Session, account_id: uuid.UUID) -> None:
    """Remove an account's factor and its recovery codes.

    :param session: The session to write through
    :param account_id: The account
    :return: None
    """
    for table in ("mfa_recovery_code", "mfa_factor"):
        session.execute(
            sa.text(f"DELETE FROM {table} WHERE account_id = :a"),  # noqa: S608  fixed table names
            {"a": account_id},
        )


def recovery_codes_left(session: Session, account_id: uuid.UUID) -> int:
    """Count the unused recovery codes.

    :param session: The session to read through
    :param account_id: The account
    :return: How many remain
    """
    return int(
        session.execute(
            sa.text(
                "SELECT count(*) FROM mfa_recovery_code "
                "WHERE account_id = :a AND used_at IS NULL"
            ),
            {"a": account_id},
        ).scalar_one()
    )
