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
from app.errors import AuthorizationError
from app.errors.codes import NOT_AVAILABLE
from app.money import Money

__all__ = [
    "CLAIM_TO_VERIFY",
    "CLASS_CANCELLED",
    "CLASS_RESCHEDULED",
    "EXAM_CANCELLED",
    "EXAM_SCHEDULED",
    "FEE_REMINDER",
    "INBOX_LIMIT",
    "LEGACY_KINDS",
    "MARKS_AVAILABLE",
    "NOTICE",
    "PAYMENT_APPROVED",
    "PAYMENT_PARTIAL",
    "PAYMENT_RECORDED",
    "PAYMENT_REJECTED",
    "ClassChange",
    "Inbox",
    "InboxItem",
    "deliver",
    "inbox",
    "mark_one_read",
    "mark_read",
    "mark_read_for_source",
    "mark_unread_for_source",
    "owned_item",
    "remove_for_source",
    "sent_class_change",
]

#: The kind a fee reminder is stored under.
FEE_REMINDER: Final[str] = "fee_reminder"

#: A payment the teacher approved, in whole or in part.
PAYMENT_APPROVED: Final[str] = "payment_approved"

#: A payment the teacher rejected.
PAYMENT_REJECTED: Final[str] = "payment_rejected"

#: A payment the teacher approved for less than was claimed.
PAYMENT_PARTIAL: Final[str] = "payment_partial"

#: Money the teacher received by hand and recorded themselves. Distinct
#: from :data:`PAYMENT_APPROVED`, whose copy answers a payment the family
#: reported: here the family reported nothing, so "your payment was
#: approved" would describe an event that did not happen.
PAYMENT_RECORDED: Final[str] = "payment_recorded"

#: A notice a teacher posted to a batch.
NOTICE: Final[str] = "notice"

#: An exam a teacher scheduled for a batch.
EXAM_SCHEDULED: Final[str] = "exam_scheduled"

#: An exam the teacher called off before its results were published.
#: Replaces that exam's :data:`EXAM_SCHEDULED` items, so a family's inbox
#: never holds both an invitation and its cancellation for one exam.
EXAM_CANCELLED: Final[str] = "exam_cancelled"

#: Marks a teacher published for an exam.
MARKS_AVAILABLE: Final[str] = "marks_available"

#: A payment claim waiting for the teacher to verify.
CLAIM_TO_VERIFY: Final[str] = "claim_to_verify"

#: A class the teacher cancelled before it was held [PO-1]. Replaces any
#: :data:`CLASS_RESCHEDULED` item for the same session, so an inbox never
#: holds "moved to Wednesday" beside "cancelled".
CLASS_CANCELLED: Final[str] = "class_cancelled"

#: A class the teacher moved to another day or time [PO-1]. A second move
#: replaces the first move's item rather than stacking beside it.
CLASS_RESCHEDULED: Final[str] = "class_rescheduled"

#: The kinds every client knew before clients began announcing theirs
#: [PO-10]. **Frozen: never add to it.** A client that does not say which
#: kinds it can show is one built before the announcement existed, and
#: these are exactly the kinds such a client renders, so its items and its
#: unread badge are counted over these and nothing newer. A new kind is
#: reached only by a client that names it, which is what keeps an old
#: install's badge from counting a message it will never draw.
LEGACY_KINDS: Final[frozenset[str]] = frozenset(
    {
        FEE_REMINDER,
        PAYMENT_APPROVED,
        PAYMENT_PARTIAL,
        PAYMENT_REJECTED,
        PAYMENT_RECORDED,
        NOTICE,
        EXAM_SCHEDULED,
        EXAM_CANCELLED,
        MARKS_AVAILABLE,
        CLAIM_TO_VERIFY,
    }
)

#: How many messages one read returns. An inbox is read on open, and a
#: year of weekly reminders across two batches stays under it.
INBOX_LIMIT: Final[int] = 100


