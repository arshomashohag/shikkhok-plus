"""The month calendar: one batch's classes, as a teacher or a family sees them.

Every state here is a DECISION the server makes, in Bangladesh's time
[TC-9]: the phone renders ``today``, ``upcoming`` or ``not_recorded``
and never compares a date itself.

**Per class**, the first that holds wins: ``cancelled``; ``taken`` (the
class was held, including one recorded today); ``today``; ``upcoming``;
else ``not_recorded`` -- a past class nobody recorded. **Per day**, the
first of ``DAY_PRECEDENCE`` present among that day's classes.

**A family's ``mark`` is read from THEIR seat's own attendance row and
no other**, and is ``not_enrolled`` outside the seat's span, so a child
who joined mid-month is not shown as absent from classes that began
before them.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final, Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import Lens, TeacherLens
from app.db.models import Attendance, Batch, BatchSubject, Session
from app.errors import ValidationError
from app.fees.generation import seat_start
from app.local_time import DHAKA, bangladesh_now
from app.teaching.roster import readable_enrollment
from app.teaching.sessions import _owned_batch

__all__ = [
    "DAY_PRECEDENCE",
    "CalendarClass",
    "CalendarDay",
    "ClassState",
    "Mark",
    "MonthView",
    "family_month",
    "teacher_month",
]

ClassState = Literal["taken", "today", "upcoming", "not_recorded", "cancelled"]
Mark = Literal["present", "absent", "not_marked", "not_enrolled"]

#: The order in which a day's classes decide the day's state.
DAY_PRECEDENCE: Final = ("today", "upcoming", "not_recorded", "taken", "cancelled")


@dataclass(frozen=True)
class CalendarClass:
    """One class on the calendar.

    :ivar session_id: The class
    :ivar date: Its date
    :ivar start_time: When it starts
    :ivar end_time: When it ends, or None
    :ivar subject_name: The subject, or None
    :ivar state: Its decided state
    :ivar topic: Its topic, or None
    :ivar notes: Its notes, or None
    :ivar plannable: Whether a teacher may still plan its topics
    :ivar recordable: Whether a teacher may record it
    :ivar mark: A family's mark for it; None for a teacher
    :ivar topic_version: The topic log's version, to compose a write
    :ivar attendance_version: The roster's version, to compose a write
    """

    session_id: uuid.UUID
    date: dt.date
    start_time: dt.time
    end_time: dt.time | None
    subject_name: str | None
    state: ClassState
    topic: str | None
    notes: str | None
    plannable: bool
    recordable: bool
    mark: Mark | None
    topic_version: int
    attendance_version: int


@dataclass(frozen=True)
class CalendarDay:
    """A day that has at least one class.

    :ivar date: The day
    :ivar state: The day's decided state
    :ivar classes: Its classes, earliest first
    """

    date: dt.date
    state: ClassState
    classes: list[CalendarClass]


@dataclass(frozen=True)
class MonthView:
    """One month of a batch's classes.

    :ivar year: The year shown
    :ivar month: The month shown
    :ivar first_month: The earliest month readable, ``YYYY-MM``
    :ivar last_month: The latest month readable, ``YYYY-MM``
    :ivar days: Days with classes, in order
    :ivar served_at: When this was computed, Bangladesh time
    :ivar today: Bangladesh's date, so the phone never reads its own
        clock to mark today
    """

    year: int
    month: int
    first_month: str
    last_month: str
    days: list[CalendarDay]
    served_at: dt.datetime
    today: dt.date


@dataclass(frozen=True)
class _Seat:
    """The span a seat is enrolled for.

    :ivar enrollment_id: The seat
    :ivar start: Its first day
    :ivar inactive_from: The day it ended, or None
    """

    enrollment_id: uuid.UUID
    start: dt.date
    inactive_from: dt.date | None

    def covers(self, day: dt.date) -> bool:
        """Say whether the seat was enrolled on a day.

        :param day: The date
        :return: True when the day is in ``[start, inactive_from)``
        """
        if day < self.start:
            return False
        return self.inactive_from is None or day < self.inactive_from


def _month_label(year: int, month: int) -> str:
    """Format a month.

    :param year: The year
    :param month: The month
    :return: ``YYYY-MM``
    """
    return f"{year:04d}-{month:02d}"


def _check_range(
    batch: Batch, *, year: int, month: int, today: dt.date
) -> tuple[str, str]:
    """Refuse a month the batch has no classes to show for.

    :param batch: The batch
    :param year: The year asked for
    :param month: The month asked for
    :param today: Bangladesh's date
    :return: The first and last readable months
    :raises ValidationError: The month is outside the readable range
    """
    created = batch.created_at.astimezone(DHAKA)
    first = _month_label(created.year, created.month)
    last = _month_label(*_next_month(today.year, today.month))
    if not first <= _month_label(year, month) <= last:
        raise ValidationError(
            code="MONTH_OUT_OF_RANGE",
            message_key="teaching.calendar.month_out_of_range",
        )
    return first, last


def _next_month(year: int, month: int) -> tuple[int, int]:
    """Step one month forward.

    :param year: The year
    :param month: The month
    :return: The following month
    """
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _class_state(row: Session, *, today: dt.date) -> ClassState:
    """Decide one class's state.

    :param row: The class
    :param today: Bangladesh's date
    :return: Its state
    """
    if row.status == "cancelled":
        return "cancelled"
    if row.status == "held":
        return "taken"
    if row.date == today:
        return "today"
    if row.date > today:
        return "upcoming"
    return "not_recorded"


def _mark(seat: _Seat, row: Session, present: dict[uuid.UUID, bool]) -> Mark:
    """Decide a family's mark for one class.

    :param seat: The family's own seat
    :param row: The class
    :param present: This seat's attendance rows, by class
    :return: Their mark
    """
    if not seat.covers(row.date):
        return "not_enrolled"
    if row.id not in present:
        return "not_marked"
    return "present" if present[row.id] else "absent"


def _build(
    session: DbSession,
    *,
    batch: Batch,
    year: int,
    month: int,
    now: dt.datetime | None,
    seat: _Seat | None,
) -> MonthView:
    """Build a month for a batch, from either side.

    :param session: The session to read through
    :param batch: The batch, already authorized
    :param year: The year
    :param month: The month
    :param now: The clock; the real one by default
    :param seat: The family's seat, or None for a teacher
    :return: The view
    :raises ValidationError: The month is outside the readable range
    """
    moment = bangladesh_now(now)
    today = moment.date()
    first, last = _check_range(batch, year=year, month=month, today=today)
    start = dt.date(year, month, 1)
    after = dt.date(*_next_month(year, month), 1)

    rows = session.execute(
        sa.select(Session, BatchSubject.name)
        .outerjoin(BatchSubject, BatchSubject.id == Session.batch_subject_id)
        .where(
            Session.batch_id == batch.id,
            Session.date >= start,
            Session.date < after,
        )
        .order_by(Session.date, Session.start_time)
    ).all()

    present: dict[uuid.UUID, bool] = {}
    if seat is not None:
        marks = session.execute(
            sa.select(Attendance.session_id, Attendance.present).where(
                Attendance.enrollment_id == seat.enrollment_id,
                Attendance.session_id.in_([entry[0].id for entry in rows]),
            )
        ).all()
        present = {entry[0]: entry[1] for entry in marks}

    by_day: dict[dt.date, list[CalendarClass]] = {}
    for row, subject_name in rows:
        started = dt.datetime.combine(row.date, row.start_time, tzinfo=DHAKA) <= moment
        open_class = batch.active and row.status != "cancelled" and seat is None
        by_day.setdefault(row.date, []).append(
            CalendarClass(
                session_id=row.id,
                date=row.date,
                start_time=row.start_time,
                end_time=row.end_time,
                subject_name=subject_name,
                state=_class_state(row, today=today),
                topic=row.topic,
                notes=row.notes,
                plannable=open_class and row.status == "scheduled" and not started,
                # A class saved as covered before its start time stays
                # correctable: held is recorded, whatever the clock says.
                recordable=open_class and (started or row.status == "held"),
                mark=None if seat is None else _mark(seat, row, present),
                topic_version=row.topic_version,
                attendance_version=row.attendance_version,
            )
        )

    days = [
        CalendarDay(
            date=day,
            state=min((c.state for c in classes), key=DAY_PRECEDENCE.index),
            classes=classes,
        )
        for day, classes in by_day.items()
    ]
    return MonthView(
        year=year,
        month=month,
        first_month=first,
        last_month=last,
        days=days,
        served_at=moment,
        today=today,
    )


def teacher_month(
    session: DbSession,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
    year: int,
    month: int,
    now: dt.datetime | None = None,
) -> MonthView:
    """Read one month of a batch this teacher owns.

    :param session: The session to read through
    :param lens: The teacher lens
    :param batch_id: The batch
    :param year: The year
    :param month: The month, 1 to 12
    :param now: The clock; the real one by default
    :return: The month
    :raises AuthorizationError: This lens does not own the batch
    :raises ValidationError: The month is outside the readable range
    """
    batch = _owned_batch(session, lens=lens, batch_id=batch_id)
    return _build(session, batch=batch, year=year, month=month, now=now, seat=None)


def family_month(
    session: DbSession,
    *,
    lens: Lens,
    enrollment_id: uuid.UUID,
    year: int,
    month: int,
    now: dt.datetime | None = None,
) -> MonthView:
    """Read one month of a seat's batch, with that seat's own marks.

    :param session: The session to read through
    :param lens: The student or guardian lens
    :param enrollment_id: The seat
    :param year: The year
    :param month: The month, 1 to 12
    :param now: The clock; the real one by default
    :return: The month
    :raises AuthorizationError: This lens does not reach the seat
    :raises ValidationError: The month is outside the readable range
    """
    record = readable_enrollment(session, lens=lens, enrollment_id=enrollment_id)
    batch = session.get_one(Batch, record.batch_id)
    seat = _Seat(
        enrollment_id=record.id,
        start=seat_start(record.joined_on, record.created_at),
        inactive_from=record.inactive_from,
    )
    return _build(session, batch=batch, year=year, month=month, now=now, seat=seat)
