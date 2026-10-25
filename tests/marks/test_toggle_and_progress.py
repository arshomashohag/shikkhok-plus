"""The marksheet toggle [BR5.4] and guardian progress [BR6.6].

**Three absences are asserted individually** on the toggle [§ 4.5].
Asserting only "not a 200" passes against a 200 carrying an empty
list, and an empty marksheet still discloses that exams exist and how
many -- which is the whole failure mode. Returning an empty collection
is the kinder-looking code, which is why it is the shape an
implementation reaches by habit.

**An absence in a progress series carries no numeric value.** An
absence plotted as zero shows a collapse in performance that did not
happen, which is the single most alarming thing that screen can say
wrongly.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.db.models import Exam
from app.errors import AuthorizationError, ConflictError
from app.marks.entry import record_mark
from app.marks.marksheet import Published
from app.marks.views import (
    guardian_progress,
    seat_marksheet,
    set_marksheet_visible,
)
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.marks.conftest import EXAM_DATE, TOTAL_MARKS


@pytest.fixture
def student_seat(
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create an accepted student seat and the account holding it.

    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: The enrollment id and the student's account id
    """
    account = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=account,
        student_decision="accepted",
        guardian_decision="pending",
    )
    return seat, account


def _fill_exam(
    session: DbSession,
    *,
    lens: TeacherLens,
    exam_id: uuid.UUID,
    seats: list[uuid.UUID],
    values: list[int],
) -> None:
    """Mark every seat so the marksheet publishes.

    :param session: The session to work through
    :param lens: The teacher lens
    :param exam_id: The exam
    :param seats: The seats to mark
    :param values: One mark per seat
    :return: None
    """
    for seat, value in zip(seats, values, strict=True):
        record_mark(
            session,
            lens=lens,
            exam_id=exam_id,
            enrollment_id=seat,
            result_state="marked",
            marks=value,
        )


