"""A batch's next classes: when, how soon, and whether one has moved.

S1 shows "Next class · in 35 min" and "Today moved to 7:30 pm"; S2 shows
"Then Mon 19 Oct, Wed 21 Oct (moved to 6:00 pm)". Each is a comparison
of dates and times, so it is made here, in Bangladesh's time, and the
phone renders it [TC-9].

**Next** means scheduled and not yet started: a class earlier today
that has begun is past, and a cancelled one is not a class.

**Moved** means a recurring class whose start no longer matches the
weekly slot for its weekday -- the teacher rescheduled it. An extra,
one-off class is not "moved"; it never had a usual time.

Two statements for any number of batches: the classes and the slots.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.db.models import BatchSubject, ScheduleSlot, Session
from app.local_time import DHAKA, bangladesh_now

__all__ = ["UpcomingSession", "upcoming_sessions"]

#: How many coming classes each batch reports: the next and two after.
COMING: Final[int] = 3


@dataclass(frozen=True, slots=True)
class UpcomingSession:
    """One class still to come.

    :ivar date: Its date
    :ivar start_time: When it starts
    :ivar end_time: When it ends, if set
    :ivar starts_in_minutes: Minutes until it starts when that is today,
        else None
    :ivar moved: Whether it was moved from its usual time
    :ivar subject_name: What it teaches, if set
    """

    date: dt.date
    start_time: dt.time
    end_time: dt.time | None
    starts_in_minutes: int | None
    moved: bool
    subject_name: str | None


def upcoming_sessions(
    session: DbSession,
    *,
    batch_ids: list[uuid.UUID],
    now: dt.datetime | None = None,
) -> dict[uuid.UUID, list[UpcomingSession]]:
    """List each batch's next classes, soonest first.

    The caller has already established that the lens reaches these
    batches; this reads only what they schedule.

    :param session: The session to read through
    :param batch_ids: The batches
    :param now: The present, Bangladesh's by default
    :return: Up to three coming classes per batch; every batch present
    """
    at = (now or bangladesh_now()).astimezone(DHAKA)
    today, clock = at.date(), at.time().replace(tzinfo=None)
    found: dict[uuid.UUID, list[UpcomingSession]] = {key: [] for key in batch_ids}
    if not batch_ids:
        return found

    usual: dict[uuid.UUID, dict[int, set[dt.time]]] = {key: {} for key in batch_ids}
    for batch_id, weekday, start in session.execute(
        sa.select(
            ScheduleSlot.batch_id, ScheduleSlot.weekday, ScheduleSlot.start_time
        ).where(ScheduleSlot.batch_id.in_(batch_ids))
    ):
        usual[batch_id].setdefault(weekday, set()).add(start)

    rows = session.execute(
        sa.select(
            Session.batch_id,
            Session.date,
            Session.start_time,
            Session.end_time,
            Session.origin,
            BatchSubject.name,
        )
        .outerjoin(BatchSubject, BatchSubject.id == Session.batch_subject_id)
        .where(
            Session.batch_id.in_(batch_ids),
            Session.status == "scheduled",
            sa.or_(
                Session.date > today,
                sa.and_(Session.date == today, Session.start_time > clock),
            ),
        )
        .order_by(Session.date, Session.start_time, Session.id)
    ).all()

    for batch_id, day, start, end, origin, subject in rows:
        if len(found[batch_id]) >= COMING:
            continue
        slots = usual[batch_id].get(day.weekday(), set())
        found[batch_id].append(
            UpcomingSession(
                date=day,
                start_time=start,
                end_time=end,
                starts_in_minutes=_minutes_until(start, clock)
                if day == today
                else None,
                moved=origin == "recurrence" and start not in slots,
                subject_name=subject,
            )
        )
    return found


def _minutes_until(start: dt.time, clock: dt.time) -> int:
    """Whole minutes from now until a later time today.

    :param start: The later time
    :param clock: Now
    :return: The minutes between them
    """
    return (start.hour * 60 + start.minute) - (clock.hour * 60 + clock.minute)
