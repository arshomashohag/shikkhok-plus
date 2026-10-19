"""Batch, enrollment and guardian routes.

**Every route here resolves a lens**, and the route-enumeration gate U2
built fails CI on one that does not. The lens is a dependency returning
the value the handler needs rather than a guard returning nothing, so a
handler cannot compile a scoped query without it [TC-11].

**Responses carry decisions, not inputs to decisions** [TC-9, D-31]. A
roster row carries ``status`` as a server-computed enum, because
``if balance > 0 then "Due"`` is a business rule about what counts as
due, written in a composable where it looks like presentation.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_session, guardian_lens, teacher_lens
from app.authz.lenses import GuardianLens, TeacherLens
from app.batches import service
from app.money import Money as DomainMoney
from app.money.wire import parse, to_wire
from app.schemas.batches import (
    BatchCreateRequest,
    BatchResponse,
    EnrollmentCreateRequest,
    GuardianChildResponse,
    InactiveFromRequest,
    RosterRowResponse,
)
from app.schemas.money import Money as WireMoney

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["batches"])


def _to_wire(amount: DomainMoney | None) -> WireMoney | None:
    """Render a stored amount as the wire component.

    **Two distinct types, deliberately.** ``app.money.Money`` is the
    arithmetic type and ``app.schemas.money.Money`` is the serialized
    one -- a JSON string carrying the canonical pattern [TC-7, D-20].
    Keeping them separate is what stops a domain value reaching a
    response body without passing the chokepoint, and mypy enforces the
    crossing because the two are not interchangeable.

    :param amount: The stored amount, or None
    :return: The wire representation, or None
    """
    if amount is None:
        return None
    return WireMoney(to_wire(amount))


def _from_wire(amount: WireMoney | None) -> DomainMoney | None:
    """Read an incoming amount into the arithmetic type.

    :param amount: The wire value, or None
    :return: The domain amount, or None
    """
    if amount is None:
        return None
    return parse(amount.root)


def _roster_status(row: service.RosterRow) -> str:
    """Decide the seat's status, server-side.

    The client switches on this enum and never compares a date of its
    own [TC-9]. Returning ``inactive_from`` alone and letting the client
    decide is the erosion path this function exists to close.

    :param row: The roster row
    :return: ``dormant``, ``inactive`` or ``active``
    """
    if row.is_dormant:
        return "dormant"
    if row.inactive_from is not None:
        return "inactive"
    return "active"


@router.post(
    "/batches",
    response_model=BatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_batch(
    body: BatchCreateRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> BatchResponse:
    """Create a batch [AC2.1.1].

    :param body: The batch to create
    :param lens: The teacher lens carrying the owner id
    :param session: The request-scoped session
    :return: The created batch
    """
    batch = service.create_batch(
        session,
        lens=lens,
        name=body.name,
        subjects=body.subjects,
        teacher_display_name=body.teacher_display_name,
        default_fee=_from_wire(body.default_fee),
        fee_due_day=body.fee_due_day,
        collection_number=body.collection_number,
        collection_channel=body.collection_channel,
    )
    return BatchResponse(
        id=batch.id,
        name=batch.name,
        subjects=sorted(body.subjects),
        teacher_display_name=batch.teacher_display_name,
        default_fee=_to_wire(batch.default_fee),
        fee_due_day=batch.fee_due_day,
        collection_number=batch.collection_number,
        collection_channel=batch.collection_channel,
        marksheet_visible=batch.marksheet_visible,
        active=batch.active,
        enrollment_count=0,
    )


@router.get("/batches", response_model=list[BatchResponse])
def list_batches(
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> list[BatchResponse]:
    """List this teacher's own batches.

    **Cites no acceptance criterion deliberately.** AC2.6.1 is the
    STUDENT's batch list -- "given I am signed in as a student" -- and
    that route is not built [traceability: AC2.6.1, Deferred]. Citing it
    here would make a Deferred row look covered, which is the failure
    the traceability manifest exists to prevent.

    :param lens: The teacher lens carrying the owner id
    :param session: The request-scoped session
    :return: One entry per batch, newest first
    """
    return [
        BatchResponse(
            id=summary.batch.id,
            name=summary.batch.name,
            subjects=summary.subjects,
            teacher_display_name=summary.batch.teacher_display_name,
            default_fee=_to_wire(summary.batch.default_fee),
            fee_due_day=summary.batch.fee_due_day,
            collection_number=summary.batch.collection_number,
            collection_channel=summary.batch.collection_channel,
            marksheet_visible=summary.batch.marksheet_visible,
            active=summary.batch.active,
            enrollment_count=summary.enrollment_count,
        )
        for summary in service.list_batches(session, lens=lens)
    ]


@router.get("/batches/{batch_id}/roster", response_model=list[RosterRowResponse])
def read_roster(
    batch_id: uuid.UUID,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> list[RosterRowResponse]:
    """List the seats in one of this teacher's batches.

    The roster is what AC2.2.x and AC2.4.x are observed through; it
    carries no numbered criterion of its own, and AC2.6.1 belongs to
    the unbuilt student-facing list.

    :param batch_id: The batch whose roster to read
    :param lens: The teacher lens carrying the owner id
    :param session: The request-scoped session
    :return: One row per seat
    """
    rows = service.list_roster(session, lens=lens, batch_id=batch_id)
    return [
        RosterRowResponse(
            enrollment_id=row.enrollment_id,
            display_name=row.display_name,
            guardian_phone=row.guardian_phone,
            fee_amount=_to_wire(row.fee_amount),
            status=_roster_status(row),
            inactive_from=row.inactive_from,
        )
        for row in rows
    ]


@router.post(
    "/batches/{batch_id}/enrollments",
    response_model=RosterRowResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_enrollment(
    batch_id: uuid.UUID,
    body: EnrollmentCreateRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> RosterRowResponse:
    """Add a student to a batch [AC2.2.2].

    :param batch_id: The batch to add to
    :param body: The seat to create
    :param lens: The teacher lens carrying the owner id
    :param session: The request-scoped session
    :return: The created seat
    """
    record = service.add_enrollment(
        session,
        lens=lens,
        batch_id=batch_id,
        display_name=body.display_name,
        guardian_phone=body.guardian_phone,
        fee_amount=_from_wire(body.fee_amount),
        joined_on=body.joined_on,
    )
    return RosterRowResponse(
        enrollment_id=record.id,
        display_name=record.display_name,
        guardian_phone=record.guardian_phone,
        fee_amount=_to_wire(record.fee_amount),
        status="dormant",
        inactive_from=None,
    )


@router.patch(
    "/enrollments/{enrollment_id}/inactive-from",
    status_code=status.HTTP_204_NO_CONTENT,
)
def set_inactive_from(
    enrollment_id: uuid.UUID,
    body: InactiveFromRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """Mark a seat inactive from a date, or clear it [AC2.4.1].

    :param enrollment_id: The seat to mark
    :param body: The date, or null to reactivate
    :param lens: The teacher lens, which scopes the write
    :param session: The request-scoped session
    :return: None
    """
    service.set_inactive_from(
        session,
        lens=lens,
        enrollment_id=enrollment_id,
        inactive_from=body.inactive_from,
    )


@router.delete("/enrollments/{enrollment_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_enrollment(
    enrollment_id: uuid.UUID,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """Remove a dormant, never-erased seat [AC2.5.1].

    :param enrollment_id: The seat to remove
    :param lens: The teacher lens, which scopes the write
    :param session: The request-scoped session
    :return: None
    """
    service.remove_enrollment(session, lens=lens, enrollment_id=enrollment_id)


@router.get("/guardian/children", response_model=list[GuardianChildResponse])
def list_children(
    lens: Annotated[GuardianLens, Depends(guardian_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> list[GuardianChildResponse]:
    """List the seats this guardian was recorded on [AC2.7.1].

    Resolved through ``guardian_account_id`` and never through the
    child, so two teachers' records never merge [BR5.3].

    :param lens: The guardian lens carrying the authenticated account
    :param session: The request-scoped session
    :return: One entry per reachable seat
    """
    return [
        GuardianChildResponse(
            enrollment_id=row.enrollment_id,
            display_name=row.display_name,
            batch_name=row.batch_name,
            teacher_display_name=None,
        )
        for row in service.list_guardian_children(session, lens=lens)
    ]