def test_with_the_toggle_off_nothing_at_all_is_returned(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    student_seat: tuple[uuid.UUID, uuid.UUID],
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    seat, account = student_seat
    others = [seat_factory(name=f"Other {i}") for i in range(5)]
    _fill_exam(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        seats=[seat, *others],
        values=[70, 90, 85, 60, 55, 40],
    )

    set_marksheet_visible(
        restricted_session,
        lens=teacher_lens,
        batch_id=teacher.batch_id,
        visible=False,
    )

    with pytest.raises(AuthorizationError) as refusal:
        seat_marksheet(
            restricted_session,
            lens=StudentLens(account_id=account),
            enrollment_id=seat,
            exam_id=exam,
        )

    # **The three absences, asserted individually** [§ 4.5]. "Not a
    # 200" alone passes against a 200 carrying an empty list.
    rendered = repr(refusal.value.details) + repr(refusal.value.code)
    assert refusal.value.code == "NOT_AVAILABLE"
    assert "exam" not in rendered.lower(), "the refusal named an exam"
    assert "[]" not in rendered, "the refusal carried an empty collection"
    assert "count" not in rendered.lower(), "the refusal carried a count"


def test_with_the_toggle_off_the_teachers_own_view_is_unaffected(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    # The toggle controls what FAMILIES see. A teacher who hid the
    # marksheet from students must still be able to read their own.
    seats = [seat_factory(name=f"S{i}") for i in range(6)]
    _fill_exam(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        seats=seats,
        values=[90, 85, 80, 70, 60, 50],
    )
    set_marksheet_visible(
        restricted_session,
        lens=teacher_lens,
        batch_id=teacher.batch_id,
        visible=False,
    )

    sheet = seat_marksheet(
        restricted_session,
        lens=teacher_lens,
        enrollment_id=seats[0],
        exam_id=exam,
    )

    assert isinstance(sheet, Published)


def test_a_non_owner_teacher_cannot_write_the_toggle(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    other = make_teacher(owner_session, name="Chemistry")

    with pytest.raises(AuthorizationError) as refusal:
        set_marksheet_visible(
            restricted_session,
            lens=TeacherLens(account_id=other.account_id, owner_id=other.owner_id),
            batch_id=teacher.batch_id,
            visible=False,
        )

    assert refusal.value.code == "NOT_AVAILABLE"


def test_the_toggle_cannot_be_written_on_an_inactive_batch(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
) -> None:
    owner_session.execute(
        sa.text("UPDATE batch SET active = false WHERE id = :id"),
        {"id": teacher.batch_id},
    )
    owner_session.commit()

    with pytest.raises(ConflictError) as refusal:
        set_marksheet_visible(
            restricted_session,
            lens=teacher_lens,
            batch_id=teacher.batch_id,
            visible=False,
        )

    assert refusal.value.code == "BATCH_INACTIVE"


def test_the_toggle_defaults_on_and_round_trips(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
) -> None:
    # AC4.2.1's "defaults to on" is satisfied by the EXISTING
    # batch-creation path, which D2 owns. D4 adds no default.
    assert (
        set_marksheet_visible(
            restricted_session,
            lens=teacher_lens,
            batch_id=teacher.batch_id,
            visible=False,
        )
        is False
    )
    assert (
        set_marksheet_visible(
            restricted_session,
            lens=teacher_lens,
            batch_id=teacher.batch_id,
            visible=True,
        )
        is True
    )


def test_a_guardian_sees_a_series_in_exam_date_order(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    subject: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    guardian = account_factory()
    child = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted",
    )

    # Three exams, created OUT of date order so an implementation
    # relying on insertion order fails.
    dates = [EXAM_DATE + dt.timedelta(days=offset) for offset in (30, 0, 60)]
    exam_ids: list[uuid.UUID] = []
    for index, when in enumerate(dates):
        row = Exam(
            batch_id=teacher.batch_id,
            batch_subject_id=subject,
            title=f"Test {index}",
            date=when,
            total_marks=TOTAL_MARKS,
            created_at=dt.datetime.now(tz=dt.UTC),
        )
        owner_session.add(row)
        owner_session.commit()
        exam_ids.append(row.id)

    # Marked, absent, marked -- the middle one is the absence.
    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam_ids[1],
        enrollment_id=child,
        result_state="marked",
        marks=60,
    )
    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam_ids[0],
        enrollment_id=child,
        result_state="absent",
        marks=None,
    )
    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam_ids[2],
        enrollment_id=child,
        result_state="marked",
        marks=80,
    )

    series = guardian_progress(
        restricted_session,
        lens=GuardianLens(account_id=guardian, child_enrollment_id=child),
        enrollment_id=child,
    )

    # Ordering asserted IN THE RESPONSE, not re-sorted by the test.
    assert [entry.date for entry in series] == sorted(dates)
    assert len(series) == 3
    assert series[1].result_state == "absent"
    assert series[1].marks is None, (
        "an absence carried a numeric value: plotted as zero it shows "
        "a collapse in performance that did not happen [BR6.6]"
    )
    assert [series[0].marks, series[2].marks] == [60, 80]


def test_a_guardian_cannot_read_a_non_child_seat(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    guardian = account_factory()
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="My child",
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted",
    )
    stranger = seat_factory(name="Someone else")

    with pytest.raises(AuthorizationError) as real_id:
        guardian_progress(
            restricted_session,
            lens=GuardianLens(account_id=guardian),
            enrollment_id=stranger,
        )
    with pytest.raises(AuthorizationError) as invented:
        guardian_progress(
            restricted_session,
            lens=GuardianLens(account_id=guardian),
            enrollment_id=uuid.uuid4(),
        )

    # **BYTE-IDENTICAL** [§ 2.3]: two independent "is a refusal"
    # assertions both pass while the bodies differ, and the difference
    # is the leak.
    assert (
        real_id.value.code,
        real_id.value.message_key,
        real_id.value.status,
        real_id.value.details,
    ) == (
        invented.value.code,
        invented.value.message_key,
        invented.value.status,
        invented.value.details,
    )


