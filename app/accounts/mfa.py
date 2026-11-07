"""Two-step verification for app accounts: turn it on, use it, turn it off.

**Optional for everyone; recommended for the people who hold money and
other people's records.** Teachers and centre members are told it is
recommended (``recommended``) and the apps offer it after sign-up;
students and guardians find it in Settings and are never pushed. A
platform administrator's number already requires the same factor at the
admin door, so for them it is ``required`` and cannot be turned off here.

**Turning it off needs the factor itself**, an authenticator code or a
recovery code, not just a signed-in session: a stolen phone that is
still signed in must not be able to remove the very thing that stops
the thief signing in elsewhere.

The rules for codes, replays, guessing and locks are the shared
factor's (``app.auth.mfa``); this module only decides when each step is
allowed and what the app is told.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.audit.log import AuthEvent, write_audit
from app.auth.mfa import (
    APP_DOOR,
    check_code,
    confirm_factor,
    disable_factor,
    issue_recovery_codes,
    load_factor,
    recovery_codes_left,
    start_enrollment,
)
from app.auth.tokens import (
    APP_MFA_CHALLENGE_AUDIENCE,
    MFA_CHALLENGE_LIFETIME,
    issue_scoped_token,
    verify_scoped_token,
)
from app.authz.admin import is_platform_admin
from app.errors import AuthorizationError, ConflictError, ValidationError

__all__ = [
    "ISSUER",
    "MfaStatus",
    "challenge_for",
    "confirm",
    "disable",
    "finish_sign_in",
    "has_confirmed_factor",
    "renew_recovery_codes",
    "setup",
    "status",
]

#: What the authenticator app shows above the code.
ISSUER: Final = "ShikkhokPlus"


@dataclass(frozen=True, slots=True)
class MfaStatus:
    """Whether two-step verification is on, and what the app should say.

    :ivar enabled: A confirmed factor exists
    :ivar enabled_at: When it was confirmed
    :ivar recovery_codes_left: Unused recovery codes
    :ivar recommended: The account teaches or helps run a centre
    :ivar required: The number is a platform administrator's
    """

    enabled: bool
    enabled_at: dt.datetime | None
    recovery_codes_left: int
    recommended: bool
    required: bool


_STANDING: Final = sa.text(
    "SELECT a.phone, "
    "EXISTS (SELECT 1 FROM owner o WHERE o.account_id = a.id "
    "        AND o.kind = 'teacher') "
    "OR EXISTS (SELECT 1 FROM owner_member m WHERE m.account_id = a.id "
    "        AND m.decision = 'accepted' AND m.revoked_at IS NULL) AS teaches "
    "FROM account a WHERE a.id = :a"
)


def _standing(session: Session, account_id: uuid.UUID) -> tuple[str, bool]:
    """Read the number and whether the account teaches.

    :param session: The session to read through
    :param account_id: The account
    :return: Its phone and whether it holds a teaching role
    """
    row = session.execute(_STANDING, {"a": account_id}).one()
    return str(row.phone), bool(row.teaches)


def _not_enabled() -> ConflictError:
    """Build the refusal for an account with no confirmed factor.

    :return: The error
    """
    return ConflictError(code="MFA_NOT_ENABLED", message_key="mfa.not_enabled")


def _one_of(code: str | None, recovery_code: str | None) -> None:
    """Require exactly one of the two kinds of code.

    :param code: An authenticator code
    :param recovery_code: A recovery code
    :return: None
    :raises ValidationError: Neither or both were given
    """
    if (code is None) == (recovery_code is None):
        raise ValidationError(code="MFA_INPUT", message_key="mfa.code_wrong")


def has_confirmed_factor(session: Session, account_id: uuid.UUID) -> bool:
    """Report whether sign-in must ask for an authenticator code.

    :param session: The session to read through
    :param account_id: The account
    :return: True when a confirmed factor exists
    """
    return bool(
        session.execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM mfa_factor WHERE account_id = :a "
                "AND confirmed_at IS NOT NULL)"
            ),
            {"a": account_id},
        ).scalar_one()
    )


def status(session: Session, account_id: uuid.UUID) -> MfaStatus:
    """Read the account's two-step verification status.

    :param session: The session to read through
    :param account_id: The account
    :return: The status
    """
    phone, teaches = _standing(session, account_id)
    confirmed_at = session.execute(
        sa.text("SELECT confirmed_at FROM mfa_factor WHERE account_id = :a"),
        {"a": account_id},
    ).scalar()
    enabled = confirmed_at is not None
    return MfaStatus(
        enabled=enabled,
        enabled_at=confirmed_at,
        recovery_codes_left=recovery_codes_left(session, account_id) if enabled else 0,
        recommended=teaches,
        required=is_platform_admin(phone),
    )


def setup(session: Session, account_id: uuid.UUID) -> tuple[str, str]:
    """Begin turning it on: a fresh secret to add to an authenticator app.

    Running it again before confirming replaces the secret, so the
    previous QR code stops working.

    :param session: The session to write through
    :param account_id: The account
    :return: The base32 secret and its ``otpauth://`` URI
    :raises ConflictError: It is already on
    """
    phone, _ = _standing(session, account_id)
    factor = load_factor(session, account_id)
    if factor is not None and factor.confirmed_at is not None:
        raise ConflictError(
            code="MFA_ALREADY_ENABLED", message_key="mfa.already_enabled"
        )
    return start_enrollment(session, account_id, f"account-{phone[-4:]}", ISSUER)


def confirm(
    session: Session, account_id: uuid.UUID, code: str, correlation_id: str
) -> list[str]:
    """Finish turning it on with the first code from the app.

    :param session: The session to write through
    :param account_id: The account
    :param code: Six digits from the app
    :param correlation_id: Ties the audit rows to the request
    :return: The ten recovery codes, shown once
    :raises ConflictError: It is already on, or setup was never started
    """
    factor = load_factor(session, account_id)
    if factor is None:
        raise ConflictError(code="MFA_NOT_STARTED", message_key="mfa.setup_not_started")
    if factor.confirmed_at is not None:
        raise ConflictError(
            code="MFA_ALREADY_ENABLED", message_key="mfa.already_enabled"
        )
    check_code(session, account_id, factor, code, None, APP_DOOR, correlation_id)
    codes = confirm_factor(session, account_id)
    write_audit(session, account_id, AuthEvent.MFA_ENROLLED, correlation_id)
    return codes


def disable(
    session: Session,
    account_id: uuid.UUID,
    code: str | None,
    recovery_code: str | None,
    correlation_id: str,
) -> None:
    """Turn it off, proven with the factor itself.

    :param session: The session to write through
    :param account_id: The account
    :param code: An authenticator code
    :param recovery_code: Or a recovery code
    :param correlation_id: Ties the audit rows to the request
    :return: None
    :raises ConflictError: It is not on, or the number is an administrator's
    """
    _one_of(code, recovery_code)
    phone, _ = _standing(session, account_id)
    if is_platform_admin(phone):
        raise ConflictError(
            code="MFA_REQUIRED_FOR_ADMIN", message_key="mfa.required_for_admin"
        )
    factor = load_factor(session, account_id)
    if factor is None or factor.confirmed_at is None:
        raise _not_enabled()
    check_code(
        session, account_id, factor, code, recovery_code, APP_DOOR, correlation_id
    )
    disable_factor(session, account_id)
    write_audit(session, account_id, AuthEvent.MFA_DISABLED, correlation_id)


def renew_recovery_codes(
    session: Session, account_id: uuid.UUID, code: str, correlation_id: str
) -> list[str]:
    """Replace the recovery codes, proven with an authenticator code.

    :param session: The session to write through
    :param account_id: The account
    :param code: Six digits from the app
    :param correlation_id: Ties the audit rows to the request
    :return: Ten new codes; the old ones stop working
    :raises ConflictError: It is not on
    """
    factor = load_factor(session, account_id)
    if factor is None or factor.confirmed_at is None:
        raise _not_enabled()
    check_code(session, account_id, factor, code, None, APP_DOOR, correlation_id)
    codes = issue_recovery_codes(session, account_id)
    write_audit(
        session, account_id, AuthEvent.MFA_RECOVERY_CODES_RENEWED, correlation_id
    )
    return codes


def challenge_for(account_id: uuid.UUID) -> str:
    """Mint the token that carries a sign-in to the authenticator step.

    :param account_id: The account the SMS code authenticated
    :return: The challenge; it grants nothing on its own
    """
    return issue_scoped_token(
        account_id, APP_MFA_CHALLENGE_AUDIENCE, MFA_CHALLENGE_LIFETIME
    )


def finish_sign_in(
    session: Session,
    challenge: str,
    code: str | None,
    recovery_code: str | None,
    correlation_id: str,
) -> uuid.UUID:
    """Accept the second step of an app sign-in.

    :param session: The session to write through
    :param challenge: From the SMS step
    :param code: An authenticator code
    :param recovery_code: Or a recovery code
    :param correlation_id: Ties the audit rows to the request
    :return: The account to issue tokens to
    :raises AuthorizationError: 401 when the challenge is bad or expired,
        or the factor was turned off since it was minted
    """
    _one_of(code, recovery_code)
    try:
        claims = verify_scoped_token(challenge, APP_MFA_CHALLENGE_AUDIENCE)
    except AuthorizationError as error:
        raise AuthorizationError(
            code="MFA_CHALLENGE_INVALID",
            message_key="mfa.challenge_expired",
            status=401,
        ) from error
    account_id = uuid.UUID(str(claims["sub"]))
    factor = load_factor(session, account_id)
    if factor is None or factor.confirmed_at is None:
        raise AuthorizationError(
            code="MFA_CHALLENGE_INVALID",
            message_key="mfa.challenge_expired",
            status=401,
        )
    check_code(
        session, account_id, factor, code, recovery_code, APP_DOOR, correlation_id
    )
    write_audit(session, account_id, AuthEvent.MFA_VERIFIED, correlation_id)
    return account_id
