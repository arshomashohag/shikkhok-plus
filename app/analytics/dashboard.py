"""One seat's progress dashboard, the same for teacher, student and guardian.

Attendance, exam results and fee months over a range of months, with the
percentages and the direction decided here so the phone only draws them
[TC-9].

**Percentages are whole numbers rounded half up, in integer arithmetic.**
They are shares of a count, not money, so they live here and not in
``app.money``. A percentage of nothing is ``None``, never zero: a month
with no held class has no attendance, which is not an attendance of nil.

**The comparison figures are numbers and never names.** The batch
average and highest mark are sent only with at least three marked seats
so a figure cannot be traced to a person, and a family lens gets them
only where the teacher published the marksheet.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final, Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.analytics.collections import months_ending
from app.authz.lenses import Lens, TeacherLens
from app.db.models import Attendance, Batch, BatchSubject, Exam
from app.db.models import Session as ClassSession
from app.fees.balances import derive_for_enrollment
from app.fees.generation import seat_start
from app.fees.views import MonthStateRow, month_strip
from app.local_time import bangladesh_today
from app.marks.results import results_for_exam
from app.marks.summary import Direction, summarise
from app.marks.views import ProgressEntry
from app.money import Money
from app.teaching.roster import readable_enrollment

__all__ = [
    "AttendanceMonth",
    "DashboardRange",
    "DashboardTiles",
    "ExamPoint",
    "SeatDashboard",
    "percent_of",
    "seat_dashboard",
]

DashboardRange = Literal["6m", "year", "all"]

RECENT_MONTHS: Final[int] = 6
MIN_MARKED_FOR_COMPARISON: Final[int] = 3


def percent_of(part: int, whole: int) -> int | None:
    """Give ``part`` as a whole percent of ``whole``, rounded half up.

    :param part: The numerator
    :param whole: The denominator
    :return: The percent, or None where ``whole`` is zero
    """
    if whole == 0:
        return None
    return (part * 100 + whole // 2) // whole


def _mean_half_up(values: list[int]) -> int | None:
    """Give the mean of whole numbers, rounded half up.

    :param values: The numbers
    :return: The mean, or None for no numbers
    """
    if not values:
        return None
    return (2 * sum(values) + len(values)) // (2 * len(values))


@dataclass(frozen=True, slots=True)
class DashboardTiles:
    """The three headline figures.

    :ivar attendance_percent: Present as a percent of held, or None
    :ivar present: Held classes attended
    :ivar held: Classes held since the seat began, within the range
    :ivar exam_average_percent: Mean of the seat's own exam percents
    :ivar direction: Which way the latest run of results went, or None
    :ivar owed: What the seat owes now
    """

    attendance_percent: int | None
    present: int
    held: int
    exam_average_percent: int | None
    direction: Direction | None
    owed: Money


@dataclass(frozen=True, slots=True)
class AttendanceMonth:
    """One month of attendance.

    :ivar period: The month, as ``YYYY-MM``
    :ivar held: Classes held
    :ivar present: Classes attended
    :ivar percent: Present as a percent of held, or None
    :ivar in_progress: The month contains today
    """

    period: str
    held: int
    present: int
    percent: int | None
    in_progress: bool


@dataclass(frozen=True, slots=True)
class ExamPoint:
    """One exam on the chart.

    :ivar exam_id: The exam
    :ivar title: Its title
    :ivar date: When it was sat
    :ivar subject: The subject, if any
    :ivar marks: The seat's mark, or None for an absence
    :ivar total: The exam's denominator
    :ivar percent: The seat's mark as a whole percent, or None
    :ivar batch_average: Mean mark of the seats with a mark, or None
    :ivar batch_highest: Highest mark, or None
    """

    exam_id: uuid.UUID
    title: str
    date: dt.date
    subject: str | None
    marks: int | None
    total: int
    percent: int | None
    batch_average: int | None
    batch_highest: int | None


@dataclass(frozen=True, slots=True)
class SeatDashboard:
    """Everything the dashboard draws for one seat.

    :ivar tiles: The headline figures
    :ivar attendance_by_month: Oldest first, ending at the current month
    :ivar exams: Oldest first
    :ivar fee_months: The fee strip over the same months
    """

    tiles: DashboardTiles
    attendance_by_month: list[AttendanceMonth]
    exams: list[ExamPoint]
    fee_months: list[MonthStateRow]


def _period_of(day: dt.date) -> str:
    """Name the month of a date.

    :param day: The date
    :return: ``YYYY-MM``
    """
    return f"{day.year:04d}-{day.month:02d}"


def _window(range_: DashboardRange, today: dt.date, start: dt.date) -> list[str]:
    """List the months a range covers.

    :param range_: ``6m``, ``year`` or ``all``
    :param today: Bangladesh's date
    :param start: The seat's first day
    :return: Period keys, oldest first, ending with today's month
    """
    if range_ == "6m":
        return months_ending(today, RECENT_MONTHS)
    if range_ == "year":
        return months_ending(today, today.month)
    first = min(start, today)
    count = (today.year - first.year) * 12 + today.month - first.month + 1
    return months_ending(today, count)


def _first_day(period: str) -> dt.date:
    """Give the first day of a month.

    :param period: ``YYYY-MM``
    :return: Its first day
    """
    return dt.date(int(period[:4]), int(period[5:7]), 1)


def _attendance(
    session: DbSession,
    *,
    batch_id: uuid.UUID,
    enrollment_id: uuid.UUID,
    window: list[str],
    since: dt.date,
    today: dt.date,
) -> list[AttendanceMonth]:
    """Count held classes and attendance per month.

    :param session: The session to read through
    :param batch_id: The seat's batch
    :param enrollment_id: The seat
    :param window: Period keys, oldest first
    :param since: The earliest date counted
    :param today: Bangladesh's date
    :return: One row per month of the window
    """
    rows = session.execute(
        sa.select(ClassSession.date, Attendance.present)
        .outerjoin(
            Attendance,
            sa.and_(
                Attendance.session_id == ClassSession.id,
                Attendance.enrollment_id == enrollment_id,
            ),
        )
        .where(
            ClassSession.batch_id == batch_id,
            ClassSession.status == "held",
            ClassSession.date >= since,
        )
    ).all()
    held: dict[str, int] = dict.fromkeys(window, 0)
    present: dict[str, int] = dict.fromkeys(window, 0)
    for date, was_present in rows:
        period = _period_of(date)
        if period in held:
            held[period] += 1
            present[period] += 1 if was_present else 0
    current = _period_of(today)
    return [
        AttendanceMonth(
            period=period,
            held=held[period],
            present=present[period],
            percent=percent_of(present[period], held[period]),
            in_progress=period == current,
        )
        for period in window
    ]


def _exams(
    session: DbSession,
    *,
    batch_id: uuid.UUID,
    enrollment_id: uuid.UUID,
    first_day: dt.date,
    today: dt.date,
    show_comparison: bool,
) -> list[ExamPoint]:
    """Build the seat's exam points inside a date range.

    :param session: The session to read through
    :param batch_id: The seat's batch
    :param enrollment_id: The seat
    :param first_day: The earliest exam date
    :param today: Bangladesh's date
    :param show_comparison: Whether this lens may see average and highest
    :return: Exams the seat sat or missed, oldest first
    """
    rows = session.execute(
        sa.select(Exam, BatchSubject.name)
        .join(BatchSubject, BatchSubject.id == Exam.batch_subject_id)
        .where(Exam.batch_id == batch_id, Exam.date >= first_day, Exam.date <= today)
        .order_by(Exam.date, Exam.id)
    ).all()
    points: list[ExamPoint] = []
    for exam, subject in rows:
        results = results_for_exam(session, exam=exam)
        own = next((r for r in results if r.enrollment_id == enrollment_id), None)
        if own is None or own.result_state not in ("marked", "absent"):
            continue
        marked = [r.marks for r in results if r.marks is not None]
        comparable = show_comparison and len(marked) >= MIN_MARKED_FOR_COMPARISON
        points.append(
            ExamPoint(
                exam_id=exam.id,
                title=exam.title,
                date=exam.date,
                subject=subject,
                marks=own.marks,
                total=exam.total_marks,
                percent=(
                    None
                    if own.marks is None
                    else percent_of(own.marks, exam.total_marks)
                ),
                batch_average=_mean_half_up(marked) if comparable else None,
                batch_highest=max(marked) if comparable else None,
            )
        )
    return points


def seat_dashboard(
    session: DbSession,
    *,
    lens: Lens,
    enrollment_id: uuid.UUID,
    range_: DashboardRange,
    today: dt.date | None = None,
) -> SeatDashboard:
    """Build one seat's dashboard for the lens asking.

    :param session: The session to read through
    :param lens: Teacher, student or guardian lens
    :param enrollment_id: The seat
    :param range_: ``6m``, ``year`` or ``all``
    :param today: Bangladesh's date by default
    :return: The tiles and the three series
    :raises AuthorizationError: The lens does not reach the seat
    """
    seat = readable_enrollment(session, lens=lens, enrollment_id=enrollment_id)
    day = today or bangladesh_today()
    start = seat_start(seat.joined_on, seat.created_at)
    window = _window(range_, day, start)
    first_day = _first_day(window[0])

    attendance = _attendance(
        session,
        batch_id=seat.batch_id,
        enrollment_id=enrollment_id,
        window=window,
        since=max(start, first_day),
        today=day,
    )
    published = isinstance(lens, TeacherLens) or bool(
        session.scalars(
            sa.select(Batch.marksheet_visible).where(Batch.id == seat.batch_id)
        ).one()
    )
    exams = _exams(
        session,
        batch_id=seat.batch_id,
        enrollment_id=enrollment_id,
        first_day=first_day,
        today=day,
        show_comparison=published,
    )
    held = sum(month.held for month in attendance)
    present = sum(month.present for month in attendance)
    summary = summarise(
        [
            ProgressEntry(
                exam_id=point.exam_id,
                title=point.title,
                date=point.date,
                total_marks=point.total,
                result_state="marked",
                marks=point.marks,
            )
            for point in exams
            if point.marks is not None
        ]
    )
    tiles = DashboardTiles(
        attendance_percent=percent_of(present, held),
        present=present,
        held=held,
        exam_average_percent=_mean_half_up(
            [point.percent for point in exams if point.percent is not None]
        ),
        direction=None if summary is None else summary.direction,
        owed=derive_for_enrollment(session, enrollment_id).total_outstanding,
    )
    return SeatDashboard(
        tiles=tiles,
        attendance_by_month=attendance,
        exams=exams,
        fee_months=month_strip(session, enrollment_id, window),
    )
