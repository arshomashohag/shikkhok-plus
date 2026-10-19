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
    "OTP_PURPOSE",
    "IssuedCode",
    "issue",
    "verify",
]

#: A code expires five minutes after issue [BR2.3].
CODE_LIFETIME: Final = dt.timedelta(minutes=5)

#: A code dies after five failed attempts; the 6th is refused [BR2.3].
ATTEMPT_CEILING: Final = 5

#: Required, with exactly one V1 value. A DEFAULT would let a second
#: consumer arrive without anyone choosing its ceiling, which is the one
#: control protecting the project's wallet.
OTP_PURPOSE: Final = "otp"


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
    now: dt.datetime | None = None,
) -> IssuedCode:
    """Issue a code, doing equivalent work whether or not the number exists.

    :param session: The session to write through
    :param phone: The number to issue for
    :param correlation_id: Ties the audit row to this request
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
        "purpose": OTP_PURPOSE,
        "issued_at": moment,
        "expires_at": moment + CODE_LIFETIME,
    }

    savepoint = session.begin_nested()
    session.execute(
        sa.text(
            "INSERT INTO otp_request "
            "(id, phone, otp_hash, purpose, issued_at, expires_at) "
            "VALUES (:id, :phone, :otp_hash, :purpose, :issued_at, "
            ":expires_at)"
        ),
        parameters,
    )
    if account_id is None:
        # The equivalent write, rolled back. The statements issued are
        # identical to the known branch's; only the outcome differs.
        savepoint.rollback()
    else:
        savepoint.commit()

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
    now: dt.datetime | None = None,
) -> uuid.UUID:
    """Verify a code and return the account it authenticates.

    The expiry, the single-use rule and the attempt ceiling share one
    transaction boundary, which is why they are one function rather than
    three guards: ``consumed_at`` is set **in the same transaction as the
    check that read it**, so a concurrent second verify cannot slip
    between them [BR2.3].

    :param session: The session to work through
    :param phone: The number being verified
    :param code: The presented code
    :param correlation_id: Ties the audit row to this request
    :param now: The moment of verification, or None for the clock
    :return: The authenticated account's id
    :raises ValidationError: The code is wrong, expired, used or dead
    """
    moment = now or dt.datetime.now(tz=dt.UTC)

    # FOR UPDATE is what makes the check-then-write atomic. Without it,
    # two concurrent verifies both read an unconsumed row.
    row = session.execute(
        sa.text(
            "SELECT id, otp_hash, expires_at, consumed_at FROM otp_request "
            "WHERE phone = :phone ORDER BY issued_at DESC LIMIT 1 "
            "FOR UPDATE"
        ),
        {"phone": phone},
    ).one_or_none()

    if row is None:
        raise _refused()

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
        raise _refused()

    matched = verify_otp(code, phone, row.otp_hash)
    _record_attempt(session, row.id, moment, succeeded=matched)

    if not matched:
        # THE CODE DIES at the ceiling, not merely the attempt. An
        # implementation that counts without invalidating passes the
        # confirmatory half and leaves brute force open.
        if attempts + 1 >= ATTEMPT_CEILING:
            session.execute(
                sa.text("UPDATE otp_request SET consumed_at = :now WHERE id = :id"),
                {"now": moment, "id": row.id},
            )
        _audit_failure(session, phone, correlation_id, moment)
        session.commit()
        raise _refused()

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
        raise _refused()

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


def _refused() -> ValidationError:
    """Build the one refusal every failed verify returns.

    **One message for every cause.** Distinguishing "expired" from
    "wrong" from "too many attempts" tells an attacker which of their
    assumptions was right, and tells a legitimate user nothing they can
    act on differently -- the remedy is "request a new code" in all
    three cases.

    :return: The error to raise
    """
    return ValidationError(
        code="OTP_NOT_VALID",
        message_key="auth.otp.not_valid",
    )
