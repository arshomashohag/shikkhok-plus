"""Who teaches each class at a centre, and where [0024].

Four things live here:

* **Rooms** -- a centre's named rooms, archived rather than deleted.
* **Checking an assignment.** Only a live member of this centre can be
  assigned, and only this centre's live rooms; a solo tutor's classes take
  neither.
* **Clashes.** A teacher or a room cannot be in two classes at once. The
  database refuses it through two exclusion constraints per table, which
  are the guarantee; the queries here run first only so the refusal can
  name the class it clashes with.
* **Moving assignments** -- a slot's change reaching its future,
  not-yet-held followers [BR1.2, amended]; a manager's per-class
  override; a swap of two classes' teachers; and freeing a removed
  teacher's future classes.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.centres.service import centre_of
from app.db.models import Batch, BatchSubject, OwnerMember, Room, ScheduleSlot, Session
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.local_time import bangladesh_today
from app.teaching.roster import writable_session
from app.teaching.unassign import unassign_member

__all__ = [
    "Clash",
    "TimetableRow",
    "add_room",
    "check_assignment",
    "find_session_clash",
    "find_slot_clash",
    "follow_slots",
    "is_exclusion",
    "list_rooms",
    "override_assignment",
    "raise_clash",
    "swap_teachers",
    "timetable",
    "unassign_member",
    "update_room",
]

#: The longest timetable read, in days; bounds the query, not a rule.
TIMETABLE_MAX_DAYS = 31

#: The exclusion constraints, by the column each guards.
SESSION_CONSTRAINTS = {
    "teacher_member_id": "ex_session_teacher_overlap",
    "room_id": "ex_session_room_overlap",
}

#: Postgres' code for an exclusion-constraint violation.
EXCLUSION_VIOLATION = "23P01"


# -------------------------------------------------------------------- rooms


def list_rooms(session: DbSession, *, lens: TeacherLens) -> list[Room]:
    """List the centre's rooms, live ones first, by name.

    :param session: The session to read through
    :param lens: The manager's lens on the centre
    :return: Every room
    :raises ConflictError: The workspace is not a centre
    """
    centre = centre_of(session, lens)
    return list(
        session.scalars(
            sa.select(Room)
            .where(Room.owner_id == centre.id)
            .order_by(Room.archived_at.is_not(None), sa.func.lower(Room.name), Room.id)
        )
    )


def _refuse_taken_name(
    session: DbSession, *, owner_id: uuid.UUID, name: str, room_id: uuid.UUID | None
) -> None:
    """Refuse a name another live room of this centre already has.

    :param session: The session to read through
    :param owner_id: The centre
    :param name: The proposed name
    :param room_id: The room being renamed, or None for a new one
    :raises ConflictError: The name is taken
    """
    taken = session.scalar(
        sa.select(Room.id).where(
            Room.owner_id == owner_id,
            Room.archived_at.is_(None),
            sa.func.lower(Room.name) == name.lower(),
            sa.true() if room_id is None else Room.id != room_id,
        )
    )
    if taken is not None:
        raise ConflictError(code="ROOM_NAME_TAKEN", message_key="room.name_taken")


def _room_name(name: str) -> str:
    """Trim a room name, refusing a blank one.

    :param name: The name as typed
    :return: The trimmed name
    :raises ValidationError: The name is blank
    """
    cleaned = name.strip()
    if not cleaned:
        raise ValidationError(code="NAME_REQUIRED", message_key="centre.name.required")
    return cleaned


def add_room(session: DbSession, *, lens: TeacherLens, name: str) -> Room:
    """Add a room to the centre. Commits.

    :param session: The session to write through
    :param lens: The manager's lens on the centre
    :param name: Its name
    :return: The new room
    :raises ConflictError: Not a centre, or the name is taken
    """
    centre = centre_of(session, lens)
    cleaned = _room_name(name)
    _refuse_taken_name(session, owner_id=centre.id, name=cleaned, room_id=None)
    room = Room(owner_id=centre.id, name=cleaned, created_at=dt.datetime.now(tz=dt.UTC))
    session.add(room)
    try:
        session.commit()
    except sa.exc.IntegrityError as error:
        session.rollback()
        raise ConflictError(
            code="ROOM_NAME_TAKEN", message_key="room.name_taken"
        ) from error
    return room


def update_room(
    session: DbSession,
    *,
    lens: TeacherLens,
    room_id: uuid.UUID,
    name: str | None,
    archived: bool | None,
) -> Room:
    """Rename a room, or archive or restore it. Commits.

    :param session: The session to write through
    :param lens: The manager's lens on the centre
    :param room_id: The room
    :param name: Its new name, or None to keep it
    :param archived: True to archive, False to restore, None to leave
    :return: The room
    :raises AuthorizationError: No such room in this centre
    :raises ConflictError: The name is taken
    """
    centre = centre_of(session, lens)
    room = session.scalar(
        sa.select(Room).where(Room.id == room_id, Room.owner_id == centre.id)
    )
    if room is None:
        raise AuthorizationError(
            code="NO_TEACHER_LENS", message_key="authz.lens.not_available"
        )
    if name is not None:
        room.name = _room_name(name)
    if archived is True and room.archived_at is None:
        room.archived_at = dt.datetime.now(tz=dt.UTC)
    if archived is False and room.archived_at is not None:
        room.archived_at = None
    if room.archived_at is None:
        _refuse_taken_name(session, owner_id=centre.id, name=room.name, room_id=room.id)
    try:
        session.commit()
    except sa.exc.IntegrityError as error:
        session.rollback()
        raise ConflictError(
            code="ROOM_NAME_TAKEN", message_key="room.name_taken"
        ) from error
    return room


# --------------------------------------------------------------- checking


def check_assignment(
    session: DbSession,
    *,
    lens: TeacherLens,
    teacher_member_id: uuid.UUID | None,
    room_id: uuid.UUID | None,
) -> None:
    """Refuse an assignment this workspace cannot make.

    :param session: The session to read through
    :param lens: The teacher lens the request acts on
    :param teacher_member_id: The proposed teacher, or None
    :param room_id: The proposed room, or None
    :raises ConflictError: A solo workspace was given either
    :raises ValidationError: The teacher is not a live member of this
        centre, or the room is not one of its live rooms
    """
    if teacher_member_id is None and room_id is None:
        return
    centre = centre_of(session, lens)
    if teacher_member_id is not None:
        live = session.scalar(
            sa.select(OwnerMember.id).where(
                OwnerMember.id == teacher_member_id,
                OwnerMember.owner_id == centre.id,
                OwnerMember.revoked_at.is_(None),
                OwnerMember.decision != "declined",
            )
        )
        if live is None:
            raise ValidationError(
                code="SCHEDULE_TEACHER_UNKNOWN",
                message_key="schedule.teacher_unknown",
            )
    if room_id is not None:
        live_room = session.scalar(
            sa.select(Room.id).where(
                Room.id == room_id,
                Room.owner_id == centre.id,
                Room.archived_at.is_(None),
            )
        )
        if live_room is None:
            raise ValidationError(
                code="SCHEDULE_ROOM_UNKNOWN", message_key="schedule.room_unknown"
            )


# ---------------------------------------------------------------- clashes


@dataclass(frozen=True, slots=True)
class Clash:
    """The class an assignment would collide with.

    :ivar batch: Its batch's name
    :ivar date: Its date, or None for a weekly slot
    :ivar weekday: Its weekday, for a weekly slot
    :ivar start_time: When it starts
    :ivar kind: ``teacher`` or ``room``
    """

    batch: str
    date: dt.date | None
    weekday: int | None
    start_time: dt.time
    kind: str


def raise_clash(clash: Clash | None) -> None:
    """Refuse with the clash named, or with no detail when it is unknown.

    :param clash: What it collides with, or None after a race the
        pre-check did not see
    :raises ConflictError: Always
    """
    details: dict[str, str] | None = None
    if clash is not None:
        details = {
            "batch": clash.batch,
            "with": clash.kind,
            "start_time": clash.start_time.strftime("%H:%M"),
        }
        if clash.date is not None:
            details["date"] = clash.date.isoformat()
        if clash.weekday is not None:
            details["weekday"] = str(clash.weekday)
    raise ConflictError(
        code="CLASS_CLASH", message_key="schedule.clash", details=details
    )


def _end(start: dt.time, end: dt.time | None) -> dt.time:
    """Return a class's end for overlap, its first minute when it has none.

    :param start: When it starts
    :param end: When it ends, or None
    :return: The end to compare with
    """
    if end is not None:
        return end
    moment = dt.datetime.combine(dt.date(2000, 1, 3), start) + dt.timedelta(minutes=1)
    return moment.time()


def find_session_clash(
    session: DbSession,
    *,
    teacher_member_id: uuid.UUID | None,
    room_id: uuid.UUID | None,
    date: dt.date,
    start_time: dt.time,
    end_time: dt.time | None,
    exclude: tuple[uuid.UUID, ...] = (),
) -> Clash | None:
    """Find a live class this one would collide with, teacher before room.

    :param session: The session to read through
    :param teacher_member_id: Its teacher, or None
    :param room_id: Its room, or None
    :param date: Its date
    :param start_time: When it starts
    :param end_time: When it ends, or None
    :param exclude: Classes to ignore, such as itself
    :return: The first clash, or None
    """
    end = _end(start_time, end_time)
    other_end = sa.func.coalesce(
        Session.end_time, Session.start_time + sa.text("interval '1 minute'")
    )
    for kind, column, value in (
        ("teacher", Session.teacher_member_id, teacher_member_id),
        ("room", Session.room_id, room_id),
    ):
        if value is None:
            continue
        row = session.execute(
            sa.select(Batch.name, Session.date, Session.start_time)
            .join(Batch, Batch.id == Session.batch_id)
            .where(
                column == value,
                Session.status != "cancelled",
                Session.date == date,
                Session.start_time < end,
                other_end > start_time,
                Session.id.not_in(exclude) if exclude else sa.true(),
            )
            .order_by(Session.start_time)
            .limit(1)
        ).first()
        if row is not None:
            return Clash(row[0], row[1], None, row[2], kind)
    return None


def find_slot_clash(
    session: DbSession,
    *,
    batch_id: uuid.UUID,
    teacher_member_id: uuid.UUID | None,
    room_id: uuid.UUID | None,
    weekday: int,
    start_time: dt.time,
    end_time: dt.time,
) -> Clash | None:
    """Find another batch's weekly class this one would collide with.

    :param session: The session to read through
    :param batch_id: The batch whose schedule is being written, ignored
    :param teacher_member_id: Its teacher, or None
    :param room_id: Its room, or None
    :param weekday: Its weekday
    :param start_time: When it starts
    :param end_time: When it ends
    :return: The first clash, or None
    """
    for kind, column, value in (
        ("teacher", ScheduleSlot.teacher_member_id, teacher_member_id),
        ("room", ScheduleSlot.room_id, room_id),
    ):
        if value is None:
            continue
        row = session.execute(
            sa.select(Batch.name, ScheduleSlot.weekday, ScheduleSlot.start_time)
            .join(Batch, Batch.id == ScheduleSlot.batch_id)
            .where(
                column == value,
                ScheduleSlot.batch_id != batch_id,
                ScheduleSlot.weekday == weekday,
                ScheduleSlot.start_time < end_time,
                ScheduleSlot.end_time > start_time,
            )
            .limit(1)
        ).first()
        if row is not None:
            return Clash(row[0], None, row[1], row[2], kind)
    return None


def is_exclusion(error: sa.exc.IntegrityError) -> bool:
    """Report whether an integrity error is a double-booking.

    :param error: The error the driver raised
    :return: True for an exclusion-constraint violation
    """
    return getattr(error.orig, "sqlstate", None) == EXCLUSION_VIOLATION


# ------------------------------------------------------ moving assignments


def follow_slots(
    session: DbSession,
    *,
    batch_id: uuid.UUID,
    today: dt.date | None = None,
) -> None:
    """Move each slot's future, unheld, following classes to its assignment.

    **The BR1.2 amendment, and no wider.** Only classes dated today or
    later, still ``scheduled``, and following their slot change; held,
    cancelled and overridden classes keep what they had, and a class's
    time and day are never touched. Adds to the caller's transaction.

    :param session: The session to write through
    :param batch_id: The batch whose schedule was just written
    :param today: The first date to move, or None for today in Bangladesh
    :raises ConflictError: A moved class would clash with another
    """
    first = today or bangladesh_today()
    slots = session.execute(
        sa.select(
            ScheduleSlot.weekday,
            ScheduleSlot.start_time,
            ScheduleSlot.teacher_member_id,
            ScheduleSlot.room_id,
        ).where(ScheduleSlot.batch_id == batch_id)
    ).all()
    for weekday, start_time, teacher, room in slots:
        followers = list(
            session.scalars(
                sa.select(Session).where(
                    Session.batch_id == batch_id,
                    Session.date >= first,
                    Session.status == "scheduled",
                    Session.assignment_source == "slot",
                    Session.start_time == start_time,
                    sa.extract("isodow", Session.date) == weekday + 1,
                )
            )
        )
        for row in followers:
            if (row.teacher_member_id, row.room_id) == (teacher, room):
                continue
            clash = find_session_clash(
                session,
                teacher_member_id=teacher,
                room_id=room,
                date=row.date,
                start_time=row.start_time,
                end_time=row.end_time,
                exclude=(row.id,),
            )
            if clash is not None:
                raise_clash(clash)
            row.teacher_member_id = teacher
            row.room_id = room
    session.flush()


def override_assignment(
    session: DbSession,
    *,
    lens: TeacherLens,
    session_id: uuid.UUID,
    teacher_member_id: uuid.UUID | None,
    room_id: uuid.UUID | None,
) -> Session:
    """Set one class's teacher and room alone, apart from its slot. Commits.

    :param session: The session to write through
    :param lens: The manager's lens
    :param session_id: The class
    :param teacher_member_id: Its teacher, or None
    :param room_id: Its room, or None
    :return: The class
    :raises AuthorizationError: Not this workspace's class
    :raises ConflictError: Cancelled, inactive, or a clash
    :raises ValidationError: An assignee this centre cannot use
    """
    row = writable_session(session, lens=lens, session_id=session_id)
    centre_of(session, lens)
    check_assignment(
        session, lens=lens, teacher_member_id=teacher_member_id, room_id=room_id
    )
    clash = find_session_clash(
        session,
        teacher_member_id=teacher_member_id,
        room_id=room_id,
        date=row.date,
        start_time=row.start_time,
        end_time=row.end_time,
        exclude=(row.id,),
    )
    if clash is not None:
        raise_clash(clash)
    row.teacher_member_id = teacher_member_id
    row.room_id = room_id
    row.assignment_source = "override"
    _commit_or_clash(session)
    return row


def swap_teachers(
    session: DbSession,
    *,
    lens: TeacherLens,
    first_id: uuid.UUID,
    second_id: uuid.UUID,
) -> tuple[Session, Session]:
    """Exchange the teachers of two of this centre's classes. Commits.

    The teacher constraint is deferred to the commit, because exchanging
    two overlapping classes' teachers passes through a moment where both
    are the same person's.

    :param session: The session to write through
    :param lens: The manager's lens
    :param first_id: One class
    :param second_id: The other
    :return: Both classes, swapped
    :raises AuthorizationError: Either is not this workspace's class
    :raises ConflictError: Either is cancelled, or a teacher would clash
        with a third class
    """
    centre_of(session, lens)
    first = writable_session(session, lens=lens, session_id=first_id)
    second = writable_session(session, lens=lens, session_id=second_id)
    both = (first.id, second.id)
    for row, teacher in (
        (first, second.teacher_member_id),
        (second, first.teacher_member_id),
    ):
        clash = find_session_clash(
            session,
            teacher_member_id=teacher,
            room_id=None,
            date=row.date,
            start_time=row.start_time,
            end_time=row.end_time,
            exclude=both,
        )
        if clash is not None:
            raise_clash(clash)
    session.execute(
        sa.text(f"SET CONSTRAINTS {SESSION_CONSTRAINTS['teacher_member_id']} DEFERRED")
    )
    first.teacher_member_id, second.teacher_member_id = (
        second.teacher_member_id,
        first.teacher_member_id,
    )
    first.assignment_source = second.assignment_source = "override"
    _commit_or_clash(session)
    return first, second


def _commit_or_clash(session: DbSession) -> None:
    """Commit, turning a double-booking the pre-check missed into a refusal.

    :param session: The session to commit
    :raises ConflictError: The database refused a double-booking
    """
    try:
        session.commit()
    except sa.exc.IntegrityError as error:
        session.rollback()
        if is_exclusion(error):
            raise ConflictError(
                code="CLASS_CLASH", message_key="schedule.clash"
            ) from error
        raise


# -------------------------------------------------------------- timetable


@dataclass(frozen=True, slots=True)
class TimetableRow:
    """One class on the centre's timetable.

    :ivar session_id: The class
    :ivar batch_id: Its batch
    :ivar batch_name: Its batch's name
    :ivar subject: Its subject, or None
    :ivar date: Its date
    :ivar start_time: When it starts
    :ivar end_time: When it ends, or None
    :ivar status: ``scheduled``, ``held`` or ``cancelled``
    :ivar teacher_member_id: Its teacher, or None
    :ivar teacher_name: The name the centre typed for them, or None
    :ivar room_id: Its room, or None
    :ivar room_name: The room's name, or None
    :ivar overridden: Whether a manager set this class apart from its slot
    """

    session_id: uuid.UUID
    batch_id: uuid.UUID
    batch_name: str
    subject: str | None
    date: dt.date
    start_time: dt.time
    end_time: dt.time | None
    status: str
    teacher_member_id: uuid.UUID | None
    teacher_name: str | None
    room_id: uuid.UUID | None
    room_name: str | None
    overridden: bool


def timetable(
    session: DbSession, *, lens: TeacherLens, first: dt.date, last: dt.date
) -> list[TimetableRow]:
    """List every class of the centre's batches between two dates.

    :param session: The session to read through
    :param lens: The manager's lens on the centre
    :param first: The first date, inclusive
    :param last: The last date, inclusive
    :return: The classes, soonest first
    :raises ConflictError: The workspace is not a centre
    :raises ValidationError: The range is backwards or too long
    """
    centre = centre_of(session, lens)
    if last < first or (last - first).days >= TIMETABLE_MAX_DAYS:
        raise ValidationError(
            code="TIMETABLE_RANGE_TOO_LONG", message_key="timetable.range_too_long"
        )
    rows = session.execute(
        sa.select(
            Session.id,
            Batch.id,
            Batch.name,
            BatchSubject.name,
            Session.date,
            Session.start_time,
            Session.end_time,
            Session.status,
            Session.teacher_member_id,
            OwnerMember.display_name,
            Session.room_id,
            Room.name,
            Session.assignment_source,
        )
        .join(Batch, Batch.id == Session.batch_id)
        .outerjoin(BatchSubject, BatchSubject.id == Session.batch_subject_id)
        .outerjoin(OwnerMember, OwnerMember.id == Session.teacher_member_id)
        .outerjoin(Room, Room.id == Session.room_id)
        .where(Batch.owner_id == centre.id, Session.date >= first, Session.date <= last)
        .order_by(Session.date, Session.start_time, Batch.name, Session.id)
    ).all()
    return [
        TimetableRow(
            session_id=r[0],
            batch_id=r[1],
            batch_name=r[2],
            subject=r[3],
            date=r[4],
            start_time=r[5],
            end_time=r[6],
            status=r[7],
            teacher_member_id=r[8],
            teacher_name=r[9],
            room_id=r[10],
            room_name=r[11],
            overridden=r[12] == "override",
        )
        for r in rows
    ]
