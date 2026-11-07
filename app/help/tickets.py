"""Help tickets: asking, answering, and closing.

**Every requester statement is scoped by the authenticated account id.**
No function on the requester side takes an account id from a request; a
ticket id belonging to someone else is indistinguishable from one that
does not exist, both answered with the same 404 [NFR14.3].

**Status follows whoever is waited on.** ``open`` waits on support,
``answered`` waits on the requester, ``closed`` waits on nobody. A
requester replying to a closed ticket reopens it, so a person is never
told "you cannot ask about this any more"; an administrator may close or
reopen any ticket.

**Ticket creation is bounded per account per day**, the way every other
write a person can repeat is: the help centre is a free-text channel into
one administrator's attention, and an unbounded one is a way to bury it.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final, Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.accounts.clients import Platform
from app.errors import AuthorizationError, ConflictError
from app.errors.codes import NOT_AVAILABLE
from app.help.identity import RequesterIdentity, identities, requester_ref

__all__ = [
    "ADMIN_PAGE_LIMIT",
    "MAX_TICKETS_PER_DAY",
    "PREVIEW_LENGTH",
    "AdminTicket",
    "AdminTicketDetail",
    "Author",
    "Message",
    "RequesterSummary",
    "Status",
    "Ticket",
    "TicketDetail",
    "admin_ticket",
    "admin_tickets",
    "my_ticket",
    "my_tickets",
    "open_ticket",
    "requester_reply",
    "requesters",
    "set_status",
    "support_reply",
]

Status = Literal["open", "answered", "closed"]
Author = Literal["requester", "support"]

#: Tickets one account may open in any rolling 24 hours.
MAX_TICKETS_PER_DAY: Final = 5

#: How much of the latest message a list shows.
PREVIEW_LENGTH: Final = 140

#: The most tickets one administrator list returns.
ADMIN_PAGE_LIMIT: Final = 200


@dataclass(frozen=True, slots=True)
class Message:
    """One message in a thread.

    :ivar message_id: The message
    :ivar author: ``requester`` or ``support``
    :ivar body: What was written
    :ivar created_at: When
    """

    message_id: uuid.UUID
    author: Author
    body: str
    created_at: dt.datetime


@dataclass(frozen=True, slots=True)
class Ticket:
    """A ticket as its requester sees it in a list.

    :ivar ticket_id: The ticket
    :ivar subject: The one-line summary
    :ivar status: ``open``, ``answered`` or ``closed``
    :ivar created_at: When it was asked
    :ivar updated_at: The latest activity
    :ivar has_new_reply: Support replied since the requester last looked
    :ivar preview: The start of the latest message
    """

    ticket_id: uuid.UUID
    subject: str
    status: Status
    created_at: dt.datetime
    updated_at: dt.datetime
    has_new_reply: bool
    preview: str


@dataclass(frozen=True, slots=True)
class TicketDetail:
    """A ticket and its whole thread, for its requester.

    :ivar ticket: The ticket
    :ivar messages: Its messages, oldest first
    """

    ticket: Ticket
    messages: tuple[Message, ...]


@dataclass(frozen=True, slots=True)
class AdminTicket:
    """A ticket as a platform administrator sees it in a list.

    :ivar ticket_id: The ticket
    :ivar subject: The one-line summary
    :ivar status: ``open``, ``answered`` or ``closed``
    :ivar platform: The app it was asked from, if known
    :ivar created_at: When it was asked
    :ivar updated_at: The latest activity
    :ivar message_count: Messages in the thread
    :ivar preview: The start of the latest message
    :ivar requester: Who asked, within the administrator boundary
    """

    ticket_id: uuid.UUID
    subject: str
    status: Status
    platform: Platform | None
    created_at: dt.datetime
    updated_at: dt.datetime
    message_count: int
    preview: str
    requester: RequesterIdentity


@dataclass(frozen=True, slots=True)
class AdminTicketDetail:
    """A ticket and its thread, for a platform administrator.

    :ivar ticket: The ticket
    :ivar messages: Its messages, oldest first
    """

    ticket: AdminTicket
    messages: tuple[Message, ...]


@dataclass(frozen=True, slots=True)
class RequesterSummary:
    """One person's tickets, summarised for the per-user view.

    :ivar requester: Who, within the administrator boundary
    :ivar tickets: How many tickets they have opened
    :ivar open: How many wait on support
    :ivar last_activity: Their latest ticket activity
    """

    requester: RequesterIdentity
    tickets: int
    open: int
    last_activity: dt.datetime


def _not_found() -> AuthorizationError:
    """Build the one answer for a missing or unreachable ticket.

    :return: The error
    """
    return AuthorizationError(
        code=NOT_AVAILABLE, message_key="help.ticket.not_found", status=404
    )


def _clock(now: dt.datetime | None) -> dt.datetime:
    """Return the moment to record.

    :param now: An injected moment, or None
    :return: It, or the clock
    """
    return now or dt.datetime.now(tz=dt.UTC)


def _preview(body: str) -> str:
    """Cut a message to its list preview.

    :param body: The message
    :return: Its first characters, with an ellipsis when cut
    """
    text = " ".join(body.split())
    if len(text) <= PREVIEW_LENGTH:
        return text
    return text[: PREVIEW_LENGTH - 1].rstrip() + "…"


def _add_message(
    session: Session,
    ticket_id: uuid.UUID,
    author: Author,
    body: str,
    now: dt.datetime,
    author_account_id: uuid.UUID | None = None,
) -> None:
    """Append a message to a thread.

    :param session: The session to write through
    :param ticket_id: The ticket
    :param author: Who wrote it
    :param body: What was written
    :param now: When
    :param author_account_id: The administrator, for a support reply
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO help_message "
            "(id, ticket_id, author, author_account_id, body, created_at) "
            "VALUES (:id, :ticket_id, CAST(:author AS help_author), "
            ":author_account_id, :body, :now)"
        ),
        {
            "id": uuid.uuid4(),
            "ticket_id": ticket_id,
            "author": author,
            "author_account_id": author_account_id,
            "body": body,
            "now": now,
        },
    )


