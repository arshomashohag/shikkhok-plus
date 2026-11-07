"""A teacher's students: listed once, seated in any number of batches.

Every route resolves a teacher lens and scopes on its ``owner_id``, so
no route can reach another teacher's student [BR1.1].
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_session, teacher_lens
from app.authz.lenses import TeacherLens
from app.money import Money as DomainMoney
from app.money.wire import parse, to_wire
from app.schemas.money import Money as WireMoney
from app.schemas.students import (
    AddStudentsRequest,
    AddStudentsResponse,
    StudentCreateRequest,
    StudentEnrollRequest,
    StudentResponse,
    StudentSeatResponse,
    StudentUpdateRequest,
)
from app.students import service

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["students"])


def _to_wire(amount: DomainMoney) -> WireMoney:
    """Render an amount as the wire component.

    :param amount: The amount
    :return: Its wire representation
    """
    return WireMoney(to_wire(amount))


def _from_wire(amount: WireMoney | None) -> DomainMoney | None:
    """Read an incoming amount into the arithmetic type.

    :param amount: The wire value, or None
    :return: The domain amount, or None
    """
    return None if amount is None else parse(amount.root)


def _response(row: service.StudentRow) -> StudentResponse:
    """Render one student, the same way for every route.

    :param row: The student the service described
    :return: The response body
    """
    return StudentResponse(
        student_id=row.student_id,
        display_name=row.display_name,
        student_phone=row.student_phone,
        guardian_phone=row.guardian_phone,
        student_state=row.student_state,
        guardian_state=row.guardian_state,
        enrollments=[
            StudentSeatResponse(
                enrollment_id=seat.enrollment_id,
                batch_id=seat.batch_id,
                batch_name=seat.batch_name,
                fee_amount=None
                if seat.fee_amount is None
                else _to_wire(seat.fee_amount),
                status="active" if seat.inactive_from is None else "inactive",
                inactive_from=seat.inactive_from,
                outstanding=_to_wire(seat.outstanding),
                is_removable=seat.is_removable,
            )
            for seat in row.seats
        ],
        total_outstanding=_to_wire(row.total_outstanding),
        is_removable=row.is_removable,
    )


@router.get("/students", response_model=list[StudentResponse])
def list_students(
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
    batch_id: Annotated[uuid.UUID | None, Query()] = None,
    unassigned: Annotated[bool, Query()] = False,
    exclude_batch_id: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=60)] = None,
) -> list[StudentResponse]:
    """List this teacher's students, filtered server-side.

    :param lens: The teacher lens carrying the owner id
    :param session: The request-scoped session
    :param batch_id: Only students in this batch
    :param unassigned: Only students in no batch
    :param exclude_batch_id: Only students NOT in this batch
    :param q: Only students whose name or number contains this
    :return: One row per student, by name
    """
    rows = service.list_students(
        session,
        lens=lens,
        where=service.StudentFilter(
            batch_id=batch_id,
            unassigned=unassigned,
            exclude_batch_id=exclude_batch_id,
            query=q or None,
        ),
    )
    return [_response(row) for row in rows]


@router.post(
    "/students", response_model=StudentResponse, status_code=status.HTTP_201_CREATED
)
def create_student(
    body: StudentCreateRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> StudentResponse:
    """Record a student, optionally seating them in batches [D3].

    :param body: The student and their batches
    :param lens: The teacher lens carrying the owner id
    :param session: The request-scoped session
    :return: The new student
    """
    row = service.create_student(
        session,
        lens=lens,
        display_name=body.display_name,
        student_phone=body.student_phone,
        guardian_phone=body.guardian_phone,
        seats=[
            service.SeatRequest(
                batch_id=seat.batch_id, fee_amount=_from_wire(seat.fee_amount)
            )
            for seat in body.enrollments
        ],
        client_mutation_id=body.client_mutation_id,
    )
    return _response(row)


@router.get("/students/{student_id}", response_model=StudentResponse)
def read_student(
    student_id: uuid.UUID,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> StudentResponse:
    """Read one student with every seat.

    :param student_id: The student
    :param lens: The teacher lens carrying the owner id
    :param session: The request-scoped session
    :return: The student
    """
    return _response(service.get_student(session, lens=lens, student_id=student_id))


@router.patch("/students/{student_id}", response_model=StudentResponse)
def update_student(
    student_id: uuid.UUID,
    body: StudentUpdateRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> StudentResponse:
    """Edit a student's name or numbers, on every seat at once.

    :param student_id: The student
    :param body: What to change; omitted fields are unchanged
    :param lens: The teacher lens carrying the owner id
    :param session: The request-scoped session
    :return: The student, as edited
    """
    sent = body.model_fields_set
    row = service.update_student(
        session,
        lens=lens,
        student_id=student_id,
        changes=service.StudentChanges(
            display_name=body.display_name,
            student_phone=body.student_phone,
            student_phone_set="student_phone" in sent,
            guardian_phone=body.guardian_phone,
            guardian_phone_set="guardian_phone" in sent,
        ),
    )
    return _response(row)


@router.delete("/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_student(
    student_id: uuid.UUID,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """Remove a student in no active batch who owes nothing [D4].

    :param student_id: The student
    :param lens: The teacher lens carrying the owner id
    :param session: The request-scoped session
    :return: None
    """
    service.remove_student(session, lens=lens, student_id=student_id)


@router.post(
    "/students/{student_id}/enrollments",
    response_model=StudentResponse,
    status_code=status.HTTP_201_CREATED,
)
def enroll_student(
    student_id: uuid.UUID,
    body: StudentEnrollRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> StudentResponse:
    """Put an existing student in one more batch.

    :param student_id: The student
    :param body: The batch and an optional fee
    :param lens: The teacher lens carrying the owner id
    :param session: The request-scoped session
    :return: The student, with the new seat
    """
    row = service.enroll_student(
        session,
        lens=lens,
        student_id=student_id,
        batch_id=body.batch_id,
        fee_amount=_from_wire(body.fee_amount),
    )
    return _response(row)


@router.post(
    "/batches/{batch_id}/students",
    response_model=AddStudentsResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_students_to_batch(
    batch_id: uuid.UUID,
    body: AddStudentsRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> AddStudentsResponse:
    """Seat existing students in one batch, all or nothing.

    :param batch_id: The batch
    :param body: The students
    :param lens: The teacher lens carrying the owner id
    :param session: The request-scoped session
    :return: How many were added
    """
    added = service.add_students_to_batch(
        session, lens=lens, batch_id=batch_id, student_ids=body.student_ids
    )
    return AddStudentsResponse(added=added)
