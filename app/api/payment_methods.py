"""Payment-method routes: the teacher's own, and the family's read [P1-P3].

**Every route resolves a lens.** The teacher routes are scoped to the
lens's owner; the family routes reach only a seat that lens accepted.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_session, guardian_lens, student_lens, teacher_lens
from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.db.models import PaymentMethod
from app.fees import methods
from app.schemas.errors import ErrorEnvelope
from app.schemas.payment_methods import (
    FamilyPaymentMethodsResponse,
    PaymentMethodRequest,
    PaymentMethodResponse,
)

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["payment-methods"])

_AUTH_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    401: {"model": ErrorEnvelope, "description": "No credential, or an expired one."},
    403: {"model": ErrorEnvelope, "description": "No lens reaches this."},
}

_WRITE_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    **_AUTH_ERRORS,
    400: {"model": ErrorEnvelope, "description": "The request is wrong."},
}


def _method_response(method: PaymentMethod) -> PaymentMethodResponse:
    """Render a stored method.

    :param method: The row
    :return: The wire shape
    """
    return PaymentMethodResponse(
        method_id=method.id,
        kind=method.kind,  # type: ignore[arg-type]
        provider=method.provider,
        mobile_number=method.mobile_number,
        account_number=method.account_number,
        account_name=method.account_name,
        branch_name=method.branch_name,
        note=method.note,
    )


def _draft(body: PaymentMethodRequest) -> methods.MethodDraft:
    """Turn a request body into a draft.

    :param body: The request
    :return: The draft
    """
    return methods.MethodDraft(**body.model_dump())


def _family_response(family: methods.FamilyMethods) -> FamilyPaymentMethodsResponse:
    """Render a family's view.

    :param family: The service result
    :return: The wire shape
    """
    return FamilyPaymentMethodsResponse(
        methods=[_method_response(method) for method in family.methods],
        services=list(family.services),
        teacher_display_name=family.teacher_display_name,
    )


@router.get(
    "/payment-methods",
    response_model=list[PaymentMethodResponse],
    responses=_AUTH_ERRORS,
)
def list_payment_methods(
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> list[PaymentMethodResponse]:
    """List the teacher's live payment methods.

    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The methods in display order
    """
    return [_method_response(m) for m in methods.list_methods(session, lens=lens)]


@router.post(
    "/payment-methods",
    response_model=PaymentMethodResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_ERRORS,
)
def create_payment_method(
    body: PaymentMethodRequest,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> PaymentMethodResponse:
    """Add a payment method.

    :param body: The method details
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The new method
    """
    return _method_response(
        methods.create_method(session, lens=lens, draft=_draft(body))
    )


@router.patch(
    "/payment-methods/{method_id}",
    response_model=PaymentMethodResponse,
    responses=_WRITE_ERRORS,
)
def update_payment_method(
    method_id: uuid.UUID,
    body: PaymentMethodRequest,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> PaymentMethodResponse:
    """Replace a payment method's details.

    :param method_id: The method, from the route path
    :param body: The new details
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The updated method
    """
    return _method_response(
        methods.update_method(
            session, lens=lens, method_id=method_id, draft=_draft(body)
        )
    )


@router.delete(
    "/payment-methods/{method_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_AUTH_ERRORS,
)
def retire_payment_method(
    method_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> Response:
    """Retire a payment method; the row is kept.

    :param method_id: The method, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: An empty response
    """
    methods.retire_method(session, lens=lens, method_id=method_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me/enrollments/{enrollment_id}/payment-methods",
    response_model=FamilyPaymentMethodsResponse,
    responses=_AUTH_ERRORS,
)
def read_seat_payment_methods(
    enrollment_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[StudentLens, Depends(student_lens)],
) -> FamilyPaymentMethodsResponse:
    """List where a student can pay for an accepted seat.

    :param enrollment_id: The seat, from the route path
    :param session: The request-scoped session
    :param lens: The student lens
    :return: The methods and suggestions
    """
    return _family_response(
        methods.methods_for_seat(session, lens=lens, enrollment_id=enrollment_id)
    )


@router.get(
    "/children/{enrollment_id}/payment-methods",
    response_model=FamilyPaymentMethodsResponse,
    responses=_AUTH_ERRORS,
)
def read_child_payment_methods(
    enrollment_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[GuardianLens, Depends(guardian_lens)],
) -> FamilyPaymentMethodsResponse:
    """List where a guardian can pay for an accepted seat.

    :param enrollment_id: The seat, from the route path
    :param session: The request-scoped session
    :param lens: The guardian lens
    :return: The methods and suggestions
    """
    return _family_response(
        methods.methods_for_seat(session, lens=lens, enrollment_id=enrollment_id)
    )
