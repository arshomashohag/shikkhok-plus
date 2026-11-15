"""Adding, replacing and removing an account's phone number or email.

**Adding** a kind the account lacks is unchanged in shape [0032]: a code
proves the destination, and the destination is refused as taken only
after the code, so asking is not a way to learn who is registered.

**Replacing and removing** [U2: FR8, ADR-006] need the account's
password [BR5.2], at most five times a day [BR5.6], and never touch a
contact on the administrator allowlist [BR5.13]. A replacement code is
bound to the account that asked for it and is selected by that account
only [BR5.3]. The new contact is verified and the old one removed in ONE
transaction [BR5.4]; the last contact can never be removed [BR5.5].

**Nothing a contact linked is unlinked when it leaves** [BR5.7]: seats
and invitations stay with the account, decisions unchanged, so its
lenses are the same before and after. The freed contact may be verified
by another account, which then links only what is still unlinked
[BR3.5, BR5.8].

**Every newly verified contact is matched** [BR3.1] -- an email as well
as a phone, which before U2 matched nothing.

**The lock order** [NFR4.2]. Each write takes the account's advisory key
and the keys of the contacts it touches before any row lock, through
:func:`app.accounts.matching.lock_account`. The account key does what
locking the account row up front used to do -- it serialises two changes
on one account and a deletion of it -- without taking the account row
ahead of seat rows.

Removal, replacement and the add verify are each one unit of work that a
caller may re-run on a serialization failure or a deadlock
(:mod:`app.db.retry`): nothing leaves the process before their commit,
and the notice to a removed contact is sent after it.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Final, Literal

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts.identifier import Channel, Identifier
from app.accounts.matching import lock_account, lock_contact, match_contact
from app.audit.log import AuthEvent, write_audit
from app.auth import otp, pending
from app.auth import passwords as hashing
from app.auth.ceilings import CeilingChecker
from app.authz.admin import is_platform_admin
from app.errors import ConflictError, ValidationError

__all__ = [
    "ContactKind",
    "attach",
    "confirm_password",
    "contact_already_set",
    "contact_taken",
    "held_value",
    "prepare_code",
    "remove",
]

_log = logging.getLogger(__name__)

#: The two kinds of contact an account holds.
ContactKind = Literal["phone", "email"]


def _refused[E: Exception](error: E, correlation_id: str, purpose: str) -> E:
    """Log a refused contact change once, at INFO, and hand the error back.

    An expected outcome under a rule, so never above INFO and never an
    alert [NFR4.8 to NFR4.10]; the line carries the refusal's key, the
    step and the correlation id, and never a contact or an account id
    [NFR3.4].

    :param error: The refusal about to be raised
    :param correlation_id: Ties the line to the request
    :param purpose: ``contact_replace`` or ``contact_remove``
    :return: The same error
    """
    _log.info(
        "contact change refused",
        extra={
            "purpose": purpose,
            "outcome": getattr(error, "message_key", type(error).__name__),
            "correlation_id": correlation_id,
        },
    )
    return error


#: The account's contacts and password, read under its advisory key.
_ACCOUNT: Final = sa.text(
    "SELECT phone, email, password_hash FROM account WHERE id = :a"
)


def contact_already_set() -> ConflictError:
    """Build the refusal for a destination the account already holds.

    :return: The error
    """
    return ConflictError(
        code="CONTACT_ALREADY_SET", message_key="account.contact.already_set"
    )


def contact_taken() -> ConflictError:
    """Build the refusal for a destination another account holds.

    :return: The error
    """
    return ConflictError(code="CONTACT_TAKEN", message_key="account.contact.taken")


def _password_required() -> ValidationError:
    """Build the refusal for a change made without the password [BR5.2].

    :return: The error
    """
    return ValidationError(
        code="CONTACT_PASSWORD_REQUIRED",
        message_key="account.contact.password_required",
    )


def _admin_locked() -> ConflictError:
    """Build the refusal for an allowlisted administrator contact [BR5.13].

    :return: The error
    """
    return ConflictError(
        code="CONTACT_ADMIN_LOCKED", message_key="account.contact.admin_locked"
    )


def _last_one() -> ConflictError:
    """Build the refusal for removing the account's only contact [BR5.5].

    :return: The error
    """
    return ConflictError(
        code="CONTACT_LAST_ONE", message_key="account.contact.last_one"
    )


def _identifier(kind: str, value: str) -> Identifier:
    """Tag a stored contact with its kind.

    :param kind: ``phone`` or ``email``
    :param value: The stored, canonical value
    :return: The identifier
    """
    return Identifier(Channel.PHONE if kind == "phone" else Channel.EMAIL, value)


def _is_admin_contact(contact: Identifier) -> bool:
    """Report whether a contact is on the administrator allowlist.

    Read exactly as administrator status reads it, through the same
    function and the same canonical comparison [BR5.13].

    :param contact: The contact that would leave the account
    :return: True when it is allowlisted
    """
    if contact.is_phone:
        return is_platform_admin(contact.value, None)
    return is_platform_admin(None, contact.value)


def held_value(session: Session, account_id: uuid.UUID, kind: str) -> str | None:
    """Return the contact of one kind the account holds, if any.

    :param session: The session to read through
    :param account_id: The account
    :param kind: ``phone`` or ``email``
    :return: The stored value, or None
    """
    row = session.execute(_ACCOUNT, {"a": account_id}).one()
    value: str | None = row.phone if kind == "phone" else row.email
    return value


def confirm_password(
    session: Session,
    account_id: uuid.UUID,
    password: str | None,
    *,
    ip_prefix: str,
    coarse_prefix: str,
) -> None:
    """Confirm the account's password for a contact change [BR5.2].

    An account with no password sets one first; a request without one is
    refused alike. A wrong one is counted under the per-account password
    ceiling ``change_password`` uses, committed, and refused, which ends
    the request. Checked before anything is read that could differ by
    the outcome.

    :param session: The session to work through
    :param account_id: The account
    :param password: What was typed, or None
    :param ip_prefix: The caller's /64 (IPv4: /24)
    :param coarse_prefix: The caller's /48 (IPv4: /24)
    :return: None
    :raises ValidationError: No password on the account or in the
        request, or the password is wrong
    :raises CeilingBreach: Too many wrong passwords this hour
    """
    stored = session.execute(_ACCOUNT, {"a": account_id}).one().password_hash
    if stored is None or password is None:
        raise _password_required()
    checker = CeilingChecker(session)
    rate_key = f"acct:{account_id}"
    checker.check_password_allowed(rate_key, ip_prefix, coarse_prefix)
    if not hashing.verify_password(password, stored):
        checker.record_password_failure(rate_key, ip_prefix, coarse_prefix)
        session.commit()
        raise ValidationError(
            code="PASSWORD_NOT_VALID", message_key="auth.password.current_wrong"
        )


def prepare_code(
    session: Session,
    account_id: uuid.UUID,
    identifier: Identifier,
    password: str | None,
    *,
    ip_prefix: str,
    coarse_prefix: str,
) -> uuid.UUID | None:
    """Decide what a code request is, refusing what cannot proceed.

    The request step of W7 [BR5.2, BR5.4, BR5.6, BR5.13]. A kind the
    account lacks is an ADD, unchanged: no password, no limit. A kind it
    holds is a REPLACEMENT: the password is confirmed, an allowlisted
    current value is refused, the same value is refused, and the change
    allowance is READ (never spent) so a person at the limit is not sent
    a code they cannot use.

    :param session: The session to work through
    :param account_id: The account asking
    :param identifier: The destination the code is for
    :param password: The password, required for a replacement
    :param ip_prefix: The caller's /64 (IPv4: /24)
    :param coarse_prefix: The caller's /48 (IPv4: /24)
    :return: The account to bind the code to for a replacement, or None
        for an add
    :raises ValidationError: The password is missing or wrong
    :raises ConflictError: Allowlisted, the same value, or at the limit
    :raises CeilingBreach: Too many wrong passwords, or too many changes
    """
    current = held_value(session, account_id, identifier.column)
    if current is None:
        return None
    confirm_password(
        session,
        account_id,
        password,
        ip_prefix=ip_prefix,
        coarse_prefix=coarse_prefix,
    )
    if _is_admin_contact(_identifier(identifier.column, current)):
        raise _admin_locked()
    if current == identifier.value:
        raise contact_already_set()
    CeilingChecker(session).check_contact_change_allowed(account_id)
    return account_id


def attach(
    session: Session,
    account_id: uuid.UUID,
    identifier: Identifier,
    code: str,
    correlation_id: str,
    now: dt.datetime | None = None,
) -> Identifier | None:
    """Spend the code sent to a destination and add it, or replace with it.

    An ADD when the account holds no contact of this kind (W5, W6); a
    REPLACEMENT when it does (W7 steps 5 to 11). Commits on every outcome
    a code decides: a refused code records its attempt, and a destination
    found taken has still had its code spent.

    :param session: The session to write through
    :param account_id: The signed-in account
    :param identifier: The number or address being added
    :param code: The code sent to it
    :param correlation_id: Ties the audit rows to the request
    :param now: The moment, or None for the clock
    :return: The contact a replacement removed, for the notice; None for
        an add
    :raises CodeRefused: The code was refused
    :raises ConflictError: Held by another account, already this
        account's, allowlisted, or over the daily change limit
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    if held_value(session, account_id, identifier.column) is None:
        _add(session, account_id, identifier, code, correlation_id, moment)
        return None
    return _replace(session, account_id, identifier, code, correlation_id, moment)


