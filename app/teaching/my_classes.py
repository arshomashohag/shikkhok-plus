"""A centre teacher's own classes, across every centre they teach at [C4].

**Derived from the account, never from a request parameter.** The rows
are the classes assigned to a membership the account holds, accepted and
unrevoked, in the same query that reads them; no other class of the same
batch is fetched and filtered away.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.db.models import Batch, BatchSubject, Owner, OwnerMember, Room, Session
from app.errors import ValidationError

__all__ = ["MAX_DAYS", "MyClass", "my_classes"]

#: The longest read, in days; bounds the query, not a rule.
MAX_DAYS = 31


@dataclass(frozen=True, slots=True)
class MyClass:
    """One class assigned to the caller.

    :ivar session_id: The class
    :ivar centre_name: The centre it belongs to
    :ivar batch_name: Its batch
    :ivar subject: Its subject, or None
    :ivar date: Its date
    :ivar start_time: When it starts
    :ivar end_time: When it ends, or None
    :ivar status: ``scheduled``, ``held`` or ``cancelled``
    :ivar room_name: Where, or None
    :ivar topic_logged: Whether its topic has been written
    """

    session_id: uuid.UUID
    centre_name: str
    batch_name: str
    subject: str | None
    date: dt.date
    start_time: dt.time
    end_time: dt.time | None
    status: str
    room_name: str | None
    topic_logged: bool


def my_classes(
    session: DbSession, *, account_id: uuid.UUID, first: dt.date, last: dt.date
) -> list[MyClass]:
    """List the classes assigned to this account between two dates.

    :param session: The session to read through
    :param account_id: The authenticated account
    :param first: The first date, inclusive
    :param last: The last date, inclusive
    :return: The classes, soonest first
    :raises ValidationError: The range is backwards or too long
    """
    if last < first or (last - first).days >= MAX_DAYS:
        raise ValidationError(
            code="TIMETABLE_RANGE_TOO_LONG", message_key="timetable.range_too_long"
        )
    rows = session.execute(
        sa.select(
            Session.id,
            Owner.name,
            Batch.name,
            BatchSubject.name,
            Session.date,
            Session.start_time,
            Session.end_time,
            Session.status,
            Room.name,
            Session.topic,
        )
        .join(Batch, Batch.id == Session.batch_id)
        .join(Owner, Owner.id == Batch.owner_id)
        .join(
            OwnerMember,
            sa.and_(
                OwnerMember.id == Session.teacher_member_id,
                OwnerMember.owner_id == Batch.owner_id,
                OwnerMember.account_id == account_id,
                OwnerMember.decision == "accepted",
                OwnerMember.revoked_at.is_(None),
            ),
        )
        .outerjoin(BatchSubject, BatchSubject.id == Session.batch_subject_id)
        .outerjoin(Room, Room.id == Session.room_id)
        .where(Session.date >= first, Session.date <= last)
        .order_by(Session.date, Session.start_time, Batch.name, Session.id)
    ).all()
    return [
        MyClass(
            session_id=r[0],
            centre_name=r[1] or "",
            batch_name=r[2],
            subject=r[3],
            date=r[4],
            start_time=r[5],
            end_time=r[6],
            status=r[7],
            room_name=r[8],
            topic_logged=r[7] == "held" and r[9] is not None,
        )
        for r in rows
    ]
