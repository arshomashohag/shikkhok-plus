"""Session generation: BR1.1, BR1.2 and BR1.4.

The idempotency half of BR1.3 that only a race can prove lives in
``test_generation_races.py``; what is here is everything a sequential
test genuinely settles.

**BR1.2 is the rule the materialised-row decision exists for.** A
computed view re-derives history, so moving a Tuesday class to Wednesday
silently moves every past Tuesday class and the attendance recorded
against it. The test generates, records against the first session,
changes the slot, generates again, and asserts the original rows are
byte-identical.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.db.models import Session
from app.teaching.generation import generate_sessions
from tests.batches.conftest import TeacherFixture
from tests.teaching.conftest import add_slot

#: A Sunday, chosen so "today" is not itself a Monday and the horizon
#: arithmetic is not accidentally satisfied by an off-by-one.
IN_FEBRUARY = dt.date(2027, 2, 7)

#: February 2027 has Mondays on the 1st, 8th, 15th and 22nd; March 2027
#: has them on the 1st, 8th, 15th, 22nd and 29th. The horizon is the
#: current calendar month plus the next, so nine Mondays in total.
FEBRUARY_MONDAYS = (
    dt.date(2027, 2, 1),
    dt.date(2027, 2, 8),
    dt.date(2027, 2, 15),
    dt.date(2027, 2, 22),
)
MARCH_MONDAYS = (
    dt.date(2027, 3, 1),
    dt.date(2027, 3, 8),
    dt.date(2027, 3, 15),
    dt.date(2027, 3, 22),
    dt.date(2027, 3, 29),
)


def _sessions(session: DbSession, batch_id: uuid.UUID) -> list[Session]:
    """Read a batch's sessions, oldest first.

    :param session: The session to read through
    :param batch_id: The batch
    :return: Every session row for that batch
    """
    return list(
        session.scalars(
            sa.select(Session)
            .where(Session.batch_id == batch_id)
            .order_by(Session.date, Session.start_time)
        ).all()
    )


def test_one_session_per_slot_occurrence_in_the_horizon(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    monday_slot: uuid.UUID,
) -> None:
    # BR1.1's own violation_behaviour, stated as an assertion: a teacher
    # opens a class to mark attendance and there must be something to
    # mark it against.
    generate_sessions(restricted_session, today=IN_FEBRUARY)

    rows = _sessions(restricted_session, teacher.batch_id)
    assert [row.date for row in rows] == list(FEBRUARY_MONDAYS + MARCH_MONDAYS)
    assert {row.start_time for row in rows} == {dt.time(16, 0)}
    assert {row.origin for row in rows} == {"recurrence"}
    assert {row.status for row in rows} == {"scheduled"}


def test_generated_sessions_start_at_version_zero(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    monday_slot: uuid.UUID,
) -> None:
    generate_sessions(restricted_session, today=IN_FEBRUARY)

    rows = _sessions(restricted_session, teacher.batch_id)
    assert {row.attendance_version for row in rows} == {0}
    assert {row.topic_version for row in rows} == {0}


def test_a_batch_with_no_slots_generates_nothing(
    restricted_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    result = generate_sessions(restricted_session, today=IN_FEBRUARY)

    assert result.sessions_created == 0
    assert _sessions(restricted_session, teacher.batch_id) == []


def test_an_inactive_batch_generates_nothing(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    monday_slot: uuid.UUID,
) -> None:
    # BR5.5: an inactive batch is read-only history. Generation is a
    # write, so it must not accrue sessions on a closed batch.
    owner_session.execute(
        sa.text("UPDATE batch SET active = false WHERE id = :id"),
        {"id": teacher.batch_id},
    )
    owner_session.commit()

    generate_sessions(restricted_session, today=IN_FEBRUARY)

    assert _sessions(restricted_session, teacher.batch_id) == []


def test_a_second_run_on_the_same_day_creates_nothing_new(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    monday_slot: uuid.UUID,
) -> None:
    first = generate_sessions(restricted_session, today=IN_FEBRUARY)
    second = generate_sessions(restricted_session, today=IN_FEBRUARY)

    assert first.sessions_created == 9
    assert second.sessions_created == 0
    assert second.sessions_skipped == 9
    assert len(_sessions(restricted_session, teacher.batch_id)) == 9


def test_a_run_on_a_later_day_is_idempotent_across_days(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    monday_slot: uuid.UUID,
) -> None:
    # The case concurrency alone misses, and the one the daily
    # self-healing re-run needs [BR1.3]. Running on the 14th must not
    # re-create the sessions the 7th already made.
    generate_sessions(restricted_session, today=IN_FEBRUARY)
    before = {row.id for row in _sessions(restricted_session, teacher.batch_id)}

    generate_sessions(restricted_session, today=dt.date(2027, 2, 14))

    after = {row.id for row in _sessions(restricted_session, teacher.batch_id)}
    assert after == before, "a later run re-created sessions that already existed"


def test_a_schedule_change_never_alters_an_existing_session(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    monday_slot: uuid.UUID,
) -> None:
    # BR1.2, and the reason sessions are ROWS rather than a view
    # computed from the recurrence rule. A computed view re-derives
    # history, so moving a Monday class to Tuesday silently moves every
    # PAST Monday class and the attendance recorded against it.
    generate_sessions(restricted_session, today=IN_FEBRUARY)
    original = [
        (row.id, row.date, row.start_time, row.status, row.origin)
        for row in _sessions(restricted_session, teacher.batch_id)
    ]

    # Move the slot to Tuesday 18:00.
    owner_session.execute(
        sa.text(
            "UPDATE schedule_slot SET weekday = 1, start_time = '18:00' WHERE id = :id"
        ),
        {"id": monday_slot},
    )
    owner_session.commit()

    generate_sessions(restricted_session, today=IN_FEBRUARY)

    rows = _sessions(restricted_session, teacher.batch_id)
    surviving = [
        (row.id, row.date, row.start_time, row.status, row.origin)
        for row in rows
        if row.id in {entry[0] for entry in original}
    ]
    assert surviving == original, (
        "a schedule change rewrote already-generated sessions: this is "
        "what a computed view would do and what BR1.2 forbids"
    )
    # The new slot's occurrences are generated alongside, not instead.
    assert any(row.start_time == dt.time(18, 0) for row in rows)


def test_generation_never_touches_an_ad_hoc_session(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    monday_slot: uuid.UUID,
) -> None:
    # BR1.4. A generation job that RECONCILED rather than inserted
    # would delete the extra class a teacher held on a Saturday,
    # taking its attendance with it.
    saturday = dt.date(2027, 2, 6)
    ad_hoc = Session(
        batch_id=teacher.batch_id,
        date=saturday,
        start_time=dt.time(10, 0),
        status="scheduled",
        origin="ad_hoc",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(ad_hoc)
    owner_session.commit()
    ad_hoc_id = ad_hoc.id

    generate_sessions(restricted_session, today=IN_FEBRUARY)

    survivor = restricted_session.get(Session, ad_hoc_id)
    assert survivor is not None, "generation deleted an ad-hoc session"
    assert survivor.origin == "ad_hoc"
    assert survivor.date == saturday
    assert survivor.start_time == dt.time(10, 0)


def test_two_slots_on_one_batch_each_generate(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    monday_slot: uuid.UUID,
) -> None:
    # A batch meeting twice a week is the normal case, and a generator
    # that stopped at the first slot would pass every single-slot test.
    add_slot(
        owner_session,
        batch_id=teacher.batch_id,
        weekday=2,
        start_time=dt.time(9, 0),
    )

    generate_sessions(restricted_session, today=IN_FEBRUARY)

    rows = _sessions(restricted_session, teacher.batch_id)
    assert {row.start_time for row in rows} == {dt.time(16, 0), dt.time(9, 0)}
