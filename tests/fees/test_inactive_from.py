"""`inactive_from` generates the containing period IN FULL [BR1.5].

Named in the affirmed testing posture as one of the rules that **fails
quietly**: it must stop future fee cycles, leave existing dues standing,
and leave the student active in other batches, and all three are money
consequences that nothing surfaces if they are wrong.

**A partial month is never prorated.** The cycle stands in full and the
teacher adjusts it through the charge-adjustment path if they choose
[FR5.6]. The boundary table in the functional spec is computed and is
reproduced here as parameters.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.fees.generation import generate_due_cycles
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll
from tests.fees.conftest import set_inactive_from, set_joined_on

#: Far enough ahead that both 2027-02 and 2027-03 are candidates.
IN_MARCH = dt.date(2027, 3, 20)


def _periods(session: Session, enrollment_id: uuid.UUID) -> list[str]:
    """List the periods a seat has cycles for.

    :param session: The session to read through
    :param enrollment_id: The seat
    :return: The period keys, oldest first
    """
    return [
        row[0]
        for row in session.execute(
            sa.text(
                "SELECT period FROM fee_cycle WHERE enrollment_id = :id ORDER BY period"
            ),
            {"id": enrollment_id},
        )
    ]


@pytest.mark.parametrize(
    ("inactive_from", "expected"),
    [
        # The date falls inside February: February generates IN FULL
        # and March does not.
        (dt.date(2027, 2, 1), ["2027-02"]),
        (dt.date(2027, 2, 15), ["2027-02"]),
        (dt.date(2027, 2, 28), ["2027-02"]),
        # The date falls in January, so February begins strictly after
        # it and does not generate.
        (dt.date(2027, 1, 31), ["2027-01"]),
    ],
)
def test_the_period_containing_the_date_generates_and_the_next_does_not(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    inactive_from: dt.date,
    expected: list[str],
) -> None:
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 1, 1))
    set_inactive_from(owner_session, enrollment_id=seat, when=inactive_from)

    generate_due_cycles(restricted_session, today=IN_MARCH)

    # Every period from joining through the containing one, and nothing
    # after it.
    periods = _periods(restricted_session, seat)
    assert periods[-1] == expected[-1]
    assert "2027-03" not in periods


def test_the_containing_period_is_charged_in_full_not_prorated(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # A seat leaving on the 15th of a 28-day month is charged the whole
    # 1500.00, not a fraction of it [FR5.6].
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))
    set_inactive_from(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 15))

    generate_due_cycles(restricted_session, today=IN_MARCH)

    charged = Money(
        restricted_session.execute(
            sa.text(
                "SELECT coalesce(sum(amount), 0) FROM ledger_entry "
                "WHERE enrollment_id = :id AND kind = 'charge'"
            ),
            {"id": seat},
        ).scalar_one()
    )
    assert charged == Money("1500.00")


def test_an_existing_due_stands_after_the_seat_goes_inactive(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # The rule stops FUTURE cycles; it does not clear what is owed.
    # D5's cross-batch dues query depends on exactly this -- a student
    # who left owing money still appears -- so a clearing
    # implementation would silently empty that view.
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 1, 1))
    generate_due_cycles(restricted_session, today=dt.date(2027, 1, 20))

    set_inactive_from(owner_session, enrollment_id=seat, when=dt.date(2027, 1, 31))
    generate_due_cycles(restricted_session, today=IN_MARCH)

    assert _periods(restricted_session, seat) == ["2027-01"]
    outstanding = Money(
        restricted_session.execute(
            sa.text(
                "SELECT coalesce(sum(amount), 0) FROM ledger_entry "
                "WHERE enrollment_id = :id AND kind = 'charge'"
            ),
            {"id": seat},
        ).scalar_one()
    )
    assert outstanding == Money("1500.00")


def test_going_inactive_in_one_batch_leaves_another_seat_generating(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    # The third consequence the posture names: `inactive_from` is a
    # property of the SEAT, so a student who left one batch keeps
    # generating in another.
    from tests.batches.conftest import make_teacher

    other = make_teacher(owner_session, name="Chemistry")
    second_seat = enroll(
        owner_session,
        batch_id=other.batch_id,
        display_name="Rahim (chemistry)",
        student_decision="accepted",
        guardian_decision="pending",
    )
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))
    set_joined_on(owner_session, enrollment_id=second_seat, when=dt.date(2027, 2, 1))
    set_inactive_from(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 10))

    generate_due_cycles(restricted_session, today=IN_MARCH)

    assert _periods(restricted_session, seat) == ["2027-02"]
    assert _periods(restricted_session, second_seat) == ["2027-02", "2027-03"]


def test_an_unset_inactive_from_generates_every_period(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 1, 1))
    set_inactive_from(owner_session, enrollment_id=seat, when=None)

    generate_due_cycles(restricted_session, today=IN_MARCH)

    assert _periods(restricted_session, seat) == ["2027-01", "2027-02", "2027-03"]
