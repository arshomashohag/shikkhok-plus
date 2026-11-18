"""The platform administration surface [TC-14, D-6].

**Every route takes a :class:`PlatformAdminLens`**, granted only to an
allowlisted phone number and checked per request. The route gate holds
the set of routes reaching that lens to ``PLATFORM_ADMIN_ROUTES``, and
the privacy gate walks these routes' response schemas for any field
outside the administrator boundary.

What crosses the boundary is decided in ``app.admin`` and
``app.help.identity``; this module only presents it.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import logging
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.admin.overview import overview
from app.admin.teachers import workspaces
from app.api.deps import get_session, platform_admin_lens
from app.api.help import present_message
from app.api.hub_media import media_store
from app.authz.lenses import PlatformAdminLens
from app.help.identity import RequesterIdentity
from app.help.tickets import (
    AdminTicket,
    AdminTicketDetail,
    admin_ticket,
    admin_tickets,
    requesters,
    set_status,
    support_reply,
)
from app.hub.media.storage import MediaStore
from app.moderation import media, reports, suspension
from app.schemas.admin import (
    AdminAppVersion,
    AdminOverviewResponse,
    AdminPlatformUsage,
    AdminReplyRequest,
    AdminRequester,
    AdminRequestersResponse,
    AdminRequesterSummary,
    AdminTicketDetailResponse,
    AdminTicketListResponse,
    AdminTicketStatusRequest,
    AdminWorkspace,
    AdminWorkspacesResponse,
)
from app.schemas.admin import AdminTicket as AdminTicketWire
from app.schemas.moderation import (
    AdminHubDecisionRequest,
    AdminHubField,
    AdminHubMediaDecided,
    AdminHubMediaDecisionRequest,
    AdminHubMediaDetail,
    AdminHubQueueItem,
    AdminHubQueueKind,
    AdminHubQueueResponse,
    AdminHubReportDecided,
    AdminHubSuspensionRequest,
    AdminHubSuspensionState,
)

__all__ = ["router"]

router = APIRouter(prefix="/v1/admin", tags=["admin"])

_log = logging.getLogger(__name__)


def _audit(lens: PlatformAdminLens, action: str) -> None:
    """Log that an administrator used the surface.

    The account id and the action, never a phone number or anything read.

    :param lens: The administrator's lens
    :param action: What they did
    :return: None
    """
    _log.info(
        "platform_admin", extra={"account_id": str(lens.account_id), "action": action}
    )


def _requester(who: RequesterIdentity) -> AdminRequester:
    """Present who asked.

    :param who: The identity, already bounded
    :return: Its response
    """
    return AdminRequester(
        ref=who.ref, roles=list(who.roles), name=who.name, centre=who.centre
    )


def _ticket(ticket: AdminTicket) -> AdminTicketWire:
    """Present one ticket.

    :param ticket: The ticket
    :return: Its response
    """
    return AdminTicketWire(
        ticket_id=ticket.ticket_id,
        subject=ticket.subject,
        status=ticket.status,
        platform=ticket.platform,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        message_count=ticket.message_count,
        preview=ticket.preview,
        requester=_requester(ticket.requester),
    )


def _detail(detail: AdminTicketDetail) -> AdminTicketDetailResponse:
    """Present a ticket and its thread.

    :param detail: The ticket and thread
    :return: Its response
    """
    return AdminTicketDetailResponse(
        ticket=_ticket(detail.ticket),
        messages=[present_message(m) for m in detail.messages],
    )


@router.get("/overview", response_model=AdminOverviewResponse)
def get_overview(
    lens: Annotated[PlatformAdminLens, Depends(platform_admin_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> AdminOverviewResponse:
    """Read the platform's aggregate figures.

    :param lens: The administrator's lens
    :param session: The request-scoped session
    :return: The figures
    """
    _audit(lens, "overview")
    figures = overview(session)
    return AdminOverviewResponse(
        generated_at=figures.generated_at,
        accounts=figures.accounts,
        new_7_days=figures.new_7_days,
        new_30_days=figures.new_30_days,
        active_7_days=figures.active_7_days,
        active_30_days=figures.active_30_days,
        teachers=figures.teachers,
        centres=figures.centres,
        centre_members=figures.centre_members,
        students=figures.students,
        guardians=figures.guardians,
        batches=figures.batches,
        seats=figures.seats,
        platforms=[
            AdminPlatformUsage(
                platform=p.platform,
                accounts=p.accounts,
                active_7_days=p.active_7_days,
                active_30_days=p.active_30_days,
            )
            for p in figures.platforms
        ],
        both_platforms=figures.both_platforms,
        no_platform=figures.no_platform,
        versions=[
            AdminAppVersion(
                platform=v.platform,
                version=v.version,
                accounts=v.accounts,
            )
            for v in figures.versions
        ],
        help_open=figures.help_open,
        help_answered=figures.help_answered,
        help_closed=figures.help_closed,
    )


@router.get("/teachers", response_model=AdminWorkspacesResponse)
def list_teachers(
    lens: Annotated[PlatformAdminLens, Depends(platform_admin_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> AdminWorkspacesResponse:
    """List teachers and coaching centres by name.

    :param lens: The administrator's lens
    :param session: The request-scoped session
    :return: The workspaces, most recently seen first
    """
    _audit(lens, "teachers")
    return AdminWorkspacesResponse(
        workspaces=[
            AdminWorkspace(
                workspace_id=w.workspace_id,
                kind=w.kind,
                name=w.name,
                platforms=list(w.platforms),
                joined_at=w.joined_at,
                last_seen_at=w.last_seen_at,
                ref=w.ref,
            )
            for w in workspaces(session)
        ]
    )


@router.get("/help/requesters", response_model=AdminRequestersResponse)
def list_requesters(
    lens: Annotated[PlatformAdminLens, Depends(platform_admin_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> AdminRequestersResponse:
    """List everyone who has asked support, with their ticket counts.

    :param lens: The administrator's lens
    :param session: The request-scoped session
    :return: One row per person, latest activity first
    """
    _audit(lens, "help.requesters")
    return AdminRequestersResponse(
        requesters=[
            AdminRequesterSummary(
                requester=_requester(r.requester),
                tickets=r.tickets,
                open=r.open,
                last_activity=r.last_activity,
            )
            for r in requesters(session)
        ]
    )


@router.get("/help/tickets", response_model=AdminTicketListResponse)
def list_tickets(
    lens: Annotated[PlatformAdminLens, Depends(platform_admin_lens)],
    session: Annotated[Session, Depends(get_session)],
    status: Annotated[Literal["open", "answered", "closed"] | None, Query()] = None,
    ref: Annotated[
        str | None, Query(min_length=10, max_length=10, pattern=r"^[0-9A-Fa-f]+$")
    ] = None,
) -> AdminTicketListResponse:
    """List tickets, optionally one status or one person's.

    :param lens: The administrator's lens
    :param session: The request-scoped session
    :param status: Only this status
    :param ref: Only this person's tickets, by their opaque label
    :return: The tickets, waiting-on-support first
    """
    _audit(lens, "help.tickets")
    return AdminTicketListResponse(
        tickets=[_ticket(t) for t in admin_tickets(session, status=status, ref=ref)]
    )


@router.get("/help/tickets/{ticket_id}", response_model=AdminTicketDetailResponse)
def get_ticket(
    ticket_id: uuid.UUID,
    lens: Annotated[PlatformAdminLens, Depends(platform_admin_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> AdminTicketDetailResponse:
    """Open any ticket.

    :param ticket_id: The ticket
    :param lens: The administrator's lens
    :param session: The request-scoped session
    :return: The ticket and its thread
    """
    _audit(lens, "help.ticket")
    return _detail(admin_ticket(session, ticket_id))


@router.post(
    "/help/tickets/{ticket_id}/messages", response_model=AdminTicketDetailResponse
)
def reply(
    ticket_id: uuid.UUID,
    body: AdminReplyRequest,
    lens: Annotated[PlatformAdminLens, Depends(platform_admin_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> AdminTicketDetailResponse:
    """Answer a ticket as ShikkhokPlus support.

    :param ticket_id: The ticket
    :param body: The reply
    :param lens: The administrator's lens
    :param session: The request-scoped session
    :return: The ticket and its thread
    """
    _audit(lens, "help.reply")
    detail = support_reply(session, lens.account_id, ticket_id, body.body)
    session.commit()
    return _detail(detail)


@router.put(
    "/help/tickets/{ticket_id}/status", response_model=AdminTicketDetailResponse
)
def change_status(
    ticket_id: uuid.UUID,
    body: AdminTicketStatusRequest,
    lens: Annotated[PlatformAdminLens, Depends(platform_admin_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> AdminTicketDetailResponse:
    """Close or reopen a ticket.

    :param ticket_id: The ticket
    :param body: The new status
    :param lens: The administrator's lens
    :param session: The request-scoped session
    :return: The ticket and its thread
    """
    _audit(lens, f"help.status.{body.status}")
    detail = set_status(session, ticket_id, body.status)
    session.commit()
    return _detail(detail)


def _correlation(request: Request) -> str:
    """Read the request's correlation id for the moderation event.

    :param request: The incoming request
    :return: The id, capped to the column width
    """
    return str(getattr(request.state, "correlation_id", "unknown"))[:64]


@router.get("/hub/queue", response_model=AdminHubQueueResponse)
def hub_queue(
    lens: Annotated[PlatformAdminLens, Depends(platform_admin_lens)],
    session: Annotated[Session, Depends(get_session)],
    kind: Annotated[AdminHubQueueKind, Query()] = "report",
) -> AdminHubQueueResponse:
    """List open reports, suspended listings, or photos to decide, oldest first.

    :param lens: The administrator's lens
    :param session: The request-scoped session
    :param kind: ``report``, ``listing`` or ``media``
    :return: The queue; a reporter appears only as an opaque label
    """
    _audit(lens, f"hub_queue_{kind}")
    return AdminHubQueueResponse(
        kind=kind,
        items=[
            AdminHubQueueItem(
                kind=i.kind,
                report_id=i.report_id,
                target_kind=i.target_kind,
                target_id=i.target_id,
                owner_id=i.owner_id,
                title=i.title,
                fields=[
                    AdminHubField.model_validate({"key": k, "value": v})
                    for k, v in i.fields
                ],
                reason=i.reason,
                note=i.note,
                reporter_ref=i.reporter_ref,
                waited_hours=i.waited_hours,
            )
            for i in reports.queue(session, kind)
        ],
    )


@router.post("/hub/reports/{report_id}/decision", response_model=AdminHubReportDecided)
def decide_report(
    report_id: uuid.UUID,
    body: AdminHubDecisionRequest,
    request: Request,
    lens: Annotated[PlatformAdminLens, Depends(platform_admin_lens)],
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[MediaStore, Depends(media_store)],
) -> AdminHubReportDecided:
    """Uphold or dismiss a report; a photo report's decision reaches the photo.

    :param report_id: The report
    :param body: The decision
    :param request: The incoming request
    :param lens: The administrator's lens
    :param session: The request-scoped session
    :param store: The photo bucket, for restoring a held photo
    :return: The report and its new status
    """
    _audit(lens, "hub_report_decision")
    reports.decide(
        session,
        lens,
        report_id,
        body.decision,
        dt.datetime.now(tz=dt.UTC),
        _correlation(request),
        store=store,
    )
    return AdminHubReportDecided(report_id=report_id, status=body.decision)


@router.put("/hub/owners/{owner_id}/suspension", response_model=AdminHubSuspensionState)
def set_suspension(
    owner_id: uuid.UUID,
    body: AdminHubSuspensionRequest,
    request: Request,
    lens: Annotated[PlatformAdminLens, Depends(platform_admin_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> AdminHubSuspensionState:
    """Suspend or restore an owner's public listing.

    :param owner_id: The owner
    :param body: Whether to suspend, and why
    :param request: The incoming request
    :param lens: The administrator's lens
    :param session: The request-scoped session
    :return: The owner and whether the listing is suspended now
    """
    _audit(lens, "hub_suspension")
    suspension.set(
        session,
        lens,
        owner_id,
        body.suspended,
        body.reason_code,
        dt.datetime.now(tz=dt.UTC),
        _correlation(request),
    )
    return AdminHubSuspensionState(owner_id=owner_id, suspended=body.suspended)


@router.get("/hub/media/{media_id}", response_model=AdminHubMediaDetail)
def hub_media(
    media_id: uuid.UUID,
    lens: Annotated[PlatformAdminLens, Depends(platform_admin_lens)],
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[MediaStore, Depends(media_store)],
) -> AdminHubMediaDetail:
    """Read one photo for review, with five-minute previews of its variants.

    :param media_id: The photo
    :param lens: The administrator's lens
    :param session: The request-scoped session
    :param store: The photo bucket
    :return: The photo, its page's public name and title, and no account
    """
    _audit(lens, "hub_media")
    return AdminHubMediaDetail.model_validate(
        dataclasses.asdict(media.detail(session, store, media_id))
    )


@router.post("/hub/media/{media_id}/decision", response_model=AdminHubMediaDecided)
def decide_media(
    media_id: uuid.UUID,
    body: AdminHubMediaDecisionRequest,
    request: Request,
    lens: Annotated[PlatformAdminLens, Depends(platform_admin_lens)],
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[MediaStore, Depends(media_store)],
) -> AdminHubMediaDecided:
    """Approve or reject a photo waiting for review or held after a report.

    :param media_id: The photo
    :param body: The decision, and the code for a rejection
    :param request: The incoming request
    :param lens: The administrator's lens
    :param session: The request-scoped session
    :param store: The photo bucket
    :return: The photo and its new status
    """
    _audit(lens, "hub_media_decision")
    decided = media.decide(
        session,
        store,
        lens,
        media_id,
        approve=body.decision == "approve",
        code=body.code,
        now=dt.datetime.now(tz=dt.UTC),
        correlation_id=_correlation(request),
    )
    return AdminHubMediaDecided(
        media_id=decided.id,
        status="approved" if decided.status == "approved" else "rejected",
    )
