"""Request and response bodies for expenses and the monthly summary [0021].

Every amount is the shared ``Money`` component, a JSON string. The
summary's difference is an amount and a verdict, never a negative
string, because the wire carries no negative money.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import MoneyField

__all__ = [
    "CategoryTotalResponse",
    "ExpenseCategory",
    "ExpenseMonthResponse",
    "ExpenseRequest",
    "ExpenseResponse",
    "ExpenseVoidRequest",
    "MoneyCollectedResponse",
    "MoneyFeeLineResponse",
    "MoneySummaryResponse",
]

#: The closed set of categories; each client renders the key in its language.
ExpenseCategory = Literal[
    "exam_paper",
    "printing",
    "rent",
    "utilities",
    "materials",
    "transport",
    "salary",
    "other",
]


class ExpenseRequest(BaseModel):
    """Record one expense.

    :ivar category: What it was spent on
    :ivar what: The detail, as typed
    :ivar amount: What was spent, more than zero
    :ivar spent_on: The day the money went; not in the future
    :ivar payee: Who it was paid to
    :ivar note: A receipt number or note
    :ivar batch_id: The batch it was for
    :ivar extra_fee_id: The exam or other fee it was for
    :ivar client_mutation_id: One per expense being recorded; a resend
        returns the original and records nothing
    """

    model_config = ConfigDict(extra="forbid")

    category: ExpenseCategory
    what: str = Field(max_length=120)
    amount: MoneyField
    spent_on: dt.date
    payee: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=200)
    batch_id: uuid.UUID | None = None
    extra_fee_id: uuid.UUID | None = None
    client_mutation_id: uuid.UUID | None = None


class ExpenseVoidRequest(BaseModel):
    """Void an expense, keeping it on the record.

    :ivar reason: Why, shown beside it
    """

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=200)


class ExpenseResponse(BaseModel):
    """One expense.

    :ivar expense_id: The expense
    :ivar category: What it was spent on
    :ivar what: The detail
    :ivar amount: What was spent
    :ivar spent_on: The day
    :ivar payee: Who it was paid to
    :ivar note: The note
    :ivar batch_id: The batch it was for
    :ivar extra_fee_id: The exam or other fee it was for
    :ivar voided: Whether it was voided; a voided expense counts for nothing
    :ivar void_reason: Why it was voided
    :ivar voided_at: When
    """

    model_config = ConfigDict(extra="forbid")

    expense_id: uuid.UUID
    category: ExpenseCategory
    what: str
    amount: MoneyField
    spent_on: dt.date
    payee: str | None = None
    note: str | None = None
    batch_id: uuid.UUID | None = None
    extra_fee_id: uuid.UUID | None = None
    voided: bool
    void_reason: str | None = None
    voided_at: dt.datetime | None = None


class CategoryTotalResponse(BaseModel):
    """What one category came to.

    :ivar category: The category
    :ivar total: Its total, voided expenses left out
    """

    model_config = ConfigDict(extra="forbid")

    category: ExpenseCategory
    total: MoneyField


class ExpenseMonthResponse(BaseModel):
    """One month's expenses with the server's totals.

    :ivar month: ``YYYY-MM``
    :ivar total: What was spent, voided expenses left out
    :ivar by_category: Each category's total, largest first
    :ivar expenses: Every expense, voided ones included, newest first
    """

    model_config = ConfigDict(extra="forbid")

    month: str
    total: MoneyField
    by_category: list[CategoryTotalResponse]
    expenses: list[ExpenseResponse]


class MoneyCollectedResponse(BaseModel):
    """What came in during a month, by what it was for.

    :ivar monthly: For monthly fees
    :ivar exam: For exam fees
    :ivar other: For other fees
    :ivar total: The three together
    """

    model_config = ConfigDict(extra="forbid")

    monthly: MoneyField
    exam: MoneyField
    other: MoneyField
    total: MoneyField


class MoneyFeeLineResponse(BaseModel):
    """One extra fee's takings against what was spent for it.

    :ivar extra_fee_id: The fee
    :ivar label: Its name
    :ivar collected: Paid against it
    :ivar spent: Spent for it
    """

    model_config = ConfigDict(extra="forbid")

    extra_fee_id: uuid.UUID
    label: str
    collected: MoneyField
    spent: MoneyField


class MoneySummaryResponse(BaseModel):
    """One month's money, in and out, and what is owed today.

    :ivar month: ``YYYY-MM``
    :ivar collected: What came in, by purpose
    :ivar spent_total: What went out
    :ivar spent_by_category: Each category's total, largest first
    :ivar net: The difference between them, never negative
    :ivar net_kind: ``surplus``, ``deficit`` or ``even``
    :ivar owed_monthly: Monthly fees still owed today
    :ivar owed_extra: Exam and other fees still owed today
    :ivar extra_fees: Fees due this month or spent for this month
    """

    model_config = ConfigDict(extra="forbid")

    month: str
    collected: MoneyCollectedResponse
    spent_total: MoneyField
    spent_by_category: list[CategoryTotalResponse]
    net: MoneyField
    net_kind: Literal["surplus", "deficit", "even"]
    owed_monthly: MoneyField
    owed_extra: MoneyField
    extra_fees: list[MoneyFeeLineResponse]
