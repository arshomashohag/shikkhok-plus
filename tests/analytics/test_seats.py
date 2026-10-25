"""The owned-seat set: two of D4's four clauses, and not the other two.

Written before ``app/analytics/seats.py`` existed. A wrong seat set
returns **another teacher's data**, which is an authorization error, and
the expected membership is tabulated upstream before any code -- so the
team's test-first predicate holds on both clauses [team.md Ordering].

**The predicate D4's roster uses has FOUR clauses and D5 shares TWO**
[entities.md § 4, BR1.2]: batch ownership and ``student_decision``. It
drops ``inactive_from`` -- a student who left owing money is exactly who
the dues view exists for -- and it drops ``joined_on`` too, because a
seat that joined after some session date can still owe money and a dues
view has no session date to compare against.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.analytics.seats import owned_seats
from tests.analytics.conftest import add_batch, lens_for, seat_with_ledger
from tests.batches.conftest import TeacherFixture


def test_only_this_owner_s_seats_are_returned(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    other_teacher: TeacherFixture,
) -> None:
    """A second teacher's seats never enter the set [BR2.5].

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: Teacher A
    :param other_teacher: Teacher B, whose seats must not appear
    :return: None
    """
    mine = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        entries=[("charge", "2027-01", "1000.00")],
    )
    theirs = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=other_teacher.batch_id,
        display_name="Karim",
        entries=[("charge", "2027-01", "1000.00")],
    )

    found = {
        seat.enrollment_id
        for seat in owned_seats(restricted_session, lens_for(teacher))
    }

    assert mine in found
    assert theirs not in found


def test_a_declined_seat_is_excluded_whatever_it_owes(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """``student_decision = 'declined'`` removes the seat [BR1.7].

    The seat **owes money**, deliberately. A declined seat with nothing
    outstanding is absent under BR1.3 as well, so it could not tell a
    correct implementation from one missing this clause.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    declined = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Mistyped number",
        entries=[("charge", "2027-01", "1200.00")],
        student_decision="declined",
    )

    found = {
        seat.enrollment_id
        for seat in owned_seats(restricted_session, lens_for(teacher))
    }

    assert declined not in found


def test_an_inactive_seat_is_still_in_the_set(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """No predicate on ``inactive_from`` at all [BR1.2].

    **The rule reusing D4's roster predicate breaks.** That predicate
    excludes a seat inactive before the session date -- correct there,
    and here it drops exactly the people most worth chasing.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    left = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Left mid-year",
        entries=[("charge", "2027-01", "1500.00")],
        inactive_from=dt.date(2027, 1, 15),
    )

    found = {
        seat.enrollment_id
        for seat in owned_seats(restricted_session, lens_for(teacher))
    }

    assert left in found, (
        "an inactive seat was dropped from the seat set: the dues query "
        "is carrying a predicate on inactive_from, which is D4's roster "
        "rule and not this one [BR1.2]"
    )


def test_a_seat_with_a_joined_on_date_is_not_filtered_by_it(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """No predicate on ``joined_on`` either [entities.md § 4].

    The fourth clause of D4's predicate, and the one most easily carried
    across unnoticed because it reads as harmless. A seat that joined
    recently can still owe money, and a dues view has no session date to
    compare a joining date against.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    from app.db.models import Enrollment

    seat = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Joined late",
        entries=[("charge", "2027-03", "800.00")],
    )
    record = owner_session.get(Enrollment, seat)
    assert record is not None
    record.joined_on = dt.date(2099, 1, 1)
    owner_session.commit()

    found = {
        seat.enrollment_id
        for seat in owned_seats(restricted_session, lens_for(teacher))
    }

    assert seat in found


def test_the_seat_set_spans_every_batch_the_teacher_owns(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """One join across all owned batches, not one batch [BR1.1].

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    second = add_batch(owner_session, teacher.owner_id, "Chemistry")
    first_seat = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="In physics",
        entries=[("charge", "2027-01", "1000.00")],
    )
    second_seat = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=second,
        display_name="In chemistry",
        entries=[("charge", "2027-01", "1000.00")],
    )

    seats = owned_seats(restricted_session, lens_for(teacher))
    found = {seat.enrollment_id for seat in seats}

    assert {first_seat, second_seat} <= found
    names = {seat.enrollment_id: seat.batch_name for seat in seats}
    assert names[first_seat] == "Physics"
    assert names[second_seat] == "Chemistry"


def test_the_seat_set_carries_the_teacher_recorded_name(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """``display_name`` is the teacher's record, never a profile field.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    seat = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Teacher-typed name",
        entries=[("charge", "2027-01", "500.00")],
    )

    rows = {
        row.enrollment_id: row
        for row in owned_seats(restricted_session, lens_for(teacher))
    }

    assert rows[seat].display_name == "Teacher-typed name"
