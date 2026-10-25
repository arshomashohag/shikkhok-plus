"""Exam creation and editing [BR4.1].

**The subject-belongs-to-batch check is an authorization boundary, not
a validation nicety** [§ 2.4]. A ``batch_subject_id`` from another
teacher's batch would attach an exam **across the ownership
boundary**, and because it is enforced in the write path rather than by
a foreign key, it is a check somebody can omit.

The refusal is the shared ``NOT_AVAILABLE`` rather than a descriptive
one: the subject id is an unreachable resource, and naming it as wrong
is the oracle [BR4.1].
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import Batch, BatchSubject, Exam
from app.errors import ConflictError, ValidationError
from app.teaching.roster import refuse

__all__ = ["ExamRow", "create_exam", "list_exams", "readable_exam", "update_exam"]


@dataclass(frozen=True, slots=True)
class ExamRow:
    """One exam, as any entitled lens sees it.

    ``total_marks`` is an **integer count**, never money.

    :ivar exam_id: The exam
    :ivar title: The teacher's name for it
    :ivar date: When it was sat
    :ivar total_marks: The denominator
    :ivar subject_name: The subject assessed
    """

    exam_id: uuid.UUID
    title: str
    date: dt.date
    total_marks: int
    subject_name: str


def _owned_active_batch(
    session: DbSession, *, lens: TeacherLens, batch_id: uuid.UUID
) -> Batch:
    """Return a batch this lens owns and may write to.

    :param session: The session to read through
    :param lens: The teacher lens
    :param batch_id: The batch
    :return: The batch row
    :raises AuthorizationError: This lens does not own it
    :raises ConflictError: The batch is inactive [BR5.5]
    """
    row = session.scalars(
        sa.select(Batch).where(Batch.id == batch_id, Batch.owner_id == lens.owner_id)
    ).one_or_none()
    if row is None:
        raise refuse()
    if not row.active:
        raise ConflictError(
            code="BATCH_INACTIVE",
            message_key="teaching.batch.inactive",
        )
    return row


def readable_exam(session: DbSession, *, lens: TeacherLens, exam_id: uuid.UUID) -> Exam:
    """Return an exam this teacher lens reaches, or refuse.

    :param session: The session to read through
    :param lens: The teacher lens
    :param exam_id: The exam
    :return: The exam row
    :raises AuthorizationError: No batch this lens owns holds it
    """
    row = session.scalars(
        sa.select(Exam)
        .join(Batch, Batch.id == Exam.batch_id)
        .where(Exam.id == exam_id, Batch.owner_id == lens.owner_id)
    ).one_or_none()
    if row is None:
        raise refuse()
    return row


def _subject_of_batch(
    session: DbSession, *, batch_id: uuid.UUID, batch_subject_id: uuid.UUID
) -> BatchSubject:
    """Return a subject belonging to this batch, or refuse.

    :param session: The session to read through
    :param batch_id: The batch the exam sits in
    :param batch_subject_id: The subject named
    :return: The subject row
    :raises AuthorizationError: The subject is not this batch's
    """
    row = session.scalars(
        sa.select(BatchSubject).where(
            BatchSubject.id == batch_subject_id,
            BatchSubject.batch_id == batch_id,
        )
    ).one_or_none()
    if row is None:
        raise refuse()
    return row


def _validate_total(total_marks: int) -> None:
    """Refuse a total below one [BR4.1].

    A total of zero makes every percentage undefined and every band
    degenerate, which is why the database carries the same CHECK.

    :param total_marks: The denominator proposed
    :return: None
    :raises ValidationError: The total is below one
    """
    if total_marks < 1:
        raise ValidationError(
            code="EXAM_TOTAL_INVALID",
            message_key="marks.exam.total_invalid",
        )


def create_exam(
    session: DbSession,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
    batch_subject_id: uuid.UUID,
    title: str,
    date: dt.date,
    total_marks: int,
) -> ExamRow:
    """Create one exam on one of this teacher's batches [BR4.1].

    :param session: The session to work through
    :param lens: The teacher lens
    :param batch_id: The batch
    :param batch_subject_id: One of that batch's subjects
    :param title: The teacher's name for it
    :param date: When it was sat
    :param total_marks: The denominator, at least 1
    :return: The new exam
    :raises AuthorizationError: This lens does not own the batch, or
        the subject is not that batch's
    :raises ConflictError: The batch is inactive
    :raises ValidationError: The total is below one
    """
    _owned_active_batch(session, lens=lens, batch_id=batch_id)
    subject = _subject_of_batch(
        session, batch_id=batch_id, batch_subject_id=batch_subject_id
    )
    _validate_total(total_marks)

    row = Exam(
        batch_id=batch_id,
        batch_subject_id=batch_subject_id,
        title=title,
        date=date,
        total_marks=total_marks,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(row)
    session.commit()

    return ExamRow(
        exam_id=row.id,
        title=row.title,
        date=row.date,
        total_marks=row.total_marks,
        subject_name=subject.name,
    )


def update_exam(
    session: DbSession,
    *,
    lens: TeacherLens,
    exam_id: uuid.UUID,
    title: str,
    date: dt.date,
    total_marks: int,
) -> ExamRow:
    """Edit an exam's title, date or total.

    **An interactive write carrying no version** [BR3.11]: applied
    everywhere, optimistic concurrency would make a teacher editing an
    exam on their own phone refetch for no reason.

    :param session: The session to work through
    :param lens: The teacher lens
    :param exam_id: The exam
    :param title: Its new title
    :param date: Its new date
    :param total_marks: Its new denominator
    :return: The updated exam
    :raises AuthorizationError: This lens does not reach the exam
    :raises ConflictError: The batch is inactive, or a live mark
        already exceeds the proposed total
    :raises ValidationError: The total is below one
    """
    row = readable_exam(session, lens=lens, exam_id=exam_id)
    _owned_active_batch(session, lens=lens, batch_id=row.batch_id)
    _validate_total(total_marks)

    # **Lowering the total below a mark already recorded would leave a
    # stored mark above its own denominator**, which the write path's
    # bound would then forbid anyone from re-entering and which every
    # percentage downstream would compute as over 100%. The bound
    # spans a foreign key in this direction too, so it is checked
    # here for the same reason it is checked on entry.
    from app.db.models import Mark

    highest = session.scalars(
        sa.select(sa.func.max(Mark.marks)).where(
            Mark.exam_id == exam_id,
            Mark.superseded_by_id.is_(None),
        )
    ).one()
    if highest is not None and highest > total_marks:
        raise ConflictError(
            code="EXAM_TOTAL_BELOW_RECORDED_MARK",
            message_key="marks.exam.total_below_recorded",
        )

    row.title = title
    row.date = date
    row.total_marks = total_marks
    session.commit()

    name = session.scalars(
        sa.select(BatchSubject.name).where(BatchSubject.id == row.batch_subject_id)
    ).one()
    return ExamRow(
        exam_id=row.id,
        title=row.title,
        date=row.date,
        total_marks=row.total_marks,
        subject_name=name,
    )


def list_exams(
    session: DbSession,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
) -> list[ExamRow]:
    """List one batch's exams, oldest first.

    :param session: The session to read through
    :param lens: The teacher lens
    :param batch_id: The batch
    :return: One row per exam
    :raises AuthorizationError: This lens does not own the batch
    """
    owned = session.scalars(
        sa.select(Batch.id).where(Batch.id == batch_id, Batch.owner_id == lens.owner_id)
    ).one_or_none()
    if owned is None:
        raise refuse()

    rows = session.execute(
        sa.select(Exam, BatchSubject.name)
        .join(BatchSubject, BatchSubject.id == Exam.batch_subject_id)
        .where(Exam.batch_id == batch_id)
        .order_by(Exam.date, Exam.id)
    ).all()
    return [
        ExamRow(
            exam_id=entry[0].id,
            title=entry[0].title,
            date=entry[0].date,
            total_marks=entry[0].total_marks,
            subject_name=entry[1],
        )
        for entry in rows
    ]
