"""Rooms, the centre timetable, and per-class assignment [0024].

**Every route resolves the teacher lens of the workspace the request
names**, so only a manager of that centre reaches them; the service
refuses a solo workspace. A class's own routes derive the centre from the
class, so a class elsewhere is refused exactly as a missing one is.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session as DbSession

from app.api.deps import get_session, teacher_lens
from app.authz.lenses import TeacherLens
from app.db.models import Room
from app.schemas.errors import ErrorEnvelope
from app.schemas.timetable import (
    AssignmentRequest,
    RoomCreateRequest,
    RoomResponse,
    RoomUpdateRequest,
    SwapRequest,
    TimetableClassResponse,
)
from app.teaching import assignment
from app.teaching.assignment import TimetableRow

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["timetable"])

_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    401: {"model": ErrorEnvelope, "description": "No credential, or an expired one."},
    403: {
        "model": ErrorEnvelope,
        "description": "No lens reaches this; absence reads the same.",
    },
    400: {
        "model": ErrorEnvelope,
        "description": "The request is wrong. Fix and resubmit; never retry as-is.",
    },
    409: {
        "model": ErrorEnvelope,
        "description": "Valid request; current state forbids it. CLASS_CLASH "
        "names the class it collides with in details.",
    },
}


def _room(room: Room) -> RoomResponse:
    """Render one room.

    :param room: The room
    :return: The response body
    """
    return RoomResponse(
        room_id=room.id, name=room.name, archived=room.archived_at is not None
    )


def _hhmm(value: dt.time | None) -> str | None:
    """Render a time to the minute.

    :param value: The time, or None
    :return: ``HH:MM``, or None
    """
    return None if value is None else value.strftime("%H:%M")


def _class(row: TimetableRow) -> TimetableClassResponse:
    """Render one timetable class.

    :param row: The class
    :return: The response body
    """
    return TimetableClassResponse(
        session_id=row.session_id,
        batch_id=row.batch_id,
        batch_name=row.batch_name,
        subject=row.subject,
        date=row.date,
        start_time=row.start_time.strftime("%H:%M"),
        end_time=_hhmm(row.end_time),
        status=row.status,
        teacher_member_id=row.teacher_member_id,
        teacher_name=row.teacher_name,
        room_id=row.room_id,
        room_name=row.room_name,
        overridden=row.overridden,
    )


@router.get("/centre/rooms", response_model=list[RoomResponse], responses=_ERRORS)
def list_rooms(
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> list[RoomResponse]:
    """List the centre's rooms, live ones first.

    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: Every room
    """
    return [_room(room) for room in assignment.list_rooms(session, lens=lens)]


@router.post(
    "/centre/rooms",
    response_model=RoomResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
)
def add_room(
    body: RoomCreateRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> RoomResponse:
    """Add a room.

    :param body: Its name
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: The new room
    """
    return _room(assignment.add_room(session, lens=lens, name=body.name))


@router.patch("/centre/rooms/{room_id}", response_model=RoomResponse, responses=_ERRORS)
def update_room(
    room_id: uuid.UUID,
    body: RoomUpdateRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> RoomResponse:
    """Rename, archive or restore a room.

    :param room_id: The room
    :param body: What to change
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: The room
    """
    return _room(
        assignment.update_room(
            session, lens=lens, room_id=room_id, name=body.name, archived=body.archived
        )
    )


@router.get(
    "/centre/timetable",
    response_model=list[TimetableClassResponse],
    responses=_ERRORS,
)
def read_timetable(
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[DbSession, Depends(get_session)],
    first: Annotated[dt.date, Query(alias="from")],
    last: Annotated[dt.date, Query(alias="to")],
) -> list[TimetableClassResponse]:
    """List every class of the centre between two dates, at most 31 days.

    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :param first: The first date, inclusive
    :param last: The last date, inclusive
    :return: The classes, soonest first
    """
    return [
        _class(row)
        for row in assignment.timetable(session, lens=lens, first=first, last=last)
    ]


@router.post(
    "/sessions/{session_id}/assignment",
    response_model=TimetableClassResponse,
    responses=_ERRORS,
)
def assign_class(
    session_id: uuid.UUID,
    body: AssignmentRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> TimetableClassResponse:
    """Set one class's teacher and room, apart from its weekly slot.

    :param session_id: The class
    :param body: Its teacher and room
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: The class as the timetable shows it
    """
    row = assignment.override_assignment(
        session,
        lens=lens,
        session_id=session_id,
        teacher_member_id=body.teacher_member_id,
        room_id=body.room_id,
    )
    return _one(session, lens, row.date, row.id)


@router.post(
    "/centre/sessions/swap",
    response_model=list[TimetableClassResponse],
    responses=_ERRORS,
)
def swap_classes(
    body: SwapRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> list[TimetableClassResponse]:
    """Exchange the teachers of two classes.

    :param body: The two classes
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: Both classes as the timetable shows them
    """
    first, second = assignment.swap_teachers(
        session,
        lens=lens,
        first_id=body.first_session_id,
        second_id=body.second_session_id,
    )
    return [
        _one(session, lens, first.date, first.id),
        _one(session, lens, second.date, second.id),
    ]


def _one(
    session: DbSession, lens: TeacherLens, date: dt.date, session_id: uuid.UUID
) -> TimetableClassResponse:
    """Read one class back as the timetable shows it.

    :param session: The session to read through
    :param lens: The manager's lens
    :param date: The class's date
    :param session_id: The class
    :return: The class
    """
    for row in assignment.timetable(session, lens=lens, first=date, last=date):
        if row.session_id == session_id:
            return _class(row)
    raise AssertionError("a class just written is on its own day")  # pragma: no cover
