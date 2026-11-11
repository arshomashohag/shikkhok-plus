"""Exam creation, editing and cancellation [BR4.1].

**The subject-belongs-to-batch check is an authorization boundary, not
a validation nicety** [§ 2.4]. A ``batch_subject_id`` from another
teacher's batch would attach an exam **across the ownership
boundary**, and because it is enforced in the write path rather than by
a foreign key, it is a check somebody can omit.

The refusal is the shared ``NOT_AVAILABLE`` rather than a descriptive
one: the subject id is an unreachable resource, and naming it as wrong
is the oracle [BR4.1].

**Cancelling** [0019] is for an exam whose results are not published.
A cancelled exam is never deleted: its row, any marks drafted against
it, and the families' inbox items all stay, and it is shown

* on the teacher's exam list for the batch, in its usual place, flagged
  ``cancelled`` -- the teacher made the decision and should be able to
  see it, and an exam silently vanishing from the list they scheduled it
  on is the more surprising behaviour;
* nowhere else: not in the teacher's next-exam or today views, not on a
  family's batch view or upcoming exam, not on any dashboard. Those
  answer "what is coming" or "how did it go", and for a cancelled exam
  the answer is nothing.

Nothing more can be written to it: marks, publishing and edits are
refused with ``EXAM_CANCELLED``.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import ExaminerLens, TeacherLens
from app.centres.service import centre_of
from app.db.models import Batch, BatchSubject, Exam, OwnerMember, ScheduleSlot
from app.errors import ConflictError, ValidationError
from app.notifications.inbox import EXAM_CANCELLED, EXAM_SCHEDULED, remove_for_source
from app.notifications.recipients import (
    deliver_to_families,
    mark_unread_for_families,
)
from app.schemas.marks import MAX_TOTAL_MARKS
from app.teaching.assignment import check_assignment
from app.teaching.roster import refuse

__all__ = [
    "ExamRow",
    "cancel_exam",
    "cancelled_refusal",
    "create_exam",
    "list_exams",
    "readable_exam",
    "update_exam",
]


@dataclass(frozen=True, slots=True)
class ExamRow:
    """One exam, as any entitled lens sees it.

    ``total_marks`` is an **integer count**, never money.

    :ivar exam_id: The exam
    :ivar title: The teacher's name for it
    :ivar date: When it was sat
    :ivar total_marks: The denominator
    :ivar subject_name: The subject assessed
    :ivar topics: What it covers, in the teacher's order
    :ivar published: Whether its results have been published to
        students and guardians; False while they are a draft
    :ivar cancelled: Whether the teacher cancelled it [0019]
    :ivar cancellation_reason: The teacher's note on cancelling, if any
    :ivar examiner_member_id: The centre member who marks it [0025], or
        None
    """

    exam_id: uuid.UUID
    title: str
    date: dt.date
    total_marks: int
    subject_name: str
    topics: list[str] = field(default_factory=list)
    published: bool = False
    cancelled: bool = False
    cancellation_reason: str | None = None
    examiner_member_id: uuid.UUID | None = None

    @classmethod
    def of(cls, exam: Exam, subject_name: str) -> ExamRow:
        """Describe a stored exam.

        :param exam: The exam row
        :param subject_name: Its subject's name
        :return: The description every reader of an exam shares
        """
        return cls(
            exam_id=exam.id,
            title=exam.title,
            date=exam.date,
            total_marks=exam.total_marks,
            subject_name=subject_name,
            topics=list(exam.topics),
            published=exam.published_at is not None,
            cancelled=exam.cancelled_at is not None,
            cancellation_reason=exam.cancellation_reason,
            examiner_member_id=exam.examiner_member_id,
        )


def cancelled_refusal() -> ConflictError:
    """Build the refusal for a write against a cancelled exam.

    :return: The conflict
    """
    return ConflictError(code="EXAM_CANCELLED", message_key="marks.exam.cancelled")


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


def readable_exam(
    session: DbSession, *, lens: TeacherLens | ExaminerLens, exam_id: uuid.UUID
) -> Exam:
    """Return an exam this teacher lens reaches, or refuse.

    **An examiner's lens reaches one exam only** [C4]: the one it was
    resolved for, while its membership is still that exam's examiner.
    Both clauses sit in this query beside the owner's.

    :param session: The session to read through
    :param lens: The teacher lens, or an examiner's lens for one exam
    :param exam_id: The exam
    :return: The exam row
    :raises AuthorizationError: No batch this lens owns holds it
    """
    scope = [Exam.id == exam_id, Batch.owner_id == lens.owner_id]
    if isinstance(lens, ExaminerLens):
        scope += [Exam.id == lens.exam_id, Exam.examiner_member_id == lens.member_id]
    row = session.scalars(
        sa.select(Exam).join(Batch, Batch.id == Exam.batch_id).where(*scope)
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
    topics: list[str] | None = None,
    examiner_member_id: uuid.UUID | None = None,
    examiner_named: bool = False,
) -> ExamRow:
    """Create one exam on one of this teacher's batches [BR4.1].

    **At a centre the manager names the examiner** [decided 2026-11-06].
    Left unnamed, the batch's one weekly teacher is the default when it
    has exactly one; otherwise the exam has none until a manager names
    one. A solo tutor marks their own exams and names nobody.

    :param session: The session to work through
    :param lens: The teacher lens
    :param batch_id: The batch
    :param batch_subject_id: One of that batch's subjects
    :param title: The teacher's name for it
    :param date: When it was sat
    :param total_marks: The denominator, at least 1
    :param topics: What it covers, kept in order; none by default
    :param examiner_member_id: The examiner the manager named, or None
    :param examiner_named: Whether the request named one, even as None;
        when it did not, the default applies
    :return: The new exam
    :raises AuthorizationError: This lens does not own the batch, or
        the subject is not that batch's
    :raises ConflictError: The batch is inactive
    :raises ValidationError: The total is below one
    """
    batch = _owned_active_batch(session, lens=lens, batch_id=batch_id)
    subject = _subject_of_batch(
        session, batch_id=batch_id, batch_subject_id=batch_subject_id
    )
    _validate_total(total_marks)
    examiner = (
        examiner_member_id
        if examiner_named
        else default_examiner(session, batch_id=batch_id)
    )
    if examiner is not None:
        check_assignment(session, lens=lens, teacher_member_id=examiner, room_id=None)

    row = Exam(
        batch_id=batch_id,
        batch_subject_id=batch_subject_id,
        title=title,
        date=date,
        total_marks=total_marks,
        topics=list(topics or []),
        created_at=dt.datetime.now(tz=dt.UTC),
        examiner_member_id=examiner,
    )
    session.add(row)
    session.flush()
    deliver_to_families(
        session,
        batch=batch,
        kind=EXAM_SCHEDULED,
        source_id=row.id,
        preview=row.title,
        now=row.created_at,
    )
    session.commit()

    return ExamRow.of(row, subject.name)


def update_exam(
    session: DbSession,
    *,
    lens: TeacherLens,
    exam_id: uuid.UUID,
    title: str,
    date: dt.date,
    total_marks: int,
    topics: list[str] | None = None,
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
    :param topics: Its new topics, replacing the old list; None keeps them
    :return: The updated exam
    :raises AuthorizationError: This lens does not reach the exam
    :raises ConflictError: The batch is inactive, the exam is cancelled,
        or a live mark already exceeds the proposed total
    :raises ValidationError: The total is below one, or is changed to
        more than :data:`~app.schemas.marks.MAX_TOTAL_MARKS`
    """
    row = readable_exam(session, lens=lens, exam_id=exam_id)
    _owned_active_batch(session, lens=lens, batch_id=row.batch_id)
    if row.cancelled_at is not None:
        raise cancelled_refusal()
    _validate_total(total_marks)
    # **The creation cap applies to a total being CHOSEN, not to one
    # already stored** [SEC-3]. An exam created before the cap existed
    # may hold a larger total; refusing every edit of it would leave its
    # title and date frozen. Keeping that total is allowed, raising any
    # total past the cap is refused as creation refuses it.
    if total_marks > MAX_TOTAL_MARKS and total_marks != row.total_marks:
        raise ValidationError(
            code="EXAM_TOTAL_INVALID",
            message_key="marks.exam.total_invalid",
        )

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

    new_topics = list(row.topics) if topics is None else list(topics)
    changed = (row.title, row.date, list(row.topics)) != (title, date, new_topics)
    row.title = title
    row.date = date
    row.total_marks = total_marks
    row.topics = new_topics
    if changed:
        mark_unread_for_families(
            session,
            batch_id=row.batch_id,
            kind=EXAM_SCHEDULED,
            source_id=row.id,
            preview=title,
        )
    session.commit()

    name = session.scalars(
        sa.select(BatchSubject.name).where(BatchSubject.id == row.batch_subject_id)
    ).one()
    return ExamRow.of(row, name)


