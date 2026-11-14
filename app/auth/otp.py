"""Issue and verify, including the oracle both branches must defeat.

Two things here are easy to get wrong in ways that pass a confirmatory
test:

**The existence oracle** [BR2.7]. The natural shape of :func:`issue` is
"look up the account; if absent, return early". That early return makes
the unknown path measurably cheaper, and the response body matching is
not enough. Worse, **the hash is the smaller asymmetry**: the known
branch performs a transactional INSERT and the unknown branch performs
none, and a database write means lock acquisition and a WAL flush --
a far larger and more reliable timing signal than a hash computation. So
the unknown branch performs the **same write and keeps it** -- a code
row nobody was told, which also lets verify answer an unknown number
exactly as it answers a known one (see :func:`issue`).

*What remains unclosed, stated so the test is not read as stronger than
it is*: equivalent work is not constant time. A patient attacker with a
very large sample could still find residual variance. Closing that needs
a fixed response deadline, which is implementable but disproportionate
here and would become a latency floor on every OTP request.

**The attempt ceiling** [BR2.3]. An implementation that counts attempts
without invalidating the code passes the confirmatory half -- the 6th
attempt is refused -- while leaving brute force open, because a correct
7th still works. The code must be **dead** afterwards.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.accounts.identifier import Identifier
from app.audit.log import AuthEvent, write_audit
from app.auth import pending
from app.auth.hashing import generate_code, hash_otp, verify_otp
from app.errors import ValidationError

__all__ = [
    "ATTEMPT_CEILING",
    "CODE_LIFETIME",
    "CONTACT_PURPOSE",
    "CONTACT_REPLACE_PURPOSE",
    "DELETION_PURPOSE",
    "OTP_PURPOSE",
    "CodeRefused",
    "IssuedCode",
    "SignupCompleter",
    "account_for",
    "consume_code",
    "consume_replacement_code",
    "find_replacement_code",
    "issue",
    "verify",
]

#: Turns the signup draft bound to a just-verified code into an account,
#: returning its id, or None when no live draft is bound to that code.
#: Passed in by the route rather than imported, so this module -- the
#: one every code passes through -- depends on nothing about accounts.
SignupCompleter = Callable[[Session, uuid.UUID, dt.datetime], uuid.UUID | None]


class CodeRefused(ValidationError):
    """A presented code was refused; the 400 every refusal returns.

    A :class:`~app.errors.ValidationError` like every refusal before it,
    so the response is unchanged. It carries one fact for the CALLER and
    never for the response: whether this attempt is the one that killed
    the code at the attempt ceiling, which the per-number dead-code
    cool-off counts [C-20].

    :ivar code_died: This attempt exhausted the code's attempts
    """

    def __init__(
        self,
        message_key: str,
        *,
        code_died: bool = False,
        details: dict[str, str] | None = None,
    ) -> None:
        """Refuse a code.

        :param message_key: The remedy shown to the person
        :param code_died: This attempt exhausted the code's attempts
        :param details: Optional payload, such as the tries left
        """
        super().__init__(code=REFUSAL_CODE, message_key=message_key, details=details)
        self.code_died = code_died


#: A code expires five minutes after issue [BR2.3].
CODE_LIFETIME: Final = dt.timedelta(minutes=5)

#: A code dies after five failed attempts; the 6th is refused [BR2.3].
ATTEMPT_CEILING: Final = 5

#: Sign-in. **Required at every call site, and there is deliberately no
#: default**: a default would let a second consumer arrive without
#: anyone choosing its ceiling, which is the one control protecting the
#: project's wallet. D6 was that second consumer, and the absent default
#: is what made it a compile-time question rather than a silent reuse.
OTP_PURPOSE: Final = "otp"

#: Account deletion [NFR14.98]. Its own purpose, so a code issued to
#: sign in cannot confirm a destruction -- which is what the code did
#: before D6, because ``verify()`` filtered on the phone alone.
#:
#: Eight characters against ``otp_request.purpose``'s ``String(32)``, so
#: no migration. The sibling control's values are constrained by a
#: ``String(16)`` and the abbreviation that forced is recorded in
#: ``app/auth/ceilings.py``; this column is wide enough that no such
#: compromise is needed here.
DELETION_PURPOSE: Final = "deletion"

#: Proving a phone number or an email address an account is ADDING
#: [0032]. Its own purpose for the reason deletion has one: a code sent
#: to sign in must not be able to attach a destination to an account,
#: and a code sent to attach one must not sign anyone in.
CONTACT_PURPOSE: Final = "contact"

#: Proving the phone number or address that REPLACES one an account holds
#: [U2: BR5.3]. Its own purpose, and bound to the account that confirmed
#: its password for it (``requested_by_account_id``): a replacement is
#: selected by its requester as part of row selection, so another
#: account's code for the same destination is never read, attempted or
#: spent. Fifteen characters against ``String(32)``.
CONTACT_REPLACE_PURPOSE: Final = "contact_replace"


@dataclass(frozen=True, slots=True)
class IssuedCode:
    """What :func:`issue` hands back to the caller.

    ``code`` is the value to transmit and is **never** persisted or
    logged. ``account_exists`` and ``pending_signup`` decide whether the
    code is SENT, after the response, and must not reach the response,
    or they become the oracle in a new place.

    :ivar code: The transmitted code
    :ivar account_exists: Whether the number had an account
    :ivar request_id: The code's row, so a skipped send can kill it
    :ivar pending_signup: Whether a live signup draft is now bound to
        this code [C-07]
    """

    code: str
    account_exists: bool
    request_id: uuid.UUID
    pending_signup: bool


def issue(
    session: Session,
    identifier: Identifier,
    correlation_id: str,
    *,
    purpose: str,
    now: dt.datetime | None = None,
    requested_by: uuid.UUID | None = None,
) -> IssuedCode:
    """Issue a code, doing equivalent work whether or not the number exists.

    ``purpose`` is **keyword-only and has no default**, so a third
    consumer cannot inherit sign-in's purpose by saying nothing. The
    keyword form is what stops it being supplied positionally into
    ``correlation_id``'s place by a caller reordering arguments.

    :param session: The session to write through
    :param identifier: The number or address to issue for
    :param correlation_id: Ties the audit row to this request
    :param purpose: What this code may be spent on
    :param now: The moment of issue, or None for the clock
    :param requested_by: For a replacement code, the account that asked
        for it after confirming its password [BR5.3]; None otherwise
    :return: The code to transmit and whether an account existed
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    code = generate_code()

    account_id = account_for(session, identifier)

    # BOTH BRANCHES HASH, AND BOTH BRANCHES WRITE. The hash is the
    # smaller asymmetry; the write is the one that dominates.
    digest = hash_otp(code, identifier.value)
    row_id = uuid.uuid4()
    parameters = {
        "id": row_id,
        **identifier.as_params(),
        "otp_hash": digest,
        "purpose": purpose,
        "issued_at": moment,
        "expires_at": moment + CODE_LIFETIME,
        "requested_by": requested_by,
    }

    # **Kept for an unknown number too, and never sent to it.** This
    # write used to be rolled back on the unknown branch, which was
    # enough while every refusal looked the same. Verify now says how
    # many tries are left and whether the code expired [BR2.3], and
    # without a row an unknown number would answer neither -- a wrong
    # code at a registered number would say "4 tries left" and at an
    # unregistered one would not, which is the existence oracle in a
    # new place [BR2.7]. With the row kept, both numbers run the same
    # verify path to the same answers, and the code can never match
    # because nobody was told it. The row ages out under
    # ``otp_request``'s seven-day retention like any other.
    session.execute(
        sa.text(
            "INSERT INTO otp_request "
            "(id, phone, email, otp_hash, purpose, issued_at, expires_at, "
            "requested_by_account_id) "
            "VALUES (:id, :phone, :email, :otp_hash, :purpose, :issued_at, "
            ":expires_at, :requested_by)"
        ),
        parameters,
    )

    # A sign-in code adopts this number's signup draft, if one is live
    # [C-07], so "send the code again" after signup sends a code that
    # completes it. Run for EVERY number, so both branches execute the
    # same statement whatever it finds [BR2.7].
    pending_signup = purpose == OTP_PURPOSE and pending.bind_code(
        session, identifier=identifier, otp_request_id=row_id, now=moment
    )

    # account_id is nullable here BY DESIGN: a placeholder would
    # reintroduce the oracle this path exists to close.
    write_audit(
        session,
        account_id=account_id,
        event=AuthEvent.OTP_ISSUED,
        correlation_id=correlation_id,
        occurred_at=moment,
    )
    session.commit()

    return IssuedCode(
        code=code,
        account_exists=account_id is not None,
        request_id=row_id,
        pending_signup=pending_signup,
    )