def test_a_pending_guardian_reads_nothing(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    # BR5.2: the guardian branch requires guardian_decision =
    # 'accepted'. Naming an account on a link is NOT the grant -- that
    # is the exposure D1 exists to close.
    guardian = account_factory()
    child = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="pending",
    )

    with pytest.raises(AuthorizationError):
        guardian_progress(
            restricted_session,
            lens=GuardianLens(account_id=guardian, child_enrollment_id=child),
            enrollment_id=child,
        )


def test_the_marksheet_never_spans_two_batches(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    student_seat: tuple[uuid.UUID, uuid.UUID],
    seat_factory: Callable[..., uuid.UUID],
    subject: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    # § 4.4, with DISJOINT marks in the second batch: equal marks in
    # both would pass either way, which is what makes the seeding
    # load-bearing rather than incidental.
    seat, account = student_seat
    others = [seat_factory(name=f"Other {i}") for i in range(5)]
    _fill_exam(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        seats=[seat, *others],
        values=[50, 50, 50, 50, 50, 50],
    )

    second = make_teacher(owner_session, name="Chemistry")
    from app.db.models import BatchSubject

    second_subject = BatchSubject(batch_id=second.batch_id, name="Chemistry")
    owner_session.add(second_subject)
    owner_session.commit()
    second_exam = Exam(
        batch_id=second.batch_id,
        batch_subject_id=second_subject.id,
        title="Other batch",
        date=EXAM_DATE,
        total_marks=TOTAL_MARKS,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(second_exam)
    owner_session.commit()

    second_lens = TeacherLens(account_id=second.account_id, owner_id=second.owner_id)
    for index in range(6):
        other_seat = enroll(
            owner_session,
            batch_id=second.batch_id,
            display_name=f"Theirs {index}",
            student_account_id=account_factory(),
            student_decision="accepted",
            guardian_decision="pending",
        )
        record_mark(
            restricted_session,
            lens=second_lens,
            exam_id=second_exam.id,
            enrollment_id=other_seat,
            result_state="marked",
            marks=100,
        )

    sheet = seat_marksheet(
        restricted_session,
        lens=StudentLens(account_id=account),
        enrollment_id=seat,
        exam_id=exam,
    )

    assert isinstance(sheet, Published)
    assert sheet.average == 50.0, (
        "the average absorbed another batch's marks: every aggregate "
        "is scoped to ONE batch [BR6.5, § 4.4]"
    )
    assert sheet.highest == 50
    assert sheet.marked_count == 6


def test_a_student_cannot_read_another_students_marksheet(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    student_seat: tuple[uuid.UUID, uuid.UUID],
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    _, account = student_seat
    stranger = seat_factory(name="Someone else")

    with pytest.raises(AuthorizationError) as refusal:
        seat_marksheet(
            restricted_session,
            lens=StudentLens(account_id=account),
            enrollment_id=stranger,
            exam_id=exam,
        )

    assert refusal.value.code == "NOT_AVAILABLE"


def test_an_exam_from_another_batch_is_unreachable(
    owner_session: DbSession,
    restricted_session: DbSession,
    student_seat: tuple[uuid.UUID, uuid.UUID],
    subject: uuid.UUID,
) -> None:
    seat, account = student_seat
    other = make_teacher(owner_session, name="Chemistry")
    from app.db.models import BatchSubject

    their_subject = BatchSubject(batch_id=other.batch_id, name="Chemistry")
    owner_session.add(their_subject)
    owner_session.commit()
    their_exam = Exam(
        batch_id=other.batch_id,
        batch_subject_id=their_subject.id,
        title="Not yours",
        date=EXAM_DATE,
        total_marks=TOTAL_MARKS,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(their_exam)
    owner_session.commit()

    with pytest.raises(AuthorizationError) as refusal:
        seat_marksheet(
            restricted_session,
            lens=StudentLens(account_id=account),
            enrollment_id=seat,
            exam_id=their_exam.id,
        )

    assert refusal.value.code == "NOT_AVAILABLE"
