"""Freeing a removed teacher's classes [0024].

Its own module because three writers end a membership -- a manager
removing a member, a staff record marked left, and account deletion --
and none of them should depend on the scheduling module to do it.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.db.models import Exam, ScheduleSlot, Session
from app.local_time import bangladesh_today

__all__ = ["unassign_member"]


def unassign_member(
    session: DbSession, *, member_id: uuid.UUID, today: dt.date | None = None
) -> None:
    """Free a removed teacher's weekly slots, future classes and open exams.

    Held and past classes keep their teacher, and published exams their
    examiner, as the record of who taught and who marked; the manager
    sees the rest as unassigned. Adds to the caller's transaction.

    :param session: The session to write through
    :param member_id: The membership that ended
    :param today: The first date to free, or None for today in Bangladesh
    :return: None
    """
    session.execute(
        sa.update(ScheduleSlot)
        .where(ScheduleSlot.teacher_member_id == member_id)
        .values(teacher_member_id=None)
    )
    session.execute(
        sa.update(Session)
        .where(
            Session.teacher_member_id == member_id,
            Session.date >= (today or bangladesh_today()),
            Session.status == "scheduled",
        )
        .values(teacher_member_id=None)
    )
    session.execute(
        sa.update(Exam)
        .where(
            Exam.examiner_member_id == member_id,
            Exam.published_at.is_(None),
            Exam.cancelled_at.is_(None),
        )
        .values(examiner_member_id=None)
    )
