"""Mark entry, correction and the two constraints [BR4.2, BR4.4, BR4.5].

**The biconditional is a database CHECK rather than a validator**,
because a validator is bypassed by every write path that forgets it. So
it is provoked directly here, as an insert the database must refuse --
not as a service call the service happens to reject.

**The upper bound is NOT a CHECK and cannot be**: ``marks <=
exam.total_marks`` spans a foreign key, which PostgreSQL will not
accept in a single-table constraint. It is enforced in the write path,
and that is exactly why it gets its own test [entities.md, BR4.2].

**A zero is a mark.** A zero stored as ``absent`` tells a guardian
their child missed an exam they sat and failed; the reverse tells them
the child scored nothing when they were ill.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.marks.entry import correction_history, record_mark
from tests.batches.conftest import TeacherFixture, make_teacher
from tests.marks.conftest import TOTAL_MARKS


def _live_marks(session: DbSession, exam_id: uuid.UUID) -> int:
    """Count an exam's live mark rows.

    :param session: The session to read through
    :param exam_id: The exam
    :return: How many rows have a null supersession pointer
    """
    return int(
        session.execute(
            sa.text(
                "SELECT count(*) FROM mark WHERE exam_id = :id "
                "AND superseded_by_id IS NULL"
            ),
            {"id": exam_id},
        ).scalar_one()
    )


def test_a_zero_is_a_marked_result_and_not_an_absence(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    seat = seat_factory()

    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        enrollment_id=seat,
        result_state="marked",
        marks=0,
    )

    row = restricted_session.execute(
        sa.text(
            "SELECT result_state, marks FROM mark WHERE exam_id = :e "
            "AND enrollment_id = :s AND superseded_by_id IS NULL"
        ),
        {"e": exam, "s": seat},
    ).one()
    assert row[0] == "marked"
    assert row[1] == 0, "a zero was stored as something other than a mark of 0"


def test_the_biconditional_check_refuses_marked_without_a_number(
    owner_session: DbSession,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    # Provoked DIRECTLY against the database, not through the service:
    # the point of a CHECK is that it holds for every write path,
    # including a repair script that never passes through the service.
    seat = seat_factory()

    with pytest.raises(sa.exc.IntegrityError) as refusal:
        owner_session.execute(
            sa.text(
                "INSERT INTO mark (id, exam_id, enrollment_id, "
                "result_state, marks, recorded_at, created_at) VALUES "
                "(:id, :e, :s, 'marked', NULL, now(), now())"
            ),
            {"id": uuid.uuid4(), "e": exam, "s": seat},
        )
    owner_session.rollback()

    assert "ck_mark_state_marks_biconditional" in str(refusal.value)


def test_the_biconditional_check_refuses_absent_with_a_number(
    owner_session: DbSession,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    # The other direction. Both are needed: a CHECK written as
    # `marks IS NOT NULL OR result_state <> 'marked'` satisfies the
    # first test and admits an absence carrying a number.
    seat = seat_factory()

    with pytest.raises(sa.exc.IntegrityError) as refusal:
        owner_session.execute(
            sa.text(
                "INSERT INTO mark (id, exam_id, enrollment_id, "
                "result_state, marks, recorded_at, created_at) VALUES "
                "(:id, :e, :s, 'absent', 0, now(), now())"
            ),
            {"id": uuid.uuid4(), "e": exam, "s": seat},
        )
    owner_session.rollback()

    assert "ck_mark_state_marks_biconditional" in str(refusal.value)


def test_a_mark_above_the_exam_total_is_refused_by_the_write_path(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    # The bound spans a foreign key, so it CANNOT be a single-table
    # CHECK. This is the test that stands in its place [BR4.2].
    seat = seat_factory()

    with pytest.raises(ValidationError) as refusal:
        record_mark(
            restricted_session,
            lens=teacher_lens,
            exam_id=exam,
            enrollment_id=seat,
            result_state="marked",
            marks=TOTAL_MARKS + 1,
        )

    assert refusal.value.code == "MARK_OUT_OF_RANGE"
    # NFR24.14: no mark reaches a log line or a message. The natural
    # message is "101 exceeds total 100", which logs a child's mark
    # while reporting a routine validation failure.
    assert "101" not in str(refusal.value.details)
    assert _live_marks(restricted_session, exam) == 0


def test_a_mark_exactly_at_the_total_is_accepted(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    # The boundary. A bound written with `<` rather than `<=` refuses
    # a full score, which is the most visible possible defect.
    seat = seat_factory()

    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        enrollment_id=seat,
        result_state="marked",
        marks=TOTAL_MARKS,
    )

    stored = restricted_session.execute(
        sa.text("SELECT marks FROM mark WHERE exam_id = :e AND enrollment_id = :s"),
        {"e": exam, "s": seat},
    ).scalar_one()
    assert stored == TOTAL_MARKS


def test_a_negative_mark_is_refused(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    seat = seat_factory()

    with pytest.raises(ValidationError):
        record_mark(
            restricted_session,
            lens=teacher_lens,
            exam_id=exam,
            enrollment_id=seat,
            result_state="marked",
            marks=-1,
        )


def test_a_correction_appends_and_supersedes(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    # BR4.4's own named case: enter 55, correct to 65, assert TWO rows
    # exist with the first superseded. An in-place update destroys the
    # fact that a mark changed, which FR9.2 requires to be visible --
    # and on a shared marksheet a silently changed mark is the one a
    # student will dispute.
    seat = seat_factory()
    first = record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        enrollment_id=seat,
        result_state="marked",
        marks=55,
    )
    second = record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        enrollment_id=seat,
        result_state="marked",
        marks=65,
    )

    rows = restricted_session.execute(
        sa.text(
            "SELECT id, marks, superseded_by_id FROM mark "
            "WHERE exam_id = :e AND enrollment_id = :s "
            "ORDER BY created_at, marks"
        ),
        {"e": exam, "s": seat},
    ).all()
    assert len(rows) == 2, "the correction updated in place rather than appending"
    assert rows[0][1] == 55
    assert rows[0][2] == second.mark_id, (
        "the old row's supersession pointer was not set to the new row"
    )
    assert rows[1][1] == 65
    assert rows[1][2] is None
    assert first.mark_id == rows[0][0]


def test_the_correction_history_returns_both_with_actor_and_time(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
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

    history = correction_history(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        enrollment_id=seat,
    )

    assert [entry.marks for entry in history] == [55, 65]
    assert all(entry.recorded_at is not None for entry in history)
    assert all(
        entry.recorded_by_account_id == teacher_lens.account_id for entry in history
    )
    assert history[0].superseded is True
    assert history[1].superseded is False


def test_the_partial_index_refuses_a_second_live_mark(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    # BR4.5, provoked directly. A correction that fails to set the old
    # pointer leaves two live marks and the marksheet counts one
    # student twice, inflating the batch size, shifting every rank and
    # skewing the average with nothing on screen to indicate it. A
    # logic-only guard would not catch this insert.
    seat = seat_factory()
    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        enrollment_id=seat,
        result_state="marked",
        marks=55,
    )

    with pytest.raises(sa.exc.IntegrityError) as refusal:
        owner_session.execute(
            sa.text(
                "INSERT INTO mark (id, exam_id, enrollment_id, "
                "result_state, marks, recorded_at, created_at) VALUES "
                "(:id, :e, :s, 'marked', 70, now(), now())"
            ),
            {"id": uuid.uuid4(), "e": exam, "s": seat},
        )
    owner_session.rollback()

    assert "uq_mark_live_per_seat" in str(refusal.value)


def test_a_superseded_row_does_not_block_a_new_live_one(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    # The index is PARTIAL, and this is what the partiality buys: a
    # full unique index would make the second correction impossible.
    seat = seat_factory()
    for value in (40, 50, 60):
        record_mark(
            restricted_session,
            lens=teacher_lens,
            exam_id=exam,
            enrollment_id=seat,
            result_state="marked",
            marks=value,
        )

    assert _live_marks(restricted_session, exam) == 1


def test_a_mark_on_another_teachers_exam_is_refused(
    owner_session: DbSession,
    restricted_session: DbSession,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    seat = seat_factory()
    other = make_teacher(owner_session, name="Chemistry")

    with pytest.raises(AuthorizationError) as refusal:
        record_mark(
            restricted_session,
            lens=TeacherLens(account_id=other.account_id, owner_id=other.owner_id),
            exam_id=exam,
            enrollment_id=seat,
            result_state="marked",
            marks=55,
        )

    assert refusal.value.code == "NOT_AVAILABLE"
    assert _live_marks(restricted_session, exam) == 0


def test_a_mark_on_an_inactive_batch_is_refused(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    # BR5.5: no write in this unit succeeds against an inactive batch.
    seat = seat_factory()
    owner_session.execute(
        sa.text("UPDATE batch SET active = false WHERE id = :id"),
        {"id": teacher.batch_id},
    )
    owner_session.commit()

    with pytest.raises(ConflictError) as refusal:
        record_mark(
            restricted_session,
            lens=teacher_lens,
            exam_id=exam,
            enrollment_id=seat,
            result_state="marked",
            marks=55,
        )

    assert refusal.value.code == "BATCH_INACTIVE"


def test_an_absent_result_carries_no_number(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    seat = seat_factory()

    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam,
        enrollment_id=seat,
        result_state="absent",
        marks=None,
    )

    stored = restricted_session.execute(
        sa.text(
            "SELECT result_state, marks FROM mark WHERE exam_id = :e "
            "AND enrollment_id = :s"
        ),
        {"e": exam, "s": seat},
    ).one()
    assert stored == ("absent", None)


def test_passing_a_number_with_a_non_marked_state_is_refused(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    seat = seat_factory()

    with pytest.raises(ValidationError):
        record_mark(
            restricted_session,
            lens=teacher_lens,
            exam_id=exam,
            enrollment_id=seat,
            result_state="absent",
            marks=0,
        )