def _messages(session: Session, ticket_id: uuid.UUID) -> tuple[Message, ...]:
    """Read a thread, oldest first.

    :param session: The session to read through
    :param ticket_id: The ticket
    :return: Its messages
    """
    rows = session.execute(
        sa.text(
            "SELECT id, author, body, created_at FROM help_message "
            "WHERE ticket_id = :ticket_id ORDER BY created_at, id"
        ),
        {"ticket_id": ticket_id},
    )
    return tuple(
        Message(message_id=r.id, author=r.author, body=r.body, created_at=r.created_at)
        for r in rows
    )


#: The columns every ticket list reads, with the latest message and the
#: thread length folded in so a list is one statement.
_TICKET_COLUMNS: Final = (
    "t.id, t.subject, t.status, t.platform, t.created_at, t.updated_at, "
    "t.support_replied_at, t.requester_seen_at, t.requester_account_id, "
    "(SELECT m.body FROM help_message m WHERE m.ticket_id = t.id "
    " ORDER BY m.created_at DESC, m.id DESC LIMIT 1) AS latest, "
    "(SELECT count(*) FROM help_message m WHERE m.ticket_id = t.id) AS messages"
)


def _ticket(row: sa.Row[tuple[object, ...]]) -> Ticket:
    """Build the requester's view of one ticket row.

    :param row: A row selected with ``_TICKET_COLUMNS``
    :return: The ticket
    """
    replied = row.support_replied_at
    seen = row.requester_seen_at
    return Ticket(
        ticket_id=row.id,
        subject=row.subject,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        has_new_reply=replied is not None and (seen is None or seen < replied),
        preview=_preview(row.latest or ""),
    )


def open_ticket(
    session: Session,
    account_id: uuid.UUID,
    subject: str,
    body: str,
    platform: Platform | None,
    now: dt.datetime | None = None,
) -> TicketDetail:
    """Ask support a question.

    Does not commit; the route does, so the ticket and its first message
    land together.

    :param session: The session to write through
    :param account_id: The authenticated requester
    :param subject: A one-line summary, already validated
    :param body: The question, already validated
    :param platform: The app it was asked from, if the client said
    :param now: The moment, or None for the clock
    :return: The new ticket and its thread
    :raises ConflictError: The account opened too many tickets today
    """
    moment = _clock(now)
    recent = session.execute(
        sa.text(
            "SELECT count(*) FROM help_ticket "
            "WHERE requester_account_id = :account_id AND created_at > :since"
        ),
        {"account_id": account_id, "since": moment - dt.timedelta(days=1)},
    ).scalar_one()
    if recent >= MAX_TICKETS_PER_DAY:
        raise ConflictError(code="HELP_TOO_MANY", message_key="help.ticket.too_many")

    ticket_id = uuid.uuid4()
    session.execute(
        sa.text(
            "INSERT INTO help_ticket "
            "(id, requester_account_id, requester_ref, subject, status, "
            " platform, created_at, updated_at, requester_seen_at) "
            "VALUES (:id, :account_id, :ref, :subject, 'open', "
            " CAST(:platform AS client_platform), :now, :now, :now)"
        ),
        {
            "id": ticket_id,
            "account_id": account_id,
            "ref": requester_ref(account_id),
            "subject": subject,
            "platform": platform,
            "now": moment,
        },
    )
    _add_message(session, ticket_id, "requester", body, moment)
    return my_ticket(session, account_id, ticket_id, now=moment)


