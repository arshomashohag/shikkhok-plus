"""Exam creation, editing and listing [BR4.1].

**The subject-belongs-to-batch check is an authorization boundary, not
a validation nicety** [§ 2.4]: a ``batch_subject_id`` from another
teacher's batch would attach an exam across the ownership boundary,
and because it is enforced in the write path rather than by a foreign
key, it is a check somebody can omit.

**Lowering a total below a mark already recorded is refused**, and
that case is this module's own addition -- the bound spans the same
foreign key in the other direction, so a total edited downward would
leave a stored mark above its own denominator and every percentage
downstream computing over 100%.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import BatchSubject
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.marks.entry import record_mark
from app.marks.exams import create_exam, list_exams, update_exam
from app.marks.results import list_exam_progress
from tests.batches.conftest import TeacherFixture, make_teacher
from tests.marks.conftest import EXAM_DATE, TOTAL_MARKS


def test_an_exam_is_created_with_its_subject_name(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    subject: uuid.UUID,
) -> None:
    row = create_exam(
        restricted_session,
        lens=teacher_lens,
        batch_id=teacher.batch_id,
        batch_subject_id=subject,
        title="April test",
        date=EXAM_DATE,
        total_marks=TOTAL_MARKS,
    )

    assert row.title == "April test"
    assert row.total_marks == TOTAL_MARKS
    assert row.subject_name == "Physics"


def test_a_subject_from_another_teachers_batch_is_refused(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
) -> None:
    # The refusal is NOT_AVAILABLE rather than descriptive: the
    # subject id is an unreachable resource and naming it as wrong is
    # the oracle [BR4.1].
    other = make_teacher(owner_session, name="Chemistry")
    foreign = BatchSubject(batch_id=other.batch_id, name="Chemistry")
    owner_session.add(foreign)
    owner_session.commit()

    with pytest.raises(AuthorizationError) as refusal:
        create_exam(
            restricted_session,
            lens=teacher_lens,
            batch_id=teacher.batch_id,
            batch_subject_id=foreign.id,
            title="Smuggled",
            date=EXAM_DATE,
            total_marks=TOTAL_MARKS,
        )

    assert refusal.value.code == "NOT_AVAILABLE"


def test_a_total_below_one_is_refused(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    subject: uuid.UUID,
) -> None:
    # A total of zero makes every percentage undefined and every band
    # degenerate, which is why the database carries the same CHECK.
    with pytest.raises(ValidationError) as refusal:
        create_exam(
            restricted_session,
            lens=teacher_lens,
            batch_id=teacher.batch_id,
            batch_subject_id=subject,
            title="Zero total",
            date=EXAM_DATE,
            total_marks=0,
        )

    assert refusal.value.code == "EXAM_TOTAL_INVALID"


def test_an_exam_cannot_be_created_on_an_inactive_batch(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    subject: uuid.UUID,
) -> None:
    owner_session.execute(
        sa.text("UPDATE batch SET active = false WHERE id = :id"),
        {"id": teacher.batch_id},
    )
    owner_session.commit()

    with pytest.raises(ConflictError) as refusal:
        create_exam(
            restricted_session,
            lens=teacher_lens,
            batch_id=teacher.batch_id,
            batch_subject_id=subject,
            title="Too late",
            date=EXAM_DATE,
            total_marks=TOTAL_MARKS,
        )

    assert refusal.value.code == "BATCH_INACTIVE"


def test_another_teacher_cannot_create_on_this_batch(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
) -> None:
    other = make_teacher(owner_session, name="Chemistry")

    with pytest.raises(AuthorizationError) as refusal:
        create_exam(
            restricted_session,
            lens=TeacherLens(account_id=other.account_id, owner_id=other.owner_id),
            batch_id=teacher.batch_id,
            batch_subject_id=subject,
            title="Not mine",
            date=EXAM_DATE,
            total_marks=TOTAL_MARKS,
        )

    assert refusal.value.code == "NOT_AVAILABLE"


def test_an_exam_is_edited_in_place(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
) -> None:
    updated = update_exam(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        title="Renamed",
        date=EXAM_DATE + dt.timedelta(days=1),
        total_marks=50,
    )

    assert updated.exam_id == exam
    assert updated.title == "Renamed"
    assert updated.total_marks == 50


def test_lowering_the_total_below_a_recorded_mark_is_refused(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    # **This module's own addition.** The `marks <= total_marks` bound
    # spans the foreign key in BOTH directions, so a total edited
    # downward would leave a stored mark above its own denominator --
    # unenterable by the write path that guards the other direction,
    # and over 100% in every percentage downstream.
    seat = seat_factory()
    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        enrollment_id=seat,
        result_state="marked",
        marks=90,
    )

    with pytest.raises(ConflictError) as refusal:
        update_exam(
            restricted_session,
            lens=teacher_lens,
            exam_id=exam,
            title="April test",
            date=EXAM_DATE,
            total_marks=50,
        )

    assert refusal.value.code == "EXAM_TOTAL_BELOW_RECORDED_MARK"


def test_lowering_the_total_above_every_recorded_mark_is_allowed(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    # The positive twin: a correction to the total is legitimate while
    # it stays at or above what was recorded.
    seat = seat_factory()
    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        enrollment_id=seat,
        result_state="marked",
        marks=40,
    )

    updated = update_exam(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        title="April test",
        date=EXAM_DATE,
        total_marks=40,
    )

    assert updated.total_marks == 40


def test_a_superseded_mark_does_not_block_lowering_the_total(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    # Only the LIVE row counts. A correction from 90 down to 30 must
    # leave the total editable to 50, or the supersession chain would
    # make every past mistake permanent.
    seat = seat_factory()
    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        enrollment_id=seat,
        result_state="marked",
        marks=90,
    )
    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        enrollment_id=seat,
        result_state="marked",
        marks=30,
    )

    updated = update_exam(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        title="April test",
        date=EXAM_DATE,
        total_marks=50,
    )

    assert updated.total_marks == 50


def test_exams_are_listed_oldest_first(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    subject: uuid.UUID,
) -> None:
    # Created out of order so an implementation relying on insertion
    # order fails.
    for offset in (30, 0, 60):
        create_exam(
            restricted_session,
            lens=teacher_lens,
            batch_id=teacher.batch_id,
            batch_subject_id=subject,
            title=f"Test {offset}",
            date=EXAM_DATE + dt.timedelta(days=offset),
            total_marks=TOTAL_MARKS,
        )

    rows = list_exams(restricted_session, lens=teacher_lens, batch_id=teacher.batch_id)

    assert [row.date for row in rows] == sorted(row.date for row in rows)
    assert [row.title for row in rows] == ["Test 0", "Test 30", "Test 60"]


def test_another_teacher_cannot_list_this_batchs_exams(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    exam: uuid.UUID,
) -> None:
    other = make_teacher(owner_session, name="Chemistry")

    with pytest.raises(AuthorizationError) as refusal:
        list_exams(
            restricted_session,
            lens=TeacherLens(account_id=other.account_id, owner_id=other.owner_id),
            batch_id=teacher.batch_id,
        )

    assert refusal.value.code == "NOT_AVAILABLE"


def test_another_teacher_cannot_edit_this_exam(
    owner_session: DbSession,
    restricted_session: DbSession,
    exam: uuid.UUID,
) -> None:
    other = make_teacher(owner_session, name="Chemistry")

    with pytest.raises(AuthorizationError) as refusal:
        update_exam(
            restricted_session,
            lens=TeacherLens(account_id=other.account_id, owner_id=other.owner_id),
            exam_id=exam,
            title="Hijacked",
            date=EXAM_DATE,
            total_marks=TOTAL_MARKS,
        )

    assert refusal.value.code == "NOT_AVAILABLE"


def test_the_list_counts_entered_results_against_expected_ones(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    teacher: TeacherFixture,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    """The exam list's "entered 2 of 3", counted by the server.

    A mark and an absence are both entered; a seat not yet reached is
    expected and not entered; a seat that joined after the exam could
    not have sat it and is in neither count.

    :param restricted_session: The application-role session
    :param teacher_lens: The teacher's lens
    :param teacher: The batch's owner
    :param exam: An exam on the batch
    :param seat_factory: Makes seats
    :return: None
    """
    marked = seat_factory("Asha")
    absent = seat_factory("Bilal")
    seat_factory("Chandni")
    seat_factory("Dipu", joined_on=EXAM_DATE + dt.timedelta(days=1))
    for seat, state, marks in ((marked, "marked", 70), (absent, "absent", None)):
        record_mark(
            restricted_session,
            lens=teacher_lens,
            exam_id=exam,
            enrollment_id=seat,
            result_state=state,
            marks=marks,
        )

    [row] = list_exam_progress(
        restricted_session, lens=teacher_lens, batch_id=teacher.batch_id
    )

    assert (row.entered_count, row.expected_count) == (2, 3)
