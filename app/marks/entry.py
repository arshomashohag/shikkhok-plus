"""Mark entry and correction [BR4.2, BR4.4, BR4.5].

**Every correction appends; no mark is ever updated in place or
deleted** [BR4.4]. The old row's ``superseded_by_id`` is set in the
SAME transaction as the new row's insert, which is what keeps the
partial unique index satisfiable: for an instant there would otherwise
be two live rows, and the index refuses that outright.

**A correction takes three statements, not two, and the reason was
measured rather than reasoned.** Two immediate constraints pull in
opposite directions: the partial unique index refuses a second live
row, and the self-referential foreign key refuses a pointer to a row
that does not exist yet. :func:`record_mark` documents the resolution
at the statement that performs it.

**The upper bound is enforced here because it cannot be a CHECK.**
``marks <= exam.total_marks`` spans a foreign key, which PostgreSQL
will not accept in a single-table constraint [entities.md, BR4.2].

**No mark reaches a log line or a refusal message** [NFR24.14]. The
natural message for an out-of-range mark is *"42 exceeds total 40"*,
which logs a child's mark while reporting a routine validation
failure. The refusal carries the exam's total and not the value
submitted.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import Batch, Exam, Mark
from app.errors import ConflictError, ValidationError
from app.marks.exams import readable_exam
from app.teaching.roster import readable_enrollment, refuse

__all__ = [
    "CorrectionEntry",
    "MarkResult",
    "correction_history",
    "live_marks_for_exam",
    "record_mark",
]

#: The four states a result can carry. Two of them -- ``not_entered``
#: and ``joined_after`` -- are DERIVED and never typed by the teacher
#: [BR4.3], so they are not accepted by :func:`record_mark`.
ENTERABLE_STATES: tuple[str, ...] = ("marked", "absent")


@dataclass(frozen=True, slots=True)
class MarkResult:
    """What one accepted mark write produced.

    :ivar mark_id: The new live row
    :ivar superseded_id: The row it replaced, or None
    """

    mark_id: uuid.UUID
    superseded_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class CorrectionEntry:
    """One row in a seat's correction history [FR9.2].

    :ivar mark_id: The row
    :ivar result_state: What it recorded
    :ivar marks: Its number, or None
    :ivar recorded_at: When it was entered
    :ivar recorded_by_account_id: Who entered it
    :ivar superseded: Whether a later row replaced it
    """

    mark_id: uuid.UUID
    result_state: str
    marks: int | None
    recorded_at: dt.datetime
    recorded_by_account_id: uuid.UUID | None
    superseded: bool


def _writable_exam(
    session: DbSession,
    *,
    lens: TeacherLens,
    exam_id: uuid.UUID,
) -> Exam:
    """Return an exam this lens may write marks against.

    Authorization first, then the state refusal, which is the same
    ordering the roster path uses and for the same reason.

    :param session: The session to read through
    :param lens: The teacher lens
    :param exam_id: The exam
    :return: The exam row
    :raises AuthorizationError: This lens does not reach the exam
    :raises ConflictError: The batch is inactive [BR5.5]
    """
    row = readable_exam(session, lens=lens, exam_id=exam_id)

    active = session.scalars(
        sa.select(Batch.active).where(Batch.id == row.batch_id)
    ).one()
    if not active:
        raise ConflictError(
            code="BATCH_INACTIVE",
            message_key="teaching.batch.inactive",
        )
    return row


def record_mark(
    session: DbSession,
    *,
    lens: TeacherLens,
    exam_id: uuid.UUID,
    enrollment_id: uuid.UUID,
    result_state: str,
    marks: int | None,
) -> MarkResult:
    """Enter or correct one seat's result [BR4.2, BR4.4].

    **An interactive write carrying no version** [BR3.11]: only
    attendance and the topic log are queued, and only they conflict.

    :param session: The session to work through
    :param lens: The teacher lens
    :param exam_id: The exam
    :param enrollment_id: The seat
    :param result_state: ``marked`` or ``absent``; the other two
        states are derived and cannot be typed
    :param marks: The number, required for ``marked`` and forbidden
        otherwise
    :return: The new row, and the one it replaced
    :raises AuthorizationError: This lens does not reach the exam or
        the seat
    :raises ConflictError: The batch is inactive
    :raises ValidationError: The state is not enterable, the
        state/marks pairing is wrong, or the mark is out of range
    """
    exam = _writable_exam(session, lens=lens, exam_id=exam_id)

    # The seat must be on the exam's own batch. A seat from another
    # batch would attach a result across the ownership boundary, the
    # same hazard the subject check closes for the exam itself.
    seat = readable_enrollment(session, lens=lens, enrollment_id=enrollment_id)
    if seat.batch_id != exam.batch_id:
        raise refuse()

    if result_state not in ENTERABLE_STATES:
        raise ValidationError(
            code="RESULT_STATE_NOT_ENTERABLE",
            message_key="marks.result_state.not_enterable",
            details={"enterable": ",".join(ENTERABLE_STATES)},
        )

    # The biconditional, checked here as well as by the CHECK. The
    # constraint is the control; this is what turns a violation into
    # a typed refusal rather than an IntegrityError at the boundary.
    if (result_state == "marked") != (marks is not None):
        raise ValidationError(
            code="MARK_STATE_MISMATCH",
            message_key="marks.state_mismatch",
        )

    if marks is not None and not 0 <= marks <= exam.total_marks:
        # The exam's total, NOT the value submitted [NFR24.14].
        raise ValidationError(
            code="MARK_OUT_OF_RANGE",
            message_key="marks.out_of_range",
            details={"total_marks": str(exam.total_marks)},
        )

    previous = session.scalars(
        sa.select(Mark).where(
            Mark.exam_id == exam_id,
            Mark.enrollment_id == enrollment_id,
            Mark.superseded_by_id.is_(None),
        )
    ).one_or_none()

    now = dt.datetime.now(tz=dt.UTC)
    fresh_id = uuid.uuid4()

    # **Three statements, and the order was measured rather than
    # reasoned.** Two immediate constraints pull in opposite
    # directions and the obvious two-step satisfies neither:
    #
    # * inserting the new live row first is refused by the partial
    #   unique index, because for that instant the seat has two live
    #   rows -- the index is checked immediately and cannot be
    #   deferred, since PostgreSQL defers CONSTRAINTS and partial
    #   uniqueness can only be an INDEX;
    # * pointing the old row at the new one first is refused by the
    #   self-referential foreign key, because the new row does not
    #   exist yet.
    #
    # The resolution uses only what the schema already guarantees: the
    # old row is pointed at ITSELF, which satisfies the foreign key
    # (the row plainly exists) and immediately removes it from the
    # index's `superseded_by_id IS NULL` predicate. The new row then
    # inserts cleanly, and the old pointer is corrected to name it.
    # A self-pointer is never observable: all three statements are in
    # ONE transaction [BR4.4], so no reader outside it ever sees the
    # intermediate state, and `correction_history` reads
    # `superseded_by_id IS NOT NULL` rather than following the chain.
    if previous is not None:
        previous.superseded_by_id = previous.id
        session.flush()

    session.add(
        Mark(
            id=fresh_id,
            exam_id=exam_id,
            enrollment_id=enrollment_id,
            result_state=result_state,
            marks=marks,
            recorded_at=now,
            recorded_by_account_id=lens.account_id,
            superseded_by_id=None,
            created_at=now,
        )
    )
    session.flush()

    if previous is not None:
        previous.superseded_by_id = fresh_id
        session.flush()

    session.commit()
    return MarkResult(
        mark_id=fresh_id,
        superseded_id=None if previous is None else previous.id,
    )


def correction_history(
    session: DbSession,
    *,
    lens: TeacherLens,
    exam_id: uuid.UUID,
    enrollment_id: uuid.UUID,
) -> list[CorrectionEntry]:
    """Return every row ever recorded for one seat, oldest first.

    This is the audit trail FR9.2 requires to be visible: on a shared
    marksheet a silently changed mark is the one a student will
    dispute, and an in-place update would leave nothing to show them.

    :param session: The session to read through
    :param lens: The teacher lens
    :param exam_id: The exam
    :param enrollment_id: The seat
    :return: Every row, oldest first
    :raises AuthorizationError: This lens does not reach the exam
    """
    readable_exam(session, lens=lens, exam_id=exam_id)

    rows = session.scalars(
        sa.select(Mark)
        .where(Mark.exam_id == exam_id, Mark.enrollment_id == enrollment_id)
        .order_by(Mark.created_at, Mark.id)
    ).all()
    return [
        CorrectionEntry(
            mark_id=row.id,
            result_state=row.result_state,
            marks=row.marks,
            recorded_at=row.recorded_at,
            recorded_by_account_id=row.recorded_by_account_id,
            superseded=row.superseded_by_id is not None,
        )
        for row in rows
    ]


def live_marks_for_exam(
    session: DbSession,
    *,
    exam_id: uuid.UUID,
) -> list[tuple[uuid.UUID, str, int | None]]:
    """Read the live result per seat for one exam.

    Unscoped by design: every caller has already resolved a lens
    against the exam, and this is the shared read the results view and
    the marksheet both fold. Keeping it lens-free rather than taking a
    :class:`Lens` it would not use is what stops a second, weaker
    scope check growing beside the real one.

    :param session: The session to read through
    :param exam_id: The exam
    :return: ``(enrollment_id, result_state, marks)`` per live row
    """
    rows = session.execute(
        sa.select(Mark.enrollment_id, Mark.result_state, Mark.marks).where(
            Mark.exam_id == exam_id,
            Mark.superseded_by_id.is_(None),
        )
    ).all()
    return [(row[0], row[1], row[2]) for row in rows]
