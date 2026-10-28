"""The in-app inbox: what an account has been sent, newest first.

**Scoped by the caller's own account id and nothing else.** The routes
pass the authenticated account; no function here takes an id from a
request, so there is no path by which one account reads another's
inbox [0009].

Writing is :func:`deliver`, which every producer calls; it adds rows to
the caller's transaction and never commits, so a producer's own record
and the messages it sends land together or not at all.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import Notification
from app.money import Money

__all__ = [
    "FEE_REMINDER",
    "INBOX_LIMIT",
    "PAYMENT_APPROVED",
    "PAYMENT_REJECTED",
    "Inbox",
    "InboxItem",
    "deliver",
    "inbox",
    "mark_read",
]

#: The kind a fee reminder is stored under.
FEE_REMINDER: Final[str] = "fee_reminder"

#: A payment the teacher approved, in whole or in part.
PAYMENT_APPROVED: Final[str] = "payment_approved"

#: A payment the teacher rejected.
PAYMENT_REJECTED: Final[str] = "payment_rejected"

#: How many messages one read returns. An inbox is read on open, and a
#: year of weekly reminders across two batches stays under it.
INBOX_LIMIT: Final[int] = 100


@dataclass(frozen=True, slots=True)
class InboxItem:
    """One message, as its owner sees it.

    :ivar notification_id: The message
    :ivar kind: What produced it
    :ivar enrollment_id: The seat it is about, if any
    :ivar batch_name: The batch it concerns, as named when sent
    :ivar period: The period it concerns, if any
    :ivar amount: The money it concerns, if any
    :ivar created_at: When it was sent
    :ivar read: Whether its owner has opened the inbox since
    """

    notification_id: uuid.UUID
    kind: str
    enrollment_id: uuid.UUID | None
    batch_name: str
    period: str | None
    amount: Money | None
    created_at: dt.datetime
    read: bool


@dataclass(frozen=True, slots=True)
class Inbox:
    """An account's messages and how many are unread.

    ``unread`` is counted over the whole inbox, not over the returned
    page, so the badge is right even past :data:`INBOX_LIMIT`.

    :ivar items: Newest first, at most :data:`INBOX_LIMIT`
    :ivar unread: How many have never been seen
    """

    items: list[InboxItem]
    unread: int


def deliver(
    session: Session,
    *,
    account_ids: list[uuid.UUID],
    kind: str,
    batch_name: str,
    now: dt.datetime,
    enrollment_id: uuid.UUID | None = None,
    period: str | None = None,
    amount: Money | None = None,
) -> None:
    """Put one message in each of these accounts' inboxes.

    Adds to the caller's transaction and does not commit.

    :param session: The caller's session
    :param account_ids: Who receives it
    :param kind: What produced it
    :param batch_name: The batch it concerns
    :param now: When it is sent
    :param enrollment_id: The seat it is about, if any
    :param period: The period it concerns, if any
    :param amount: The money it concerns, if any
    :return: None
    """
    for account_id in account_ids:
        session.add(
            Notification(
                account_id=account_id,
                enrollment_id=enrollment_id,
                kind=kind,
                batch_name=batch_name,
                period=period,
                amount=amount,
                created_at=now,
            )
        )


def inbox(session: Session, *, account_id: uuid.UUID) -> Inbox:
    """Read an account's own inbox.

    :param session: The session to read through
    :param account_id: The authenticated caller
    :return: Their messages, newest first, and the unread count
    """
    rows = session.scalars(
        sa.select(Notification)
        .where(Notification.account_id == account_id)
        .order_by(Notification.created_at.desc(), Notification.id)
        .limit(INBOX_LIMIT)
    ).all()
    unread = session.scalar(
        sa.select(sa.func.count())
        .select_from(Notification)
        .where(
            Notification.account_id == account_id,
            Notification.read_at.is_(None),
        )
    )
    return Inbox(
        items=[
            InboxItem(
                notification_id=row.id,
                kind=row.kind,
                enrollment_id=row.enrollment_id,
                batch_name=row.batch_name,
                period=row.period,
                amount=row.amount,
                created_at=row.created_at,
                read=row.read_at is not None,
            )
            for row in rows
        ],
        unread=unread or 0,
    )


def mark_read(
    session: Session,
    *,
    account_id: uuid.UUID,
    now: dt.datetime | None = None,
) -> None:
    """Mark every unread message in an account's own inbox as read.

    The whole inbox at once, because the screen shows them all on open;
    a per-message flag would ask the reader to tap each one.

    :param session: The session to write through
    :param account_id: The authenticated caller
    :param now: When it was read; the current time by default
    :return: None
    """
    session.execute(
        sa.update(Notification)
        .where(
            Notification.account_id == account_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=now or dt.datetime.now(tz=dt.UTC))
    )
    session.commit()
