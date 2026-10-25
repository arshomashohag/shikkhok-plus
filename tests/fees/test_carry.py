"""A carry is a PAIR, committed together [BR3.1, BR3.2].

**The figure team memory warns about.** Carrying 1000 into a second 1000
charge reads **2000.00** owed two-sided and **3000.00** one-sided. An
earlier form of that rule paired 2500 against a true 1500, which
reproduces under no implementation -- the pair mixed two cases and made
the rule's own example unfalsifiable. Every figure here was run through
the fold rather than read off a document.

``app/money/_ledger.py`` already returns the pair from one call, so a
one-sided carry is unrepresentable in the *arithmetic*. What this file
tests is the PERSISTENCE counterpart: both rows committed together,
which is a transaction property the fold cannot enforce.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.fees.balances import derive_for_enrollment
from app.fees.ledger_writer import append_carry_pair, append_entry
from app.money import Money, MoneyValidationError
from tests.batches.conftest import TeacherFixture

IN_FEBRUARY = dt.date(2027, 2, 20)


def _kinds(session: Session, enrollment_id: uuid.UUID) -> list[tuple[str, str, Money]]:
    """List a seat's entries as (period, kind, amount).

    :param session: The session to read through
    :param enrollment_id: The seat
    :return: The entries, ordered by period then kind
    """
    return [
        (row[0], row[1], Money(row[2]))
        for row in session.execute(
            sa.text(
                "SELECT period, kind, amount FROM ledger_entry "
                "WHERE enrollment_id = :id ORDER BY period, kind"
            ),
            {"id": enrollment_id},
        )
    ]


def _charged_1000_in_january(
    session: Session, owner_session: Session, seat: uuid.UUID
) -> None:
    """Arrange a single 1000.00 January charge.

    :param session: The session to write through
    :param owner_session: An arranging session
    :param seat: The enrollment
    :return: None
    """
    append_entry(
        session,
        enrollment_id=seat,
        period="2027-01",
        kind="charge",
        amount=Money("1000.00"),
    )
    session.commit()


def test_a_carry_writes_both_halves(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    _charged_1000_in_january(restricted_session, owner_session, seat)

    append_carry_pair(
        restricted_session,
        enrollment_id=seat,
        amount=Money("1000.00"),
        origin="2027-01",
        receiver="2027-02",
    )
    restricted_session.commit()

    assert sorted(_kinds(restricted_session, seat)) == sorted(
        [
            ("2027-01", "charge", Money("1000.00")),
            ("2027-01", "carried_out", Money("1000.00")),
            ("2027-02", "carry_forward", Money("1000.00")),
        ]
    )


def test_carrying_1000_into_a_second_1000_charge_reads_2000_not_3000(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # THE SEPARATING CASE. A one-sided carry -- writing only the
    # carry_forward and leaving January still owing -- gives 3000.00,
    # and the gap grows with every period.
    _charged_1000_in_january(restricted_session, owner_session, seat)

    append_carry_pair(
        restricted_session,
        enrollment_id=seat,
        amount=Money("1000.00"),
        origin="2027-01",
        receiver="2027-02",
    )
    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        kind="charge",
        amount=Money("1000.00"),
    )
    restricted_session.commit()

    derived = derive_for_enrollment(restricted_session, seat)

    assert derived.total_outstanding == Money("2000.00")
    assert derived.per_cycle["2027-01"] == Money("0.00")
    assert derived.per_cycle["2027-02"] == Money("2000.00")


def test_the_two_sides_of_every_carry_sum_equal(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # The enrollment-level structural check: sum(carry_forward) ==
    # sum(carried_out). A one-sided carry fails it immediately.
    _charged_1000_in_january(restricted_session, owner_session, seat)
    append_carry_pair(
        restricted_session,
        enrollment_id=seat,
        amount=Money("400.00"),
        origin="2027-01",
        receiver="2027-02",
    )
    append_carry_pair(
        restricted_session,
        enrollment_id=seat,
        amount=Money("300.00"),
        origin="2027-01",
        receiver="2027-03",
    )
    restricted_session.commit()

    derived = derive_for_enrollment(restricted_session, seat)
    assert derived.total_carry_forward == derived.total_carried_out
    assert derived.total_carry_forward == Money("700.00")


def test_a_carry_exceeding_the_origins_balance_is_refused(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # [BR3.2] Carrying 1200 out of a period owing 1000 manufactures
    # debt: the receiver is charged in full while the origin is
    # relieved only to its zero floor, and the surplus appears from
    # nowhere.
    _charged_1000_in_january(restricted_session, owner_session, seat)

    with pytest.raises(MoneyValidationError):
        append_carry_pair(
            restricted_session,
            enrollment_id=seat,
            amount=Money("1200.00"),
            origin="2027-01",
            receiver="2027-02",
        )


def test_a_refused_carry_writes_neither_half(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # The refusal must happen BEFORE either row is added, or a rolled
    # back half still leaves the session dirty for the next flush.
    _charged_1000_in_january(restricted_session, owner_session, seat)
    before = _kinds(restricted_session, seat)

    with pytest.raises(MoneyValidationError):
        append_carry_pair(
            restricted_session,
            enrollment_id=seat,
            amount=Money("1200.00"),
            origin="2027-01",
            receiver="2027-02",
        )
    restricted_session.rollback()

    assert _kinds(restricted_session, seat) == before


def test_a_multi_period_carry_chain_totals_correctly(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # Computed: Jan 1000 carried to Feb; Feb 1000 charged plus 1000
    # carried in, all carried to Mar; Mar 1000 charged. Outstanding
    # 3000.00.
    _charged_1000_in_january(restricted_session, owner_session, seat)
    append_carry_pair(
        restricted_session,
        enrollment_id=seat,
        amount=Money("1000.00"),
        origin="2027-01",
        receiver="2027-02",
    )
    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        kind="charge",
        amount=Money("1000.00"),
    )
    restricted_session.commit()

    append_carry_pair(
        restricted_session,
        enrollment_id=seat,
        amount=Money("2000.00"),
        origin="2027-02",
        receiver="2027-03",
    )
    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2027-03",
        kind="charge",
        amount=Money("1000.00"),
    )
    restricted_session.commit()

    derived = derive_for_enrollment(restricted_session, seat)
    assert derived.total_outstanding == Money("3000.00")
    assert derived.per_cycle["2027-03"] == Money("3000.00")