def my_tickets(session: Session, account_id: uuid.UUID) -> list[Ticket]:
    """List the requester's own tickets, most recently active first.

    :param session: The session to read through
    :param account_id: The authenticated requester
    :return: Their tickets
    """
    rows = session.execute(
        sa.text(
            f"SELECT {_TICKET_COLUMNS} FROM help_ticket t "  # noqa: S608  fixed column list
            "WHERE t.requester_account_id = :account_id "
            "ORDER BY t.updated_at DESC, t.id"
        ),
        {"account_id": account_id},
    )
    return [_ticket(r) for r in rows]


def my_ticket(
    session: Session,
    account_id: uuid.UUID,
    ticket_id: uuid.UUID,
    now: dt.datetime | None = None,
) -> TicketDetail:
    """Open one of the requester's own tickets, marking replies seen.

    :param session: The session to read and write through
    :param account_id: The authenticated requester
    :param ticket_id: The ticket, from the path
    :param now: The moment, or None for the clock
    :return: The ticket and its thread
    :raises AuthorizationError: 404 when it is not this requester's
    """
    seen = session.execute(
        sa.text(
            "UPDATE help_ticket SET requester_seen_at = :now "
            "WHERE id = :ticket_id AND requester_account_id = :account_id "
            "RETURNING id"
        ),
        {"ticket_id": ticket_id, "account_id": account_id, "now": _clock(now)},
    ).first()
    if seen is None:
        raise _not_found()
    row = session.execute(
        sa.text(
            f"SELECT {_TICKET_COLUMNS} FROM help_ticket t WHERE t.id = :ticket_id"  # noqa: S608  fixed column list
        ),
        {"ticket_id": ticket_id},
    ).one()
    return TicketDetail(ticket=_ticket(row), messages=_messages(session, ticket_id))


def requester_reply(
    session: Session,
    account_id: uuid.UUID,
    ticket_id: uuid.UUID,
    body: str,
    now: dt.datetime | None = None,
) -> TicketDetail:
    """Add the requester's message, reopening the ticket.

    :param session: The session to write through
    :param account_id: The authenticated requester
    :param ticket_id: The ticket, from the path
    :param body: The message, already validated
    :param now: The moment, or None for the clock
    :return: The ticket and its thread
    :raises AuthorizationError: 404 when it is not this requester's
    """
    moment = _clock(now)
    updated = session.execute(
        sa.text(
            "UPDATE help_ticket SET status = 'open', closed_at = NULL, "
            "updated_at = :now "
            "WHERE id = :ticket_id AND requester_account_id = :account_id "
            "RETURNING id"
        ),
        {"ticket_id": ticket_id, "account_id": account_id, "now": moment},
    ).first()
    if updated is None:
        raise _not_found()
    _add_message(session, ticket_id, "requester", body, moment)
    return my_ticket(session, account_id, ticket_id, now=moment)


def _admin_ticket(
    row: sa.Row[tuple[object, ...]], who: dict[uuid.UUID, RequesterIdentity]
) -> AdminTicket:
    """Build the administrator's view of one ticket row.

    :param row: A row selected with ``_TICKET_COLUMNS``
    :param who: Identities for the rows' requesters
    :return: The ticket
    """
    return AdminTicket(
        ticket_id=row.id,
        subject=row.subject,
        status=row.status,
        platform=row.platform,
        created_at=row.created_at,
        updated_at=row.updated_at,
        message_count=row.messages,
        preview=_preview(row.latest or ""),
        requester=who[row.requester_account_id],
    )