def consume_code(
    session: Session,
    identifier: Identifier,
    code: str,
    correlation_id: str,
    *,
    purpose: str,
    now: dt.datetime | None = None,
) -> uuid.UUID:
    """Check and spend the latest code of one purpose for one destination.

    The expiry, the single-use rule and the attempt ceiling share one
    transaction boundary, which is why they are one function rather than
    three guards: ``consumed_at`` is set **in the same transaction as the
    check that read it**, so a concurrent second verify cannot slip
    between them [BR2.3].

    **Does not commit a success**: the caller does whatever the code
    proves inside the same transaction, so a failure there leaves the
    code unspent. Every refusal commits its attempt row before raising.

    :param session: The session to work through
    :param identifier: The number or address the code was sent to
    :param code: The presented code
    :param correlation_id: Ties the audit row to this request
    :param purpose: What the presented code must have been issued for
    :param now: The moment of verification, or None for the clock
    :return: The spent code's row id
    :raises CodeRefused: The code is wrong, expired, used, dead, or was
        issued for a different purpose
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    column = identifier.column

    # FOR UPDATE is what makes the check-then-write atomic. Without it,
    # two concurrent verifies both read an unconsumed row.
    #
    # **`purpose` is in the WHERE, beside the destination, and that
    # placement is the design rather than a style choice** [DESIGN-1].
    # This query returns the LATEST row, so checking the purpose after
    # fetching means a sign-in code issued after a deletion code SHADOWS
    # it: the user's valid deletion code is refused, with `_refused()`,
    # which discloses nothing -- so they retry, spend ceiling budget, and
    # conclude the feature is broken.
    #
    # The column name is a literal from Identifier.column, never text
    # from a request.
    row = session.execute(
        sa.text(
            "SELECT id, otp_hash, expires_at, consumed_at FROM otp_request "  # noqa: S608
            f"WHERE {column} = :value AND purpose = :purpose "
            "ORDER BY issued_at DESC LIMIT 1 "
            "FOR UPDATE"
        ),
        {"value": identifier.value, "purpose": purpose},
    ).one_or_none()

    if row is None:
        raise CodeRefused(message_key="auth.otp.not_valid")
    return _spend(session, identifier, code, correlation_id, row, moment)


#: The latest replacement code this account asked for, for one
#: destination [BR5.3]. The requester is part of the selection, so another
#: account's later code for the same destination cannot shadow this one.
_REPLACEMENT_CODE: Final = {
    column: sa.text(
        f"SELECT id FROM otp_request WHERE {column} = :value "  # noqa: S608
        "AND purpose = :purpose AND requested_by_account_id = :requester "
        "ORDER BY issued_at DESC LIMIT 1"
    )
    for column in ("phone", "email")
}

#: The row read again under its lock, by id [NFR4.2 LO-3 (c)].
_LOCKED_BY_ID: Final = sa.text(
    "SELECT id, phone, email, purpose, requested_by_account_id, otp_hash, "
    "expires_at, consumed_at FROM otp_request WHERE id = :id FOR UPDATE"
)


def find_replacement_code(
    session: Session, identifier: Identifier, *, requester: uuid.UUID
) -> uuid.UUID | None:
    """Find, WITHOUT locking, the replacement code this account asked for.

    The unlocked read of the replacement verify [NFR4.2 LO-3 (a)]: it runs
    before the advisory keys are taken, so it locks no row. Another
    account's code for the same destination is never selected [BR5.3].

    :param session: The session to read through
    :param identifier: The destination the code was sent to
    :param requester: The verifying account
    :return: The code's id, or None when this account asked for none
    """
    found: uuid.UUID | None = session.execute(
        _REPLACEMENT_CODE[identifier.column],
        {
            "value": identifier.value,
            "purpose": CONTACT_REPLACE_PURPOSE,
            "requester": requester,
        },
    ).scalar_one_or_none()
    return found


def consume_replacement_code(
    session: Session,
    identifier: Identifier,
    code: str,
    correlation_id: str,
    *,
    requester: uuid.UUID,
    code_id: uuid.UUID,
    now: dt.datetime | None = None,
) -> uuid.UUID:
    """Lock the code the unlocked read found, re-check it, and spend it.

    [NFR4.2 LO-3 (c), (d)]. Between the unlocked read and this lock a
    concurrent request may have spent or expired the row, or issued a
    newer one for the same destination and requester. Any difference is
    refused as an invalid code, with the attempt recorded against THIS
    row only, exactly as a wrong code is; no other row is spent.

    **Does not commit a success**, like :func:`consume_code`.

    :param session: The session to work through
    :param identifier: The destination the code was sent to
    :param code: The presented code
    :param correlation_id: Ties the audit row to this request
    :param requester: The verifying account
    :param code_id: The row the unlocked read found
    :param now: The moment of verification, or None for the clock
    :return: The spent code's row id
    :raises CodeRefused: The code is wrong, expired, used, dead, or the
        row changed since it was read
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    row = session.execute(_LOCKED_BY_ID, {"id": code_id}).one_or_none()
    if row is None:
        raise CodeRefused(message_key="auth.otp.not_valid")
    latest = find_replacement_code(session, identifier, requester=requester)
    unchanged = (
        getattr(row, identifier.column) == identifier.value
        and row.purpose == CONTACT_REPLACE_PURPOSE
        and row.requested_by_account_id == requester
        and latest == row.id
    )
    if not unchanged:
        _record_attempt(session, row.id, moment, succeeded=False)
        _audit_failure(session, identifier, correlation_id, moment)
        session.commit()
        raise CodeRefused(message_key="auth.otp.not_valid")
    return _spend(session, identifier, code, correlation_id, row, moment)


