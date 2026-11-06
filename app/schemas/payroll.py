"""Request and response bodies for payroll and My pay [P1, D15].

Every amount is the shared ``Money`` component, a JSON string; every
figure is the server's. A centre teacher's My pay uses the same line
shape, holding only their own lines.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import MoneyField

__all__ = [
    "AdjustmentRequest",
    "AdjustmentResponse",
    "SalaryLineResponse",
    "SalaryPaymentRequest",
    "SalaryPaymentResponse",
]


class AdjustmentRequest(BaseModel):
    """Add a named addition or deduction to a draft line.

    :ivar kind: ``addition`` or ``deduction``
    :ivar label: What it is for
    :ivar amount: How much, above zero; the kind carries the sign
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["addition", "deduction"]
    label: str = Field(min_length=1, max_length=80)
    amount: MoneyField


class SalaryPaymentRequest(BaseModel):
    """Record a payment against an approved line.

    :ivar amount: How much, above zero
    :ivar paid_on: When; today when omitted
    :ivar client_mutation_id: The retry key, so a resend pays once
    :ivar note: A receipt number or note
    """

    model_config = ConfigDict(extra="forbid")

    amount: MoneyField
    paid_on: dt.date | None = None
    client_mutation_id: uuid.UUID
    note: str | None = Field(default=None, max_length=200)


class AdjustmentResponse(BaseModel):
    """One adjustment on a line.

    :ivar adjustment_id: The adjustment
    :ivar kind: ``addition`` or ``deduction``
    :ivar label: What it is for
    :ivar amount: How much
    """

    adjustment_id: uuid.UUID
    kind: Literal["addition", "deduction"]
    label: str
    amount: MoneyField


class SalaryPaymentResponse(BaseModel):
    """One standing payment against a line.

    :ivar expense_id: The expense that records it
    :ivar amount: How much
    :ivar paid_on: When
    """

    expense_id: uuid.UUID
    amount: MoneyField
    paid_on: dt.date


class SalaryLineResponse(BaseModel):
    """One salary line, every figure the server's.

    :ivar line_id: The line
    :ivar staff_id: The person
    :ivar staff_name: The name the centre typed
    :ivar centre_name: The centre
    :ivar period: ``YYYY-MM``
    :ivar basis: ``monthly`` or ``per_class``
    :ivar rate: The salary or the rate per class
    :ivar classes_held: Classes held; live for a draft, frozen once approved
    :ivar base: The base; live for a draft, frozen once approved
    :ivar owed: Base plus additions less deductions
    :ivar paid: Everything paid against it
    :ivar remaining: What is still owed
    :ivar status: ``draft`` or ``approved``
    :ivar adjustments: Its adjustments
    :ivar payments: Its standing payments
    """

    line_id: uuid.UUID
    staff_id: uuid.UUID
    staff_name: str
    centre_name: str
    period: str
    basis: Literal["monthly", "per_class"]
    rate: MoneyField
    classes_held: int
    base: MoneyField
    owed: MoneyField
    paid: MoneyField
    remaining: MoneyField
    status: Literal["draft", "approved"]
    adjustments: list[AdjustmentResponse]
    payments: list[SalaryPaymentResponse]
