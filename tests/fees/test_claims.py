"""Submitting a payment claim [BR5.1, BR5.2].

A claim is an **assertion**, not a payment: there is no gateway, and the
system records what the claimant says and what the teacher decides
[FR6.10].

Two validation rules with opposite shapes, which is why both are tested:
zero and negative are **refused before the claim is recorded**, and an
amount **exceeding** the balance is **accepted**. Blocking an over-claim
at submission makes a genuine overpayment unreportable, leaving a phone
call as the only route -- the thing this feature exists to remove.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.errors import ValidationError
from app.fees.claims import submit_claim
from app.fees.ledger_writer import append_entry
from app.money import Money, MoneyValidationError
from tests.batches.conftest import TeacherFixture


def _charge(session: Session, seat: uuid.UUID, period: str, amount: str) -> None:
    """Append one charge entry.

    :param session: The session to write through
    :param seat: The enrollment
    :param period: The period
    :param amount: The amount, as a canonical string
    :return: None
    """
    append_entry(
        session,
        enrollment_id=seat,
        period=period,
        kind="charge",
        amount=Money(amount),
    )
    session.commit()


def test_a_claim_resolves_to_the_oldest_unpaid_cycle(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    # [BR5.1] With two unpaid cycles the stored period is the EARLIER
    # one, so the claimant and the teacher look at the same cycle.
    _charge(restricted_session, seat, "2027-01", "1000.00")
    _charge(restricted_session, seat, "2027-02", "1000.00")

    claim = submit_claim(
        restricted_session,
        enrollment_id=seat,
        submitted_by_account_id=account_factory(),
        claimed_amount=Money("1000.00"),
        channel="bKash",
        transaction_id="TX123",
    )

    assert claim.period == "2027-01"
    assert claim.status == "pending"


def test_a_claim_skips_a_settled_cycle_and_takes_the_next_owing(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    _charge(restricted_session, seat, "2027-01", "1000.00")
    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2027-01",
        kind="receipt",
        amount=Money("1000.00"),
    )
    restricted_session.commit()
    _charge(restricted_session, seat, "2027-02", "1000.00")

    claim = submit_claim(
        restricted_session,
        enrollment_id=seat,
        submitted_by_account_id=account_factory(),
        claimed_amount=Money("1000.00"),
        channel="Nagad",
    )

    assert claim.period == "2027-02"


def test_a_claim_with_no_open_cycle_is_refused_and_creates_none(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    # [BR5.1] Creating a cycle to receive a payment would bill the
    # student for a period that had not begun.
    with pytest.raises(ValidationError):
        submit_claim(
            restricted_session,
            enrollment_id=seat,
            submitted_by_account_id=account_factory(),
            claimed_amount=Money("500.00"),
            channel="cash",
        )
    restricted_session.rollback()

    cycles = restricted_session.execute(
        sa.text("SELECT count(*) FROM fee_cycle WHERE enrollment_id = :id"),
        {"id": seat},
    ).scalar_one()
    claims = restricted_session.execute(
        sa.text("SELECT count(*) FROM payment_claim WHERE enrollment_id = :id"),
        {"id": seat},
    ).scalar_one()
    assert cycles == 0
    assert claims == 0


def test_a_zero_claim_is_refused_before_it_is_recorded(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    _charge(restricted_session, seat, "2027-01", "1000.00")

    with pytest.raises(ValidationError):
        submit_claim(
            restricted_session,
            enrollment_id=seat,
            submitted_by_account_id=account_factory(),
            claimed_amount=Money("0.00"),
            channel="bKash",
        )
    restricted_session.rollback()

    recorded = restricted_session.execute(
        sa.text("SELECT count(*) FROM payment_claim WHERE enrollment_id = :id"),
        {"id": seat},
    ).scalar_one()
    assert recorded == 0


def test_a_negative_claim_is_refused(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    _charge(restricted_session, seat, "2027-01", "1000.00")

    # The wire type admits no sign at all, so a negative amount cannot
    # even be constructed from a request body. Both refusals are
    # acceptable; what is not is a negative claim reaching the table.
    with pytest.raises((ValidationError, MoneyValidationError)):
        submit_claim(
            restricted_session,
            enrollment_id=seat,
            submitted_by_account_id=account_factory(),
            claimed_amount=Money("-1.00"),
            channel="bKash",
        )
    restricted_session.rollback()


def test_an_over_claim_is_accepted_as_pending(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    # [BR5.2, AC6.1.7] 5000 against a 1000 balance is RECORDED. Money
    # may genuinely have been overpaid out of band and the teacher
    # decides at verification.
    _charge(restricted_session, seat, "2027-01", "1000.00")

    claim = submit_claim(
        restricted_session,
        enrollment_id=seat,
        submitted_by_account_id=account_factory(),
        claimed_amount=Money("5000.00"),
        channel="bKash",
    )

    assert claim.claimed_amount == Money("5000.00")
    assert claim.status == "pending"
    assert claim.period == "2027-01"


def test_the_transaction_reference_is_optional(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    # Nullable regardless of how OQ-1 is answered, which is what makes
    # this schema answer-agnostic.
    _charge(restricted_session, seat, "2027-01", "1000.00")

    claim = submit_claim(
        restricted_session,
        enrollment_id=seat,
        submitted_by_account_id=account_factory(),
        claimed_amount=Money("1000.00"),
        channel="cash",
        transaction_id=None,
    )

    assert claim.transaction_id is None
