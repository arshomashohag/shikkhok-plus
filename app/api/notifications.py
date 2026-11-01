"""The reader's own in-app inbox: read it, and mark it read.

**Authenticated, and lens-exempt on ``GET /v1/me``'s reasoning.** All
routes act on the authenticated account's own messages. The two that
take an id check it against the caller in SQL, so another account's id
is indistinguishable from a missing one and there is no other
account's data for a lens to scope -- and requiring one would hide a
reminder from a guardian whose lens is exactly what the reminder is
about. All are listed in
``LENS_EXEMPT_AUTHENTICATED`` with that justification.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import authenticated_account, get_session
from app.money.wire import to_wire
from app.notifications.detail import ItemDetail, open_item
from app.notifications.inbox import (
    CLAIM_TO_VERIFY,
    EXAM_SCHEDULED,
    FEE_REMINDER,
    MARKS_AVAILABLE,
    NOTICE,
    PAYMENT_APPROVED,
    PAYMENT_PARTIAL,
    PAYMENT_REJECTED,
    InboxItem,
    inbox,
    mark_one_read,
    mark_read,
)
from app.schemas.money import Money as WireMoney
from app.schemas.notifications import (
    ExamBlock,
    InboxResponse,
    NoticeBlock,
    NotificationDetailResponse,
    NotificationResponse,
    PaymentBlock,
)

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["notifications"])


Kind = Literal[
    "fee_reminder",
    "payment_approved",
    "payment_partial",
    "payment_rejected",
    "notice",
    "exam_scheduled",
    "marks_available",
    "claim_to_verify",
]

#: The kinds the contract publishes, each to itself.
_PUBLISHED: dict[str, Kind] = {
    FEE_REMINDER: "fee_reminder",
    PAYMENT_APPROVED: "payment_approved",
    PAYMENT_PARTIAL: "payment_partial",
    PAYMENT_REJECTED: "payment_rejected",
    NOTICE: "notice",
    EXAM_SCHEDULED: "exam_scheduled",
    MARKS_AVAILABLE: "marks_available",
    CLAIM_TO_VERIFY: "claim_to_verify",
}


def _kind(stored: str) -> Kind:
    """Narrow a stored kind onto the published set, checking it.

    A kind added to the table without a decision here raises rather
    than reaching a client that cannot render it.

    :param stored: The stored kind
    :return: The published kind
    :raises ValueError: The kind is not one the contract publishes
    """
    published = _PUBLISHED.get(stored)
    if published is None:
        raise ValueError(f"unpublished notification kind: {stored}")
    return published


def _present(item: InboxItem) -> NotificationResponse:
    """Present one item on the wire.

    :param item: The item
    :return: Its response
    """
    return NotificationResponse(
        notification_id=item.notification_id,
        kind=_kind(item.kind),
        enrollment_id=item.enrollment_id,
        batch_name=item.batch_name,
        period=item.period,
        amount=None if item.amount is None else WireMoney(to_wire(item.amount)),
        created_at=item.created_at,
        read=item.read,
        source_id=item.source_id,
        child_name=item.child_name,
        preview=item.preview,
    )


def _present_detail(opened: ItemDetail) -> NotificationDetailResponse:
    """Present one opened item on the wire.

    :param opened: The item and its source
    :return: Its response
    """
    base = _present(opened.item).model_dump()
    notice, exam, payment = opened.notice, opened.exam, opened.payment
    return NotificationDetailResponse(
        **base,
        available=opened.available,
        notice=None if notice is None else NoticeBlock(**asdict(notice)),
        exam=None if exam is None else ExamBlock(**asdict(exam)),
        payment=None
        if payment is None
        else PaymentBlock(
            claim_id=payment.claim_id,
            period=payment.period,
            claimed=WireMoney(to_wire(payment.claimed)),
            approved=None
            if payment.approved is None
            else WireMoney(to_wire(payment.approved)),
            outcome=payment.outcome,
            reason=payment.reason,
        ),
    )


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
        items=[_present(item) for item in found.items],
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


@router.get(
    "/me/notifications/{notification_id}",
    response_model=NotificationDetailResponse,
)
def read_item(
    notification_id: uuid.UUID,
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
) -> NotificationDetailResponse:
    """Open one of this account's own messages.

    Does not mark it read; the client does that on its own call.

    :param notification_id: The message
    :param account_id: The authenticated account
    :param session: The request-scoped session
    :return: The message and what it opens to
    :raises AuthorizationError: The id is missing or another account's
    """
    return _present_detail(
        open_item(session, account_id=account_id, notification_id=notification_id)
    )


@router.post(
    "/me/notifications/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
)
def read_one(
    notification_id: uuid.UUID,
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """Mark one of this account's own messages as read.

    :param notification_id: The message
    :param account_id: The authenticated account
    :param session: The request-scoped session
    :return: None
    """
    mark_one_read(session, account_id=account_id, notification_id=notification_id)
