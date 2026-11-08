"""Signing in with a password, and the only ways a password is set.

**A session is issued by a password and never by a code alone** [0032].
A verified code -- for a new signup, a forgotten password, or an account
that never had one -- yields a *password-setup token*, and the token
yields a session only once a password has been chosen with it. So a
code can recover an account but cannot be used to sign in to one, and
"codes are for recovery only" is a property of the types rather than a
convention a later route could forget.

**An account with an authenticator app keeps it.** Choosing a password
through a code asks for the authenticator code as well, so holding the
phone (or the mailbox) alone is never enough to take over an account
that has a second factor, and password sign-in goes on to the existing
authenticator step.

**Setting a password signs out everywhere.** A password set through a
code is a recovery; one changed in settings may be a reaction to a
leak. Either way, the sessions that existed before it are the ones not
to trust.

**One answer for every failed sign-in** [BR2.7]: an unknown phone number
or address, an account with no password yet, and a wrong password are
refused alike, after the same scrypt work, and counted alike against the
same per-identifier ceiling.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.accounts.identifier import Identifier
from app.accounts.mfa import has_confirmed_factor
from app.audit.log import AuthEvent, write_audit
from app.auth import passwords
from app.auth.ceilings import CeilingBreach, CeilingChecker
from app.auth.mfa import APP_DOOR, check_code, load_factor
from app.auth.otp import account_for
from app.auth.tokens import (
    PASSWORD_SETUP_AUDIENCE,
    PASSWORD_SETUP_LIFETIME,
    issue_scoped_token,
    revoke_all_families,
    verify_scoped_token,
)
from app.errors import AuthorizationError, ValidationError

__all__ = [
    "PasswordRefused",
    "SetupGrant",
    "change_password",
    "complete_setup",
    "grant_setup",
    "has_password",
    "sign_in",
]

#: The claim a setup token carries: the account's ``password_changed_at``
#: when it was minted, in epoch microseconds, or 0 for no password yet.
_VERSION_CLAIM: Final = "pwv"


class PasswordRefused(ValidationError):
    """The one refusal every failed password sign-in returns."""

    def __init__(self) -> None:
        """Refuse without saying which of the three reasons it was."""
        super().__init__(code="PASSWORD_NOT_VALID", message_key="auth.password.wrong")


@dataclass(frozen=True, slots=True)
class SetupGrant:
    """What a verified code yields: the right to choose a password.

    :ivar token: Carries the person to ``POST /v1/auth/password/setup``
    :ivar expires_in: Seconds until it lapses
    :ivar mfa_required: The authenticator code must come with the password
    """

    token: str
    expires_in: int
    mfa_required: bool


def grant_setup(session: Session, account_id: uuid.UUID) -> SetupGrant:
    """Mint the password-setup token for an account a code just proved.

    :param session: The session to read through
    :param account_id: The account the code authenticated
    :return: The token, its lifetime and whether a second factor follows
    """
    token = issue_scoped_token(
        account_id,
        PASSWORD_SETUP_AUDIENCE,
        PASSWORD_SETUP_LIFETIME,
        extra={_VERSION_CLAIM: _version(_changed_at(session, account_id))},
    )
    return SetupGrant(
        token=token,
        expires_in=int(PASSWORD_SETUP_LIFETIME.total_seconds()),
        mfa_required=has_confirmed_factor(session, account_id),
    )


def complete_setup(
    session: Session,
    token: str,
    password: str,
    code: str | None,
    recovery_code: str | None,
    correlation_id: str,
) -> uuid.UUID:
    """Set the password a setup token was granted for. Does not commit.

    :param session: The session to write through
    :param token: The setup token
    :param password: The chosen password
    :param code: An authenticator code, for an account with one
    :param recovery_code: Or a recovery code
    :param correlation_id: Ties the audit rows to the request
    :return: The account, now with a password and no other sessions
    :raises AuthorizationError: 401 when the token is bad, expired or spent
    :raises ValidationError: The password breaks the policy, or the
        authenticator code is missing or wrong
    """
    try:
        claims = verify_scoped_token(token, PASSWORD_SETUP_AUDIENCE)
    except AuthorizationError as error:
        raise _setup_expired() from error
    account_id = uuid.UUID(str(claims["sub"]))

    # Locked, so two concurrent setups with one token cannot both see
    # the version unchanged; the second waits and then finds it spent.
    row = session.execute(
        sa.text("SELECT password_changed_at FROM account WHERE id = :a FOR UPDATE"),
        {"a": account_id},
    ).one_or_none()
    if row is None or str(claims.get(_VERSION_CLAIM)) != _version(
        row.password_changed_at
    ):
        raise _setup_expired()

    # The policy before the second factor, so a refused password does not
    # spend the person's authenticator code.
    passwords.check_policy(password)

    factor = load_factor(session, account_id)
    if factor is not None and factor.confirmed_at is not None:
        if code is None and recovery_code is None:
            raise ValidationError(
                code="MFA_CODE_REQUIRED", message_key="mfa.code_required"
            )
        check_code(
            session, account_id, factor, code, recovery_code, APP_DOOR, correlation_id
        )
        write_audit(session, account_id, AuthEvent.MFA_VERIFIED, correlation_id)

    _store(session, account_id, password)
    revoke_all_families(session, account_id, correlation_id)
    write_audit(session, account_id, AuthEvent.PASSWORD_SET, correlation_id)
    return account_id


def sign_in(
    session: Session,
    identifier: Identifier,
    password: str,
    *,
    ip_prefix: str,
    coarse_prefix: str,
    correlation_id: str,
) -> uuid.UUID:
    """Check a password and return the account it signs in to.

    :param session: The session to work through
    :param identifier: The phone number or address typed
    :param password: The password typed
    :param ip_prefix: The caller's /64 (IPv4: /24)
    :param coarse_prefix: The caller's /48 (IPv4: /24)
    :param correlation_id: Ties the audit rows to the request
    :return: The account
    :raises CeilingBreach: Too many failures for this identifier or
        network; nothing is checked
    :raises PasswordRefused: Unknown, no password, or wrong -- alike
    """
    checker = CeilingChecker(session)
    try:
        checker.check_password_allowed(identifier.rate_key, ip_prefix, coarse_prefix)
    except CeilingBreach:
        write_audit(session, None, AuthEvent.PASSWORD_CEILING_BREACHED, correlation_id)
        session.commit()
        raise

    account_id = account_for(session, identifier)
    stored: str | None = None
    if account_id is not None:
        stored = session.execute(
            sa.text("SELECT password_hash FROM account WHERE id = :a"),
            {"a": account_id},
        ).scalar_one_or_none()

    # The same scrypt work whether or not there was anything to check.
    if stored is None:
        passwords.verify_nothing(password)
        matched = False
    else:
        matched = passwords.verify_password(password, stored)

    if not matched:
        checker.record_password_failure(identifier.rate_key, ip_prefix, coarse_prefix)
        write_audit(
            session, account_id, AuthEvent.PASSWORD_SIGN_IN_FAILED, correlation_id
        )
        session.commit()
        raise PasswordRefused()

    assert account_id is not None and stored is not None  # noqa: S101 -- matched
    if passwords.needs_rehash(stored):
        _store(session, account_id, password, keep_version=True)
    write_audit(
        session, account_id, AuthEvent.PASSWORD_SIGN_IN_SUCCEEDED, correlation_id
    )
    return account_id


def change_password(
    session: Session,
    account_id: uuid.UUID,
    current: str | None,
    new: str,
    *,
    ip_prefix: str,
    coarse_prefix: str,
    correlation_id: str,
) -> None:
    """Set or change the password of a signed-in account. Does not commit.

    An account with no password sets its first one here with no current
    password: the session it signed in with was itself proved by a code.
    An account with one must give it, so a borrowed phone left signed in
    is not a way to take the account for good.

    :param session: The session to write through
    :param account_id: The signed-in account
    :param current: The current password, required when one is set
    :param new: The new password
    :param ip_prefix: The caller's /64 (IPv4: /24)
    :param coarse_prefix: The caller's /48 (IPv4: /24)
    :param correlation_id: Ties the audit rows to the request
    :return: None
    :raises ValidationError: The current password is missing or wrong
        (``auth.password.current_wrong``), or the new one breaks the policy
    :raises CeilingBreach: Too many wrong current passwords
    :raises ValidationError: The new password breaks the policy
    """
    stored = session.execute(
        sa.text("SELECT password_hash FROM account WHERE id = :a FOR UPDATE"),
        {"a": account_id},
    ).scalar_one()
    if stored is not None:
        checker = CeilingChecker(session)
        rate_key = f"acct:{account_id}"
        checker.check_password_allowed(rate_key, ip_prefix, coarse_prefix)
        if current is None or not passwords.verify_password(current, stored):
            checker.record_password_failure(rate_key, ip_prefix, coarse_prefix)
            session.commit()
            # Its own key, not sign-in's: "that phone or email and
            # password don't match" misleads on a settings screen, where
            # the person typed only a password.
            raise ValidationError(
                code="PASSWORD_NOT_VALID", message_key="auth.password.current_wrong"
            )

    passwords.check_policy(new)
    _store(session, account_id, new)
    revoke_all_families(session, account_id, correlation_id)
    write_audit(
        session,
        account_id,
        AuthEvent.PASSWORD_CHANGED if stored else AuthEvent.PASSWORD_SET,
        correlation_id,
    )


def has_password(session: Session, account_id: uuid.UUID) -> bool:
    """Report whether an account has a password.

    :param session: The session to read through
    :param account_id: The account
    :return: True when one is set
    """
    return bool(
        session.execute(
            sa.text("SELECT password_hash IS NOT NULL FROM account WHERE id = :a"),
            {"a": account_id},
        ).scalar_one_or_none()
    )


def _store(
    session: Session,
    account_id: uuid.UUID,
    password: str,
    *,
    keep_version: bool = False,
) -> None:
    """Write a new hash, and spend outstanding setup tokens unless rehashing.

    :param session: The session to write through
    :param account_id: The account
    :param password: The password to hash
    :param keep_version: True for a transparent rehash of the same
        password, which must not spend anything
    :return: None
    """
    if keep_version:
        session.execute(
            sa.text("UPDATE account SET password_hash = :h WHERE id = :a"),
            {"h": passwords.hash_password(password), "a": account_id},
        )
        return
    session.execute(
        sa.text(
            "UPDATE account SET password_hash = :h, password_changed_at = :now "
            "WHERE id = :a"
        ),
        {
            "h": passwords.hash_password(password),
            "now": dt.datetime.now(tz=dt.UTC),
            "a": account_id,
        },
    )


def _changed_at(session: Session, account_id: uuid.UUID) -> dt.datetime | None:
    """Read when an account's password was last set.

    :param session: The session to read through
    :param account_id: The account
    :return: The moment, or None when it never was
    """
    value: dt.datetime | None = session.execute(
        sa.text("SELECT password_changed_at FROM account WHERE id = :a"),
        {"a": account_id},
    ).scalar_one_or_none()
    return value


def _version(changed_at: dt.datetime | None) -> str:
    """Render ``password_changed_at`` as the claim a setup token carries.

    :param changed_at: The moment, or None
    :return: Epoch microseconds as a string, or ``0``
    """
    if changed_at is None:
        return "0"
    return str(int(changed_at.timestamp() * 1_000_000))


def _setup_expired() -> AuthorizationError:
    """Build the refusal for a bad, expired or spent setup token.

    :return: The error
    """
    return AuthorizationError(
        code="PASSWORD_SETUP_EXPIRED",
        message_key="auth.password.setup_expired",
        status=401,
    )
