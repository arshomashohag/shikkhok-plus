"""Credit: granted on over-approval, applied at the next generation.

**The figure ADR-002's first correction attempt got wrong.** A 1000
charge with 200 credit applied leaves **800.00** outstanding -- that
attempt computed 1000, because the per-cycle form was missing its
`credit_applied` term. Every figure in this file was run through the
fold.

Three properties, each with a plausible wrong version:

* Credit belongs to the **enrollment**, not to a cycle [BR4.1]. Credit
  trapped in a closed period can never be spent, so an overpayment
  vanishes.
* The applied amount is **computed**, never supplied [BR4.4]. That is
  what makes over-application unrepresentable rather than refused.
* Credit is applied **after** the charge, in the same transaction
  [BR4.5]. Applying first computes ``min(available, 0)`` and spends
  nothing, so the credit is never used at all.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.fees.balances import derive_for_enrollment
from app.fees.generation import generate_due_cycles
from app.fees.ledger_writer import append_entry, apply_available_credit
from app.money import Money
from tests.batches.conftest import TeacherFixture
from tests.fees.conftest import set_joined_on

IN_FEBRUARY = dt.date(2027, 2, 20)
IN_MARCH = dt.date(2027, 3, 20)


def _grant(session: Session, seat: uuid.UUID, amount: Money, period: str) -> None:
    """Record a credit grant against a seat.

    :param session: The session to write through
    :param seat: The enrollment
    :param amount: The credit granted
    :param period: The period the grant was recorded in
    :return: None
    """
    append_entry(
        session,
        enrollment_id=seat,
        period=period,
        kind="credit_grant",
        amount=amount,
    )
    session.commit()


def test_over_approval_becomes_credit_and_never_a_negative_balance(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # Computed: a 1000 charge approved at 1200 gives outstanding 0.00
    # and credit 200.00, with the identity at -200 on both sides. Cash
    # in is receipt + credit_grant, which is exactly where ADR-002's
    # first correction attempt failed.
    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2027-01",
        kind="charge",
        amount=Money("1000.00"),
    )
    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2027-01",
        kind="receipt",
        amount=Money("1000.00"),
    )
    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2027-01",
        kind="credit_grant",
        amount=Money("200.00"),
    )
    restricted_session.commit()

    derived = derive_for_enrollment(restricted_session, seat)

    assert derived.total_outstanding == Money("0.00")
    assert derived.available_credit == Money("200.00")


def test_credit_granted_in_one_period_is_spent_in_another(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # [BR4.1] Credit belongs to the ENROLLMENT. Credit trapped in a
    # closed period can never be spent and the overpayment vanishes.
    _grant(restricted_session, seat, Money("200.00"), "2027-01")

    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        kind="charge",
        amount=Money("1000.00"),
    )
    apply_available_credit(restricted_session, enrollment_id=seat, period="2027-02")
    restricted_session.commit()

    derived = derive_for_enrollment(restricted_session, seat)

    # THE FIGURE: 800, not 1000.
    assert derived.per_cycle["2027-02"] == Money("800.00")
    assert derived.available_credit == Money("0.00")


def test_credit_exceeding_the_charge_applies_only_what_is_owed(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # [BR4.4] 1500.00 held against a 1000.00 charge applies 1000.00 and
    # leaves 500.00 available. An implementation that applied the whole
    # credit would drive the balance negative, which the invariant
    # forbids.
    _grant(restricted_session, seat, Money("1500.00"), "2027-01")

    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        kind="charge",
        amount=Money("1000.00"),
    )
    applied = apply_available_credit(
        restricted_session, enrollment_id=seat, period="2027-02"
    )
    restricted_session.commit()

    assert applied is not None
    assert applied.amount == Money("1000.00")

    derived = derive_for_enrollment(restricted_session, seat)
    assert derived.per_cycle["2027-02"] == Money("0.00")
    assert derived.available_credit == Money("500.00")


def test_generation_applies_available_credit_in_the_same_transaction(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # [BR4.3, BR4.5] A student who overpaid must not be billed in full
    # the next month and have to ask for their own money back. The
    # batch default is 1500.00, so 200.00 credit leaves 1300.00.
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))
    _grant(restricted_session, seat, Money("200.00"), "2027-01")

    generate_due_cycles(restricted_session, today=IN_FEBRUARY)

    derived = derive_for_enrollment(restricted_session, seat)

    assert derived.per_cycle["2027-02"] == Money("1300.00")
    assert derived.available_credit == Money("0.00")

    kinds = [
        row[0]
        for row in restricted_session.execute(
            sa.text(
                "SELECT kind FROM ledger_entry WHERE enrollment_id = :id "
                "AND period = '2027-02' ORDER BY created_at"
            ),
            {"id": seat},
        )
    ]
    # The charge FIRST, then the application. Reversed, the computation
    # is min(available, 0) and nothing is spent.
    assert kinds == ["charge", "credit_apply"]


def test_credit_larger_than_one_period_carries_into_the_next_generation(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # 2000.00 credit against two 1500.00 months: the first is fully
    # covered, the second takes the remaining 500.00 and owes 1000.00.
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))
    _grant(restricted_session, seat, Money("2000.00"), "2027-01")

    generate_due_cycles(restricted_session, today=IN_FEBRUARY)
    generate_due_cycles(restricted_session, today=IN_MARCH)

    derived = derive_for_enrollment(restricted_session, seat)

    assert derived.per_cycle["2027-02"] == Money("0.00")
    assert derived.per_cycle["2027-03"] == Money("1000.00")
    assert derived.available_credit == Money("0.00")
    assert derived.total_outstanding == Money("1000.00")


def test_no_credit_available_appends_no_entry(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # A zero-amount credit_apply row would be noise on an append-only
    # ledger and would make "was credit used" unanswerable by presence.
    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        kind="charge",
        amount=Money("1000.00"),
    )
    applied = apply_available_credit(
        restricted_session, enrollment_id=seat, period="2027-02"
    )
    restricted_session.commit()

    assert applied is None
    kinds = [
        row[0]
        for row in restricted_session.execute(
            sa.text("SELECT kind FROM ledger_entry WHERE enrollment_id = :id"),
            {"id": seat},
        )
    ]
    assert kinds == ["charge"]


def test_credit_against_a_settled_period_applies_nothing(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # Nothing is owed, so min(available, owed) is zero and the credit
    # stays available for a later period.
    _grant(restricted_session, seat, Money("500.00"), "2027-01")
    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        kind="charge",
        amount=Money("300.00"),
    )
    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        kind="receipt",
        amount=Money("300.00"),
    )
    restricted_session.commit()

    applied = apply_available_credit(
        restricted_session, enrollment_id=seat, period="2027-02"
    )
    restricted_session.commit()

    assert applied is None
    assert derive_for_enrollment(restricted_session, seat).available_credit == Money(
        "500.00"
    )