@dataclass(frozen=True, slots=True)
class ClassChange:
    """Which class a class-change message is about, as it was when sent.

    Copied onto the message like ``batch_name``: the session row holds
    only where the class is now, and the time a reschedule moved it from
    exists nowhere else.

    :ivar class_date: The day the class is on now, or was on if cancelled
    :ivar class_time: Its start time that day
    :ivar moved_from_date: For a reschedule, the day it was on before
    :ivar moved_from_time: For a reschedule, the start time before
    """

    class_date: dt.date
    class_time: dt.time
    moved_from_date: dt.date | None = None
    moved_from_time: dt.time | None = None


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
    :ivar source_id: The record that produced it, if any
    :ivar child_name: Which child it is about, for a guardian's copy
    :ivar preview: A short line of its content, if any
    :ivar class_change: The class it is about, for a class change
    """

    notification_id: uuid.UUID
    kind: str
    enrollment_id: uuid.UUID | None
    batch_name: str
    period: str | None
    amount: Money | None
    created_at: dt.datetime
    read: bool
    source_id: uuid.UUID | None
    child_name: str | None
    preview: str | None
    class_change: ClassChange | None = None


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
    source_id: uuid.UUID | None = None,
    preview: str | None = None,
    child_names: dict[uuid.UUID, str] | None = None,
    class_change: ClassChange | None = None,
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
    :param source_id: The record that produced it, if any
    :param preview: A short line of its content, if any
    :param child_names: Child label to store, keyed by recipient account
    :param class_change: The class it is about, for a class change
    :return: None
    """
    labels = child_names or {}
    change = class_change
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
                source_id=source_id,
                preview=preview,
                child_name=labels.get(account_id),
                class_date=None if change is None else change.class_date,
                class_time=None if change is None else change.class_time,
                moved_from_date=None if change is None else change.moved_from_date,
                moved_from_time=None if change is None else change.moved_from_time,
            )
        )


def _item(row: Notification) -> InboxItem:
    """Present one stored row as its owner sees it.

    :param row: The stored notification
    :return: The item
    """
    return InboxItem(
        notification_id=row.id,
        kind=row.kind,
        enrollment_id=row.enrollment_id,
        batch_name=row.batch_name,
        period=row.period,
        amount=row.amount,
        created_at=row.created_at,
        read=row.read_at is not None,
        source_id=row.source_id,
        child_name=row.child_name,
        preview=row.preview,
        class_change=_class_change(row),
    )


def _class_change(row: Notification) -> ClassChange | None:
    """Read the class a stored row names, if it names one.

    :param row: The stored notification
    :return: The class, or None for a row about no class
    """
    if row.class_date is None or row.class_time is None:
        return None
    return ClassChange(
        class_date=row.class_date,
        class_time=row.class_time,
        moved_from_date=row.moved_from_date,
        moved_from_time=row.moved_from_time,
    )


def inbox(
    session: Session,
    *,
    account_id: uuid.UUID,
    kinds: frozenset[str] | None = None,
) -> Inbox:
    """Read an account's own inbox.

    **The items and the unread count are taken over the same kinds**
    [PO-10]. A client drops a kind it cannot draw, so counting one it
    will drop would show a badge with nothing behind it; restricting
    both to the kinds the client can show keeps the badge honest. The
    rows not shown are left as they are, unread, for the client that
    can show them.

    :param session: The session to read through
    :param account_id: The authenticated caller
    :param kinds: The kinds to read; every kind when None
    :return: Their messages, newest first, and the unread count
    """
    mine = [Notification.account_id == account_id]
    if kinds is not None:
        mine.append(Notification.kind.in_(sorted(kinds)))
    rows = session.scalars(
        sa.select(Notification)
        .where(*mine)
        .order_by(Notification.created_at.desc(), Notification.id)
        .limit(INBOX_LIMIT)
    ).all()
    unread = session.scalar(
        sa.select(sa.func.count())
        .select_from(Notification)
        .where(*mine, Notification.read_at.is_(None))
    )
    return Inbox(
        items=[_item(row) for row in rows],
        unread=unread or 0,
    )


def mark_read(
    session: Session,
    *,
    account_id: uuid.UUID,
    now: dt.datetime | None = None,
    kinds: frozenset[str] | None = None,
) -> None:
    """Mark every unread message in an account's own inbox as read.

    The whole inbox at once, because the screen shows them all on open;
    a per-message flag would ask the reader to tap each one. Only the
    kinds the reader's client can show, when it says which: a message
    an old client never drew stays unread for the client that will.

    :param session: The session to write through
    :param account_id: The authenticated caller
    :param now: When it was read; the current time by default
    :param kinds: The kinds to mark; every kind when None
    :return: None
    """
    mine = [Notification.account_id == account_id, Notification.read_at.is_(None)]
    if kinds is not None:
        mine.append(Notification.kind.in_(sorted(kinds)))
    session.execute(
        sa.update(Notification)
        .where(*mine)
        .values(read_at=now or dt.datetime.now(tz=dt.UTC))
    )
    session.commit()


