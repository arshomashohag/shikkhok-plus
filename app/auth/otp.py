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
the unknown branch performs an **equivalent write and rolls it back**,
inside the same transaction shape.

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
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.audit.log import AuthEvent, write_audit
from app.auth.hashing import generate_code, hash_otp, verify_otp
from app.errors import ValidationError

__all__ = [
    "ATTEMPT_CEILING",
    "CODE_LIFETIME",
    "DELETION_PURPOSE",
    "OTP_PURPOSE",
    "IssuedCode",
    "issue",
    "verify",
]

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


@dataclass(frozen=True, slots=True)
class IssuedCode:
    """What :func:`issue` hands back to the caller.

    ``code`` is the value to transmit and is **never** persisted or
    logged. ``account_exists`` is for the caller's audit row only and must
    not reach the response, or it becomes the oracle in a new place.

    :ivar code: The transmitted code
    :ivar account_exists: Whether the number had an account
    """

    code: str
    account_exists: bool


def issue(
    session: Session,
    phone: str,
    correlation_id: str,
    *,
    purpose: str,
    now: dt.datetime | None = None,
) -> IssuedCode:
    """Issue a code, doing equivalent work whether or not the number exists.

    ``purpose`` is **keyword-only and has no default**, so a third
    consumer cannot inherit sign-in's purpose by saying nothing. The
    keyword form is what stops it being supplied positionally into
    ``correlation_id``'s place by a caller reordering arguments.

    :param session: The session to write through
    :param phone: The number to issue for
    :param correlation_id: Ties the audit row to this request
    :param purpose: What this code may be spent on
    :param now: The moment of issue, or None for the clock
    :return: The code to transmit and whether an account existed
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    code = generate_code()

    account_id = session.execute(
        sa.text("SELECT id FROM account WHERE phone = :phone"),
        {"phone": phone},
    ).scalar_one_or_none()

    # BOTH BRANCHES HASH, AND BOTH BRANCHES WRITE. The hash is the
    # smaller asymmetry; the write is the one that dominates.
    digest = hash_otp(code, phone)
    row_id = uuid.uuid4()
    parameters = {
        "id": row_id,
        "phone": phone,
        "otp_hash": digest,
        "purpose": purpose,
        "issued_at": moment,
        "expires_at": moment + CODE_LIFETIME,
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
            "(id, phone, otp_hash, purpose, issued_at, expires_at) "
            "VALUES (:id, :phone, :otp_hash, :purpose, :issued_at, "
            ":expires_at)"
        ),
        parameters,
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

    return IssuedCode(code=code, account_exists=account_id is not None)


def verify(
    session: Session,
    phone: str,
    code: str,
    correlation_id: str,
    *,
    purpose: str,
    now: dt.datetime | None = None,
) -> uuid.UUID:
    """Verify a code of one purpose and return the account it authenticates.

    The expiry, the single-use rule and the attempt ceiling share one
    transaction boundary, which is why they are one function rather than
    three guards: ``consumed_at`` is set **in the same transaction as the
    check that read it**, so a concurrent second verify cannot slip
    between them [BR2.3].

    :param session: The session to work through
    :param phone: The number being verified
    :param code: The presented code
    :param correlation_id: Ties the audit row to this request
    :param purpose: What the presented code must have been issued for
    :param now: The moment of verification, or None for the clock
    :return: The authenticated account's id
    :raises ValidationError: The code is wrong, expired, used, dead, or
        was issued for a different purpose
    """
    moment = now or dt.datetime.now(tz=dt.UTC)

    # FOR UPDATE is what makes the check-then-write atomic. Without it,
    # two concurrent verifies both read an unconsumed row.
    #
    # **`purpose` is in the WHERE, beside `phone`, and that placement is
    # the design rather than a style choice** [DESIGN-1]. This query
    # returns the LATEST row, so checking the purpose after fetching
    # means a sign-in code issued after a deletion code SHADOWS it: the
    # user's valid deletion code is refused, with `_refused()`, which
    # discloses nothing -- so they retry, spend ceiling budget, and
    # conclude the feature is broken.
    #
    # The order is plausible in real use, not contrived: a person
    # requests a deletion code, is unsure, signs in to look at their
    # data first, then returns to the deletion page.
    #
    # Filtering here gives each purpose its own most-recent code, which
    # is what the single-use rule below is then applied to.
    row = session.execute(
        sa.text(
            "SELECT id, otp_hash, expires_at, consumed_at FROM otp_request "
            "WHERE phone = :phone AND purpose = :purpose "
            "ORDER BY issued_at DESC LIMIT 1 "
            "FOR UPDATE"
        ),
        {"phone": phone, "purpose": purpose},
    ).one_or_none()

    if row is None:
        raise ValidationError(code=REFUSAL_CODE, message_key="auth.otp.not_valid")

    attempts = session.execute(
        sa.text("SELECT count(*) FROM verify_attempt WHERE otp_request_id = :id"),
        {"id": row.id},
    ).scalar_one()

    expired = moment > row.expires_at
    consumed = row.consumed_at is not None
    exhausted = attempts >= ATTEMPT_CEILING

    if expired or consumed or exhausted:
        _record_attempt(session, row.id, moment, succeeded=False)
        _audit_failure(session, phone, correlation_id, moment)
        session.commit()
        # Expiry is named because its remedy is specific: the code was
        # right and too slow. A used or dead code is "ask for a new one".
        if expired and not consumed and not exhausted:
            raise ValidationError(code=REFUSAL_CODE, message_key="auth.otp.expired")
        raise ValidationError(code=REFUSAL_CODE, message_key="auth.otp.not_valid")

    matched = verify_otp(code, phone, row.otp_hash)
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
        _audit_failure(session, phone, correlation_id, moment)
        session.commit()
        if remaining <= 0:
            raise ValidationError(
                code=REFUSAL_CODE, message_key="auth.otp.no_tries_left"
            )
        raise ValidationError(
            code=REFUSAL_CODE,
            message_key="auth.otp.wrong",
            details={"attempts_left": str(remaining)},
        )

    session.execute(
        sa.text("UPDATE otp_request SET consumed_at = :now WHERE id = :id"),
        {"now": moment, "id": row.id},
    )

    # Annotated at the query site: a raw-SQL scalar is typed Any, and
    # letting that Any reach the return would silently weaken the
    # signature every caller relies on.
    account_id: uuid.UUID | None = session.execute(
        sa.text("SELECT id FROM account WHERE phone = :phone"),
        {"phone": phone},
    ).scalar_one_or_none()

    if account_id is None:
        session.commit()
        raise ValidationError(code=REFUSAL_CODE, message_key="auth.otp.not_valid")

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
    session: Session, phone: str, correlation_id: str, moment: dt.datetime
) -> None:
    """Write a ``VERIFY_FAILED`` row, carrying no number and no code.

    :param session: The session to write through
    :param phone: The number, used only to resolve the account id
    :param correlation_id: Ties the row to this request
    :param moment: When the failure happened
    :return: None
    """
    account_id = session.execute(
        sa.text("SELECT id FROM account WHERE phone = :phone"),
        {"phone": phone},
    ).scalar_one_or_none()
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
