"""Response bodies for a centre teacher's own classes [C4].

**Names only, by schema** [D2]. The roster carries a seat id, the name
the teacher who added the student typed, and the mark: no phone, no
guardian, no fee, no profile field. The class-teacher schema gate asserts
it over every route this lens reaches.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel

from app.schemas.schedule import HHMM

__all__ = [
    "ClassRosterResponse",
    "ClassRosterSeatResponse",
    "ExamineeResponse",
    "ExaminerResultsResponse",
    "MyClassResponse",
    "MyExamResponse",
]


class MyClassResponse(BaseModel):
    """One class assigned to the caller.

    :ivar session_id: The class
    :ivar centre_name: The centre it belongs to
    :ivar batch_name: Its batch
    :ivar subject: Its subject, or None
    :ivar date: Its date
    :ivar start_time: When it starts, ``HH:MM``
    :ivar end_time: When it ends, ``HH:MM``, or None
    :ivar status: ``scheduled``, ``held`` or ``cancelled``
    :ivar room_name: Where, or None
    :ivar topic_logged: Whether its topic has been written
    """

    session_id: uuid.UUID
    centre_name: str
    batch_name: str
    subject: str | None = None
    date: dt.date
    start_time: HHMM
    end_time: HHMM | None = None
    status: Literal["scheduled", "held", "cancelled"]
    room_name: str | None = None
    topic_logged: bool


class ClassRosterSeatResponse(BaseModel):
    """One student on a class teacher's roster: a name and a mark.

    :ivar enrollment_id: The seat, to mark against
    :ivar display_name: The name the centre typed for the student
    :ivar present: The recorded mark, or None while unmarked
    """

    enrollment_id: uuid.UUID
    display_name: str
    present: bool | None = None


class ClassRosterResponse(BaseModel):
    """A class's roster as its assigned teacher sees it.

    :ivar seats: Every seat on the roster
    :ivar attendance_version: The version a write is composed against
    :ivar writable: Whether a write would be accepted now
    :ivar topic: What was taught, as last written, or None
    :ivar topic_version: The version a topic write is composed against
    """

    seats: list[ClassRosterSeatResponse]
    attendance_version: int
    writable: bool
    topic: str | None = None
    topic_version: int


class MyExamResponse(BaseModel):
    """One exam the caller marks [C4].

    :ivar exam_id: The exam
    :ivar centre_name: Its centre
    :ivar batch_name: Its batch
    :ivar subject_name: Its subject
    :ivar title: Its name
    :ivar date: When it was sat
    :ivar total_marks: The denominator
    :ivar published: Whether its results have been published
    :ivar cancelled: Whether it was cancelled
    """

    exam_id: uuid.UUID
    centre_name: str
    batch_name: str
    subject_name: str
    title: str
    date: dt.date
    total_marks: int
    published: bool
    cancelled: bool


class ExamineeResponse(BaseModel):
    """One seat on an exam, as its examiner sees it: a name and a result.

    :ivar enrollment_id: The seat, to mark against
    :ivar display_name: The name the centre typed for the student
    :ivar result_state: ``marked``, ``absent``, ``not_entered`` or
        ``joined_after``
    :ivar marks: The number, for ``marked``
    """

    enrollment_id: uuid.UUID
    display_name: str
    result_state: Literal["marked", "absent", "not_entered", "joined_after"]
    marks: float | None = None


class ExaminerResultsResponse(BaseModel):
    """An exam's results as its examiner sees them.

    :ivar exam: The exam
    :ivar results: One row per seat
    :ivar writable: Whether a mark would be accepted now
    """

    exam: MyExamResponse
    results: list[ExamineeResponse]
    writable: bool