def cancel_exam(
    session: DbSession,
    *,
    lens: TeacherLens,
    exam_id: uuid.UUID,
    reason: str | None = None,
    now: dt.datetime | None = None,
) -> ExamRow:
    """Cancel an exam whose results are not published, and tell its families.

    **Idempotent.** Cancelling a cancelled exam returns it as it is: the
    first time and reason stand and nobody is told twice, so a retried
    tap cannot send a second round of messages.

    **The families' items are replaced, not added to.** Every
    ``exam_scheduled`` item for this exam is removed and an
    ``exam_cancelled`` item delivered, the way a corrected payment
    decision replaces the earlier decision's items: an inbox holding
    "exam on 20 April" beside "exam cancelled" asks the reader to work
    out which is current. Recipients are exactly those a new exam would
    reach today (:func:`deliver_to_families`), so a seat that has left
    or a link still pending hears nothing, as it heard nothing of the
    exam being scheduled. The preview carries the title and the ISO date,
    because the item outlives any later read of the exam.

    :param session: The session to work through
    :param lens: The teacher lens
    :param exam_id: The exam
    :param reason: The teacher's short note; blank is stored as none
    :param now: When it was cancelled; the current time by default
    :return: The cancelled exam
    :raises AuthorizationError: This lens does not reach the exam
    :raises ConflictError: Its results are published, or the batch is
        inactive
    """
    row = readable_exam(session, lens=lens, exam_id=exam_id)
    subject = session.scalars(
        sa.select(BatchSubject.name).where(BatchSubject.id == row.batch_subject_id)
    ).one()
    if row.cancelled_at is not None:
        return ExamRow.of(row, subject)
    if row.published_at is not None:
        raise ConflictError(code="EXAM_PUBLISHED", message_key="marks.exam.published")
    batch = _owned_active_batch(session, lens=lens, batch_id=row.batch_id)

    when = now or dt.datetime.now(tz=dt.UTC)
    row.cancelled_at = when
    row.cancellation_reason = (reason or "").strip() or None
    session.flush()
    remove_for_source(session, kind=EXAM_SCHEDULED, source_id=row.id)
    deliver_to_families(
        session,
        batch=batch,
        kind=EXAM_CANCELLED,
        source_id=row.id,
        preview=f"{row.title} · {row.date.isoformat()}",
        now=when,
    )
    session.commit()
    return ExamRow.of(row, subject)


