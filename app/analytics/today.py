"""The teacher's Today screen (T1): money owed, today's classes, payments.

**One read for the whole screen**, assembled from reads that already
exist plus three single statements: the fee due dates for the owned
seats, today's sessions across the owned batches, and today's exams. No
query runs per seat or per batch.

**"Today" is Bangladesh's date.** The server stores and generates in
UTC, which is right for records and wrong for a screen titled "Today":
at 1 am in Dhaka it is still yesterday in UTC. Bangladesh keeps no
daylight saving, so a fixed UTC+6 offset is exact and needs no time
zone database in the image.

**"Overdue" is a server decision**: money still owing on a period whose
due date has passed. The client shows the figure and never compares a
due date with the clock itself.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.analytics.seats import ledger_for_seats, owned_seats
from app.authz.lenses import TeacherLens
from app.db.models import Batch, BatchSubject, Exam, FeeCycle
from app.db.models import Session as ClassSession
from app.fees.queue import QueueItem, verification_queue
from app.money import Money, derive

__all__ = [
    "DHAKA",
    "Outstanding",
    "TodayClass",
    "TodayView",
    "today_view",
]

#: Bangladesh Standard Time. No daylight saving, so a fixed offset.
DHAKA = dt.timezone(dt.timedelta(hours=6), name="Asia/Dhaka")

#: How many waiting payments the screen previews before "See all".
VERIFY_PREVIEW = 2


@dataclass(frozen=True, slots=True)
class Outstanding:
    """What students owe across every batch, and how much is late.

    :ivar total: Everything still owed
    :ivar overdue: The part owed on periods past their due date
    :ivar overdue_students: Seats with anything overdue
    :ivar batch_count: Batches with anything owing
    """

    total: Money
    overdue: Money
    overdue_students: int
    batch_count: int


@dataclass(frozen=True, slots=True)
class TodayClass:
    """One class today.

    :ivar session_id: The class
    :ivar batch_id: Its batch
    :ivar batch_name: The batch's name
    :ivar subject_name: The subject, where one is set
    :ivar start_time: When it starts
    :ivar end_time: When it ends, where set
    :ivar status: ``scheduled``, ``held`` or ``cancelled``
    :ivar topic: The logged topic, where one was written
    :ivar topic_logged: Whether a topic was written at all
    :ivar attendance_version: The version a roster write composes against
    :ivar topic_version: The version a topic write composes against
    :ivar is_next: The first class still to start
    :ivar starts_in_minutes: Minutes until it starts, or None once begun
    :ivar exam_id: An exam this batch sits today, where there is one
    :ivar exam_title: That exam's title
    """

    session_id: uuid.UUID
    batch_id: uuid.UUID
    batch_name: str
    subject_name: str | None
    start_time: dt.time
    end_time: dt.time | None
    status: str
    topic: str | None
    topic_logged: bool
    attendance_version: int
    topic_version: int
    is_next: bool
    starts_in_minutes: int | None
    exam_id: uuid.UUID | None
    exam_title: str | None


@dataclass(frozen=True, slots=True)
class TodayView:
    """Everything T1 shows.

    :ivar date: Today, in Bangladesh
    :ivar outstanding: Money owed and overdue
    :ivar classes: Today's classes, by start time
    :ivar to_verify_count: How many payments wait to be checked
    :ivar to_verify: The first few of them, oldest first
    :ivar has_batches: Whether the teacher has made a batch yet, so a
        first run shows how to start rather than three empty sections
    """

    date: dt.date
    outstanding: Outstanding
    classes: list[TodayClass]
    to_verify_count: int
    to_verify: list[QueueItem]
    has_batches: bool


def _due_dates(
    session: Session, seat_ids: list[uuid.UUID]
) -> dict[tuple[uuid.UUID, str], dt.date]:
    """Read every fee period's due date for these seats, in one statement.

    :param session: The session to read through
    :param seat_ids: The seats
    :return: ``(seat, period)`` to due date
    """
    if not seat_ids:
        return {}
    rows = session.execute(
        sa.select(FeeCycle.enrollment_id, FeeCycle.period, FeeCycle.due_date).where(
            FeeCycle.enrollment_id.in_(seat_ids)
        )
    ).all()
    return {(row[0], row[1]): row[2] for row in rows}


def _outstanding(session: Session, lens: TeacherLens, today: dt.date) -> Outstanding:
    """Total what is owed and what of it is past due.

    :param session: The session to read through
    :param lens: The teacher lens
    :param today: Bangladesh's date
    :return: The totals
    """
    seats = owned_seats(session, lens)
    ids = [seat.enrollment_id for seat in seats]
    ledger = ledger_for_seats(session, ids)
    due = _due_dates(session, ids)

    owed: list[Money] = []
    late: list[Money] = []
    late_seats = 0
    owing_batches: set[uuid.UUID] = set()
    for seat in seats:
        per_cycle = derive(ledger.get(seat.enrollment_id, [])).per_cycle
        seat_late = [
            balance
            for period, balance in per_cycle.items()
            if balance.is_positive()
            and (due_date := due.get((seat.enrollment_id, period))) is not None
            and due_date < today
        ]
        seat_owed = Money.sum(per_cycle.values())
        if seat_owed.is_positive():
            owed.append(seat_owed)
            owing_batches.add(seat.batch_id)
        if seat_late:
            late.extend(seat_late)
            late_seats += 1
    return Outstanding(
        total=Money.sum(owed),
        overdue=Money.sum(late),
        overdue_students=late_seats,
        batch_count=len(owing_batches),
    )


def _classes(session: Session, lens: TeacherLens, now: dt.datetime) -> list[TodayClass]:
    """Read today's classes across every owned batch, by start time.

    :param session: The session to read through
    :param lens: The teacher lens
    :param now: The present, in Bangladesh time
    :return: Today's classes
    """
    today = now.date()
    rows = session.execute(
        sa.select(ClassSession, Batch.name, BatchSubject.name)
        .join(Batch, Batch.id == ClassSession.batch_id)
        .outerjoin(BatchSubject, BatchSubject.id == ClassSession.batch_subject_id)
        .where(Batch.owner_id == lens.owner_id, ClassSession.date == today)
        .order_by(ClassSession.start_time, ClassSession.id)
    ).all()
    exams: dict[uuid.UUID, tuple[uuid.UUID, str]] = {}
    for exam_id, batch_id, title in session.execute(
        sa.select(Exam.id, Exam.batch_id, Exam.title)
        .join(Batch, Batch.id == Exam.batch_id)
        .where(Batch.owner_id == lens.owner_id, Exam.date == today)
        .order_by(Exam.created_at)
    ).all():
        exams.setdefault(batch_id, (exam_id, title))

    clock = now.replace(tzinfo=None).time()
    next_found = False
    classes: list[TodayClass] = []
    for row, batch_name, subject_name in rows:
        upcoming = row.status == "scheduled" and row.start_time > clock
        is_next = upcoming and not next_found
        next_found = next_found or is_next
        exam = exams.get(row.batch_id)
        classes.append(
            TodayClass(
                session_id=row.id,
                batch_id=row.batch_id,
                batch_name=batch_name,
                subject_name=subject_name,
                start_time=row.start_time,
                end_time=row.end_time,
                status=row.status,
                topic=row.topic,
                topic_logged=row.topic is not None,
                attendance_version=row.attendance_version,
                topic_version=row.topic_version,
                is_next=is_next,
                starts_in_minutes=_minutes_until(clock, row.start_time)
                if upcoming
                else None,
                exam_id=exam[0] if exam else None,
                exam_title=exam[1] if exam else None,
            )
        )
    return classes


def _minutes_until(clock: dt.time, start: dt.time) -> int:
    """Count whole minutes from now until a later time today.

    :param clock: The present time of day
    :param start: A later time of day
    :return: Minutes between them
    """
    today = dt.date(2000, 1, 1)
    gap = dt.datetime.combine(today, start) - dt.datetime.combine(today, clock)
    return int(gap.total_seconds() // 60)


def today_view(
    session: Session,
    *,
    lens: TeacherLens,
    now: dt.datetime | None = None,
) -> TodayView:
    """Assemble the Today screen for one teacher.

    :param session: The session to read through
    :param lens: The teacher lens
    :param now: The present; the real clock by default
    :return: The view
    """
    local = (now or dt.datetime.now(tz=dt.UTC)).astimezone(DHAKA)
    queue = verification_queue(session, lens=lens, now=local.astimezone(dt.UTC))
    return TodayView(
        date=local.date(),
        outstanding=_outstanding(session, lens, local.date()),
        classes=_classes(session, lens, local),
        to_verify_count=len(queue.pending),
        to_verify=queue.pending[:VERIFY_PREVIEW],
        has_batches=session.execute(
            sa.select(sa.exists().where(Batch.owner_id == lens.owner_id))
        ).scalar_one(),
    )