def _spend(
    session: Session,
    identifier: Identifier,
    code: str,
    correlation_id: str,
    row: sa.Row[tuple[object, ...]],
    moment: dt.datetime,
) -> uuid.UUID:
    """Check one locked code row and spend it, or record the refusal.

    The expiry, the single-use rule and the attempt ceiling, shared by
    every purpose so they cannot drift between them.

    :param session: The session to work through
    :param identifier: The destination the code was sent to
    :param code: The presented code
    :param correlation_id: Ties the audit row to this request
    :param row: The code's row, already locked
    :param moment: The moment of verification
    :return: The spent code's row id
    :raises CodeRefused: The code is wrong, expired, used or dead
    """
    attempts = session.execute(
        sa.text("SELECT count(*) FROM verify_attempt WHERE otp_request_id = :id"),
        {"id": row.id},
    ).scalar_one()

    expired = moment > row.expires_at
    consumed = row.consumed_at is not None
    exhausted = attempts >= ATTEMPT_CEILING

    if expired or consumed or exhausted:
        _record_attempt(session, row.id, moment, succeeded=False)
        _audit_failure(session, identifier, correlation_id, moment)
        session.commit()
        # Expiry is named because its remedy is specific: the code was
        # right and too slow. A used or dead code is "ask for a new one".
        if expired and not consumed and not exhausted:
            raise CodeRefused(message_key="auth.otp.expired")
        raise CodeRefused(message_key="auth.otp.not_valid")

    matched = verify_otp(code, identifier.value, row.otp_hash)
    _record_attempt(session, row.id, moment, succeeded=matched)

    if not matched:
        # THE CODE DIES at the ceiling, not merely the attempt. An
        # implementation that counts without invalidating passes the
        # confirmatory half and leaves brute force open.
        remaining = ATTEMPT_CEILING - (attempts + 1)
        if remaining <= 0:
            session.execute(
                sa.text("UPDATE otp_request SET consumed_at = :now WHERE id = :id"),
                {"now": moment, "id": row.id},
            )
        _audit_failure(session, identifier, correlation_id, moment)
        session.commit()
        if remaining <= 0:
            raise CodeRefused(message_key="auth.otp.no_tries_left", code_died=True)
        raise CodeRefused(
            message_key="auth.otp.wrong",
            details={"attempts_left": str(remaining)},
        )

    session.execute(
        sa.text("UPDATE otp_request SET consumed_at = :now WHERE id = :id"),
        {"now": moment, "id": row.id},
    )
    request_id: uuid.UUID = row.id
    return request_id


