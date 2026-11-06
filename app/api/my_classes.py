"""A centre teacher's classroom routes [C4, D2].

**The only routes a :class:`ClassTeacherLens` reaches**, held to an
explicit allowlist by the route gate: the listing of their own classes,
and the roster, attendance and topic of one assigned class. A centre
teacher sees no fees, dues, payment methods, notices, batch settings or
any class not assigned to them; none of those routes accepts this lens.

The writes reuse the teacher's own write paths, scoped to the one class
the lens carries: the same version checks, the same replay keys, and the
same refusals, plus ``CLASS_REASSIGNED`` when the class has moved.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DbSession

from app.api.deps import authenticated_account, class_teacher_lens, get_session
from app.authz.lenses import ClassTeacherLens
from app.schemas.errors import ErrorEnvelope
from app.schemas.my_classes import (
    ClassRosterResponse,
    ClassRosterSeatResponse,
    MyClassResponse,
)
from app.schemas.teaching import (
    AttendanceSubmitRequest,
    AttendanceSubmitResponse,
    TopicWriteRequest,
    TopicWriteResponse,
)
from app.teaching.my_classes import my_classes
from app.teaching.roster import readable_session, session_roster, write_refusal
from app.teaching.submissions import SeatMark, submit_roster, write_topic

__all__ = ["router"]

router = APIRouter(prefix="/v1/me/classes", tags=["my-classes"])

_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    401: {"model": ErrorEnvelope, "description": "No credential, or an expired one."},
    403: {
        "model": ErrorEnvelope,
        "description": "No class lens reaches this; absence reads the same.",
    },
    409: {
        "model": ErrorEnvelope,
        "description": "CLASS_REASSIGNED when the class has moved to another "
        "teacher, or a stale version. Refetch and decide.",
    },
}


@router.get("", response_model=list[MyClassResponse], responses=_ERRORS)
def list_my_classes(
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[DbSession, Depends(get_session)],
    first: Annotated[dt.date, Query(alias="from")],
    last: Annotated[dt.date, Query(alias="to")],
) -> list[MyClassResponse]:
    """List the classes assigned to me, across every centre, at most 31 days.

    :param account_id: The authenticated account
    :param session: The request-scoped session
    :param first: The first date, inclusive
    :param last: The last date, inclusive
    :return: My classes, soonest first
    """
    return [
        MyClassResponse(
            session_id=row.session_id,
            centre_name=row.centre_name,
            batch_name=row.batch_name,
            subject=row.subject,
            date=row.date,
            start_time=row.start_time.strftime("%H:%M"),
            end_time=None if row.end_time is None else row.end_time.strftime("%H:%M"),
            status=row.status,  # type: ignore[arg-type]
            room_name=row.room_name,
            topic_logged=row.topic_logged,
        )
        for row in my_classes(session, account_id=account_id, first=first, last=last)
    ]


@router.get(
    "/{session_id}/attendance", response_model=ClassRosterResponse, responses=_ERRORS
)
def read_class_roster(
    lens: Annotated[ClassTeacherLens, Depends(class_teacher_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> ClassRosterResponse:
    """Read the roster of one class assigned to me: names and marks only.

    :param lens: The lens for this one class
    :param session: The request-scoped session
    :return: The seats, their version, and whether a write is accepted
    """
    seats = session_roster(session, lens=lens, session_id=lens.session_id)
    row = readable_session(session, lens=lens, session_id=lens.session_id)
    return ClassRosterResponse(
        seats=[
            ClassRosterSeatResponse(
                enrollment_id=seat.enrollment_id,
                display_name=seat.display_name,
                present=seat.present,
            )
            for seat in seats
        ],
        attendance_version=row.attendance_version,
        writable=write_refusal(session, row) is None,
        topic=row.topic,
        topic_version=row.topic_version,
    )


@router.post(
    "/{session_id}/attendance",
    response_model=AttendanceSubmitResponse,
    responses=_ERRORS,
)
def submit_class_roster(
    body: AttendanceSubmitRequest,
    lens: Annotated[ClassTeacherLens, Depends(class_teacher_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> AttendanceSubmitResponse:
    """Take attendance for one class assigned to me, the whole roster at once.

    :param body: The version, the replay key and every seat's mark
    :param lens: The lens for this one class
    :param session: The request-scoped session
    :return: The version now in force
    """
    result = submit_roster(
        session,
        lens=lens,
        session_id=lens.session_id,
        base_version=body.base_attendance_version,
        client_mutation_id=body.client_mutation_id,
        seats=[
            SeatMark(enrollment_id=mark.enrollment_id, present=mark.present)
            for mark in body.seats
        ],
        composed_at=body.composed_at,
    )
    return AttendanceSubmitResponse(
        attendance_version=result.attendance_version,
        submission_id=result.submission_id,
    )


@router.put("/{session_id}/topic", response_model=TopicWriteResponse, responses=_ERRORS)
def write_class_topic(
    body: TopicWriteRequest,
    lens: Annotated[ClassTeacherLens, Depends(class_teacher_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> TopicWriteResponse:
    """Log the topic of one class assigned to me.

    :param body: The version, the replay key and the topic
    :param lens: The lens for this one class
    :param session: The request-scoped session
    :return: The topic version now in force
    """
    return TopicWriteResponse(
        topic_version=write_topic(
            session,
            lens=lens,
            session_id=lens.session_id,
            base_version=body.base_topic_version,
            client_mutation_id=body.client_mutation_id,
            topic=body.topic,
            plan=body.plan,
            notes=body.notes,
            notes_supplied="notes" in body.model_fields_set,
        ).topic_version
    )
