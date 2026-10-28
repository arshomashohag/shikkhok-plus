"""A student's next classes: when, how soon, and whether one moved.

**Written before the module existed.** S1 reads "Next class · in 35 min,
Today, 4:00 pm" and "Today moved to 7:30 pm"; S2 reads "Then Mon 19 Oct,
Wed 21 Oct (moved to 6:00 pm)". All of it is a comparison of dates and
times, so the server makes it, measured in Bangladesh's time [TC-9].

**A class has moved** when it is a recurring class whose start no longer
matches the weekly slot for its weekday -- the teacher rescheduled it.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.orm import Session as DbSession

from app.db.models import Session
from app.local_time import DHAKA
from app.teaching.upcoming import upcoming_sessions
from tests.batches.conftest import TeacherFixture
from tests.teaching.conftest import add_slot

#: A Saturday, 15:25 in Dhaka: 35 minutes before a 16:00 class.
NOW = dt.datetime(2026, 10, 17, 15, 25, tzinfo=DHAKA)
SATURDAY, MONDAY, WEDNESDAY = 5, 0, 2


def _class(
    session: DbSession,
    batch_id: uuid.UUID,
    day: dt.date,
    start: dt.time,
    status: str = "scheduled",
) -> None:
    """Add one class.

    :param session: An arranging session
    :param batch_id: The batch
    :param day: Its date
    :param start: Its start
    :param status: Its status
    :return: None
    """
    session.add(
        Session(
            batch_id=batch_id,
            date=day,
            start_time=start,
            end_time=dt.time(start.hour + 1, 30),
            status=status,
            origin="recurrence",
            attendance_version=0,
            topic_version=0,
            created_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    session.commit()


def test_the_next_classes_say_how_soon_and_which_moved(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    """Today at 16:00 in 35 minutes; Monday as usual; Wednesday moved.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :return: None
    """
    for weekday in (SATURDAY, MONDAY, WEDNESDAY):
        add_slot(owner_session, batch_id=teacher.batch_id, weekday=weekday)
    _class(owner_session, teacher.batch_id, dt.date(2026, 10, 17), dt.time(16, 0))
    _class(owner_session, teacher.batch_id, dt.date(2026, 10, 19), dt.time(16, 0))
    _class(owner_session, teacher.batch_id, dt.date(2026, 10, 21), dt.time(18, 0))

    [first, second, third] = upcoming_sessions(
        restricted_session, batch_ids=[teacher.batch_id], now=NOW
    )[teacher.batch_id]

    assert (first.date, first.start_time, first.starts_in_minutes) == (
        dt.date(2026, 10, 17),
        dt.time(16, 0),
        35,
    )
    assert first.end_time == dt.time(17, 30)
    assert second.starts_in_minutes is None
    assert [s.moved for s in (first, second, third)] == [False, False, True]


def test_a_started_or_cancelled_class_is_not_next(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    """Today's 15:00 has begun and Monday is cancelled: Wednesday is next.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :return: None
    """
    _class(owner_session, teacher.batch_id, dt.date(2026, 10, 17), dt.time(15, 0))
    _class(
        owner_session,
        teacher.batch_id,
        dt.date(2026, 10, 19),
        dt.time(16, 0),
        status="cancelled",
    )
    _class(owner_session, teacher.batch_id, dt.date(2026, 10, 21), dt.time(16, 0))

    upcoming = upcoming_sessions(
        restricted_session, batch_ids=[teacher.batch_id], now=NOW
    )[teacher.batch_id]

    assert [s.date for s in upcoming] == [dt.date(2026, 10, 21)]


def test_a_batch_with_no_classes_has_an_empty_list(
    restricted_session: DbSession, teacher: TeacherFixture
) -> None:
    """Nothing scheduled is an empty list, never a missing key.

    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :return: None
    """
    assert upcoming_sessions(
        restricted_session, batch_ids=[teacher.batch_id], now=NOW
    ) == {teacher.batch_id: []}
