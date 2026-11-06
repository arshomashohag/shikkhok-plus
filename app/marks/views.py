"""Lens-scoped marksheet and progress reads [BR5.2, BR5.4, BR6.6].

**The toggle is an authorization control, not a display preference**
[§ 4.5]. When ``Batch.marksheet_visible`` is false, **no marksheet is
returned at all** to any student or guardian lens -- not an empty one,
not one with the comparison fields nulled. An empty marksheet still
discloses that exams exist and how many, and returning an empty
collection is the kinder-looking code, which is why it is the shape an
implementation reaches by habit.

**The column is already built and non-null.** D4 adds no migration and
no default for it; AC4.2.1's "defaults to on" is satisfied by the
existing batch-creation path, and a test asserts this unit's migration
touches no ``batch`` column.

**Every aggregate is scoped to ONE batch** [BR6.5, § 4.4]. A
cross-batch aggregate would disclose the existence and shape of a
batch the viewer is not enrolled in.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import ExaminerLens, GuardianLens, Lens, StudentLens, TeacherLens
from app.db.models import Batch, BatchSubject, Enrollment, Exam, Mark, Notification
from app.errors import ConflictError
from app.marks.entry import announce_result, writable_exam
from app.marks.marksheet import Marksheet, Published, compute_marksheet
from app.marks.results import SeatResult, results_for_exam
from app.notifications.inbox import MARKS_AVAILABLE
from app.teaching.roster import readable_enrollment, refuse

__all__ = [
    "ProgressEntry",
    "SeatMarksheet",
    "guardian_progress",
    "publish_exam",
    "seat_marksheet",
    "set_marksheet_visible",
]


@dataclass(frozen=True, slots=True)
class SeatMarksheet:
    """One seat's marksheet with the heading the screen shows above it.

    The heading travels with the sheet so the screen can be opened from
    any list -- progress, a notification, the teacher's results --
    without each caller having to carry the exam's title along.

    :ivar exam_title: The exam's title
    :ivar total_marks: Its denominator
    :ivar viewer_result_state: The viewer's own result, one of the four
        states, so an absence reads as an absence and not as no mark
    :ivar sheet: The published comparison, or the suppressed sheet
    """

    exam_title: str
    total_marks: int
    viewer_result_state: str
    sheet: Marksheet


@dataclass(frozen=True, slots=True)
class ProgressEntry:
    """One exam in a child's progress series [BR6.6].

    **An absence carries no numeric value at all**, rather than a
    zero. An absence plotted as zero shows a collapse in performance
    that did not happen, which is the single most alarming thing this
    screen can say wrongly.

    :ivar exam_id: The exam
    :ivar title: Its title
    :ivar date: When it was sat
    :ivar total_marks: Its denominator
    :ivar result_state: One of the four states
    :ivar marks: The number, or None for the other three states
    :ivar subject_name: Which subject the exam was in
    :ivar rank: The viewer's rank among marked results, only where the
        exam's marksheet publishes its comparison [BR6.4]; else None
    :ivar ranked_out_of: How many marked results the rank is among, on
        the same condition
    :ivar batch_average: The batch's average mark, on the same condition
    """

    exam_id: uuid.UUID
    title: str
    date: dt.date
    total_marks: int
    result_state: str
    marks: float | None
    subject_name: str | None = None
    rank: int | None = None
    ranked_out_of: int | None = None
    batch_average: float | None = None


def _marksheet_is_visible(session: DbSession, *, batch_id: uuid.UUID) -> bool:
    """Read the batch's existing toggle.

    :param session: The session to read through
    :param batch_id: The batch
    :return: Whether families may see a marksheet
    """
    return bool(
        session.scalars(
            sa.select(Batch.marksheet_visible).where(Batch.id == batch_id)
        ).one()
    )


def seat_marksheet(
    session: DbSession,
    *,
    lens: Lens,
    enrollment_id: uuid.UUID,
    exam_id: uuid.UUID,
) -> SeatMarksheet:
    """Compute one seat's marksheet for one exam [BR6.2, BR5.4].

    **The refusal when the toggle is off is the shared
    ``NOT_AVAILABLE``**, and nothing at all is returned: not an empty
    marksheet, not one with the comparison nulled. The teacher's own
    view is unaffected, because the toggle controls what FAMILIES see.

    :param session: The session to read through
    :param lens: The lens asking; student and guardian are scoped by
        their own decision column
    :param enrollment_id: The seat whose marksheet this is
    :param exam_id: The exam
    :return: The marksheet with its heading
    :raises AuthorizationError: This lens does not reach the seat, the
        exam is not that seat's batch's, or the toggle is off
    """
    seat = readable_enrollment(session, lens=lens, enrollment_id=enrollment_id)

    exam = session.scalars(
        sa.select(Exam).where(Exam.id == exam_id, Exam.batch_id == seat.batch_id)
    ).one_or_none()
    if exam is None:
        # Scoped to the SEAT's batch, so an exam id from elsewhere is
        # unreachable rather than merely mismatched -- and the refusal
        # does not say which.
        raise refuse()

    # The toggle, for FAMILY lenses only. A teacher reads their own
    # batch's marksheet whatever the toggle says.
    if not isinstance(lens, TeacherLens) and not _marksheet_is_visible(
        session, batch_id=seat.batch_id
    ):
        raise refuse()
    # **A draft is the teacher's own** (decided 2026-11-05): a family
    # reads an exam's marksheet only once its results are published,
    # and is refused the same way as for an exam that is not theirs.
    if not isinstance(lens, TeacherLens) and exam.published_at is None:
        raise refuse()

    results = results_for_exam(session, exam=exam)
    viewer = next(
        (row for row in results if row.enrollment_id == enrollment_id),
        SeatResult(
            enrollment_id=enrollment_id,
            display_name=seat.display_name,
            result_state="not_entered",
            marks=None,
        ),
    )
    return SeatMarksheet(
        exam_title=exam.title,
        total_marks=exam.total_marks,
        viewer_result_state=viewer.result_state,
        sheet=compute_marksheet(results, total_marks=exam.total_marks, viewer=viewer),
    )


def set_marksheet_visible(
    session: DbSession,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
    visible: bool,
) -> bool:
    """Write the toggle, through the one route that may [BR5.4].

    **No migration and no default** -- the column is already built and
    non-null. This is the unit that gives it an effect.

    :param session: The session to work through
    :param lens: The teacher lens; only the batch's owner may write it
    :param batch_id: The batch
    :param visible: Whether families may see a marksheet
    :return: The value now in force
    :raises AuthorizationError: This lens does not own the batch
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

    was_visible = row.marksheet_visible
    row.marksheet_visible = visible
    session.flush()
    if visible and not was_visible:
        _announce_held_results(session, batch_id=batch_id)
    session.commit()
    return row.marksheet_visible