def read_exam_row(
    session: DbSession,
    *,
    lens: TeacherLens,
    exam_id: uuid.UUID,
) -> ExamRow:
    """Read one exam with its subject name, for the results screen.

    ``readable_exam`` returns the row and checks the lens; this adds
    the subject name, which lives on a joined table and which
    ``ExamResponse`` carries. Written beside ``list_exams`` so the two
    cannot describe an exam differently.

    :param session: The session to read through
    :param lens: The teacher lens
    :param exam_id: The exam
    :return: The exam, with its subject
    :raises AuthorizationError: This lens does not reach the exam
    """
    exam = readable_exam(session, lens=lens, exam_id=exam_id)
    subject = session.scalars(
        sa.select(BatchSubject.name).where(BatchSubject.id == exam.batch_subject_id)
    ).one_or_none()
    return ExamRow.of(exam, subject or "")


def list_exams(
    session: DbSession,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
) -> list[ExamRow]:
    """List one batch's exams, oldest first, cancelled ones included.

    A cancelled exam stays in its place, flagged, because this is the
    list the teacher scheduled it on; see the module docstring.

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
    return [ExamRow.of(entry[0], entry[1]) for entry in rows]


def default_examiner(session: DbSession, *, batch_id: uuid.UUID) -> uuid.UUID | None:
    """Return the batch's one weekly teacher, when it has exactly one.

    :param session: The session to read through
    :param batch_id: The batch
    :return: That membership, or None for none or several
    """
    teachers = set(
        session.scalars(
            sa.select(ScheduleSlot.teacher_member_id).where(
                ScheduleSlot.batch_id == batch_id,
                ScheduleSlot.teacher_member_id.is_not(None),
            )
        )
    )
    return teachers.pop() if len(teachers) == 1 else None


def examiner_name(session: DbSession, member_id: uuid.UUID | None) -> str | None:
    """Read the name the centre typed for an examiner.

    :param session: The session to read through
    :param member_id: The examiner, or None
    :return: Their name, or None
    """
    if member_id is None:
        return None
    return session.scalar(
        sa.select(OwnerMember.display_name).where(OwnerMember.id == member_id)
    )


def set_examiner(
    session: DbSession,
    *,
    lens: TeacherLens,
    exam_id: uuid.UUID,
    examiner_member_id: uuid.UUID | None,
) -> ExamRow:
    """Name, change or clear an exam's examiner. Commits.

    :param session: The session to write through
    :param lens: The manager's lens on the centre
    :param exam_id: The exam
    :param examiner_member_id: The new examiner, or None to clear
    :return: The exam
    :raises AuthorizationError: Not this workspace's exam
    :raises ConflictError: A solo workspace, or the exam is cancelled
    :raises ValidationError: The examiner is not a live member here
    """
    exam = readable_exam(session, lens=lens, exam_id=exam_id)
    if exam.cancelled_at is not None:
        raise cancelled_refusal()
    centre_of(session, lens)
    check_assignment(
        session, lens=lens, teacher_member_id=examiner_member_id, room_id=None
    )
    exam.examiner_member_id = examiner_member_id
    subject = session.scalar(
        sa.select(BatchSubject.name).where(BatchSubject.id == exam.batch_subject_id)
    )
    session.commit()
    return ExamRow.of(exam, subject or "")
