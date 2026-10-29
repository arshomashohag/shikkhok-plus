"""The guardian's home (G1) and payments (G3) on the wire.

Everything here is about the guardian's own children: names are the
teacher-typed ones on the seats they accepted [TC-13], and every amount,
trend and lateness is the server's [TC-9].
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.fees import PayableResponse, WaitingPaymentResponse
from app.schemas.money import MoneyField
from app.schemas.teaching import UpcomingSessionResponse

__all__ = [
    "ChildBatchResponse",
    "ChildResultResponse",
    "ChildSummaryResponse",
    "GuardianHomeResponse",
    "PaymentLineResponse",
    "PaymentMonthResponse",
    "PaymentsResponse",
    "ProgressSummaryResponse",
]


class ChildResultResponse(BaseModel):
    """A child's latest marked result in one batch, with its trend.

    :ivar enrollment_id: The seat
    :ivar batch_name: The batch
    :ivar title: The exam
    :ivar date: When it was sat
    :ivar marks: The mark
    :ivar total_marks: Out of how many
    :ivar previous_marks: The mark before it in the same batch, or null
    :ivar trend: ``up``, ``down`` or ``same`` against the previous
        mark as a share of its total, or ``first``
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_id: uuid.UUID
    batch_name: str
    title: str
    date: dt.date
    marks: int = Field(ge=0)
    total_marks: int = Field(ge=1)
    previous_marks: int | None = None
    trend: Literal["up", "down", "same", "first"]


class ChildBatchResponse(BaseModel):
    """One of the child's batches, with its next class.

    :ivar enrollment_id: The seat
    :ivar batch_name: The batch
    :ivar teacher_display_name: The teacher, or null
    :ivar next_session: The next class, or null
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_id: uuid.UUID
    batch_name: str
    teacher_display_name: str | None = None
    next_session: UpcomingSessionResponse | None = None


class ChildSummaryResponse(BaseModel):
    """One child on G1.

    :ivar key: The child's first seat, which names them in other reads
    :ivar display_name: The teacher-typed name
    :ivar batch_count: How many batches
    :ivar next_payment: The most urgent fee to pay, or null
    :ivar waiting: Payments sent and being checked
    :ivar latest_results: Each batch's latest marked result
    :ivar batches: The batches, with their next classes
    """

    model_config = ConfigDict(extra="forbid")

    key: uuid.UUID
    display_name: str
    batch_count: int = Field(ge=1)
    next_payment: PayableResponse | None = None
    waiting: list[WaitingPaymentResponse] = Field(default_factory=list)
    latest_results: list[ChildResultResponse] = Field(default_factory=list)
    batches: list[ChildBatchResponse] = Field(default_factory=list)


class GuardianHomeResponse(BaseModel):
    """Every child this guardian has accepted, by name.

    :ivar children: The children; empty before any is linked
    """

    model_config = ConfigDict(extra="forbid")

    children: list[ChildSummaryResponse] = Field(default_factory=list)


class PaymentLineResponse(BaseModel):
    """One batch's fee in one month, and where its payment stands (G3).

    :ivar enrollment_id: The seat
    :ivar batch_name: The batch
    :ivar amount: What the month charged
    :ivar state: ``paid``, ``partly_paid``, ``waived``, ``verifying`` or
        ``due``
    :ivar due_date: When it was due
    :ivar sent_on: When the latest payment for it was sent, or null
    :ivar decided_on: When that payment was approved, or null
    :ivar channel: Which app it moved through, or null
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_id: uuid.UUID
    batch_name: str
    amount: MoneyField
    state: Literal["paid", "partly_paid", "waived", "verifying", "due"]
    due_date: dt.date
    sent_on: dt.date | None = None
    decided_on: dt.date | None = None
    channel: str | None = None


class PaymentMonthResponse(BaseModel):
    """One month's fees across the child's batches.

    :ivar period: ``YYYY-MM``
    :ivar lines: One per batch charged that month
    """

    model_config = ConfigDict(extra="forbid")

    period: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    lines: list[PaymentLineResponse]


class PaymentsResponse(BaseModel):
    """A child's fee history, newest month first (G3).

    :ivar display_name: The child
    :ivar year: The year the total covers
    :ivar paid_this_year: What payments approved this year came to
    :ivar months: The months, newest first
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str
    year: int
    paid_this_year: MoneyField
    months: list[PaymentMonthResponse] = Field(default_factory=list)


class ProgressSummaryResponse(BaseModel):
    """G2's reading of a child's latest run of results in one batch.

    :ivar direction: ``up``, ``down`` or ``same``
    :ivar run: How many tests the run spans
    :ivar first_marks: The run's first mark
    :ivar last_marks: Its last mark
    :ivar total_marks: The last test's total
    :ivar above_average: Whether the last mark beats the published batch
        average, or null where none was published
    """

    model_config = ConfigDict(extra="forbid")

    direction: Literal["up", "down", "same"]
    run: int = Field(ge=2)
    first_marks: int = Field(ge=0)
    last_marks: int = Field(ge=0)
    total_marks: int = Field(ge=1)
    above_average: bool | None = None
