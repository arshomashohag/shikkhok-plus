"""The next exam: one statement, scoped by the lens, with ``LIMIT 1``.

**An unscoped ``LIMIT 1`` returns SOMEBODY's soonest exam**, which is
why the scope probe for this figure seeds teacher B's exam **sooner**
than teacher A's [security-design § 2]. A probe where B's exam is later
passes against a leak, because the correct answer and the leaked one
would both be A's.

**The tiebreaker lives in the ORDER BY rather than in Python**
[performance § 2]. Fetching every upcoming exam and picking in code
would work and would make the determinism a property of the code rather
than of the query -- after which a later ``ORDER BY`` change could
silently alter which exam is "next" with nothing failing.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.db.models import Batch, BatchSubject, Exam

__all__ = ["NextExam", "next_exam"]


@dataclass(frozen=True, slots=True)
class NextExam:
    """The soonest exam dated today or later, across owned batches.

    :ivar exam_id: The exam
    :ivar title: The teacher's name for it
    :ivar batch_name: Which class sits it
    :ivar subject_name: The subject assessed
    :ivar date: When it is sat
    :ivar days_remaining: Whole days from today, computed server-side
    """

    exam_id: uuid.UUID
    title: str
    batch_name: str
    subject_name: str
    date: dt.date
    days_remaining: int


def next_exam(
    session: Session, lens: TeacherLens, *, today: dt.date
) -> NextExam | None:
    """Return the soonest upcoming exam, or nothing scheduled.

    **``>= today``, not ``> today``** [BR3.1]. An exam a teacher is
    about to sit is the one they most need to see, and an exam dated
    today reports zero days remaining rather than being dropped.

    **``today`` is supplied rather than read here**, and that is the
    server's calendar date in both cases -- the parameter exists so the
    boundary is testable at all, since a test that cannot name "today"
    cannot assert the boundary. It is never a client-supplied value: a
    device clock must not be able to change which exam a teacher is
    shown [TC-9].

    **Days remaining is whole days, computed server-side** [BR3.2]. A
    client computing it from a date would use the device clock and
    would disagree across time zones.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param today: The server's calendar date
    :return: The next exam, or None when none is dated today or later
        [BR3.4]
    """
    row = session.execute(
        sa.select(
            Exam.id,
            Exam.title,
            Batch.name,
            BatchSubject.name,
            Exam.date,
        )
        .join(Batch, Batch.id == Exam.batch_id)
        .join(BatchSubject, BatchSubject.id == Exam.batch_subject_id)
        .where(Batch.owner_id == lens.owner_id, Exam.date >= today)
        # The stated tiebreaker [BR3.3]: created_at before exam_id so a
        # tie is broken by something meaningful to a person, with the id
        # as the final total order. "Deterministic" with no key named is
        # how two implementations disagree while both satisfying the
        # criterion.
        .order_by(Exam.date, Exam.created_at, Exam.id)
        .limit(1)
    ).first()

    if row is None:
        return None

    return NextExam(
        exam_id=row[0],
        title=row[1],
        batch_name=row[2],
        subject_name=row[3],
        date=row[4],
        days_remaining=(row[4] - today).days,
    )