def mark_one_read(
    session: Session,
    *,
    account_id: uuid.UUID,
    notification_id: uuid.UUID,
    now: dt.datetime | None = None,
) -> None:
    """Mark one of an account's own messages as read.

    A no-op for an id that is not the caller's, so another account's
    message is neither changed nor confirmed to exist.

    :param session: The session to write through
    :param account_id: The authenticated caller
    :param notification_id: The message to mark
    :param now: When it was read; the current time by default
    :return: None
    """
    session.execute(
        sa.update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.account_id == account_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=now or dt.datetime.now(tz=dt.UTC))
    )
    session.commit()


def mark_unread_for_source(
    session: Session,
    *,
    kind: str,
    source_id: uuid.UUID,
    reaches: list[tuple[uuid.UUID, uuid.UUID]],
    preview: str | None = None,
) -> None:
    """Make the copies of an edited record unread again, for who it reaches.

    **Only the rows of ``(account, seat)`` pairs the record still reaches
    change.** A guardian who declined, a seat removed or one that has
    left keeps the copy as it was: the old preview and its read state.
    Rewriting it would put the edit in the inbox of someone who no
    longer has access [BR5.2]. ``created_at`` is left as sent. Adds to
    the caller's transaction and does not commit.

    :param session: The caller's session
    :param kind: What produced the messages
    :param source_id: The record they came from
    :param reaches: The ``(account_id, enrollment_id)`` pairs it reaches now
    :param preview: The record's new preview line; left as is when None
    :return: None
    """
    if not reaches:
        return
    values: dict[str, object] = {"read_at": None}
    if preview is not None:
        values["preview"] = preview
    session.execute(
        sa.update(Notification)
        .where(
            Notification.kind == kind,
            Notification.source_id == source_id,
            sa.tuple_(Notification.account_id, Notification.enrollment_id).in_(reaches),
        )
        .values(**values)
    )


def mark_read_for_source(
    session: Session,
    *,
    kind: str,
    source_id: uuid.UUID,
    now: dt.datetime | None = None,
) -> None:
    """Mark every unread copy of a record's messages as read.

    Used when the record stops waiting on its reader: a claim the
    teacher has decided is no longer one to verify. Rows already read
    keep their time. Adds to the caller's transaction and does not
    commit.

    :param session: The caller's session
    :param kind: What produced the messages
    :param source_id: The record they came from
    :param now: When it was settled; the current time by default
    :return: None
    """
    session.execute(
        sa.update(Notification)
        .where(
            Notification.kind == kind,
            Notification.source_id == source_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=now or dt.datetime.now(tz=dt.UTC))
    )


def sent_class_change(
    session: Session, *, kind: str, source_id: uuid.UUID
) -> ClassChange | None:
    """Read the class change a record's messages already carry, if any.

    Every recipient's copy of one record carries the same change, so
    any one of them answers.

    :param session: The session to read through
    :param kind: What produced the messages
    :param source_id: The record they came from
    :return: The change as sent, or None when nothing was sent
    """
    row = session.scalars(
        sa.select(Notification)
        .where(Notification.kind == kind, Notification.source_id == source_id)
        .limit(1)
    ).first()
    return None if row is None else _class_change(row)


def remove_for_source(session: Session, *, kind: str, source_id: uuid.UUID) -> None:
    """Delete every recipient's copy of a record.

    Adds to the caller's transaction and does not commit.

    :param session: The caller's session
    :param kind: What produced the messages
    :param source_id: The record they came from
    :return: None
    """
    session.execute(
        sa.delete(Notification).where(
            Notification.kind == kind, Notification.source_id == source_id
        )
    )


def owned_item(
    session: Session, *, account_id: uuid.UUID, notification_id: uuid.UUID
) -> InboxItem:
    """Read one message, only if it is the caller's own.

    An id that does not exist and an id that belongs to someone else
    raise the same error, so a caller cannot tell them apart.

    :param session: The session to read through
    :param account_id: The authenticated caller
    :param notification_id: The message to open
    :return: The message
    :raises AuthorizationError: If it is absent or not the caller's
    """
    row = session.scalar(
        sa.select(Notification).where(
            Notification.id == notification_id,
            Notification.account_id == account_id,
        )
    )
    if row is None:
        raise AuthorizationError(code=NOT_AVAILABLE, message_key="inbox.not_available")
    return _item(row)
