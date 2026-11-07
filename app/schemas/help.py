"""The help centre on the wire, as its requester sees it.

Addressed to the requester themselves: their own questions and the
answers to them. A support reply is signed ``support`` and never names
the administrator who wrote it.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

__all__ = [
    "HelpBody",
    "HelpMessageResponse",
    "HelpReplyRequest",
    "HelpSubject",
    "HelpTicketDetailResponse",
    "HelpTicketListResponse",
    "HelpTicketRequest",
    "HelpTicketResponse",
]

#: A one-line summary. Whitespace is trimmed before the length check, so
#: a subject of only spaces is refused rather than stored blank.
HelpSubject = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]

#: A message: up to 4000 characters, the database's own limit.
HelpBody = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]


class HelpTicketRequest(BaseModel):
    """Ask support a question.

    :ivar subject: A one-line summary
    :ivar body: The question
    """

    model_config = ConfigDict(extra="forbid")

    subject: HelpSubject
    body: HelpBody


class HelpReplyRequest(BaseModel):
    """Add a message to a thread.

    :ivar body: The message
    """

    model_config = ConfigDict(extra="forbid")

    body: HelpBody


class HelpMessageResponse(BaseModel):
    """One message in a thread.

    :ivar message_id: The message
    :ivar author: ``requester`` for the asker, ``support`` for ShikkhokPlus
    :ivar body: What was written
    :ivar created_at: When
    """

    model_config = ConfigDict(extra="forbid")

    message_id: uuid.UUID
    author: Literal["requester", "support"]
    body: str
    created_at: dt.datetime


class HelpTicketResponse(BaseModel):
    """One of the requester's tickets.

    :ivar ticket_id: The ticket
    :ivar subject: The one-line summary
    :ivar status: ``open`` (with support), ``answered`` (support replied),
        or ``closed``
    :ivar created_at: When it was asked
    :ivar updated_at: The latest activity
    :ivar has_new_reply: Support replied since the requester last opened it
    :ivar preview: The start of the latest message
    """

    model_config = ConfigDict(extra="forbid")

    ticket_id: uuid.UUID
    subject: str
    status: Literal["open", "answered", "closed"]
    created_at: dt.datetime
    updated_at: dt.datetime
    has_new_reply: bool
    preview: str


class HelpTicketListResponse(BaseModel):
    """The requester's tickets, most recently active first.

    :ivar tickets: The tickets
    :ivar new_replies: How many carry a reply not yet seen
    """

    model_config = ConfigDict(extra="forbid")

    tickets: list[HelpTicketResponse]
    new_replies: int


class HelpTicketDetailResponse(BaseModel):
    """A ticket and its whole thread.

    :ivar ticket: The ticket
    :ivar messages: Its messages, oldest first
    """

    model_config = ConfigDict(extra="forbid")

    ticket: HelpTicketResponse
    messages: list[HelpMessageResponse]
