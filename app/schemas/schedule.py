"""A weekly class slot as it crosses the wire.

**Times are ``HH:MM`` strings, not Pydantic ``time``**, which serialises as
``16:00:00``. The app sends and shows minutes; a seconds field it never
uses would be one more thing two clients could disagree about.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = ["HHMM", "ScheduleRequest", "ScheduleSlotWire", "WeeklyClassWire"]

#: A clock time to the minute, 24-hour.
HHMM = Annotated[str, Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]

#: More slots than any batch could hold; bounds the request, not a rule.
MAX_SLOTS = 21


class ScheduleSlotWire(BaseModel):
    """One weekly class.

    :ivar weekday: 0-6, Monday through Sunday
    :ivar start_time: When it starts, ``HH:MM``
    :ivar end_time: When it ends, ``HH:MM``, after the start
    :ivar teacher_member_id: Who teaches it, at a centre [0024]. Left out,
        a re-save keeps the stored teacher; null clears it. A solo tutor
        never sends it
    :ivar room_id: Where, at a centre; left out keeps it, null clears it
    """

    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(ge=0, le=6)
    start_time: HHMM
    end_time: HHMM
    teacher_member_id: uuid.UUID | None = None
    room_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _ends_after_it_starts(self) -> Self:
        """Refuse a class that ends at or before its start.

        Compared as strings, which is correct for zero-padded ``HH:MM``.

        :return: The slot
        :raises ValueError: It ends at or before it starts
        """
        if self.end_time <= self.start_time:
            raise ValueError("a class must end after it starts")
        return self


class ScheduleRequest(BaseModel):
    """A batch's complete weekly schedule, replacing the old one.

    :ivar slots: Every weekly class; empty clears the schedule
    """

    model_config = ConfigDict(extra="forbid")

    slots: list[ScheduleSlotWire] = Field(max_length=MAX_SLOTS)


class WeeklyClassWire(BaseModel):
    """One weekly class as a family sees it: the day and the times only.

    Kept apart from :class:`ScheduleSlotWire` so a family's schema never
    grows the centre's assignment fields [0024].

    :ivar weekday: 0-6, Monday through Sunday
    :ivar start_time: When it starts, ``HH:MM``
    :ivar end_time: When it ends, ``HH:MM``
    """

    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(ge=0, le=6)
    start_time: HHMM
    end_time: HHMM
