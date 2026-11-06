"""Expense and monthly-summary routes [0021].

**Every route resolves the teacher lens** and scopes by its owner. There
is no family route: what an owner spends is theirs alone.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_session, teacher_lens
from app.authz.lenses import TeacherLens
from app.db.models import Expense
from app.expenses.service import (
    ExpenseDraft,
    expenses_in_month,
    month_of,
    record_expense,
    void_expense,
)
from app.expenses.summary import month_summary
from app.money import Money as DomainMoney
from app.money.wire import parse, to_wire
from app.schemas.errors import ErrorEnvelope
from app.schemas.expenses import (
    CategoryTotalResponse,
    ExpenseMonthResponse,
    ExpenseRequest,
    ExpenseResponse,
    ExpenseVoidRequest,
    MoneyCollectedResponse,
    MoneyFeeLineResponse,
    MoneySummaryResponse,
)
from app.schemas.money import Money as WireMoney

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["expenses"])

_AUTH_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    401: {"model": ErrorEnvelope, "description": "No credential, or an expired one."},
    403: {
        "model": ErrorEnvelope,
        "description": "No lens reaches this; absence reads the same.",
    },
}

_WRITE_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    **_AUTH_ERRORS,
    400: {
        "model": ErrorEnvelope,
        "description": "The request is wrong. Fix and resubmit; never retry as-is.",
    },
    409: {
        "model": ErrorEnvelope,
        "description": "Valid request; current state forbids it. Refetch and decide.",
    },
}


def _wire(amount: DomainMoney) -> WireMoney:
    """Render an amount as the wire component.

    :param amount: The domain amount
    :return: The JSON-string component
    """
    return WireMoney(to_wire(amount))


def _expense(row: Expense) -> ExpenseResponse:
    """Render one expense.

    :param row: The stored expense
    :return: The response body
    """
    return ExpenseResponse.model_validate(
        {
            "expense_id": row.id,
            "category": row.category,
            "what": row.what,
            "amount": _wire(row.amount),
            "spent_on": row.spent_on,
            "payee": row.payee,
            "note": row.note,
            "batch_id": row.batch_id,
            "extra_fee_id": row.extra_fee_id,
            "voided": row.voided_at is not None,
            "void_reason": row.void_reason,
            "voided_at": row.voided_at,
        }
    )


def _categories(pairs: list[tuple[str, DomainMoney]]) -> list[CategoryTotalResponse]:
    """Render category totals.

    :param pairs: Category and total, in order
    :return: The response rows
    """
    return [
        CategoryTotalResponse.model_validate({"category": c, "total": _wire(t)})
        for c, t in pairs
    ]


@router.post(
    "/expenses",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_ERRORS,
)
def create_expense(
    body: ExpenseRequest,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> ExpenseResponse:
    """Record one expense. A resend under the same key returns the original.

    :param body: The expense as typed
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The expense
    """
    return _expense(
        record_expense(
            session,
            lens=lens,
            draft=ExpenseDraft(
                category=body.category,
                what=body.what,
                amount=parse(body.amount.root),
                spent_on=body.spent_on,
                payee=body.payee,
                note=body.note,
                batch_id=body.batch_id,
                extra_fee_id=body.extra_fee_id,
                client_mutation_id=body.client_mutation_id,
            ),
        )
    )


@router.post(
    "/expenses/{expense_id}/void",
    response_model=ExpenseResponse,
    responses=_WRITE_ERRORS,
)
def void_one_expense(
    expense_id: uuid.UUID,
    body: ExpenseVoidRequest,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> ExpenseResponse:
    """Void an expense, keeping it on the record.

    :param expense_id: The expense, from the route path
    :param body: Why
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The voided expense
    """
    return _expense(
        void_expense(session, lens=lens, expense_id=expense_id, reason=body.reason)
    )


@router.get(
    "/expenses",
    response_model=ExpenseMonthResponse,
    responses=_WRITE_ERRORS,
)
def read_expenses(
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    month: str | None = None,
) -> ExpenseMonthResponse:
    """One month's expenses with the server's totals; this month by default.

    :param session: The request-scoped session
    :param lens: The teacher lens
    :param month: ``YYYY-MM``
    :return: The month
    """
    found = expenses_in_month(session, lens=lens, month=month_of(month))
    return ExpenseMonthResponse(
        month=found.month,
        total=_wire(found.total),
        by_category=_categories(found.by_category),
        expenses=[_expense(row) for row in found.expenses],
    )


@router.get(
    "/money/summary",
    response_model=MoneySummaryResponse,
    responses=_WRITE_ERRORS,
)
def read_money_summary(
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    month: str | None = None,
) -> MoneySummaryResponse:
    """One month's money in and out, and what is owed today.

    :param session: The request-scoped session
    :param lens: The teacher lens
    :param month: ``YYYY-MM``; this month by default
    :return: The summary
    """
    summary = month_summary(session, lens=lens, month=month_of(month))
    return MoneySummaryResponse(
        month=summary.month,
        collected=MoneyCollectedResponse(
            monthly=_wire(summary.collected_monthly),
            exam=_wire(summary.collected_exam),
            other=_wire(summary.collected_other),
            total=_wire(summary.collected_total),
        ),
        spent_total=_wire(summary.spent_total),
        spent_by_category=_categories(summary.spent_by_category),
        net=_wire(summary.net),
        net_kind=summary.net_kind,
        owed_monthly=_wire(summary.owed_monthly),
        owed_extra=_wire(summary.owed_extra),
        extra_fees=[
            MoneyFeeLineResponse(
                extra_fee_id=line.extra_fee_id,
                label=line.label,
                collected=_wire(line.collected),
                spent=_wire(line.spent),
            )
            for line in summary.extra_fees
        ],
    )