def _add(
    session: Session,
    account_id: uuid.UUID,
    identifier: Identifier,
    code: str,
    correlation_id: str,
    moment: dt.datetime,
) -> None:
    """Add a kind the account lacks [BR5.1, W5, W6].

    :param session: The session to write through
    :param account_id: The signed-in account
    :param identifier: The destination being added
    :param code: The code sent to it
    :param correlation_id: Ties the audit rows to the request
    :param moment: The moment of verification
    :return: None
    :raises CodeRefused: The code was refused
    :raises ConflictError: Already set, or another account holds it
    """
    lock_account(session, account_id, [identifier])
    if held_value(session, account_id, identifier.column) is not None:
        # A concurrent add finished first; the code is left unspent.
        raise contact_already_set()
    otp.consume_code(
        session,
        identifier,
        code,
        correlation_id,
        purpose=otp.CONTACT_PURPOSE,
        now=moment,
    )
    _store(session, account_id, identifier)
    write_audit(session, account_id, AuthEvent.CONTACT_ADDED, correlation_id)
    session.commit()


def _replace(
    session: Session,
    account_id: uuid.UUID,
    identifier: Identifier,
    code: str,
    correlation_id: str,
    moment: dt.datetime,
) -> Identifier | None:
    """Replace a contact with a newly verified one, in one transaction [BR5.4].

    :param session: The session to write through
    :param account_id: The signed-in account
    :param identifier: The new destination
    :param code: The code sent to it
    :param correlation_id: Ties the audit rows to the request
    :param moment: The moment of verification
    :return: The contact that left the account
    :raises CodeRefused: No replacement code of this account's, or it
        was refused
    :raises ConflictError: Held by another account, allowlisted, or over
        the daily change limit
    """
    code_id = otp.find_replacement_code(session, identifier, requester=account_id)
    if code_id is None:
        raise otp.CodeRefused(message_key="auth.otp.not_valid")
    current = held_value(session, account_id, identifier.column)
    contacts = [identifier]
    if current is not None:
        contacts.append(_identifier(identifier.column, current))
    lock_account(session, account_id, contacts)
    old = held_value(session, account_id, identifier.column)
    if old is None:
        # Removed concurrently: there is nothing left to replace.
        raise otp.CodeRefused(message_key="auth.otp.not_valid")
    if old == identifier.value:
        # Refused at the request step too; the code is left unspent.
        raise _refused(contact_already_set(), correlation_id, "contact_replace")
    leaving = _identifier(identifier.column, old)
    lock_contact(session, leaving)

    otp.consume_replacement_code(
        session,
        identifier,
        code,
        correlation_id,
        requester=account_id,
        code_id=code_id,
        now=moment,
    )
    if otp.account_for(session, identifier) is not None:
        # Taken: refused after the code, as an add is, and BEFORE the day's
        # count -- only a completed change counts [BR5.6].
        session.commit()
        raise _refused(contact_taken(), correlation_id, "contact_replace")
    if _is_admin_contact(leaving):
        # Checked again at verify: the allowlist may have changed since
        # the request. Rolled back, so the code stays unspent.
        session.rollback()
        raise _refused(_admin_locked(), correlation_id, "contact_replace")
    try:
        CeilingChecker(session).consume_contact_change(account_id, moment)
    except ConflictError as breach:
        session.rollback()
        raise _refused(breach, correlation_id, "contact_replace") from None
    # A destination taken in the instant since the check above reaches the
    # unique index; the whole change, count included, is rolled back.
    _store(session, account_id, identifier, keep_spent_code=False)
    write_audit(session, account_id, AuthEvent.CONTACT_REPLACED, correlation_id)
    session.commit()
    return leaving