def _announce_held_results(session: DbSession, *, batch_id: uuid.UUID) -> None:
    """Tell families about results entered while the sheet was hidden.

    Every seat with a live result on an exam of the batch is told once
    per exam: a seat that already has the item is skipped, so showing,
    hiding and showing again adds nothing. Does not commit.

    :param session: The caller's session
    :param batch_id: The batch whose sheet was just shown
    :return: None
    """
    now = dt.datetime.now(tz=dt.UTC)
    pairs = session.execute(
        sa.select(Exam, Mark.enrollment_id)
        .join(Mark, Mark.exam_id == Exam.id)
        .where(
            Exam.batch_id == batch_id,
            Exam.published_at.is_not(None),
            Mark.superseded_by_id.is_(None),
        )
        .order_by(Exam.id, Mark.enrollment_id)
    ).all()
    for exam, enrollment_id in pairs:
        already = session.scalar(
            sa.select(sa.func.count())
            .select_from(Notification)
            .where(
                Notification.kind == MARKS_AVAILABLE,
                Notification.source_id == exam.id,
                Notification.enrollment_id == enrollment_id,
            )
        )
        if not already:
            announce_result(session, exam=exam, enrollment_id=enrollment_id, now=now)


def guardian_progress(
    session: DbSession,
    *,
    lens: GuardianLens | StudentLens,
    enrollment_id: uuid.UUID,
) -> list[ProgressEntry]:
    """Return one child's results across exams, in date order [BR6.6].

    **Ordered by exam date IN THE QUERY**, never by the client. The
    server sends decisions, not inputs to decisions [TC-9, D-31], and
    a client sorting a domain list is one of the five erosion paths
    the layer-boundary rule names.

    **An absence contributes no numeric value**, which is the rule's
    whole content: an absence plotted as zero shows a collapse in
    performance that did not happen.

    :param session: The session to read through
    :param lens: The guardian or student lens
    :param enrollment_id: The child's seat
    :return: One entry per exam, oldest first
    :raises AuthorizationError: This lens does not reach the seat, or
        the batch's marksheet toggle is off
    """
    seat = readable_enrollment(session, lens=lens, enrollment_id=enrollment_id)

    if not _marksheet_is_visible(session, batch_id=seat.batch_id):
        raise refuse()

    rows = session.execute(
        sa.select(
            Exam.id,
            Exam.title,
            Exam.date,
            Exam.total_marks,
            Mark.result_state,
            Mark.marks,
            Enrollment.joined_on,
            BatchSubject.name,
        )
        .select_from(Exam)
        .join(BatchSubject, BatchSubject.id == Exam.batch_subject_id)
        .outerjoin(
            Mark,
            sa.and_(
                Mark.exam_id == Exam.id,
                Mark.enrollment_id == enrollment_id,
                Mark.superseded_by_id.is_(None),
            ),
        )
        .join(Enrollment, Enrollment.id == enrollment_id)
        # Published exams only (decided 2026-11-05): a family never reads
        # a draft's marks, nor learns from a gap that one exists.
        .where(Exam.batch_id == seat.batch_id, Exam.published_at.is_not(None))
        # The ORDER is the server's decision, asserted in the response.
        .order_by(Exam.date, Exam.id)
    ).all()

    entries: list[ProgressEntry] = []
    for exam_id, title, date, total, state, marks, joined_on, subject in rows:
        if state is None:
            # The same derivation results.py performs, and for the
            # same reason: a seat that joined later could not have sat
            # the exam and must never read as an absence.
            derived = (
                "joined_after"
                if joined_on is not None and joined_on > date
                else "not_entered"
            )
            entries.append(
                ProgressEntry(
                    exam_id=exam_id,
                    title=title,
                    date=date,
                    total_marks=total,
                    result_state=derived,
                    marks=None,
                    subject_name=subject,
                )
            )
            continue
        rank, out_of, average = (
            _published_rank(session, exam_id=exam_id, enrollment_id=enrollment_id)
            if state == "marked"
            else (None, None, None)
        )
        entries.append(
            ProgressEntry(
                exam_id=exam_id,
                title=title,
                date=date,
                total_marks=total,
                result_state=state,
                marks=marks,
                subject_name=subject,
                rank=rank,
                ranked_out_of=out_of,
                batch_average=average,
            )
        )
    return entries


