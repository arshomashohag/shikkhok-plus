"""The reader's own in-app inbox: read it, and mark it read.

**Authenticated, and lens-exempt on ``GET /v1/me``'s reasoning.** Both
routes act on the authenticated account's own messages and take no id
from the request, so there is no other account's data for a lens to
scope -- and requiring one would hide a reminder from a guardian whose
lens is exactly what the reminder is about. Both are listed in
``LENS_EXEMPT_AUTHENTICATED`` with that justification.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import authenticated_account, get_session
from app.money.wire import to_wire
from app.notifications.inbox import FEE_REMINDER, inbox, mark_read
from app.schemas.money import Money as WireMoney
from app.schemas.notifications import InboxResponse, NotificationResponse

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["notifications"])


def _kind(stored: str) -> Literal["fee_reminder"]:
    """Narrow a stored kind onto the published set, checking it.

    A kind added to the table without a decision here raises rather
    than reaching a client that cannot render it.

    :param stored: The stored kind
    :return: The published kind
    :raises ValueError: The kind is not one the contract publishes
    """
    if stored == FEE_REMINDER:
        return "fee_reminder"
    raise ValueError(f"unpublished notification kind: {stored}")


@router.get("/me/notifications", response_model=InboxResponse)
def read_inbox(
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
) -> InboxResponse:
    """Read this account's own messages, newest first.

    :param account_id: The authenticated account
    :param session: The request-scoped session
    :return: The messages and the unread count
    """
    found = inbox(session, account_id=account_id)
    return InboxResponse(
        items=[
            NotificationResponse(
                notification_id=item.notification_id,
                kind=_kind(item.kind),
                enrollment_id=item.enrollment_id,
                batch_name=item.batch_name,
                period=item.period,
                amount=None if item.amount is None else WireMoney(to_wire(item.amount)),
                created_at=item.created_at,
                read=item.read,
            )
            for item in found.items
        ],
        unread=found.unread,
    )


@router.post("/me/notifications/read", status_code=status.HTTP_204_NO_CONTENT)
def read_all(
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """Mark every message in this account's own inbox as read.

    :param account_id: The authenticated account
    :param session: The request-scoped session
    :return: None
    """
    mark_read(session, account_id=account_id)