def _store(
    session: Session,
    account_id: uuid.UUID,
    identifier: Identifier,
    *,
    keep_spent_code: bool = True,
) -> None:
    """Make a verified destination the account's, and match it [LO-4].

    The destination is checked free, then inside a savepoint the matcher
    links what it names and the account takes it; a unique violation on
    the account write undoes the links with it and answers taken. Sign-up
    drafts for the destination are moot.

    :param session: The session to write through
    :param account_id: The account
    :param identifier: The verified destination
    :param keep_spent_code: On a taken refusal, commit the spent code (an
        add, as built), or roll the whole transaction back (a replacement,
        whose day's count must not survive a change that did not happen)
    :return: None
    :raises ConflictError: Another account holds the destination
    """

    def taken() -> ConflictError:
        """End the transaction as the caller asked and build the refusal.

        :return: The error
        """
        if keep_spent_code:
            session.commit()
        else:
            session.rollback()
        return contact_taken()

    if otp.account_for(session, identifier) is not None:
        raise taken()
    try:
        with session.begin_nested():
            match_contact(session, account_id=account_id, contact=identifier)
            session.execute(
                sa.text(
                    f"UPDATE account SET {identifier.column} = :value WHERE id = :a"  # noqa: S608
                ),
                {"value": identifier.value, "a": account_id},
            )
    except IntegrityError as error:
        # Another account took it between the read above and this write.
        raise taken() from error
    # A signup someone started for this destination is moot now.
    pending.discard(session, identifier=identifier)


