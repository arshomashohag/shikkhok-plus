"""Request and response bodies for exam and other fees [0020].

Every amount is the shared ``Money`` component, a JSON string, never a
number [TC-7, D-20]. Every status is the server's: a client renders
``waived`` and ``paid`` as it is told and compares no amount itself
[TC-9, D-31].
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import MoneyField

__all__ = [
    "BatchExtraFeesResponse",
    "ExtraFeeDetailResponse",
    "ExtraFeeKind",
    "ExtraFeeRaiseRequest",
    "ExtraFeeRefResponse",
    "ExtraFeeStudentResponse",
    "ExtraFeeSummaryResponse",
    "PaymentPurpose",
    "SeatAmountRequest",
    "SeatExtraFeeResponse",
    "SeatExtraFeesResponse",
]

#: What kind of fee a teacher raised.
ExtraFeeKind = Literal["exam", "other"]

#: What a payment is for: the monthly fee, or one extra fee.
PaymentPurpose = Literal["monthly", "extra"]

#: The server's status for one student's charge, as for a month.
ChargeStatus = Literal["paid", "partly_paid", "unpaid", "waived"]


class SeatAmountRequest(BaseModel):
    """One student given a different amount; zero waives it.

    :ivar enrollment_id: The seat
    :ivar amount: Their amount, zero or more
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_id: uuid.UUID
    amount: MoneyField


class ExtraFeeRaiseRequest(BaseModel):
    """Raise an exam or other fee on a batch.

    :ivar purpose: ``exam`` or ``other``
    :ivar label: The name families see
    :ivar exam_id: The exam an exam fee is for, if linked
    :ivar amount: The per-student amount
    :ivar due_on: When it is due
    :ivar seat_amounts: Students given a different amount
    :ivar excluded_enrollment_ids: Students left out
    :ivar client_mutation_id: One UUID per fee being raised, reused on
        every resend. A resend returns the original fee with the original
        201 and charges nobody twice; the same id with a different fee is
        a 409
    """

    model_config = ConfigDict(extra="forbid")

    purpose: ExtraFeeKind
    label: str = Field(max_length=200)
    exam_id: uuid.UUID | None = None
    amount: MoneyField
    due_on: dt.date
    seat_amounts: list[SeatAmountRequest] = Field(default_factory=list, max_length=500)
    excluded_enrollment_ids: list[uuid.UUID] = Field(
        default_factory=list, max_length=500
    )
    client_mutation_id: uuid.UUID | None = None


class ExtraFeeSummaryResponse(BaseModel):
    """One fee with its totals.

    :ivar extra_fee_id: The fee
    :ivar purpose: ``exam`` or ``other``
    :ivar label: The name families see
    :ivar exam_id: The linked exam, if any
    :ivar exam_title: That exam's title, if any
    :ivar amount: The per-student amount it was raised with
    :ivar due_on: When it is due
    :ivar created_at: When it was raised
    :ivar student_count: Students charged
    :ivar paid_count: Students paid
    :ivar waived_count: Students waived
    :ivar owing_count: Students still owing
    :ivar charged_total: Everything charged
    :ivar collected_total: Everything that arrived
    :ivar owed_total: Everything still owed
    """

    model_config = ConfigDict(extra="forbid")

    extra_fee_id: uuid.UUID
    purpose: ExtraFeeKind
    label: str
    exam_id: uuid.UUID | None = None
    exam_title: str | None = None
    amount: MoneyField
    due_on: dt.date
    created_at: dt.datetime
    student_count: int
    paid_count: int
    waived_count: int
    owing_count: int
    charged_total: MoneyField
    collected_total: MoneyField
    owed_total: MoneyField


class ExtraFeeStudentResponse(BaseModel):
    """One student under one fee, as the teacher sees it.

    :ivar enrollment_id: The seat
    :ivar display_name: The teacher-typed name
    :ivar charged: What was charged
    :ivar paid: What arrived
    :ivar owed: What is still owed
    :ivar status: The server's status
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_id: uuid.UUID
    display_name: str
    charged: MoneyField
    paid: MoneyField
    owed: MoneyField
    status: ChargeStatus


class ExtraFeeDetailResponse(ExtraFeeSummaryResponse):
    """One fee with every student charged.

    :ivar students: Each student's row, by display name
    """

    model_config = ConfigDict(extra="forbid")

    students: list[ExtraFeeStudentResponse]


class BatchExtraFeesResponse(BaseModel):
    """Every fee raised on a batch, newest first.

    :ivar fees: The fees
    """

    model_config = ConfigDict(extra="forbid")

    fees: list[ExtraFeeSummaryResponse]


class SeatExtraFeeResponse(BaseModel):
    """One fee as a student or guardian sees it.

    :ivar extra_fee_id: The fee, which a payment names
    :ivar purpose: ``exam`` or ``other``
    :ivar label: The name
    :ivar due_on: When it is due
    :ivar charged: What was charged
    :ivar paid: What arrived
    :ivar owed: What is still owed
    :ivar status: The server's status
    """

    model_config = ConfigDict(extra="forbid")

    extra_fee_id: uuid.UUID
    purpose: ExtraFeeKind
    label: str
    due_on: dt.date
    charged: MoneyField
    paid: MoneyField
    owed: MoneyField
    status: ChargeStatus


class SeatExtraFeesResponse(BaseModel):
    """Every extra fee one seat was charged, soonest due first.

    :ivar fees: The fees
    """

    model_config = ConfigDict(extra="forbid")

    fees: list[SeatExtraFeeResponse]


class ExtraFeeRefResponse(BaseModel):
    """An extra fee as a payment names it.

    :ivar extra_fee_id: The fee
    :ivar purpose: ``exam`` or ``other``
    :ivar label: The name families see
    :ivar due_on: When it is due
    """

    model_config = ConfigDict(extra="forbid")

    extra_fee_id: uuid.UUID
    purpose: ExtraFeeKind
    label: str
    due_on: dt.date