def _published_rank(
    session: DbSession, *, exam_id: uuid.UUID, enrollment_id: uuid.UUID
) -> tuple[int | None, int | None, float | None]:
    """Return a seat's rank, field size and the average, where published.

    The same computation the marksheet itself makes, so the two cannot
    disagree: a suppressed marksheet discloses no rank here either.

    :param session: The session to read through
    :param exam_id: The exam, already reached by the caller's lens
    :param enrollment_id: The seat
    :return: Rank, how many it is among and the average, or all None
    """
    exam = session.get(Exam, exam_id)
    if exam is None:
        return None, None, None
    results = results_for_exam(session, exam=exam)
    viewer = next((row for row in results if row.enrollment_id == enrollment_id), None)
    if viewer is None:
        return None, None, None
    sheet = compute_marksheet(results, total_marks=exam.total_marks, viewer=viewer)
    if not isinstance(sheet, Published) or sheet.viewer_rank is None:
        return None, None, None
    return sheet.viewer_rank, sheet.marked_count, sheet.average


def publish_exam(
    session: DbSession,
    *,
    lens: TeacherLens | ExaminerLens,
    exam_id: uuid.UUID,
) -> None:
    """Publish an exam's results to its students and guardians.

    **Draft, review, publish** (decided 2026-11-05). Marks are the
    teacher's own while they enter and review them; publishing is the
    one moment families can read them, and every seat with a result is
    told at once, as the marksheet toggle allows. Publishing again is a
    no-op, and a correction after it is read at once but announced to
    nobody, as a correction always was.

    **Refused while any seat that could have sat it has no result**, so
    a family never reads "not entered" beside a published sheet. An
    absence is a result and counts.

    :param session: The session to write through
    :param lens: The teacher lens
    :param exam_id: The exam
    :return: None
    :raises AuthorizationError: This lens does not reach the exam
    :raises ConflictError: The batch is inactive, or a seat still has
        no result
    """
    exam = writable_exam(session, lens=lens, exam_id=exam_id)
    if exam.published_at is not None:
        return
    results = results_for_exam(session, exam=exam)
    missing = sum(1 for result in results if result.result_state == "not_entered")
    if missing:
        raise ConflictError(
            code="MARKS_INCOMPLETE",
            message_key="marks.publish.incomplete",
            details={"not_entered": str(missing)},
        )
    now = dt.datetime.now(tz=dt.UTC)
    exam.published_at = now
    session.flush()
    for result in results:
        if result.result_state in ("marked", "absent"):
            announce_result(
                session, exam=exam, enrollment_id=result.enrollment_id, now=now
            )
    session.commit()