def remove(
    session: Session,
    account_id: uuid.UUID,
    kind: ContactKind,
    password: str,
    *,
    ip_prefix: str,
    coarse_prefix: str,
    correlation_id: str,
    now: dt.datetime | None = None,
) -> Identifier | None:
    """Remove one of the account's contacts [W8, BR5.2, BR5.5 to BR5.13].

    :param session: The session to write through
    :param account_id: The signed-in account
    :param kind: Which contact to remove
    :param password: The account's password
    :param ip_prefix: The caller's /64 (IPv4: /24)
    :param coarse_prefix: The caller's /48 (IPv4: /24)
    :param correlation_id: Ties the audit row to the request
    :param now: The moment, or None for the clock
    :return: The contact removed, for the notice; None when the account
        held none of that kind and nothing changed [BR5.12]
    :raises ValidationError: The password is missing or wrong
    :raises ConflictError: Allowlisted, the last contact, or over the
        daily change limit
    :raises CeilingBreach: Too many wrong passwords this hour
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    lock_account(session, account_id)
    confirm_password(
        session,
        account_id,
        password,
        ip_prefix=ip_prefix,
        coarse_prefix=coarse_prefix,
    )
    row = session.execute(_ACCOUNT, {"a": account_id}).one()
    value: str | None = row.phone if kind == "phone" else row.email
    if value is None:
        session.rollback()
        return None
    leaving = _identifier(kind, value)
    lock_contact(session, leaving)
    if _is_admin_contact(leaving):
        session.rollback()
        raise _refused(_admin_locked(), correlation_id, "contact_remove")
    other = row.email if kind == "phone" else row.phone
    if other is None:
        session.rollback()
        raise _refused(_last_one(), correlation_id, "contact_remove")
    try:
        CeilingChecker(session).consume_contact_change(account_id, moment)
    except ConflictError as breach:
        session.rollback()
        raise _refused(breach, correlation_id, "contact_remove") from None
    try:
        with session.begin_nested():
            session.execute(
                sa.text(f"UPDATE account SET {kind} = NULL WHERE id = :a"),  # noqa: S608
                {"a": account_id},
            )
    except IntegrityError:
        # ck_account_has_identifier: the backstop for the check above.
        session.rollback()
        raise _refused(_last_one(), correlation_id, "contact_remove") from None
    write_audit(session, account_id, AuthEvent.CONTACT_REMOVED, correlation_id)
    session.commit()
    return leaving
