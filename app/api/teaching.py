"""Session, attendance, topic and announcement routes.

**Every route resolves a lens**, and the built route-enumeration gate
fails CI on one that does not -- it walks ``route.dependant``
recursively and matches on the dependency's **return annotation being
a ``Lens`` subtype**, so renaming one does not defeat the check.

**D4 adds NO entry to ``PUBLIC_ROUTES``.** Every route here is
authenticated; the frozenset holds eight entries and two assertions
check that count, so a D4 route added to it fails ``make check``
rather than passing quietly.

**The handler scopes its query by the value the lens carries**, never
by an id from the request body [BR5.1]. The domain functions take the
lens and derive their query from it, so a handler cannot compile a
scoped query without one.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session as DbSession

from app.api.deps import get_session, guardian_lens, student_lens, teacher_lens
from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.schemas.errors import ErrorEnvelope
from app.schemas.teaching import (
    AnnouncementBodyRequest,
    AnnouncementResponse,
    AttendanceEntryResponse,
    AttendanceSubmitRequest,
    AttendanceSubmitResponse,
    FamilyBatchViewResponse,
    RosterSeatResponse,
    SessionCreateRequest,
    SessionOrigin,
    SessionRescheduleRequest,
    SessionResponse,
    SessionStatus,
    SessionSubjectRequest,
    TopicWriteRequest,
    TopicWriteResponse,
)
from app.teaching import announcements as notes
from app.teaching import sessions as session_service
from app.teaching.roster import session_roster
from app.teaching.submissions import SeatMark, submit_roster, write_topic

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["teaching"])

#: The error responses every lensed D4 route can produce. Declared
#: once and spread onto each route, so a new route cannot quietly ship
#: with an undeclared envelope.
_AUTH_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    401: {
        "model": ErrorEnvelope,
        "description": "No credential, or an expired one.",
    },
    403: {
        "model": ErrorEnvelope,
        "description": (
            "No lens reaches this. Deliberately indistinguishable from "
            "absence: one code covers both, because a pair would be an "
            "existence oracle."
        ),
    },
}

#: The same plus the write shapes.
_WRITE_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    **_AUTH_ERRORS,
    400: {
        "model": ErrorEnvelope,
        "description": "The request is wrong. Fix and resubmit; never retry as-is.",
    },
    409: {
        "model": ErrorEnvelope,
        "description": (
            "Valid request; current state forbids it. Refetch and "
            "decide. On a version conflict the details carry the "
            "current version and the current roster, which is why this "
            "is unreachable before authorization."
        ),
    },
}


#: The closed sets, typed with the Literal as the ELEMENT type so a
#: membership test NARROWS rather than merely checks. A plain
#: ``tuple[str, ...]`` type-checks the test and leaves the value
#: ``str``, which is the difference between proving the property and
#: asserting it. Asserted equal to the database enum's own value lists
#: by a test, so a migration widening one without the contract
#: following fails loudly instead of diverging silently.
_STATUSES: Final[tuple[SessionStatus, ...]] = (
    "scheduled",
    "held",
    "cancelled",
)
_ORIGINS: Final[tuple[SessionOrigin, ...]] = ("recurrence", "ad_hoc")


def _status(stored: str) -> SessionStatus:
    """Narrow a stored status onto the closed set, checking it.

    **A real check rather than a cast, and mypy agrees it is one.**
    The column is a database enum and the ORM types it ``str``, so the
    crossing has to happen somewhere; a ``cast`` would ASSERT the
    property while the membership test against the typed tuple PROVES
    it. A value outside the set means the enum was widened by a
    migration without the contract following, which is a bug the
    client would otherwise meet as an unrenderable status. This is the
    shape ``app/fees/views.py`` already established.

    :param stored: The value read from the column
    :return: The same value, narrowed
    :raises ValueError: The stored value is outside the closed set
    """
    if stored not in _STATUSES:
        raise ValueError(
            f"{stored!r} is not a session status. The database enum and "
            "app.schemas.teaching.SessionStatus have diverged."
        )
    return stored


def _origin(stored: str) -> SessionOrigin:
    """Narrow a stored origin onto the closed set, checking it.

    :param stored: The value read from the column
    :return: The same value, narrowed
    :raises ValueError: The stored value is outside the closed set
    """
    if stored not in _ORIGINS:
        raise ValueError(
            f"{stored!r} is not a session origin. The database enum and "
            "app.schemas.teaching.SessionOrigin have diverged."
        )
    return stored


def _session_response(row: session_service.SessionRow) -> SessionResponse:
    """Render one session for the wire.

    :param row: The session as the view described it
    :return: The response body
    """
    return SessionResponse(
        session_id=row.session_id,
        date=row.date,
        start_time=row.start_time,
        end_time=row.end_time,
        status=_status(row.status),
        origin=_origin(row.origin),
        topic=row.topic,
        topic_logged=row.topic_logged,
        subject_name=row.subject_name,
        attendance_version=row.attendance_version,
        topic_version=row.topic_version,
    )


def _announcement_response(
    row: notes.AnnouncementRow,
) -> AnnouncementResponse:
    """Render one announcement for the wire.

    :param row: The note as the view described it
    :return: The response body
    """
    return AnnouncementResponse(
        announcement_id=row.announcement_id,
        body=row.body,
        created_at=row.created_at,
        edited=row.edited,
    )


@router.get(
    "/batches/{batch_id}/sessions",
    response_model=list[SessionResponse],
    responses=_AUTH_ERRORS,
)
def read_batch_sessions(
    batch_id: uuid.UUID,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> list[SessionResponse]:
    """List one of this teacher's batches' sessions.

    :param batch_id: The batch, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens carrying the owner id
    :return: One row per session, oldest first
    """
    return [
        _session_response(row)
        for row in session_service.list_sessions(session, lens=lens, batch_id=batch_id)
    ]


@router.post(
    "/batches/{batch_id}/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_ERRORS,
)
def create_session(
    batch_id: uuid.UUID,
    body: SessionCreateRequest,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> SessionResponse:
    """Create an ad-hoc session for a date with no slot [BR1.4].

    :param batch_id: The batch, from the route path
    :param body: The date, time and optional subject
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The new session
    """
    return _session_response(
        session_service.create_ad_hoc_session(
            session,
            lens=lens,
            batch_id=batch_id,
            date=body.date,
            start_time=body.start_time,
            end_time=body.end_time,
            batch_subject_id=body.batch_subject_id,
        )
    )


@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    responses=_AUTH_ERRORS,
)
def read_session(
    session_id: uuid.UUID,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> SessionResponse:
    """Read one session.

    :param session_id: The session, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The session
    """
    return _session_response(
        session_service.read_session(session, lens=lens, session_id=session_id)
    )


@router.put(
    "/sessions/{session_id}/schedule",
    response_model=SessionResponse,
    responses=_WRITE_ERRORS,
)
def reschedule_session(
    session_id: uuid.UUID,
    body: SessionRescheduleRequest,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> SessionResponse:
    """Move a session, preserving its identity [BR1.7].

    :param session_id: The session, from the route path
    :param body: Its new date and start time
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The moved session
    """
    return _session_response(
        session_service.reschedule_session(
            session,
            lens=lens,
            session_id=session_id,
            date=body.date,
            start_time=body.start_time,
        )
    )


@router.post(
    "/sessions/{session_id}/cancellation",
    response_model=SessionResponse,
    responses=_WRITE_ERRORS,
)
def cancel_session(
    session_id: uuid.UUID,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> SessionResponse:
    """Cancel a session [BR1.6].

    Terminal for writes and not for reads: the row and its history
    remain readable.

    :param session_id: The session, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The cancelled session
    """
    return _session_response(
        session_service.cancel_session(session, lens=lens, session_id=session_id)
    )


@router.put(
    "/sessions/{session_id}/subject",
    response_model=SessionResponse,
    responses=_WRITE_ERRORS,
)
def set_session_subject(
    session_id: uuid.UUID,
    body: SessionSubjectRequest,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> SessionResponse:
    """Set which subject a session taught.

    :param session_id: The session, from the route path
    :param body: The subject, or null to clear it
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The updated session
    """
    return _session_response(
        session_service.write_session_subject(
            session,
            lens=lens,
            session_id=session_id,
            batch_subject_id=body.batch_subject_id,
        )
    )


@router.put(
    "/sessions/{session_id}/topic",
    response_model=TopicWriteResponse,
    responses=_WRITE_ERRORS,
)
def write_session_topic(
    session_id: uuid.UUID,
    body: TopicWriteRequest,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> TopicWriteResponse:
    """Write a session's topic [BR2.1].

    **One of exactly two D4 writes carrying ``client_mutation_id``**
    and a version, because it is one of the two mid-class paths the
    device queue covers [§ B.7, NFR5]. The replay key is FORWARDED, not
    merely declared: a body that carries the field while the call drops
    it leaves this path with no replay protection, and the schema-level
    contract test cannot see the difference. ``test_api.py``'s
    ``test_both_declared_mutation_id_paths_actually_replay`` is what
    asserts the forwarding.

    :param session_id: The session, from the route path
    :param body: The version, the replay key and the topic
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The topic version now in force
    """
    return TopicWriteResponse(
        topic_version=write_topic(
            session,
            lens=lens,
            session_id=session_id,
            base_version=body.base_topic_version,
            client_mutation_id=body.client_mutation_id,
            topic=body.topic,
        ).topic_version
    )


@router.get(
    "/sessions/{session_id}/attendance",
    response_model=list[RosterSeatResponse],
    responses=_AUTH_ERRORS,
)
def read_session_roster(
    session_id: uuid.UUID,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> list[RosterSeatResponse]:
    """Read one session's roster [BR1.5].

    :param session_id: The session, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: One row per seat on the roster
    """
    return [
        RosterSeatResponse(
            enrollment_id=row.enrollment_id,
            display_name=row.display_name,
            present=row.present,
        )
        for row in session_roster(session, lens=lens, session_id=session_id)
    ]


@router.post(
    "/sessions/{session_id}/attendance",
    response_model=AttendanceSubmitResponse,
    responses=_WRITE_ERRORS,
)
def submit_session_roster(
    session_id: uuid.UUID,
    body: AttendanceSubmitRequest,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> AttendanceSubmitResponse:
    """Submit a whole roster in one atomic write [BR3.3-BR3.8].

    **The other of the two D4 writes carrying
    ``client_mutation_id``.** A replay returns the ORIGINAL stored
    result with 200 and writes nothing; a stale version is refused
    with 409 **after** the lens has been resolved, because the
    conflict's details carry the current roster.

    :param session_id: The session, from the route path
    :param body: The version, the replay key and every seat's mark
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The version now in force
    """
    result = submit_roster(
        session,
        lens=lens,
        session_id=session_id,
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


@router.get(
    "/batches/{batch_id}/announcements",
    response_model=list[AnnouncementResponse],
    responses=_AUTH_ERRORS,
)
def read_announcements(
    batch_id: uuid.UUID,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> list[AnnouncementResponse]:
    """List a batch's visible announcements, for its teacher.

    :param batch_id: The batch, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The visible notes, newest first
    """
    return [
        _announcement_response(row)
        for row in notes.list_announcements(session, lens=lens, batch_id=batch_id)
    ]


@router.post(
    "/batches/{batch_id}/announcements",
    response_model=AnnouncementResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_ERRORS,
)
def create_announcement(
    batch_id: uuid.UUID,
    body: AnnouncementBodyRequest,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> AnnouncementResponse:
    """Post one note to a batch [BR7.1].

    :param batch_id: The batch, from the route path
    :param body: What it says
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The posted note
    """
    return _announcement_response(
        notes.post_announcement(session, lens=lens, batch_id=batch_id, body=body.body)
    )


@router.put(
    "/announcements/{announcement_id}",
    response_model=AnnouncementResponse,
    responses=_WRITE_ERRORS,
)
def update_announcement(
    announcement_id: uuid.UUID,
    body: AnnouncementBodyRequest,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> AnnouncementResponse:
    """Edit a note, marking it as edited [AC3.3.2].

    :param announcement_id: The note, from the route path
    :param body: Its new text
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The edited note
    """
    return _announcement_response(
        notes.edit_announcement(
            session,
            lens=lens,
            announcement_id=announcement_id,
            body=body.body,
        )
    )


@router.delete(
    "/announcements/{announcement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_WRITE_ERRORS,
)
def remove_announcement(
    announcement_id: uuid.UUID,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> Response:
    """Soft-delete a note [AC3.3.3].

    The row survives; only its visibility ends.

    :param announcement_id: The note, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: An empty 204
    """
    notes.delete_announcement(session, lens=lens, announcement_id=announcement_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me/batches/{enrollment_id}/teaching",
    response_model=FamilyBatchViewResponse,
    responses=_AUTH_ERRORS,
)
def read_my_batch_teaching(
    enrollment_id: uuid.UUID,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[StudentLens, Depends(student_lens)],
) -> FamilyBatchViewResponse:
    """Return what this student sees of one of their batches [BR7.2].

    :param enrollment_id: Their seat, from the route path
    :param session: The request-scoped session
    :param lens: The student lens
    :return: The batch view, with its server timestamp
    """
    return _family_view(
        notes.family_batch_view(session, lens=lens, enrollment_id=enrollment_id)
    )


@router.get(
    "/children/{enrollment_id}/teaching",
    response_model=FamilyBatchViewResponse,
    responses=_AUTH_ERRORS,
)
def read_child_batch_teaching(
    enrollment_id: uuid.UUID,
    session: Annotated[DbSession, Depends(get_session)],
    lens: Annotated[GuardianLens, Depends(guardian_lens)],
) -> FamilyBatchViewResponse:
    """Return what this guardian sees of their child's batch [BR7.2].

    The child arrives as a **path parameter**, never from a
    client-supplied lens hint.

    :param enrollment_id: The child's seat, from the route path
    :param session: The request-scoped session
    :param lens: The guardian lens
    :return: The batch view, with its server timestamp
    """
    return _family_view(
        notes.family_batch_view(session, lens=lens, enrollment_id=enrollment_id)
    )


def _family_view(view: notes.FamilyBatchView) -> FamilyBatchViewResponse:
    """Render a family batch view for the wire.

    :param view: The view as the service described it
    :return: The response body
    """
    return FamilyBatchViewResponse(
        next_session_date=view.next_session_date,
        next_session_start_time=view.next_session_start_time,
        past_sessions=[
            AttendanceEntryResponse(
                session_id=entry.session_id,
                date=entry.date,
                start_time=entry.start_time,
                topic=entry.topic,
                topic_logged=entry.topic_logged,
                present=entry.present,
            )
            for entry in view.past_sessions
        ],
        announcements=[_announcement_response(row) for row in view.announcements],
        served_at=view.served_at,
    )
