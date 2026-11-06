"""An examiner's routes: the exams they mark, results, marks, publish [C4].

**The only routes an :class:`ExaminerLens` reaches**, held with the
class-teacher routes to the explicit allowlist the route gate asserts.
"A manager creates the exam and names the examiner; the examiner enters
and publishes its marks" (decided 2026-11-06). The writes reuse the
teacher's own mark and publish paths, scoped to the one exam.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as DbSession

from app.api.deps import authenticated_account, examiner_lens, get_session
from app.authz.lenses import ExaminerLens
from app.marks import views
from app.marks.entry import exam_is_writable, record_mark
from app.marks.my_exams import MyExam, my_exams
from app.marks.results import exam_results
from app.schemas.errors import ErrorEnvelope
from app.schemas.marks import MarkWriteRequest
from app.schemas.my_classes import (
    ExamineeResponse,
    ExaminerResultsResponse,
    MyExamResponse,
)

__all__ = ["router"]

router = APIRouter(prefix="/v1/me/exams", tags=["my-exams"])

_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    401: {"model": ErrorEnvelope, "description": "No credential, or an expired one."},
    403: {
        "model": ErrorEnvelope,
        "description": "No examiner lens reaches this; absence reads the same.",
    },
    400: {
        "model": ErrorEnvelope,
        "description": "The request is wrong. Fix and resubmit; never retry as-is.",
    },
    409: {
        "model": ErrorEnvelope,
        "description": "EXAM_REASSIGNED when another member marks it now, or the "
        "exam's state forbids the write. Refetch and decide.",
    },
}


def _exam(row: MyExam) -> MyExamResponse:
    """Render one exam the caller marks.

    :param row: The exam
    :return: The response body
    """
    return MyExamResponse(
        exam_id=row.exam_id,
        centre_name=row.centre_name,
        batch_name=row.batch_name,
        subject_name=row.subject_name,
        title=row.title,
        date=row.date,
        total_marks=row.total_marks,
        published=row.published,
        cancelled=row.cancelled,
    )


@router.get("", response_model=list[MyExamResponse], responses=_ERRORS)
def list_my_exams(
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[DbSession, Depends(get_session)],
) -> list[MyExamResponse]:
    """List the exams I am the examiner of, across every centre.

    :param account_id: The authenticated account
    :param session: The request-scoped session
    :return: The exams, newest first
    """
    return [_exam(row) for row in my_exams(session, account_id=account_id)]


@router.get(
    "/{exam_id}/results", response_model=ExaminerResultsResponse, responses=_ERRORS
)
def read_examiner_results(
    lens: Annotated[ExaminerLens, Depends(examiner_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> ExaminerResultsResponse:
    """Read every seat's result on one exam I mark: names and results only.

    :param lens: The lens for this one exam
    :param session: The request-scoped session
    :return: The exam, one row per seat, and whether marks are accepted
    """
    results = exam_results(session, lens=lens, exam_id=lens.exam_id)
    exam = next(
        row
        for row in my_exams(session, account_id=lens.account_id)
        if row.exam_id == lens.exam_id
    )
    return ExaminerResultsResponse(
        exam=_exam(exam),
        results=[
            ExamineeResponse.model_validate(
                {
                    "enrollment_id": row.enrollment_id,
                    "display_name": row.display_name,
                    "result_state": row.result_state,
                    "marks": row.marks,
                }
            )
            for row in results
        ],
        writable=exam_is_writable(session, exam_id=lens.exam_id),
    )


@router.post(
    "/{exam_id}/marks", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS
)
def write_examiner_mark(
    body: MarkWriteRequest,
    lens: Annotated[ExaminerLens, Depends(examiner_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> None:
    """Enter or correct one seat's result on an exam I mark.

    :param body: The seat, the state and the number
    :param lens: The lens for this one exam
    :param session: The request-scoped session
    :return: None
    """
    record_mark(
        session,
        lens=lens,
        exam_id=lens.exam_id,
        enrollment_id=body.enrollment_id,
        result_state=body.result_state,
        marks=body.marks,
    )


@router.post(
    "/{exam_id}/publish", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS
)
def publish_examiner_exam(
    lens: Annotated[ExaminerLens, Depends(examiner_lens)],
    session: Annotated[DbSession, Depends(get_session)],
) -> None:
    """Publish an exam I mark to its students and guardians.

    :param lens: The lens for this one exam
    :param session: The request-scoped session
    :return: None
    """
    views.publish_exam(session, lens=lens, exam_id=lens.exam_id)
