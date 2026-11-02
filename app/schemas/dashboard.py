"""The progress dashboard response, one shape for three lenses.

**Percentages are whole numbers and a percentage of nothing is null.**
``batch_average`` and ``batch_highest`` are numbers in the exam's own
marks, present only where at least three seats have a mark and, for a
family lens, where the teacher published the marksheet. They never carry
a name. ``owed`` is a money string.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.fees import MonthState
from app.schemas.money import MoneyField

__all__ = [
    "AttendanceMonthResponse",
    "DashboardExamResponse",
    "DashboardFeeMonthResponse",
    "DashboardResponse",
    "DashboardTilesResponse",
]

PERIOD_PATTERN = r"^[0-9]{4}-(0[1-9]|1[0-2])$"


class DashboardTilesResponse(BaseModel):
    """The headline figures.

    :ivar attendance_percent: Present as a percent of held, or null
    :ivar present: Held classes attended
    :ivar held: Classes held
    :ivar exam_average_percent: Mean of the seat's exam percents, or null
    :ivar direction: Which way the latest run went, or null
    :ivar owed: What the seat owes now
    """

    model_config = ConfigDict(extra="forbid")

    attendance_percent: int | None = Field(ge=0, le=100)
    present: int = Field(ge=0)
    held: int = Field(ge=0)
    exam_average_percent: int | None
    direction: Literal["up", "down", "same"] | None
    owed: MoneyField


class AttendanceMonthResponse(BaseModel):
    """One month of attendance.

    :ivar period: The month, as ``YYYY-MM``
    :ivar held: Classes held; cancelled ones are not counted
    :ivar present: Classes attended
    :ivar percent: Present as a percent of held, or null
    :ivar in_progress: The month contains today
    """

    model_config = ConfigDict(extra="forbid")

    period: str = Field(pattern=PERIOD_PATTERN)
    held: int = Field(ge=0)
    present: int = Field(ge=0)
    percent: int | None = Field(ge=0, le=100)
    in_progress: bool


class DashboardExamResponse(BaseModel):
    """One exam on the chart.

    :ivar exam_id: The exam
    :ivar title: Its title
    :ivar date: When it was sat
    :ivar subject: The subject, or null
    :ivar marks: The seat's mark, or null for an absence
    :ivar total: The exam's denominator
    :ivar percent: The mark as a whole percent, or null
    :ivar batch_average: The batch's mean mark, or null
    :ivar batch_highest: The batch's highest mark, or null
    """

    model_config = ConfigDict(extra="forbid")

    exam_id: uuid.UUID
    title: str
    date: dt.date
    subject: str | None
    marks: int | None
    total: int
    percent: int | None
    batch_average: int | None
    batch_highest: int | None


class DashboardFeeMonthResponse(BaseModel):
    """One month on the fee strip.

    :ivar period: The month, as ``YYYY-MM``
    :ivar state: The server-computed payment state
    """

    model_config = ConfigDict(extra="forbid")

    period: str = Field(pattern=PERIOD_PATTERN)
    state: MonthState


class DashboardResponse(BaseModel):
    """Everything the dashboard draws for one seat.

    :ivar tiles: The headline figures
    :ivar attendance_by_month: Oldest first
    :ivar exams: Oldest first
    :ivar fee_months: Oldest first
    """

    model_config = ConfigDict(extra="forbid")

    tiles: DashboardTilesResponse
    attendance_by_month: list[AttendanceMonthResponse]
    exams: list[DashboardExamResponse]
    fee_months: list[DashboardFeeMonthResponse]
