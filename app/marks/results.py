"""The four result states, two of them derived [BR4.3].

**``not_entered`` and ``joined_after`` are derived from facts rather
than typed by the teacher.** A seat with no live ``Mark`` row is
``joined_after`` when the enrollment's ``joined_on`` is after the
exam's date, and ``not_entered`` otherwise.

The conflation this prevents is specific and bad in two directions:
treating "I have not marked this yet" as "they were absent" publishes
an absence the teacher never recorded, on a **shared** marksheet, which
makes it visible to the whole batch; and a student who joined in May
showing as absent from an April exam reads as a record of truancy.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import Enrollment, Exam
from app.marks.entry import live_marks_for_exam
from app.marks.exams import ExamRow, list_exams, readable_exam

__all__ = [
    "ExamProgress",
    "SeatResult",
    "exam_results",
    "list_exam_progress",
    "progress_of",
    "results_for_exam",
]

#: The states a teacher has typed; the other two are derived.
ENTERED_STATES = frozenset({"marked", "absent"})


@dataclass(frozen=True, slots=True)
class SeatResult:
    """One seat's result in one exam, as its teacher sees it.

    Carries the **enrollment id and the teacher-typed display name**,
    never a global account key [BR5.3].

    :ivar enrollment_id: The teacher-facing key
    :ivar display_name: The teacher-typed name
    :ivar result_state: One of the four states
    :ivar marks: The number, or None for the other three states
    """

    enrollment_id: uuid.UUID
    display_name: str
    result_state: str
    marks: int | None


def exam_results(
    session: DbSession,
    *,
    lens: TeacherLens,
    exam_id: uuid.UUID,
) -> list[SeatResult]:
    """Return every batch seat's result for one exam [BR4.3].

    A seat that had already left, or whose student link is declined,
    does not appear. A seat that joined AFTER the exam does appear,
    carrying ``joined_after`` -- see :func:`results_for_exam`.

    :param session: The session to read through
    :param lens: The teacher lens
    :param exam_id: The exam
    :return: One row per seat, ordered by the teacher-typed name
    :raises AuthorizationError: This lens does not reach the exam
    """
    exam = readable_exam(session, lens=lens, exam_id=exam_id)
    return results_for_exam(session, exam=exam)


def results_for_exam(session: DbSession, *, exam: Exam) -> list[SeatResult]:
    """Build the four-state result list for an already-scoped exam.

    Split from :func:`exam_results` so the marksheet can reuse it
    under a student or guardian lens without re-resolving a teacher
    one -- and so there is exactly ONE derivation of the two computed
    states rather than a second copy that can disagree.

    :param session: The session to read through
    :param exam: The exam, already authorized
    :return: One row per roster seat
    """
    # **NOT BR1.5's roster predicate**, and the difference is the
    # point. That predicate excludes a seat whose `joined_on` is after
    # the date, which is right for attendance -- a student is never
    # marked against a class they could not attend. Applied here it
    # would make `joined_after` UNREACHABLE: the state exists exactly
    # to say "this seat is on the batch and could not have sat this
    # exam" [AC4.1.5], so the seat has to be in the list to carry it.
    #
    # What IS shared is the other two clauses: a declined seat and one
    # that had already left are excluded, for BR1.5's own reasons.
    seats = session.execute(
        sa.select(
            Enrollment.id,
            Enrollment.display_name,
            Enrollment.joined_on,
        )
        .where(
            Enrollment.batch_id == exam.batch_id,
            Enrollment.student_decision != "declined",
            sa.or_(
                Enrollment.inactive_from.is_(None),
                Enrollment.inactive_from > exam.date,
            ),
        )
        .order_by(Enrollment.display_name, Enrollment.id)
    ).all()

    recorded = {
        entry[0]: (entry[1], entry[2])
        for entry in live_marks_for_exam(session, exam_id=exam.id)
    }

    results: list[SeatResult] = []
    for seat_id, display_name, joined_on in seats:
        if seat_id in recorded:
            state, marks = recorded[seat_id]
        elif joined_on is not None and joined_on > exam.date:
            # Could not have sat it. Never `absent`, which would read
            # as a record of truancy.
            state, marks = "joined_after", None
        else:
            # The teacher has not reached this seat yet. Never
            # `absent`, which would publish an absence nobody
            # recorded on a shared marksheet.
            state, marks = "not_entered", None
        results.append(
            SeatResult(
                enrollment_id=seat_id,
                display_name=display_name,
                result_state=state,
                marks=marks,
            )
        )
    return results


@dataclass(frozen=True, slots=True)
class ExamProgress:
    """One exam with how far its marking has got.

    :ivar exam: The exam
    :ivar entered_count: Seats with a mark or an absence entered
    :ivar expected_count: Seats that could have sat it, which leaves
        out a seat that joined after the exam date
    """

    exam: ExamRow
    entered_count: int
    expected_count: int


def list_exam_progress(
    session: DbSession,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
) -> list[ExamProgress]:
    """List a batch's exams, each with its marking progress.

    Counted from :func:`results_for_exam`, so the list and the results
    screen cannot disagree about which seats are still to mark.

    :param session: The session to read through
    :param lens: The teacher lens
    :param batch_id: The batch
    :return: One entry per exam, oldest first
    :raises AuthorizationError: This lens does not own the batch
    """
    progress: list[ExamProgress] = []
    for row in list_exams(session, lens=lens, batch_id=batch_id):
        exam = session.get(Exam, row.exam_id)
        if exam is None:
            continue
        progress.append(progress_of(row, results_for_exam(session, exam=exam)))
    return progress


def progress_of(exam: ExamRow, results: list[SeatResult]) -> ExamProgress:
    """Count how far one exam's marking has got.

    :param exam: The exam
    :param results: Its four-state results
    :return: The exam with its counts
    """
    states = [result.result_state for result in results]
    return ExamProgress(
        exam=exam,
        entered_count=sum(state in ENTERED_STATES for state in states),
        expected_count=sum(state != "joined_after" for state in states),
    )
