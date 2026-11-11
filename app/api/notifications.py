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

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import authenticated_account, get_session
from app.money.wire import to_wire
from app.notifications.detail import ItemDetail, open_item
from app.notifications.inbox import (
    CLAIM_TO_VERIFY,
    CLASS_CANCELLED,
    CLASS_RESCHEDULED,
    EXAM_CANCELLED,
    EXAM_SCHEDULED,
    FEE_REMINDER,
    LEGACY_KINDS,
    MARKS_AVAILABLE,
    NOTICE,
    PAYMENT_APPROVED,
    PAYMENT_PARTIAL,
    PAYMENT_RECORDED,
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
    "payment_recorded",
    "notice",
    "exam_scheduled",
    "exam_cancelled",
    "marks_available",
    "claim_to_verify",
    "class_cancelled",
    "class_rescheduled",
]

#: The kinds the contract publishes, each to itself.
_PUBLISHED: dict[str, Kind] = {
    FEE_REMINDER: "fee_reminder",
    PAYMENT_APPROVED: "payment_approved",
    PAYMENT_PARTIAL: "payment_partial",
    PAYMENT_REJECTED: "payment_rejected",
    PAYMENT_RECORDED: "payment_recorded",
    NOTICE: "notice",
    EXAM_SCHEDULED: "exam_scheduled",
    EXAM_CANCELLED: "exam_cancelled",
    MARKS_AVAILABLE: "marks_available",
    CLAIM_TO_VERIFY: "claim_to_verify",
    CLASS_CANCELLED: "class_cancelled",
    CLASS_RESCHEDULED: "class_rescheduled",
}

#: ``?kind=`` as the read and mark-all routes declare it.
AnnouncedKinds = Annotated[
    list[str] | None,
    Query(
        alias="kind",
        description=(
            "The kinds this client can show, repeated. Items and the unread "
            "count are both taken over these. Omitted: the kinds every client "
            "showed before kinds were announced. A kind this server does not "
            "publish is ignored."
        ),
    ),
]


def _readable(announced: list[str] | None) -> frozenset[str]:
    """Decide which kinds a client's inbox is read over [PO-10].

    **The client announces what it can draw, and the server counts only
    that.** Both clients drop a kind they do not know, so before this an
    old install showed a badge counting a message it would never render.
    The two alternatives were weaker: pinning the old behaviour in a test
    documents a wrong badge rather than fixing it, and filtering on the
    client cannot fix ``unread``, which is counted over the whole inbox
    and past the returned page.

    **Silence means the frozen legacy set**, not "everything". A client
    that sends no ``kind`` is one built before announcing existed -- the
    installed Android apps in the field -- and :data:`LEGACY_KINDS` is
    exactly what such a client renders. Each future kind is then reached
    only by a client that names it, with no change here.

    **An unknown kind is ignored rather than refused**, so a client newer
    than the server still reads its inbox.

    :param announced: The ``kind`` values the client sent, if any
    :return: The kinds to read and count over
    """
    if announced is None:
        return LEGACY_KINDS
    return frozenset(announced) & frozenset(_PUBLISHED)


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
    change = item.class_change
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
        class_date=None if change is None else change.class_date,
        class_time=None if change is None else change.class_time,
        moved_from_date=None if change is None else change.moved_from_date,
        moved_from_time=None if change is None else change.moved_from_time,
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
    kind: AnnouncedKinds = None,
) -> InboxResponse:
    """Read this account's own messages, newest first.

    Only the kinds the client announces, and the unread count over the
    same kinds (:func:`_readable`).

    :param account_id: The authenticated account
    :param session: The request-scoped session
    :param kind: The kinds the client can show
    :return: The messages and the unread count
    """
    found = inbox(session, account_id=account_id, kinds=_readable(kind))
    return InboxResponse(
        items=[_present(item) for item in found.items],
        unread=found.unread,
    )


@router.post("/me/notifications/read", status_code=status.HTTP_204_NO_CONTENT)
def read_all(
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
    kind: AnnouncedKinds = None,
) -> None:
    """Mark every message this client can show as read.

    A kind the client did not announce stays unread, for the client
    that can show it (:func:`_readable`).

    :param account_id: The authenticated account
    :param session: The request-scoped session
    :param kind: The kinds the client can show
    :return: None
    """
    mark_read(session, account_id=account_id, kinds=_readable(kind))


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
