"""The four result states, two of them derived [BR4.3].

**Three seats differing only in ``joined_on`` and whether a Mark row
exists must produce three different states from one read.** That is
BR4.3's own named assertion, and it is what distinguishes a derivation
from a default: an implementation returning ``not_entered`` for every
unmarked seat passes a two-seat test.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.marks.entry import record_mark
from app.marks.results import exam_results
from tests.marks.conftest import EXAM_DATE


def test_three_seats_differing_only_in_joined_on_give_three_states(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    marked = seat_factory(name="A marked")
    not_entered = seat_factory(name="B not entered")
    joined_after = seat_factory(
        name="C joined after", joined_on=EXAM_DATE + dt.timedelta(days=1)
    )

    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        enrollment_id=marked,
        result_state="marked",
        marks=72,
    )

    rows = {
        row.enrollment_id: row
        for row in exam_results(restricted_session, lens=teacher_lens, exam_id=exam)
    }

    assert rows[marked].result_state == "marked"
    assert rows[marked].marks == 72
    assert rows[not_entered].result_state == "not_entered", (
        "an unmarked seat the teacher simply has not reached was not "
        "reported as not_entered [AC4.1.4]"
    )
    assert rows[not_entered].marks is None
    assert rows[joined_after].result_state == "joined_after", (
        "a seat that joined after the exam was not distinguished from "
        "one the teacher has not marked: a student who joined in May "
        "showing as absent from an April exam reads as truancy "
        "[AC4.1.5]"
    )
    assert rows[joined_after].marks is None


def test_a_seat_joining_exactly_on_the_exam_date_sat_it(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    # The boundary. `joined_on > exam.date` is the rule, so joining ON
    # the day means the seat could have sat the exam and is
    # `not_entered` rather than `joined_after`.
    same_day = seat_factory(name="Joined on the day", joined_on=EXAM_DATE)

    rows = {
        row.enrollment_id: row
        for row in exam_results(restricted_session, lens=teacher_lens, exam_id=exam)
    }

    assert rows[same_day].result_state == "not_entered"


def test_an_absent_seat_is_not_a_zero(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    absent = seat_factory(name="Absent")
    zero = seat_factory(name="Scored zero")

    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        enrollment_id=absent,
        result_state="absent",
        marks=None,
    )
    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        enrollment_id=zero,
        result_state="marked",
        marks=0,
    )

    rows = {
        row.enrollment_id: row
        for row in exam_results(restricted_session, lens=teacher_lens, exam_id=exam)
    }

    assert (rows[absent].result_state, rows[absent].marks) == ("absent", None)
    assert (rows[zero].result_state, rows[zero].marks) == ("marked", 0)


def test_a_declined_seat_does_not_appear_in_the_results(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    declined = seat_factory(name="Declined")
    owner_session.execute(
        sa.text("UPDATE enrollment SET student_decision = 'declined' WHERE id = :id"),
        {"id": declined},
    )
    owner_session.commit()

    rows = exam_results(restricted_session, lens=teacher_lens, exam_id=exam)

    assert declined not in {row.enrollment_id for row in rows}


def test_a_seat_that_had_already_left_does_not_appear(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    gone = seat_factory(name="Left before")
    owner_session.execute(
        sa.text("UPDATE enrollment SET inactive_from = :d WHERE id = :id"),
        {"d": EXAM_DATE - dt.timedelta(days=30), "id": gone},
    )
    owner_session.commit()

    rows = exam_results(restricted_session, lens=teacher_lens, exam_id=exam)

    assert gone not in {row.enrollment_id for row in rows}


def test_a_correction_shows_only_the_live_value(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    # BR4.5: the live result is the ONE row with a null supersession
    # pointer. A read that followed every row would count the student
    # twice and the marksheet would then inflate the batch size.
    seat = seat_factory()
    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        enrollment_id=seat,
        result_state="marked",
        marks=55,
    )
    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        enrollment_id=seat,
        result_state="marked",
        marks=65,
    )

    rows = exam_results(restricted_session, lens=teacher_lens, exam_id=exam)

    assert len([row for row in rows if row.enrollment_id == seat]) == 1
    assert next(row for row in rows if row.enrollment_id == seat).marks == 65