def verify(
    session: Session,
    identifier: Identifier,
    code: str,
    correlation_id: str,
    *,
    purpose: str,
    now: dt.datetime | None = None,
    complete_signup: SignupCompleter | None = None,
) -> uuid.UUID:
    """Verify a code of one purpose and return the account it authenticates.

    **Verify-first signup completes here** [C-07]. A right code for a
    destination with no account creates the account from the signup
    draft bound to that code, through ``complete_signup``, in the SAME
    transaction that consumes the code: a failure creating it leaves
    neither an account nor a spent code. A destination that does have an
    account is authenticated as before, and any draft for it is
    discarded.

    :param session: The session to work through
    :param identifier: The number or address being verified
    :param code: The presented code
    :param correlation_id: Ties the audit row to this request
    :param purpose: What the presented code must have been issued for
    :param now: The moment of verification, or None for the clock
    :param complete_signup: Creates the account from a bound draft; None
        where a code may only authenticate an existing account
    :return: The authenticated account's id
    :raises CodeRefused: The code is wrong, expired, used, dead, or was
        issued for a different purpose
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    request_id = consume_code(
        session, identifier, code, correlation_id, purpose=purpose, now=moment
    )

    account_id = account_for(session, identifier)

    if account_id is None and complete_signup is not None:
        # The draft bound to THIS code, and only that one: a draft
        # someone else submitted later is bound to a later code, which
        # shadows this one [C-07].
        account_id = complete_signup(session, request_id, moment)
    elif account_id is not None and purpose == OTP_PURPOSE:
        # Authenticated as an account that exists: a draft submitted for
        # this destination is moot, and holds an address, so it goes now
        # rather than at the purge.
        pending.discard(session, identifier=identifier)

    if account_id is None:
        session.commit()
        raise CodeRefused(message_key="auth.otp.not_valid")

    # Activate if dormant. This is what lets a student or guardian claim
    # a record a teacher created, without being invited [AC1.2.1].
    session.execute(
        sa.text(
            "UPDATE account SET activated_at = coalesce(activated_at, :now) "
            "WHERE id = :id"
        ),
        {"now": moment, "id": account_id},
    )

    write_audit(
        session,
        account_id=account_id,
        event=AuthEvent.VERIFY_SUCCEEDED,
        correlation_id=correlation_id,
        occurred_at=moment,
    )
    session.commit()
    return account_id


def account_for(session: Session, identifier: Identifier) -> uuid.UUID | None:
    """Return the account a phone number or an email address belongs to.

    :param session: The session to read through
    :param identifier: The number or address
    :return: The account's id, or None
    """
    # Annotated at the query site: a raw-SQL scalar is typed Any, and
    # letting that Any reach the return would silently weaken the
    # signature every caller relies on.
    account_id: uuid.UUID | None = session.execute(
        sa.text(f"SELECT id FROM account WHERE {identifier.column} = :value"),  # noqa: S608
        {"value": identifier.value},
    ).scalar_one_or_none()
    return account_id


def _record_attempt(
    session: Session,
    otp_request_id: uuid.UUID,
    moment: dt.datetime,
    succeeded: bool,
) -> None:
    """Record one attempt against one code.

    A row per attempt rather than a counter, so the audit log can answer
    "was this code attacked" rather than only "how many times".

    :param session: The session to write through
    :param otp_request_id: The code attempted against
    :param moment: When the attempt was made
    :param succeeded: Whether the code matched
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO verify_attempt "
            "(id, otp_request_id, attempted_at, succeeded) "
            "VALUES (:id, :otp_request_id, :attempted_at, :succeeded)"
        ),
        {
            "id": uuid.uuid4(),
            "otp_request_id": otp_request_id,
            "attempted_at": moment,
            "succeeded": succeeded,
        },
    )


def _audit_failure(
    session: Session,
    identifier: Identifier,
    correlation_id: str,
    moment: dt.datetime,
) -> None:
    """Write a ``VERIFY_FAILED`` row, carrying no destination and no code.

    :param session: The session to write through
    :param identifier: The destination, used only to resolve the account
    :param correlation_id: Ties the row to this request
    :param moment: When the failure happened
    :return: None
    """
    account_id = account_for(session, identifier)
    write_audit(
        session,
        account_id=account_id,
        event=AuthEvent.VERIFY_FAILED,
        correlation_id=correlation_id,
        occurred_at=moment,
    )


#: The machine value every refused code carries, whatever the cause.
#:
#: **One machine code, and a message per remedy.** The person is told what
#: to do next -- type it again with so many tries left, or ask for a new
#: code because this one expired or is spent -- which the sign-in design
#: shows and one identical message could not. That is safe only because
#: an unknown number keeps its code row too (see :func:`issue`), so every
#: answer is the same for a number with an account and one without
#: [BR2.7].
REFUSAL_CODE: Final = "OTP_NOT_VALID"
