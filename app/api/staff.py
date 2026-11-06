"""The Teachers & staff console routes [0023].

**Every route resolves the teacher lens of the workspace the request
names**, and the service refuses a solo workspace, so only a manager of
that centre reaches a staff record. These are the only routes that serve
staff contact and address fields; the privacy gate fails any other route
whose response carries them.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_session, teacher_lens
from app.authz.lenses import TeacherLens
from app.money import Money as DomainMoney
from app.money.wire import parse, to_wire
from app.schemas.errors import ErrorEnvelope
from app.schemas.money import Money as WireMoney
from app.schemas.staff import (
    StaffLeaveRequest,
    StaffOtherRequest,
    StaffResponse,
    StaffTeacherRequest,
    StaffUpdateRequest,
)
from app.staff import service
from app.staff.service import StaffDraft, StaffView

__all__ = ["router"]

router = APIRouter(prefix="/v1/centre/staff", tags=["staff"])

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
        "description": "Valid request; current state forbids it. Refetch and decide.",
    },
}


def _money(value: WireMoney | None) -> DomainMoney | None:
    """Read an optional wire amount.

    :param value: The wire amount, or None
    :return: The domain amount, or None
    """
    return None if value is None else parse(value.root)


def _response(view: StaffView) -> StaffResponse:
    """Render one record for the manager.

    :param view: The record and its access
    :return: The response body
    """
    staff = view.staff
    return StaffResponse.model_validate(
        {
            "staff_id": staff.id,
            "kind": staff.kind,
            "display_name": staff.display_name,
            "role_label": staff.role_label,
            "phone": staff.phone,
            "email": staff.email,
            "staff_house": staff.staff_house,
            "staff_road": staff.staff_road,
            "staff_city": staff.staff_city,
            "staff_postcode": staff.staff_postcode,
            "pay_basis": staff.pay_basis,
            "pay_rate": None if staff.pay_rate is None else to_wire(staff.pay_rate),
            "joined_on": staff.joined_on,
            "left_on": staff.left_on,
            "status": "left" if staff.left_on is not None else "active",
            "access": view.access,
        }
    )


def _draft(body: StaffTeacherRequest | StaffOtherRequest) -> StaffDraft:
    """Turn a request into what the service records.

    :param body: The request
    :return: The draft
    """
    return StaffDraft(
        display_name=body.display_name,
        phone=body.phone,
        email=body.email,
        staff_house=body.staff_house,
        staff_road=body.staff_road,
        staff_city=body.staff_city,
        staff_postcode=body.staff_postcode,
        role_label=body.role_label if isinstance(body, StaffOtherRequest) else None,
        pay_basis=body.pay_basis,
        pay_rate=_money(body.pay_rate),
        joined_on=body.joined_on,
    )


@router.get("", response_model=list[StaffResponse], responses=_ERRORS)
def list_staff(
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> list[StaffResponse]:
    """List the centre's teachers and staff, active first.

    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: Every record
    """
    return [_response(view) for view in service.list_staff(session, lens=lens)]


@router.post(
    "/teachers",
    response_model=StaffResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
)
def invite_teacher(
    body: StaffTeacherRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> StaffResponse:
    """Record a teacher and offer them app access; nothing is granted yet.

    :param body: Their details and pay terms
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: The new record
    """
    return _response(service.invite_teacher(session, lens=lens, draft=_draft(body)))


@router.post(
    "",
    response_model=StaffResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
)
def add_other_staff(
    body: StaffOtherRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> StaffResponse:
    """Record someone who works at the centre without app access.

    :param body: Their details and pay terms
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: The new record
    """
    return _response(service.add_other(session, lens=lens, draft=_draft(body)))


@router.get("/{staff_id}", response_model=StaffResponse, responses=_ERRORS)
def read_staff(
    staff_id: uuid.UUID,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> StaffResponse:
    """Read one record.

    :param staff_id: The record
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: The record
    """
    return _response(service.read_staff(session, lens=lens, staff_id=staff_id))


@router.patch("/{staff_id}", response_model=StaffResponse, responses=_ERRORS)
def update_staff(
    staff_id: uuid.UUID,
    body: StaffUpdateRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> StaffResponse:
    """Correct a record; an omitted field is unchanged and null clears it.

    :param staff_id: The record
    :param body: The fields to change
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: The corrected record
    """
    changes: dict[str, object] = {}
    for field in body.model_fields_set:
        value = getattr(body, field)
        changes[field] = _money(value) if field == "pay_rate" else value
    if "pay_basis" in changes and changes["pay_basis"] is None:
        del changes["pay_basis"]
    return _response(
        service.update_staff(session, lens=lens, staff_id=staff_id, changes=changes)
    )


@router.post("/{staff_id}/leave", response_model=StaffResponse, responses=_ERRORS)
def mark_left(
    staff_id: uuid.UUID,
    body: StaffLeaveRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> StaffResponse:
    """Record that someone left; their app access ends in the same step.

    :param staff_id: The record
    :param body: Their last day
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: The record, marked left
    """
    return _response(
        service.leave(session, lens=lens, staff_id=staff_id, left_on=body.left_on)
    )
