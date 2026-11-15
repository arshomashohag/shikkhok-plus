"""The "Runs classes on ShikkhokPlus" badge."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.local_time import DHAKA

__all__ = ["BADGE_MIN_ACCEPTED", "BADGE_WINDOW_DAYS", "runs_classes"]

#: Accepted seats an owner needs for the badge.
BADGE_MIN_ACCEPTED: Final = 5

#: How recent attendance must be, in days.
BADGE_WINDOW_DAYS: Final = 30

_ACCEPTED: Final = sa.text(
    "SELECT count(*) FROM enrollment e JOIN batch b ON b.id = e.batch_id "
    "WHERE b.owner_id = :owner AND b.active "
    "AND (e.student_decision = 'accepted' OR e.guardian_decision = 'accepted') "
    "AND (e.inactive_from IS NULL OR e.inactive_from >= :today)"
)

_RECENT: Final = sa.text(
    "SELECT EXISTS (SELECT 1 FROM attendance a "
    "JOIN session s ON s.id = a.session_id "
    "JOIN batch b ON b.id = s.batch_id "
    "WHERE b.owner_id = :owner AND a.recorded_at >= :since)"
)


def runs_classes(session: Session, owner_id: uuid.UUID, today: dt.date) -> bool:
    """Say whether an owner earns the badge.

    Five or more accepted seats across the owner's batches, and attendance
    recorded on one of their sessions within the last thirty days. Counts
    only; it reads no student's name or contact. A seat counts when either
    the student or the guardian accepted it, in an active batch, and not
    past its ``inactive_from``. The window starts at Dhaka midnight.

    :param session: The session to read through
    :param owner_id: The owner
    :param today: The day to count back from
    :return: True when both conditions hold
    """
    accepted = session.execute(
        _ACCEPTED, {"owner": owner_id, "today": today}
    ).scalar_one()
    if accepted < BADGE_MIN_ACCEPTED:
        return False
    since = dt.datetime.combine(
        today - dt.timedelta(days=BADGE_WINDOW_DAYS), dt.time.min, tzinfo=DHAKA
    )
    found = session.execute(_RECENT, {"owner": owner_id, "since": since})
    return bool(found.scalar_one())
