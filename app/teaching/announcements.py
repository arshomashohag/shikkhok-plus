"""Announcements [BR7.1] and the student and guardian batch reads.

**No expiry column and no scheduled job**, and that absence is the
part an implementation adds by habit [AC3.3.4]. A silently expiring
announcement is a message the teacher believes was delivered.

**Soft-deleted rather than removed**: AC3.3.3 requires it to disappear
from student and guardian views while FR9.2's correction history and
the governance basis both require the fact of it to survive.

**``edited_at``'s non-null-ness IS the "shows as edited" flag**
[AC3.3.2]. A separate boolean would be a second source of truth that
can disagree with the timestamp.

**Every schedule and topic read carries the server time it was
produced** [BR7.3]. A client rendering from cache cannot state an age
the server never sent -- it would have to use the device clock, which
is the very thing excluded from decisions, and a phone with a wrong
clock would display a confidently wrong age. The caching itself is
Android work with no server rule behind it, so this module states only
the half the server owns.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import Lens, TeacherLens
from app.db.models import (
    Announcement,
    Attendance,
    Batch,
    BatchSubject,
    Exam,
    Session,
)
from app.errors import ConflictError
from app.local_time import bangladesh_today
from app.teaching.roster import readable_enrollment, refuse
from app.teaching.upcoming import UpcomingSession, upcoming_sessions

__all__ = [
    "AnnouncementRow",
    "AttendanceEntry",
    "FamilyBatchView",
    "delete_announcement",
    "edit_announcement",
    "family_batch_view",
    "list_announcements",
    "post_announcement",
]


@dataclass(frozen=True, slots=True)
class AnnouncementRow:
    """One visible announcement.

    :ivar announcement_id: The note
    :ivar body: What it says
    :ivar created_at: When it was posted
    :ivar edited: Whether it has been edited [AC3.3.2]
    """

    announcement_id: uuid.UUID
    body: str
    created_at: dt.datetime
    edited: bool


@dataclass(frozen=True, slots=True)
class AttendanceEntry:
    """One past session and this seat's attendance at it.

    :ivar session_id: The session
    :ivar date: When it met
    :ivar start_time: When it started
    :ivar topic: What was covered, or None if never logged
    :ivar topic_logged: Whether a topic was ever written [BR2.2]
    :ivar present: What was recorded, or None where nothing was
    :ivar subject_name: What the class taught, if set
    """

    session_id: uuid.UUID
    date: dt.date
    start_time: dt.time
    topic: str | None
    topic_logged: bool
    present: bool | None
    subject_name: str | None = None


@dataclass(frozen=True, slots=True)
class FamilyBatchView:
    """What a student or guardian sees of one batch [BR7.2].

    ``served_at`` is BR7.3's server timestamp: the client renders an
    age from it rather than from the device clock.

    :ivar next_session_date: The next scheduled session's date, or
        None
    :ivar next_session_start_time: Its start time, or None
    :ivar past_sessions: Past sessions with topics and attendance
    :ivar announcements: The batch's visible announcements
    :ivar served_at: When the server computed this [BR7.3]
    :ivar coming: The next classes, soonest first: the first is "Next
        class", the rest are "Then ..."
    :ivar upcoming_exam: The next exam still to be sat, if any
    """

    next_session_date: dt.date | None
    next_session_start_time: dt.time | None
    past_sessions: list[AttendanceEntry]
    announcements: list[AnnouncementRow]
    served_at: dt.datetime
    coming: list[UpcomingSession] = field(default_factory=list)
    upcoming_exam: UpcomingExam | None = None


@dataclass(frozen=True, slots=True)
class UpcomingExam:
    """The next exam a student will sit ("Coming up").

    :ivar title: Its title
    :ivar date: When
    :ivar total_marks: Out of how many
    :ivar subject_name: Which subject
    """

    title: str
    date: dt.date
    total_marks: int
    subject_name: str


def _writable_batch(
    session: DbSession, *, lens: TeacherLens, batch_id: uuid.UUID
) -> Batch:
    """Return a batch this lens owns and may write to.

    :param session: The session to read through
    :param lens: The teacher lens
    :param batch_id: The batch
    :return: The batch row
    :raises AuthorizationError: This lens does not own it
    :raises ConflictError: The batch is inactive [BR5.5]
    """
    row = session.scalars(
        sa.select(Batch).where(Batch.id == batch_id, Batch.owner_id == lens.owner_id)
    ).one_or_none()
    if row is None:
        raise refuse()
    if not row.active:
        raise ConflictError(
            code="BATCH_INACTIVE",
            message_key="teaching.batch.inactive",
        )
    return row


def _row(record: Announcement) -> AnnouncementRow:
    """Render one announcement.

    :param record: The announcement
    :return: The view row
    """
    return AnnouncementRow(
        announcement_id=record.id,
        body=record.body,
        created_at=record.created_at,
        # The TIMESTAMP is the flag. A separate boolean would be a
        # second source of truth that can disagree with it.
        edited=record.edited_at is not None,
    )


def _reachable_announcement(
    session: DbSession, *, lens: TeacherLens, announcement_id: uuid.UUID
) -> Announcement:
    """Return an announcement this teacher lens reaches, or refuse.

    :param session: The session to read through
    :param lens: The teacher lens
    :param announcement_id: The note
    :return: The announcement row
    :raises AuthorizationError: No batch this lens owns holds it
    """
    row = session.scalars(
        sa.select(Announcement)
        .join(Batch, Batch.id == Announcement.batch_id)
        .where(
            Announcement.id == announcement_id,
            Batch.owner_id == lens.owner_id,
        )
    ).one_or_none()
    if row is None:
        raise refuse()
    return row


def post_announcement(
    session: DbSession,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
    body: str,
) -> AnnouncementRow:
    """Post one note to a batch [BR7.1].

    :param session: The session to work through
    :param lens: The teacher lens
    :param batch_id: The batch
    :param body: What it says
    :return: The posted note
    :raises AuthorizationError: This lens does not own the batch
    :raises ConflictError: The batch is inactive
    """
    _writable_batch(session, lens=lens, batch_id=batch_id)

    record = Announcement(
        batch_id=batch_id,
        body=body,
        created_at=dt.datetime.now(tz=dt.UTC),
        edited_at=None,
        deleted_at=None,
        posted_by_account_id=lens.account_id,
    )
    session.add(record)
    session.commit()
    return _row(record)


def edit_announcement(
    session: DbSession,
    *,
    lens: TeacherLens,
    announcement_id: uuid.UUID,
    body: str,
) -> AnnouncementRow:
    """Edit a note, marking it as edited [AC3.3.2].

    :param session: The session to work through
    :param lens: The teacher lens
    :param announcement_id: The note
    :param body: Its new text
    :return: The edited note
    :raises AuthorizationError: This lens does not reach it
    :raises ConflictError: The batch is inactive, or it is deleted
    """
    record = _reachable_announcement(
        session, lens=lens, announcement_id=announcement_id
    )
    _writable_batch(session, lens=lens, batch_id=record.batch_id)

    if record.deleted_at is not None:
        raise ConflictError(
            code="ANNOUNCEMENT_DELETED",
            message_key="teaching.announcement.deleted",
        )

    record.body = body
    record.edited_at = dt.datetime.now(tz=dt.UTC)
    session.commit()
    return _row(record)


def delete_announcement(
    session: DbSession,
    *,
    lens: TeacherLens,
    announcement_id: uuid.UUID,
) -> None:
    """Soft-delete a note [AC3.3.3].

    The row survives; only its visibility ends. FR9.2's history and
    the governance basis both require the fact of it to remain.

    :param session: The session to work through
    :param lens: The teacher lens
    :param announcement_id: The note
    :return: None
    :raises AuthorizationError: This lens does not reach it
    :raises ConflictError: The batch is inactive
    """
    record = _reachable_announcement(
        session, lens=lens, announcement_id=announcement_id
    )
    _writable_batch(session, lens=lens, batch_id=record.batch_id)

    if record.deleted_at is None:
        record.deleted_at = dt.datetime.now(tz=dt.UTC)
        session.commit()


def _visible_announcements(
    session: DbSession, *, batch_id: uuid.UUID
) -> list[AnnouncementRow]:
    """Read a batch's undeleted announcements, newest first.

    :param session: The session to read through
    :param batch_id: The batch
    :return: The visible notes
    """
    rows = session.scalars(
        sa.select(Announcement)
        .where(
            Announcement.batch_id == batch_id,
            Announcement.deleted_at.is_(None),
        )
        .order_by(Announcement.created_at.desc(), Announcement.id)
    ).all()
    return [_row(record) for record in rows]


def list_announcements(
    session: DbSession,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
) -> list[AnnouncementRow]:
    """List a batch's visible announcements, for its teacher.

    :param session: The session to read through
    :param lens: The teacher lens
    :param batch_id: The batch
    :return: The visible notes, newest first
    :raises AuthorizationError: This lens does not own the batch
    """
    owned = session.scalars(
        sa.select(Batch.id).where(Batch.id == batch_id, Batch.owner_id == lens.owner_id)
    ).one_or_none()
    if owned is None:
        raise refuse()
    return _visible_announcements(session, batch_id=batch_id)


def family_batch_view(
    session: DbSession,
    *,
    lens: Lens,
    enrollment_id: uuid.UUID,
    today: dt.date | None = None,
) -> FamilyBatchView:
    """Return what a student or guardian sees of one batch [BR7.2].

    The seat arrives as a **path parameter** and the grant is checked
    against it, never the other way round: the handler cannot reach a
    second seat because this read refuses one the lens does not hold.

    :param session: The session to read through
    :param lens: The student or guardian lens
    :param enrollment_id: The seat, from the route path
    :param today: The day to compute "next" from; the real one by
        default
    :return: The batch view, carrying its own server timestamp
    :raises AuthorizationError: This lens does not reach the seat
    """
    seat = readable_enrollment(session, lens=lens, enrollment_id=enrollment_id)
    now = dt.datetime.now(tz=dt.UTC)
    when = today or bangladesh_today()
    coming = upcoming_sessions(session, batch_ids=[seat.batch_id])[seat.batch_id]
    upcoming = (coming[0].date, coming[0].start_time) if coming else None
    past = session.execute(
        sa.select(
            Session.id,
            Session.date,
            Session.start_time,
            Session.topic,
            Attendance.present,
            BatchSubject.name,
        )
        .select_from(Session)
        .outerjoin(BatchSubject, BatchSubject.id == Session.batch_subject_id)
        .outerjoin(
            Attendance,
            sa.and_(
                Attendance.session_id == Session.id,
                # **Scoped to THIS seat.** A guardian sees their own
                # child's attendance and no other's [BR7.2], and the
                # scoping is in the join rather than in a filter
                # above it.
                Attendance.enrollment_id == enrollment_id,
            ),
        )
        .where(
            Session.batch_id == seat.batch_id,
            Session.date < when,
            Session.status != "cancelled",
        )
        .order_by(Session.date.desc(), Session.start_time.desc())
    ).all()

    return FamilyBatchView(
        next_session_date=None if upcoming is None else upcoming[0],
        next_session_start_time=None if upcoming is None else upcoming[1],
        past_sessions=[
            AttendanceEntry(
                session_id=entry[0],
                date=entry[1],
                start_time=entry[2],
                topic=entry[3],
                topic_logged=entry[3] is not None,
                present=entry[4],
                subject_name=entry[5],
            )
            for entry in past
        ],
        announcements=_visible_announcements(session, batch_id=seat.batch_id),
        # BR7.3: the client cannot state an age the server never sent.
        served_at=now,
        coming=coming,
        upcoming_exam=_next_exam(session, batch_id=seat.batch_id, today=when),
    )


def _next_exam(
    session: DbSession, *, batch_id: uuid.UUID, today: dt.date
) -> UpcomingExam | None:
    """Return the batch's next exam still to be sat, today included.

    :param session: The session to read through
    :param batch_id: The batch, already reached by the caller's lens
    :param today: Bangladesh's date
    :return: The exam, or None when none is coming
    """
    row = session.execute(
        sa.select(Exam.title, Exam.date, Exam.total_marks, BatchSubject.name)
        .join(BatchSubject, BatchSubject.id == Exam.batch_subject_id)
        .where(Exam.batch_id == batch_id, Exam.date >= today)
        .order_by(Exam.date, Exam.id)
        .limit(1)
    ).one_or_none()
    if row is None:
        return None
    return UpcomingExam(
        title=row[0], date=row[1], total_marks=row[2], subject_name=row[3]
    )