def admin_tickets(
    session: Session,
    status: Status | None = None,
    ref: str | None = None,
    limit: int = ADMIN_PAGE_LIMIT,
) -> list[AdminTicket]:
    """List tickets for an administrator, waiting-on-support first.

    :param session: The session to read through
    :param status: Only this status, or None for all
    :param ref: Only this requester's tickets, by opaque label
    :param limit: At most this many, capped at ``ADMIN_PAGE_LIMIT``
    :return: The tickets
    """
    rows = session.execute(
        sa.text(
            f"SELECT {_TICKET_COLUMNS} FROM help_ticket t "  # noqa: S608  fixed column list
            "WHERE (CAST(:status AS help_ticket_status) IS NULL "
            "       OR t.status = CAST(:status AS help_ticket_status)) "
            "AND (CAST(:ref AS text) IS NULL OR t.requester_ref = :ref) "
            "ORDER BY (t.status = 'open') DESC, t.updated_at DESC, t.id "
            "LIMIT :limit"
        ),
        {
            "status": status,
            "ref": ref.upper() if ref else None,
            "limit": max(1, min(limit, ADMIN_PAGE_LIMIT)),
        },
    ).all()
    who = identities(session, (r.requester_account_id for r in rows))
    return [_admin_ticket(r, who) for r in rows]


def admin_ticket(session: Session, ticket_id: uuid.UUID) -> AdminTicketDetail:
    """Open any ticket for an administrator.

    Opening it does not mark it seen by the requester or change it.

    :param session: The session to read through
    :param ticket_id: The ticket, from the path
    :return: The ticket and its thread
    :raises AuthorizationError: 404 when no such ticket exists
    """
    row = session.execute(
        sa.text(
            f"SELECT {_TICKET_COLUMNS} FROM help_ticket t WHERE t.id = :ticket_id"  # noqa: S608  fixed column list
        ),
        {"ticket_id": ticket_id},
    ).first()
    if row is None:
        raise _not_found()
    who = identities(session, [row.requester_account_id])
    return AdminTicketDetail(
        ticket=_admin_ticket(row, who), messages=_messages(session, ticket_id)
    )


def support_reply(
    session: Session,
    admin_account_id: uuid.UUID,
    ticket_id: uuid.UUID,
    body: str,
    now: dt.datetime | None = None,
) -> AdminTicketDetail:
    """Answer a ticket as ShikkhokPlus support.

    :param session: The session to write through
    :param admin_account_id: The administrator, recorded on the message
    :param ticket_id: The ticket, from the path
    :param body: The reply, already validated
    :param now: The moment, or None for the clock
    :return: The ticket and its thread
    :raises AuthorizationError: 404 when no such ticket exists
    """
    moment = _clock(now)
    updated = session.execute(
        sa.text(
            "UPDATE help_ticket SET status = 'answered', closed_at = NULL, "
            "updated_at = :now, support_replied_at = :now "
            "WHERE id = :ticket_id RETURNING id"
        ),
        {"ticket_id": ticket_id, "now": moment},
    ).first()
    if updated is None:
        raise _not_found()
    _add_message(
        session, ticket_id, "support", body, moment, author_account_id=admin_account_id
    )
    return admin_ticket(session, ticket_id)


def set_status(
    session: Session,
    ticket_id: uuid.UUID,
    status: Literal["open", "closed"],
    now: dt.datetime | None = None,
) -> AdminTicketDetail:
    """Close a ticket, or reopen it, as an administrator.

    :param session: The session to write through
    :param ticket_id: The ticket, from the path
    :param status: ``closed`` to close it, ``open`` to reopen it
    :param now: The moment, or None for the clock
    :return: The ticket and its thread
    :raises AuthorizationError: 404 when no such ticket exists
    """
    moment = _clock(now)
    updated = session.execute(
        sa.text(
            "UPDATE help_ticket SET status = CAST(:status AS help_ticket_status), "
            "closed_at = CASE WHEN :status = 'closed' THEN :now END, "
            "updated_at = :now WHERE id = :ticket_id RETURNING id"
        ),
        {"ticket_id": ticket_id, "status": status, "now": moment},
    ).first()
    if updated is None:
        raise _not_found()
    return admin_ticket(session, ticket_id)


def requesters(session: Session) -> list[RequesterSummary]:
    """Summarise tickets per person, for the per-user view.

    :param session: The session to read through
    :return: One row per person who has asked, latest activity first
    """
    rows = session.execute(
        sa.text(
            "SELECT requester_account_id, count(*) AS tickets, "
            "count(*) FILTER (WHERE status = 'open') AS open, "
            "max(updated_at) AS last_activity "
            "FROM help_ticket GROUP BY requester_account_id "
            "ORDER BY max(updated_at) DESC LIMIT :limit"
        ),
        {"limit": ADMIN_PAGE_LIMIT},
    ).all()
    who = identities(session, (r.requester_account_id for r in rows))
    return [
        RequesterSummary(
            requester=who[r.requester_account_id],
            tickets=r.tickets,
            open=r.open,
            last_activity=r.last_activity,
        )
        for r in rows
    ]
