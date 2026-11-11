"""Session reads and the interactive writes: ad-hoc, reschedule, cancel.

**These are INTERACTIVE writes and carry no version** [BR3.11]. Stating
that is what stops the queued-path rule from spreading: applied
everywhere, optimistic concurrency would make a teacher correcting a
session on their own phone refetch for no reason. Only attendance and
the topic log are queued, and only they conflict.

**A reschedule is a self-transition, not a new row** [BR1.7]. Written
as an UPDATE of ``date`` and ``start_time`` on the existing row, so the
identity, the topic and every attendance row survive it. Implemented as
delete-and-recreate it would silently discard both.

**An unrecorded past session stays ``scheduled``** [NFR19.45]. Nothing
here transitions a session by the clock passing; ``held`` is reached by
RECORDING, in ``submissions.py``. A clock-driven transition would
quietly bury the classes most needing attention.

**Cancelling or moving a class still to come tells its families**
[PO-1]. The message is added to the same transaction as the change, so
the two land together or not at all, and a refused change (a cancelled
class, an inactive batch, an occupied slot) writes none. Recipients are
:func:`~app.notifications.recipients.deliver_to_families`'s: accepted
students and guardians only, never a pending or declined link and never
the teacher. No push is sent: V1 has no device-token store, so the
inbox is the channel, as it is for exams and notices.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import Batch, BatchSubject, Session
from app.errors import ConflictError
from app.local_time import DHAKA, bangladesh_now, bangladesh_today
from app.notifications.inbox import (
    CLASS_CANCELLED,
    CLASS_RESCHEDULED,
    ClassChange,
    remove_for_source,
    sent_class_change,
)
from app.notifications.recipients import deliver_to_families
from app.teaching.roster import readable_session, refuse, writable_session

__all__ = [
    "SessionRow",
    "cancel_session",
    "create_ad_hoc_session",
    "list_sessions",
    "read_session",
    "reschedule_session",
]


@dataclass(frozen=True, slots=True)
class SessionRow:
    """One session, as any entitled lens sees it.

    ``topic_logged`` is a **server-computed decision** [TC-9, D-31]:
    the client renders it and never compares ``topic`` to ``''``
    itself. It is what makes BR2.2's distinction reach the screen --
    an unwritten topic is not the same fact as one saved as blank.

    :ivar session_id: The session
    :ivar date: When it meets
    :ivar start_time: When it starts
    :ivar end_time: When it ends, or None
    :ivar status: ``scheduled``, ``held`` or ``cancelled``
    :ivar origin: ``recurrence`` or ``ad_hoc``
    :ivar topic: What was covered, or None if never logged
    :ivar topic_logged: Whether a topic was ever written
    :ivar subject_name: The subject taught, or None
    :ivar attendance_version: The roster's current version
    :ivar topic_version: The topic log's current version
    """

    session_id: uuid.UUID
    date: dt.date
    start_time: dt.time
    end_time: dt.time | None
    status: str
    origin: str
    topic: str | None
    topic_logged: bool
    subject_name: str | None
    attendance_version: int
    topic_version: int


def _row(record: Session, subject_name: str | None) -> SessionRow:
    """Render one session row.

    :param record: The session
    :param subject_name: Its subject's name, or None
    :return: The view row
    """
    return SessionRow(
        session_id=record.id,
        date=record.date,
        start_time=record.start_time,
        end_time=record.end_time,
        status=record.status,
        origin=record.origin,
        topic=record.topic,
        # BR2.2: NULL is "nobody logged this"; '' is "logged as
        # blank". Before a class is held the column holds its PLAN,
        # which is not a logged topic. Computed here so no client has to.
        topic_logged=record.status == "held" and record.topic is not None,
        subject_name=subject_name,
        attendance_version=record.attendance_version,
        topic_version=record.topic_version,
    )


def _owned_batch(
    session: DbSession, *, lens: TeacherLens, batch_id: uuid.UUID
) -> Batch:
    """Return a batch this lens owns, or refuse.

    :param session: The session to read through
    :param lens: The teacher lens
    :param batch_id: The batch
    :return: The batch row
    :raises AuthorizationError: This lens does not own it
    """
    row = session.scalars(
        sa.select(Batch).where(Batch.id == batch_id, Batch.owner_id == lens.owner_id)
    ).one_or_none()
    if row is None:
        raise refuse()
    return row


def list_sessions(
    session: DbSession,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
) -> list[SessionRow]:
    """List one batch's sessions, oldest first.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param batch_id: The batch
    :return: One row per session
    :raises AuthorizationError: This lens does not own the batch
    """
    _owned_batch(session, lens=lens, batch_id=batch_id)

    rows = session.execute(
        sa.select(Session, BatchSubject.name)
        .outerjoin(BatchSubject, BatchSubject.id == Session.batch_subject_id)
        .where(Session.batch_id == batch_id)
        .order_by(Session.date, Session.start_time)
    ).all()
    return [_row(entry[0], entry[1]) for entry in rows]


def read_session(
    session: DbSession,
    *,
    lens: TeacherLens,
    session_id: uuid.UUID,
) -> SessionRow:
    """Read one session [BR5.2, reader 2].

    :param session: The session to read through
    :param lens: The teacher lens
    :param session_id: The session
    :return: The view row
    :raises AuthorizationError: This lens does not reach it
    """
    record = readable_session(session, lens=lens, session_id=session_id)
    name = session.scalars(
        sa.select(BatchSubject.name).where(BatchSubject.id == record.batch_subject_id)
    ).one_or_none()
    return _row(record, name)


def _assert_subject_belongs_to_batch(
    session: DbSession,
    *,
    batch_id: uuid.UUID,
    batch_subject_id: uuid.UUID | None,
) -> None:
    """Refuse a subject from another batch [BR4.1's reasoning].

    The refusal is the shared ``NOT_AVAILABLE`` rather than a
    descriptive one: the subject id is an unreachable resource, and
    naming it as wrong is the oracle.

    :param session: The session to read through
    :param batch_id: The batch the row belongs to
    :param batch_subject_id: The subject named, or None
    :return: None
    :raises AuthorizationError: The subject is not this batch's
    """
    if batch_subject_id is None:
        return
    owned = session.scalars(
        sa.select(BatchSubject.id).where(
            BatchSubject.id == batch_subject_id,
            BatchSubject.batch_id == batch_id,
        )
    ).one_or_none()
    if owned is None:
        raise refuse()


def create_ad_hoc_session(
    session: DbSession,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
    date: dt.date,
    start_time: dt.time,
    end_time: dt.time | None = None,
    batch_subject_id: uuid.UUID | None = None,
) -> SessionRow:
    """Create a session for a date with no scheduled slot [BR1.4].

    ``origin`` is stated as ``ad_hoc`` explicitly, and generation
    never creates, modifies or deletes one.

    :param session: The session to work through
    :param lens: The teacher lens
    :param batch_id: The batch meeting
    :param date: When
    :param start_time: When it starts
    :param end_time: When it ends, or None
    :param batch_subject_id: The subject, or None
    :return: The new session
    :raises AuthorizationError: This lens does not own the batch, or
        the subject is not that batch's
    :raises ConflictError: The batch is inactive, or a session already
        exists at that date and time
    """
    batch = _owned_batch(session, lens=lens, batch_id=batch_id)
    if not batch.active:
        raise ConflictError(
            code="BATCH_INACTIVE",
            message_key="teaching.batch.inactive",
        )
    _assert_subject_belongs_to_batch(
        session, batch_id=batch_id, batch_subject_id=batch_subject_id
    )

    record = Session(
        batch_id=batch_id,
        batch_subject_id=batch_subject_id,
        date=date,
        start_time=start_time,
        end_time=end_time,
        status="scheduled",
        origin="ad_hoc",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    try:
        session.commit()
    except sa.exc.IntegrityError as error:
        session.rollback()
        # The (batch_id, date, start_time) constraint. A ConflictError
        # rather than a ValidationError: the request is well-formed
        # and the CURRENT STATE is what forbids it.
        raise ConflictError(
            code="SESSION_ALREADY_EXISTS",
            message_key="teaching.session.already_exists",
        ) from error

    return _row(record, None)


def reschedule_session(
    session: DbSession,
    *,
    lens: TeacherLens,
    session_id: uuid.UUID,
    date: dt.date,
    start_time: dt.time,
    now: dt.datetime | None = None,
) -> SessionRow:
    """Move a session, preserving its identity [BR1.7], and tell its families.

    **A move is news when the class is still to be held** [PO-1]: it is
    ``scheduled``, its date or time actually changed, and the old slot
    or the new one starts now or later in Bangladesh -- the start time,
    not only the day, so a class held this morning is not news this
    evening. Either slot suffices, because families expected the old
    one: **moving a class still to come into the past still tells
    them**, since the class they expect will not happen. Each accepted
    student and guardian then gets one ``class_rescheduled`` item with
    the old and new day and time (see :func:`_announce_move`). A refused
    move writes nothing.

    The row is read under its lock, so a cancel racing this move either
    lands first and refuses it, or waits for it and cancels the moved
    class.

    **An UPDATE of the existing row**, never a delete-and-recreate.
    The id, the topic and every attendance row survive, which is the
    whole content of the rule: implemented as delete-and-recreate, a
    reschedule silently discards the topic and attendance already
    recorded against the class.

    :param session: The session to work through
    :param lens: The teacher lens
    :param session_id: The session being moved
    :param date: Its new date
    :param start_time: Its new start time
    :param now: The present, or None for the clock
    :return: The moved session
    :raises AuthorizationError: This lens does not reach it
    :raises ConflictError: It is cancelled, its batch is inactive, or
        the new slot collides with another session of the same batch
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    record = writable_session(session, lens=lens, session_id=session_id, lock=True)
    was = (record.date, record.start_time)
    announce = (
        record.status == "scheduled"
        and was != (date, start_time)
        and (
            _still_to_come(was[0], was[1], moment)
            or _still_to_come(date, start_time, moment)
        )
    )

    record.date = date
    record.start_time = start_time
    try:
        # Flushed before any message is written, so an occupied slot
        # refuses here and no family hears of a move that never happened.
        session.flush()
    except sa.exc.IntegrityError as error:
        session.rollback()
        raise ConflictError(
            code="SESSION_ALREADY_EXISTS",
            message_key="teaching.session.already_exists",
        ) from error

    if announce:
        _announce_move(
            session, record, was=was, today=bangladesh_today(moment), now=moment
        )
    session.commit()

    return _row(record, None)


def _announce_move(
    session: DbSession,
    record: Session,
    *,
    was: tuple[dt.date, dt.time],
    today: dt.date,
    now: dt.datetime,
) -> None:
    """Tell a moved class's families where it is now, replacing any earlier move.

    **One item per person, never a stack.** The previous move's items
    are removed and one new item written. It says where the class was
    before the FIRST move, because the item it replaces may never have
    been opened and the reader's last-known time is then the original;
    moved back to that original, it names the move just made instead,
    since "from 4 pm to 4 pm" says nothing.

    **Membership is judged on the earlier of the two days**, no earlier
    than today. A seat that has left by then would attend neither class.

    Adds to the caller's transaction and does not commit.

    :param session: The caller's session, holding the moved row
    :param record: The session, already at its new date and time
    :param was: Its date and start time before this move
    :param today: Today in Bangladesh
    :param now: The present, stamped on the items
    :return: None
    """
    now_at = (record.date, record.start_time)
    sent = sent_class_change(session, kind=CLASS_RESCHEDULED, source_id=record.id)
    origin = was
    if sent is not None and sent.moved_from_date and sent.moved_from_time:
        origin = (sent.moved_from_date, sent.moved_from_time)
    if origin == now_at:
        origin = was

    remove_for_source(session, kind=CLASS_RESCHEDULED, source_id=record.id)
    deliver_to_families(
        session,
        batch=session.get_one(Batch, record.batch_id),
        kind=CLASS_RESCHEDULED,
        source_id=record.id,
        preview=None,
        now=now,
        on=max(today, min(was[0], record.date)),
        class_change=ClassChange(
            class_date=record.date,
            class_time=record.start_time,
            moved_from_date=origin[0],
            moved_from_time=origin[1],
        ),
    )


def cancel_session(
    session: DbSession,
    *,
    lens: TeacherLens,
    session_id: uuid.UUID,
    now: dt.datetime | None = None,
) -> SessionRow:
    """Cancel a session [BR1.6], and tell its families if it was still to come.

    ``cancelled`` is **terminal for writes and not for reads**: the
    row and its history remain readable, and only new attendance and
    topic writes are refused.

    **Only a class still to be held is news** [PO-1]: a ``scheduled``
    class whose start, in Bangladesh, is now or later. The start time
    counts, not only the day: a class held this morning and cancelled
    this evening corrects the record and is not news to a family.
    Each accepted student and
    guardian gets one ``class_cancelled`` item naming the class's day
    and time, replacing any ``class_rescheduled`` item for it. A past or
    already-held class is cancelled as before and tells nobody; an
    already-cancelled one keeps its refusal and writes nothing.

    The row is read under its lock, so a reschedule racing this cancel
    either lands first and is cancelled with it, or waits and is refused.

    :param session: The session to work through
    :param lens: The teacher lens
    :param session_id: The session being cancelled
    :param now: The present, or None for the clock
    :return: The cancelled session
    :raises AuthorizationError: This lens does not reach it
    :raises ConflictError: Its batch is inactive, or it is already
        cancelled
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    record = writable_session(session, lens=lens, session_id=session_id, lock=True)
    announce = record.status == "scheduled" and _still_to_come(
        record.date, record.start_time, moment
    )
    record.status = "cancelled"
    session.flush()
    # A move's item is withdrawn whether or not the cancellation is
    # news: "moved to Wednesday" must not outlive the class it names.
    remove_for_source(session, kind=CLASS_RESCHEDULED, source_id=record.id)
    if announce:
        deliver_to_families(
            session,
            batch=session.get_one(Batch, record.batch_id),
            kind=CLASS_CANCELLED,
            source_id=record.id,
            preview=None,
            now=moment,
            on=record.date,
            class_change=ClassChange(
                class_date=record.date, class_time=record.start_time
            ),
        )
    session.commit()
    return _row(record, None)


def _still_to_come(day: dt.date, start: dt.time, now: dt.datetime) -> bool:
    """Say whether a class slot starts now or later, in Bangladesh time.

    The stored date and start time are Bangladesh wall-clock values, so
    they are read in that zone and compared with the present there.

    :param day: The class's date
    :param start: Its start time
    :param now: The present
    :return: True while the class has not yet started
    """
    return dt.datetime.combine(day, start, tzinfo=DHAKA) >= bangladesh_now(now)


def write_session_subject(
    session: DbSession,
    *,
    lens: TeacherLens,
    session_id: uuid.UUID,
    batch_subject_id: uuid.UUID | None,
) -> SessionRow:
    """Set which subject a session taught [BR2.1's first half].

    An interactive write carrying no version [BR3.11]: unlike the
    topic log, the subject is chosen from a list while online.

    :param session: The session to work through
    :param lens: The teacher lens
    :param session_id: The session
    :param batch_subject_id: The subject, or None to clear it
    :return: The updated session
    :raises AuthorizationError: This lens does not reach the session,
        or the subject is not its batch's
    :raises ConflictError: The session is cancelled or its batch is
        inactive
    """
    record = writable_session(session, lens=lens, session_id=session_id)
    _assert_subject_belongs_to_batch(
        session, batch_id=record.batch_id, batch_subject_id=batch_subject_id
    )
    record.batch_subject_id = batch_subject_id
    session.commit()

    name = session.scalars(
        sa.select(BatchSubject.name).where(BatchSubject.id == batch_subject_id)
    ).one_or_none()
    return _row(record, name)
