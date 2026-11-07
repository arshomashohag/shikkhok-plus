"""The requester's help centre: ask, read the answer, reply.

**Authenticated, and lens-exempt on the inbox's reasoning.** Every
route acts on the authenticated account's own tickets. Each statement
is scoped by that account id in SQL, so another account's ticket id is
indistinguishable from a missing one and there is no other account's
data for a lens to scope. Requiring a lens would be worse than
redundant: a person who signed up and was never enrolled holds none, and
that is exactly the person most likely to need help. All four routes
are in ``LENS_EXEMPT_AUTHENTICATED`` with that justification.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.accounts.clients import CLIENT_PLATFORM_HEADER, parse_platform
from app.api.deps import authenticated_account, get_session
from app.help.tickets import (
    Message,
    Ticket,
    TicketDetail,
    my_ticket,
    my_tickets,
    open_ticket,
    requester_reply,
)
from app.schemas.help import (
    HelpMessageResponse,
    HelpReplyRequest,
    HelpTicketDetailResponse,
    HelpTicketListResponse,
    HelpTicketRequest,
    HelpTicketResponse,
)

__all__ = ["present_message", "router"]

router = APIRouter(prefix="/v1/me/help", tags=["help"])


def _present(ticket: Ticket) -> HelpTicketResponse:
    """Present one ticket on the wire.

    :param ticket: The ticket
    :return: Its response
    """
    return HelpTicketResponse(
        ticket_id=ticket.ticket_id,
        subject=ticket.subject,
        status=ticket.status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        has_new_reply=ticket.has_new_reply,
        preview=ticket.preview,
    )


def present_message(message: Message) -> HelpMessageResponse:
    """Present one message on the wire.

    :param message: The message
    :return: Its response
    """
    return HelpMessageResponse(
        message_id=message.message_id,
        author=message.author,
        body=message.body,
        created_at=message.created_at,
    )


def _present_detail(detail: TicketDetail) -> HelpTicketDetailResponse:
    """Present a ticket and its thread.

    :param detail: The ticket and thread
    :return: Its response
    """
    return HelpTicketDetailResponse(
        ticket=_present(detail.ticket),
        messages=[present_message(m) for m in detail.messages],
    )


@router.get("/tickets", response_model=HelpTicketListResponse)
def list_tickets(
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> HelpTicketListResponse:
    """List the caller's own tickets, most recently active first.

    :param session: The request-scoped session
    :param account_id: The authenticated account
    :return: The tickets and how many carry an unseen reply
    """
    tickets = my_tickets(session, account_id)
    return HelpTicketListResponse(
        tickets=[_present(t) for t in tickets],
        new_replies=sum(1 for t in tickets if t.has_new_reply),
    )


@router.post(
    "/tickets",
    response_model=HelpTicketDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_ticket(
    body: HelpTicketRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> HelpTicketDetailResponse:
    """Ask ShikkhokPlus support a question.

    :param body: The subject and the question
    :param request: The incoming request, for the app it came from
    :param session: The request-scoped session
    :param account_id: The authenticated account
    :return: The new ticket and its thread
    """
    detail = open_ticket(
        session,
        account_id,
        subject=body.subject,
        body=body.body,
        platform=parse_platform(request.headers.get(CLIENT_PLATFORM_HEADER)),
    )
    session.commit()
    return _present_detail(detail)


@router.get("/tickets/{ticket_id}", response_model=HelpTicketDetailResponse)
def get_ticket(
    ticket_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> HelpTicketDetailResponse:
    """Open one of the caller's tickets, marking support's replies seen.

    :param ticket_id: The ticket
    :param session: The request-scoped session
    :param account_id: The authenticated account
    :return: The ticket and its thread
    """
    detail = my_ticket(session, account_id, ticket_id)
    session.commit()
    return _present_detail(detail)


@router.post("/tickets/{ticket_id}/messages", response_model=HelpTicketDetailResponse)
def reply(
    ticket_id: uuid.UUID,
    body: HelpReplyRequest,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> HelpTicketDetailResponse:
    """Add a message to one of the caller's tickets, reopening it.

    :param ticket_id: The ticket
    :param body: The message
    :param session: The request-scoped session
    :param account_id: The authenticated account
    :return: The ticket and its thread
    """
    detail = requester_reply(session, account_id, ticket_id, body.body)
    session.commit()
    return _present_detail(detail)
