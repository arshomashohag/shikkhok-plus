"""The daily session-generation job [BR1.1-BR1.4].

**The idempotency guarantee is the database constraint, not this
module** [BR1.3]. The insert is ``ON CONFLICT DO NOTHING`` on
``(batch_id, date, start_time)`` and the conflict is the SUCCESS path.
There is deliberately no application-level "has this run?" guard: that
shape passes a sequential test and creates two sessions for one class
under two workers, which Phase 1 has -- and two sessions for one class
means attendance marked on one is invisible on the other.

**Generation INSERTS; it never updates and never deletes** [BR1.4]. A
reconciling implementation would delete the extra class a teacher held
on a Saturday, taking its attendance with it. Rows with
``origin = 'ad_hoc'`` are not merely preserved by accident -- nothing
here ever issues a DELETE or an UPDATE against ``session`` at all.

**A schedule change never alters an existing session** [BR1.2]. This
falls out of the same property: later runs insert what is absent and
leave everything else exactly as it is, which is why sessions are
materialised rows rather than a view computed from the recurrence rule.
A computed view re-derives history, so moving a Tuesday class to
Wednesday would silently move every past Tuesday class.

**The horizon is the current calendar month plus the next.** No
upstream artifact fixes it; this is the functional design's stated
assumption in force. Longer creates sessions for slots the teacher is
about to change, which BR1.2 then freezes; shorter leaves a teacher
unable to open tomorrow's class.
"""

from __future__ import annotations

import calendar
import datetime as dt
import logging
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session as DbSession

from app.db.models import Batch, ScheduleSlot, Session

__all__ = ["GenerationResult", "generate_sessions", "horizon_dates"]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """What one run of the job did.

    The counts are carried for the heartbeat row, which is how they are
    queryable without a metrics backend. A sustained non-zero
    ``sessions_skipped`` is normal here rather than a signal: the job
    runs daily over a two-month horizon, so almost every occurrence is
    already present on almost every run.

    :ivar sessions_created: Sessions inserted
    :ivar sessions_skipped: Inserts that conflicted and did nothing
    :ivar batches_failed: Batches that raised and were skipped, leaving
        the rest of the run to continue
    """

    sessions_created: int
    sessions_skipped: int
    batches_failed: int


def horizon_dates(today: dt.date, weekday: int) -> list[dt.date]:
    """List every date in the horizon falling on one weekday.

    The horizon is **the current calendar month plus the next**,
    computed from the first of the current month through the last day
    of the next, so a run on any day of a month produces the same set.
    That is what makes a missed day self-heal rather than leaving a gap
    the following run cannot see.

    :param today: The day the job is running for
    :param weekday: 0-6, Monday through Sunday, as ``ScheduleSlot``
        numbers it
    :return: Every matching date in the horizon, ascending
    """
    first = today.replace(day=1)
    if first.month == 12:
        next_month = first.replace(year=first.year + 1, month=1)
    else:
        next_month = first.replace(month=first.month + 1)
    last = next_month.replace(
        day=calendar.monthrange(next_month.year, next_month.month)[1]
    )

    # Step forward to the first matching weekday, then by whole weeks.
    # Counting days one at a time over two months would work and would
    # be sixty-one comparisons per slot per run.
    offset = (weekday - first.weekday()) % 7
    current = first + dt.timedelta(days=offset)
    dates: list[dt.date] = []
    while current <= last:
        dates.append(current)
        current += dt.timedelta(days=7)
    return dates


def _insert_session(
    session: DbSession,
    *,
    batch_id: uuid.UUID,
    date: dt.date,
    start_time: dt.time,
    end_time: dt.time | None,
) -> bool:
    """Insert one generated session, treating a conflict as success.

    ``ON CONFLICT DO NOTHING`` with ``RETURNING id``: the returned row
    is present exactly when this call created it. Reading the result
    rather than counting rows is what makes "did I create it" an answer
    from the database instead of a guess -- and it is the same shape
    ``app/fees/generation.py`` uses.

    ``origin`` is stated explicitly rather than defaulted, on ADR-013's
    reasoning: a later insert path that does not state it is a path
    that forgot to think about it [BR1.4].

    :param session: The session to write through
    :param batch_id: The batch meeting
    :param date: The occurrence's date
    :param start_time: When it starts
    :param end_time: When it ends, or None
    :return: True if this call created the row, False if it conflicted
    """
    statement = (
        pg_insert(Session)
        .values(
            id=uuid.uuid4(),
            batch_id=batch_id,
            batch_subject_id=None,
            date=date,
            start_time=start_time,
            end_time=end_time,
            topic=None,
            status="scheduled",
            origin="recurrence",
            attendance_version=0,
            topic_version=0,
            created_at=dt.datetime.now(tz=dt.UTC),
        )
        .on_conflict_do_nothing(constraint="uq_session_batch_date_start")
        .returning(Session.id)
    )
    return session.execute(statement).scalar_one_or_none() is not None


def generate_sessions(
    session: DbSession,
    *,
    today: dt.date | None = None,
    batch_id: uuid.UUID | None = None,
) -> GenerationResult:
    """Generate every session the active batches' schedules imply.

    **The clock is a parameter, not a module global.** The across-days
    obligation needs the job run as though it were a different day, and
    a patched global is both wider than the caller and invisible at the
    call site.

    Safe to run any number of times on any number of days.

    :param session: The session to work through
    :param today: The date to generate around; the real one by default
    :param batch_id: Only this batch, when a teacher has just set its
        schedule and should not wait for the nightly run; every active
        batch when None, which is the nightly job
    :return: The run's three counts
    """
    when = today or dt.datetime.now(tz=dt.UTC).date()
    created = skipped = failed = 0

    rows = session.execute(
        sa.select(
            ScheduleSlot.batch_id,
            ScheduleSlot.weekday,
            ScheduleSlot.start_time,
            ScheduleSlot.end_time,
        )
        # BR5.5: an inactive batch is read-only history, so it accrues
        # no new sessions. The join is the filter rather than a check
        # above it, because a check above a query is one the next query
        # can bypass.
        .join(Batch, Batch.id == ScheduleSlot.batch_id)
        .where(Batch.active.is_(True))
        .where(sa.true() if batch_id is None else ScheduleSlot.batch_id == batch_id)
        .order_by(ScheduleSlot.batch_id, ScheduleSlot.weekday)
    ).all()

    for batch_id, weekday, start_time, end_time in rows:
        try:
            for date in horizon_dates(when, weekday):
                if _insert_session(
                    session,
                    batch_id=batch_id,
                    date=date,
                    start_time=start_time,
                    end_time=end_time,
                ):
                    created += 1
                else:
                    skipped += 1
            # Committed per SLOT, so one bad slot cannot abort a run
            # that has already generated correctly for other batches.
            session.commit()
        except sa.exc.SQLAlchemyError:
            session.rollback()
            failed += 1
            # Nothing identifying reaches this line: a batch id and a
            # weekday, never a name, a number or a child [NFR24.13].
            log.exception(
                "session generation failed for a slot",
                extra={"batch_id": str(batch_id), "weekday": weekday},
            )

    return GenerationResult(
        sessions_created=created,
        sessions_skipped=skipped,
        batches_failed=failed,
    )
