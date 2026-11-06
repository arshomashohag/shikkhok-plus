"""Request and response bodies for rooms and the centre timetable [0024].

A teacher appears by the name the centre typed for them and a member id
to assign by; no phone, no profile field.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.schedule import HHMM

__all__ = [
    "AssignmentRequest",
    "RoomCreateRequest",
    "RoomResponse",
    "RoomUpdateRequest",
    "SwapRequest",
    "TimetableClassResponse",
]


class RoomCreateRequest(BaseModel):
    """Add a room.

    :ivar name: Its name
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)


class RoomUpdateRequest(BaseModel):
    """Rename, archive or restore a room.

    :ivar name: Its new name, or None to keep it
    :ivar archived: True to archive, False to restore, None to leave
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=60)
    archived: bool | None = None


class RoomResponse(BaseModel):
    """One room.

    :ivar room_id: The room
    :ivar name: Its name
    :ivar archived: Whether it is no longer offered
    """

    room_id: uuid.UUID
    name: str
    archived: bool


class AssignmentRequest(BaseModel):
    """Set one class's teacher and room, apart from its weekly slot.

    :ivar teacher_member_id: Its teacher, or null for none
    :ivar room_id: Its room, or null for none
    """

    model_config = ConfigDict(extra="forbid")

    teacher_member_id: uuid.UUID | None
    room_id: uuid.UUID | None


class SwapRequest(BaseModel):
    """Exchange the teachers of two classes.

    :ivar first_session_id: One class
    :ivar second_session_id: The other
    """

    model_config = ConfigDict(extra="forbid")

    first_session_id: uuid.UUID
    second_session_id: uuid.UUID


class TimetableClassResponse(BaseModel):
    """One class on the centre's timetable.

    :ivar session_id: The class
    :ivar batch_id: Its batch
    :ivar batch_name: Its batch's name
    :ivar subject: Its subject, or None
    :ivar date: Its date
    :ivar start_time: When it starts, ``HH:MM``
    :ivar end_time: When it ends, ``HH:MM``, or None
    :ivar status: ``scheduled``, ``held`` or ``cancelled``
    :ivar teacher_member_id: Its teacher, or None
    :ivar teacher_name: The name the centre typed for them, or None
    :ivar room_id: Its room, or None
    :ivar room_name: The room's name, or None
    :ivar overridden: Whether a manager set it apart from its slot
    """

    session_id: uuid.UUID
    batch_id: uuid.UUID
    batch_name: str
    subject: str | None = None
    date: dt.date
    start_time: HHMM
    end_time: HHMM | None = None
    status: str
    teacher_member_id: uuid.UUID | None = None
    teacher_name: str | None = None
    room_id: uuid.UUID | None = None
    room_name: str | None = None
    overridden: bool
