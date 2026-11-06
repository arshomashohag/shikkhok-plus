"""Exam and other fee routes [0020].

**Every route resolves a lens**, and the route-enumeration gate fails CI
on one that does not. The three teacher routes take the teacher lens and
scope by its owner; the family route takes a student or guardian lens
and reaches a seat only through the family rule.

**Responses carry decisions, not inputs to decisions** [TC-9, D-31].
Each student's charge carries the server's status, so no client compares
what was charged with what was paid.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import family_lens, family_lenses, get_session, teacher_lens
from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.fees.extra import (
    ExtraFeeSummary,
    FeeDraft,
    StudentRow,
    batch_extra_fees,
    chargeable_students,
    extra_fee_detail,
    raise_extra_fee,
    seat_extra_fees,
)
from app.fees.submissions import lens_reaching
from app.money import Money as DomainMoney
from app.money.wire import parse, to_wire
from app.schemas.errors import ErrorEnvelope
from app.schemas.extra_fees import (
    BatchExtraFeesResponse,
    ChargeableStudentResponse,
    ExtraFeeDetailResponse,
    ExtraFeeRaiseRequest,
    ExtraFeeStudentResponse,
    ExtraFeeSummaryResponse,
    SeatExtraFeeResponse,
    SeatExtraFeesResponse,
)
from app.schemas.money import Money as WireMoney

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["fees"])

_AUTH_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    401: {"model": ErrorEnvelope, "description": "No credential, or an expired one."},
    403: {
        "model": ErrorEnvelope,
        "description": (
            "No lens reaches this. Deliberately indistinguishable from "
            "absence: one code covers both."
        ),
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


def _summary(fee: ExtraFeeSummary) -> ExtraFeeSummaryResponse:
    """Render one fee's totals.

    :param fee: The fee
    :return: The response body
    """
    return ExtraFeeSummaryResponse(
        extra_fee_id=fee.extra_fee_id,
        purpose=fee.purpose,
        label=fee.label,
        exam_id=fee.exam_id,
        exam_title=fee.exam_title,
        amount=_wire(fee.amount),
        due_on=fee.due_on,
        created_at=fee.created_at,
        student_count=fee.student_count,
        paid_count=fee.paid_count,
        waived_count=fee.waived_count,
        owing_count=fee.owing_count,
        charged_total=_wire(fee.charged_total),
        collected_total=_wire(fee.collected_total),
        owed_total=_wire(fee.owed_total),
    )


def _student(row: StudentRow) -> ExtraFeeStudentResponse:
    """Render one student's row.

    :param row: The row
    :return: The response body
    """
    return ExtraFeeStudentResponse(
        enrollment_id=row.enrollment_id,
        display_name=row.display_name,
        charged=_wire(row.charged),
        paid=_wire(row.paid),
        owed=_wire(row.owed),
        status=row.status,
    )


@router.post(
    "/batches/{batch_id}/extra-fees",
    response_model=ExtraFeeSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_ERRORS,
)
def raise_fee(
    batch_id: uuid.UUID,
    body: ExtraFeeRaiseRequest,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> ExtraFeeSummaryResponse:
    """Raise an exam or other fee and charge the batch's students.

    A resend under the same ``client_mutation_id`` returns the original
    fee with the same 201 and charges nobody twice.

    :param batch_id: The batch, from the route path
    :param body: The fee as the teacher typed it
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The fee with its totals
    """
    fee = raise_extra_fee(
        session,
        lens=lens,
        batch_id=batch_id,
        draft=FeeDraft(
            purpose=body.purpose,
            label=body.label,
            exam_id=body.exam_id,
            amount=parse(body.amount.root),
            due_on=body.due_on,
            seat_amounts={
                item.enrollment_id: parse(item.amount.root)
                for item in body.seat_amounts
            },
            excluded=frozenset(body.excluded_enrollment_ids),
            client_mutation_id=body.client_mutation_id,
        ),
    )
    summary, _rows = extra_fee_detail(session, lens=lens, extra_fee_id=fee.id)
    return _summary(summary)


@router.get(
    "/batches/{batch_id}/extra-fees",
    response_model=BatchExtraFeesResponse,
    responses=_AUTH_ERRORS,
)
def read_batch_extra_fees(
    batch_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> BatchExtraFeesResponse:
    """List every fee raised on one of this teacher's batches.

    :param batch_id: The batch, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The fees, newest first
    """
    return BatchExtraFeesResponse(
        fees=[
            _summary(fee)
            for fee in batch_extra_fees(session, lens=lens, batch_id=batch_id)
        ],
        chargeable_students=[
            ChargeableStudentResponse(enrollment_id=seat_id, display_name=name)
            for seat_id, name in chargeable_students(
                session, lens=lens, batch_id=batch_id
            )
        ],
    )


@router.get(
    "/extra-fees/{extra_fee_id}",
    response_model=ExtraFeeDetailResponse,
    responses=_AUTH_ERRORS,
)
def read_extra_fee(
    extra_fee_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> ExtraFeeDetailResponse:
    """Read one fee with every student charged.

    :param extra_fee_id: The fee, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The fee and its students
    """
    summary, rows = extra_fee_detail(session, lens=lens, extra_fee_id=extra_fee_id)
    return ExtraFeeDetailResponse.model_validate(
        {
            **_summary(summary).model_dump(),
            "students": [_student(row).model_dump() for row in rows],
        }
    )


@router.get(
    "/enrollments/{enrollment_id}/extra-fees",
    response_model=SeatExtraFeesResponse,
    responses=_AUTH_ERRORS,
)
def read_seat_extra_fees(
    enrollment_id: uuid.UUID,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[StudentLens | GuardianLens, Depends(family_lens)],
) -> SeatExtraFeesResponse:
    """List the exam and other fees one seat was charged.

    :param enrollment_id: The seat, from the route path
    :param request: The request carrying the lens memo
    :param session: The request-scoped session
    :param lens: The authenticated family lens
    :return: The fees, soonest due first
    """
    chosen = lens_reaching(
        session, family_lenses(request, session, lens.account_id), enrollment_id
    )
    return SeatExtraFeesResponse(
        fees=[
            SeatExtraFeeResponse(
                extra_fee_id=fee.extra_fee_id,
                purpose=fee.purpose,
                label=fee.label,
                due_on=fee.due_on,
                charged=_wire(fee.charged),
                paid=_wire(fee.paid),
                owed=_wire(fee.owed),
                status=fee.status,
            )
            for fee in seat_extra_fees(
                session, lens=chosen, enrollment_id=enrollment_id
            )
        ]
    )
