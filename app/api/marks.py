"""Exam, mark and marksheet routes.

**Every route resolves a lens**, and the handler scopes its query by
the value the lens carries rather than by an id from the request body
[BR5.1]. **No entry is added to ``PUBLIC_ROUTES``.**

**The marksheet toggle is written through exactly ONE route** [BR5.4],
under a teacher lens scoped to the batch's owner. When it is off, the
family reads refuse outright -- not an empty marksheet, which would
still disclose that exams exist and how many.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as DbSession

from app.api.deps import get_session, guardian_lens, student_lens, teacher_lens
from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.marks import views
from app.marks.entry import correction_history, record_mark
from app.marks.exams import create_exam, list_exams, update_exam
from app.marks.marksheet import Marksheet, Published
from app.marks.results import exam_results
from app.schemas.errors import ErrorEnvelope
from app.schemas.marks import (
    BandResponse,
    CorrectionEntryResponse,
    ExamCreateRequest,
    ExamResponse,
    MarksheetResponse,
    MarkWriteRequest,
    ProgressEntryResponse,
    PublishedMarksheetResponse,
    ResultState,
    SeatResultResponse,
    SuppressedMarksheetResponse,
    SuppressionReason,
)
from app.schemas.teaching import MarksheetToggleRequest

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["marks"])

_AUTH_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    401: {
        "model": ErrorEnvelope,
        "description": "No credential, or an expired one.",
    },
    403: {
        "model": ErrorEnvelope,
        "description": (
            "No lens reaches this. Deliberately indistinguishable from "
            "absence, and the refusal when the marksheet toggle is off "
            "is the same one: an empty marksheet would still disclose "
            "that exams exist and how many."
        ),
    },
}

#: The two reasons a marksheet publishes no comparison [BR6.4], as the
#: closed set the narrowing check below tests against.
SUPPRESSION_REASONS: Final[tuple[SuppressionReason, ...]] = (
    "too_few_results",
    "marking_incomplete",
)

#: The four result states, typed with the Literal as the ELEMENT type
#: so a membership test NARROWS rather than merely checks.
_RESULT_STATES: Final[tuple[ResultState, ...]] = (
    "marked",
    "absent",
    "not_entered",
    "joined_after",
)

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


def _result_state(stored: str) -> ResultState:
    """Narrow a stored result state onto the closed set, checking it.

    A real check rather than a cast: a value outside the set means the
    database enum was widened without the contract following, which a
    client switching on the enum would meet as an unrenderable state.

    :param stored: The value read from the column or derived
    :return: The same value, narrowed
    :raises ValueError: The stored value is outside the closed set
    """
    if stored not in _RESULT_STATES:
        raise ValueError(
            f"{stored!r} is not a result state. The database enum and "
            "app.schemas.marks.ResultState have diverged."
        )
    return stored


def _marksheet_response(sheet: Marksheet) -> MarksheetResponse:
    """Render a marksheet for the wire.

    The two outcomes are **distinct shapes** rather than one with
    nulls: a rank of null beside an average of zero would read as a
    real result [BR6.4].

    :param sheet: The computed marksheet
    :return: The response body
    """
    if isinstance(sheet, Published):
        return PublishedMarksheetResponse(
            viewer_marks=sheet.viewer_marks,
            viewer_rank=sheet.viewer_rank,
            average=sheet.average,
            highest=sheet.highest,
            marked_count=sheet.marked_count,
            bands=[
                BandResponse(low=band.low, high=band.high, count=band.count)
                for band in sheet.bands
            ],
        )
    if sheet.reason not in SUPPRESSION_REASONS:
        raise ValueError(
            f"{sheet.reason!r} is not a suppression reason. "
            "app.marks.marksheet and app.schemas.marks have diverged."
        )
    return SuppressedMarksheetResponse(
        viewer_marks=sheet.viewer_marks,
        reason=sheet.reason,
    )


@router.get(
    "/batches/{batch_id}/exams",
    response_model=list[ExamResponse],
    responses=_AUTH_ERRORS,
)
def read_batch_exams(
    batch_id: uuid.UUID,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> list[ExamResponse]:
    """List one batch's exams, oldest first.

    :param batch_id: The batch, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: One row per exam
    """
    return [
        ExamResponse(
            exam_id=row.exam_id,
            title=row.title,
            date=row.date,
            total_marks=row.total_marks,
            subject_name=row.subject_name,
        )
        for row in list_exams(session, lens=lens, batch_id=batch_id)
    ]


@router.post(
    "/batches/{batch_id}/exams",
    response_model=ExamResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_ERRORS,
)
def create_batch_exam(
    batch_id: uuid.UUID,
    body: ExamCreateRequest,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> ExamResponse:
    """Create one exam [BR4.1].

    The subject must be one of **this batch's own**; a subject id from
    another teacher's batch would attach an exam across the ownership
    boundary, and the refusal is the shared ``NOT_AVAILABLE`` because
    naming it as wrong is the oracle.

    :param batch_id: The batch, from the route path
    :param body: The subject, title, date and total
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The new exam
    """
    row = create_exam(
        session,
        lens=lens,
        batch_id=batch_id,
        batch_subject_id=body.batch_subject_id,
        title=body.title,
        date=body.date,
        total_marks=body.total_marks,
    )
    return ExamResponse(
        exam_id=row.exam_id,
        title=row.title,
        date=row.date,
        total_marks=row.total_marks,
        subject_name=row.subject_name,
    )


@router.put(
    "/exams/{exam_id}",
    response_model=ExamResponse,
    responses=_WRITE_ERRORS,
)
def update_batch_exam(
    exam_id: uuid.UUID,
    body: ExamCreateRequest,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> ExamResponse:
    """Edit an exam's title, date or total.

    :param exam_id: The exam, from the route path
    :param body: Its new values
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The updated exam
    """
    row = update_exam(
        session,
        lens=lens,
        exam_id=exam_id,
        title=body.title,
        date=body.date,
        total_marks=body.total_marks,
    )
    return ExamResponse(
        exam_id=row.exam_id,
        title=row.title,
        date=row.date,
        total_marks=row.total_marks,
        subject_name=row.subject_name,
    )


@router.get(
    "/exams/{exam_id}/results",
    response_model=list[SeatResultResponse],
    responses=_AUTH_ERRORS,
)
def read_exam_results(
    exam_id: uuid.UUID,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> list[SeatResultResponse]:
    """Read every seat's result for one exam [BR4.3].

    ``not_entered`` and ``joined_after`` are **derived** and never
    typed by the teacher.

    :param exam_id: The exam, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: One row per seat
    """
    return [
        SeatResultResponse(
            enrollment_id=row.enrollment_id,
            display_name=row.display_name,
            result_state=_result_state(row.result_state),
            marks=row.marks,
        )
        for row in exam_results(session, lens=lens, exam_id=exam_id)
    ]


@router.post(
    "/exams/{exam_id}/marks",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_WRITE_ERRORS,
)
def write_exam_mark(
    exam_id: uuid.UUID,
    body: MarkWriteRequest,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> None:
    """Enter or correct one seat's result [BR4.2, BR4.4].

    A correction **appends and supersedes**; no mark is ever updated
    in place or deleted, because FR9.2 requires a change to be
    visible and on a shared marksheet a silently changed mark is the
    one a student will dispute.

    :param exam_id: The exam, from the route path
    :param body: The seat, the state and the number
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: None
    """
    record_mark(
        session,
        lens=lens,
        exam_id=exam_id,
        enrollment_id=body.enrollment_id,
        result_state=body.result_state,
        marks=body.marks,
    )


@router.get(
    "/exams/{exam_id}/marks/{enrollment_id}/history",
    response_model=list[CorrectionEntryResponse],
    responses=_AUTH_ERRORS,
)
def read_mark_history(
    exam_id: uuid.UUID,
    enrollment_id: uuid.UUID,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> list[CorrectionEntryResponse]:
    """Read one seat's correction history [FR9.2].

    :param exam_id: The exam, from the route path
    :param enrollment_id: The seat, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: Every row ever recorded, oldest first
    """
    return [
        CorrectionEntryResponse(
            mark_id=entry.mark_id,
            result_state=_result_state(entry.result_state),
            marks=entry.marks,
            recorded_at=entry.recorded_at,
            superseded=entry.superseded,
        )
        for entry in correction_history(
            session, lens=lens, exam_id=exam_id, enrollment_id=enrollment_id
        )
    ]


@router.put(
    "/batches/{batch_id}/marksheet-visibility",
    response_model=MarksheetToggleRequest,
    responses=_WRITE_ERRORS,
)
def set_batch_marksheet_visibility(
    batch_id: uuid.UUID,
    body: MarksheetToggleRequest,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> MarksheetToggleRequest:
    """Write the marksheet toggle [BR5.4].

    **The one route that writes it.** The column is already built and
    non-null, so D4 ships no migration and no default for it.

    :param batch_id: The batch, from the route path
    :param body: Whether families may see a marksheet
    :param session: The request-scoped session
    :param lens: The teacher lens; only the owner may write it
    :return: The value now in force
    """
    return MarksheetToggleRequest(
        visible=views.set_marksheet_visible(
            session, lens=lens, batch_id=batch_id, visible=body.visible
        )
    )


@router.get(
    "/me/enrollments/{enrollment_id}/exams/{exam_id}/marksheet",
    response_model=MarksheetResponse,
    responses=_AUTH_ERRORS,
)
def read_my_marksheet(
    enrollment_id: uuid.UUID,
    exam_id: uuid.UUID,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[StudentLens, Depends(student_lens)],
) -> MarksheetResponse:
    """Read this student's own marksheet for one exam [BR6.2].

    :param enrollment_id: Their seat, from the route path
    :param exam_id: The exam, from the route path
    :param session: The request-scoped session
    :param lens: The student lens
    :return: The published comparison, or a suppressed marksheet
    """
    return _marksheet_response(
        views.seat_marksheet(
            session, lens=lens, enrollment_id=enrollment_id, exam_id=exam_id
        )
    )


@router.get(
    "/children/{enrollment_id}/exams/{exam_id}/marksheet",
    response_model=MarksheetResponse,
    responses=_AUTH_ERRORS,
)
def read_child_marksheet(
    enrollment_id: uuid.UUID,
    exam_id: uuid.UUID,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[GuardianLens, Depends(guardian_lens)],
) -> MarksheetResponse:
    """Read one child's marksheet, for their recorded guardian.

    :param enrollment_id: The child's seat, from the route path
    :param exam_id: The exam, from the route path
    :param session: The request-scoped session
    :param lens: The guardian lens
    :return: The published comparison, or a suppressed marksheet
    """
    return _marksheet_response(
        views.seat_marksheet(
            session, lens=lens, enrollment_id=enrollment_id, exam_id=exam_id
        )
    )


@router.get(
    "/children/{enrollment_id}/progress",
    response_model=list[ProgressEntryResponse],
    responses=_AUTH_ERRORS,
)
def read_child_progress(
    enrollment_id: uuid.UUID,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[GuardianLens, Depends(guardian_lens)],
) -> list[ProgressEntryResponse]:
    """Read one child's results across exams, in date order [BR6.6].

    **Ordered by the server**, not the client, and an absence carries
    no numeric value: plotted as zero it would show a collapse in
    performance that did not happen.

    :param enrollment_id: The child's seat, from the route path
    :param session: The request-scoped session
    :param lens: The guardian lens
    :return: One entry per exam, oldest first
    """
    return [
        ProgressEntryResponse(
            exam_id=entry.exam_id,
            title=entry.title,
            date=entry.date,
            total_marks=entry.total_marks,
            result_state=_result_state(entry.result_state),
            marks=entry.marks,
        )
        for entry in views.guardian_progress(
            session, lens=lens, enrollment_id=enrollment_id
        )
    ]
