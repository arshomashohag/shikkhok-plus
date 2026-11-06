"""Payroll routes, and a centre teacher's My pay [P1, D15].

**The manager's routes resolve the centre's teacher lens**; the service
refuses a solo workspace, which has no staff. **My pay is lens-exempt** on
``GET /v1/me/classes``'s reasoning: it reports only the lines paying the
authenticated account, through its own live memberships, in the query
that reads them.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session as DbSession

from app.api.deps import authenticated_account, get_session, teacher_lens
from app.authz.lenses import TeacherLens
from app.money.wire import parse, to_wire
from app.payroll import service
from app.payroll.service import LineView
from app.schemas.errors import ErrorEnvelope
from app.schemas.payroll import (
    AdjustmentRequest,
    AdjustmentResponse,
    SalaryLineResponse,
    SalaryPaymentRequest,
    SalaryPaymentResponse,
)

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["payroll"])

#: A month, ``YYYY-MM``.
PeriodKey = Annotated[str, Path(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")]

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
        "description": "Valid request; the line's state forbids it. Refetch, decide.",
    },
}


def _line(view: LineView) -> SalaryLineResponse:
    """Render one salary line.

    :param view: The folded line
    :return: The response body
    """
    return SalaryLineResponse.model_validate(
        {
            "line_id": view.line_id,
            "staff_id": view.staff_id,
            "staff_name": view.staff_name,
            "centre_name": view.centre_name,
            "period": view.period,
            "basis": view.basis,
            "rate": to_wire(view.rate),
            "classes_held": view.classes_held,
            "base": to_wire(view.base),
            "owed": to_wire(view.owed),
            "paid": to_wire(view.paid),
            "remaining": to_wire(view.remaining),
            "status": view.status,
            "adjustments": [
                AdjustmentResponse.model_validate(
                    {
                        "adjustment_id": a.adjustment_id,
                        "kind": a.kind,
                        "label": a.label,
                        "amount": to_wire(a.amount),
                    }
                )
                for a in view.adjustments
            ],
            "payments": [
                SalaryPaymentResponse.model_validate(
                    {
                        "expense_id": p.expense_id,
                        "amount": to_wire(p.amount),
                        "paid_on": p.paid_on,
                    }
                )
                for p in view.payments
            ],
        }
    )


@router.get(
    "/centre/payroll/{period}",
    response_model=list[SalaryLineResponse],
    responses=_ERRORS,
)
def read_month(
    period: PeriodKey,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> list[SalaryLineResponse]:
    """List a month's salary lines.

    :param period: The month
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: The lines, by name
    """
    return [
        _line(v) for v in service.month_lines(session, lens=lens, period_key=period)
    ]


@router.post(
    "/centre/payroll/{period}/lines",
    response_model=list[SalaryLineResponse],
    responses=_ERRORS,
)
def draw_month(
    period: PeriodKey,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> list[SalaryLineResponse]:
    """Draw the month's lines for every paid staff member, once.

    :param period: The month
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: Every line the month has
    """
    return [_line(v) for v in service.draw_month(session, lens=lens, period_key=period)]


@router.post(
    "/centre/payroll/lines/{line_id}/adjustments",
    response_model=SalaryLineResponse,
    responses=_ERRORS,
)
def add_adjustment(
    line_id: uuid.UUID,
    body: AdjustmentRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> SalaryLineResponse:
    """Add a named addition or deduction to a draft line.

    :param line_id: The line
    :param body: The kind, label and amount
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: The line, refolded
    """
    return _line(
        service.add_adjustment(
            session,
            lens=lens,
            line_id=line_id,
            kind=body.kind,
            label=body.label,
            amount=parse(body.amount.root),
        )
    )


@router.delete(
    "/centre/payroll/lines/{line_id}/adjustments/{adjustment_id}",
    response_model=SalaryLineResponse,
    responses=_ERRORS,
)
def remove_adjustment(
    line_id: uuid.UUID,
    adjustment_id: uuid.UUID,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> SalaryLineResponse:
    """Remove an adjustment from a draft line.

    :param line_id: The line
    :param adjustment_id: The adjustment
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: The line, refolded
    """
    return _line(
        service.remove_adjustment(
            session, lens=lens, line_id=line_id, adjustment_id=adjustment_id
        )
    )


@router.post(
    "/centre/payroll/lines/{line_id}/approve",
    response_model=SalaryLineResponse,
    responses=_ERRORS,
)
def approve_line(
    line_id: uuid.UUID,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> SalaryLineResponse:
    """Approve a draft line, freezing its class count and base.

    :param line_id: The line
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: The line, frozen
    """
    return _line(service.approve(session, lens=lens, line_id=line_id))


@router.post(
    "/centre/payroll/lines/{line_id}/payments",
    response_model=SalaryLineResponse,
    responses=_ERRORS,
)
def pay_line(
    line_id: uuid.UUID,
    body: SalaryPaymentRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> SalaryLineResponse:
    """Record a payment against an approved line, as a salary expense.

    :param line_id: The line
    :param body: The amount, the date, the retry key and a note
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: The line, with the payment counted
    """
    return _line(
        service.pay(
            session,
            lens=lens,
            line_id=line_id,
            amount=parse(body.amount.root),
            paid_on=body.paid_on,
            client_mutation_id=body.client_mutation_id,
            note=body.note,
        )
    )


@router.get("/me/pay", response_model=list[SalaryLineResponse], responses=_ERRORS)
def read_my_pay(
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[DbSession, Depends(get_session)],
) -> list[SalaryLineResponse]:
    """List my approved salary lines at every centre, newest month first.

    :param account_id: The authenticated account
    :param session: The request-scoped session
    :return: My lines, with their adjustments and payments
    """
    return [_line(v) for v in service.my_pay(session, account_id=account_id)]
