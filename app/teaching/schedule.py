"""A batch's weekly schedule: what the nightly job turns into sessions.

**The writer that did not exist.** Sessions are generated from
``schedule_slot`` rows and nothing could write one -- no route, and no
field on batch creation -- so no batch ever had a session, and attendance
and topic logging could not be reached by anyone.

**Setting a schedule generates this batch's sessions at once**, rather
than at the next nightly run. Otherwise a teacher who has just set up a
batch opens attendance and finds nothing until tomorrow.

**A changed schedule leaves existing sessions alone** [BR1.2]. The slots
are replaced; the sessions already generated from the old ones stay,
because generation inserts and never updates or deletes [BR1.4] -- a
Tuesday class moved to Wednesday keeps its generated Tuesdays, and the
teacher cancels those individually. That is the rule as it stands.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.batches.service import BatchNotFound
from app.db.models import Batch, ScheduleSlot
from app.errors import ValidationError
from app.schemas.schedule import ScheduleSlotWire
from app.teaching.generation import generate_sessions

__all__ = [
    "Slot",
    "read_schedule",
    "refuse_duplicate_slots",
    "set_schedule",
    "slot_of",
    "slots_of",
]


@dataclass(frozen=True, slots=True)
class Slot:
    """One weekly class: a weekday and its times.

    :ivar weekday: 0-6, Monday through Sunday
    :ivar start_time: When the class starts
    :ivar end_time: When the class ends
    """

    weekday: int
    start_time: dt.time
    end_time: dt.time


def slot_of(wire: ScheduleSlotWire) -> Slot:
    """Read one wire slot into the domain shape.

    :param wire: The slot as the request carried it
    :return: The slot with real times
    """
    return Slot(
        weekday=wire.weekday,
        start_time=dt.time.fromisoformat(wire.start_time),
        end_time=dt.time.fromisoformat(wire.end_time),
    )


def refuse_duplicate_slots(slots: list[Slot]) -> None:
    """Refuse the same class listed twice.

    Called before anything is written, including before a batch created
    with its schedule, so a typing error cannot leave a batch behind.

    :param slots: The proposed slots
    :return: None
    :raises ValidationError: Two slots share a weekday and start time
    """
    keys = [(slot.weekday, slot.start_time) for slot in slots]
    if len(keys) != len(set(keys)):
        raise ValidationError(
            code="SCHEDULE_DUPLICATE_SLOT",
            message_key="schedule.duplicate_slot",
        )


def _owned(session: DbSession, *, lens: TeacherLens, batch_id: uuid.UUID) -> None:
    """Refuse a batch this lens does not own, without confirming it exists.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param batch_id: The batch
    :return: None
    :raises BatchNotFound: No such batch, or another owner's
    """
    owned = session.execute(
        sa.select(Batch.id).where(Batch.id == batch_id, Batch.owner_id == lens.owner_id)
    ).scalar_one_or_none()
    if owned is None:
        raise BatchNotFound(code="BATCH_NOT_FOUND", message_key="batch.not_found")


def read_schedule(
    session: DbSession, *, lens: TeacherLens, batch_id: uuid.UUID
) -> list[Slot]:
    """Read one batch's weekly slots, in weekday then time order.

    :param session: The session to read through
    :param lens: The teacher lens
    :param batch_id: The batch
    :return: Its slots
    :raises BatchNotFound: Not this lens's batch
    """
    _owned(session, lens=lens, batch_id=batch_id)
    return slots_of(session, batch_id)


def slots_of(session: DbSession, batch_id: uuid.UUID) -> list[Slot]:
    """Read a batch's slots with no ownership check, for an owned caller.

    :param session: The session to read through
    :param batch_id: A batch the caller has already authorized
    :return: Its slots, in weekday then time order
    """
    rows = session.execute(
        sa.select(ScheduleSlot.weekday, ScheduleSlot.start_time, ScheduleSlot.end_time)
        .where(ScheduleSlot.batch_id == batch_id)
        .order_by(ScheduleSlot.weekday, ScheduleSlot.start_time)
    ).all()
    return [Slot(weekday, start, end) for weekday, start, end in rows]


def set_schedule(
    session: DbSession,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
    slots: list[Slot],
    today: dt.date | None = None,
) -> list[Slot]:
    """Replace a batch's weekly slots, then generate its sessions at once.

    :param session: The session to write through
    :param lens: The teacher lens
    :param batch_id: The batch
    :param slots: The complete new schedule; empty clears it
    :param today: The date generation runs around; the real one by default
    :return: The schedule as stored
    :raises BatchNotFound: Not this lens's batch
    :raises ValidationError: The same class is listed twice
    """
    refuse_duplicate_slots(slots)
    _owned(session, lens=lens, batch_id=batch_id)

    session.execute(sa.delete(ScheduleSlot).where(ScheduleSlot.batch_id == batch_id))
    session.add_all(
        ScheduleSlot(
            batch_id=batch_id,
            weekday=slot.weekday,
            start_time=slot.start_time,
            end_time=slot.end_time,
        )
        for slot in slots
    )
    session.commit()

    generate_sessions(session, today=today, batch_id=batch_id)
    return slots_of(session, batch_id)
