"""The in-app inbox on the wire.

Addressed to the reader themselves, so it carries the batch name and the
amount owed -- facts about their own seat -- and nothing about anyone
else.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import MoneyField

__all__ = ["InboxResponse", "NotificationResponse"]


class NotificationResponse(BaseModel):
    """One message in the reader's own inbox.

    :ivar notification_id: The message
    :ivar kind: What produced it
    :ivar enrollment_id: The seat it is about, if any
    :ivar batch_name: The batch, as named when it was sent
    :ivar period: The period it concerns, as ``YYYY-MM``, if any
    :ivar amount: The money it concerns, if any
    :ivar created_at: When it was sent
    :ivar read: Whether the reader has opened the inbox since
    """

    model_config = ConfigDict(extra="forbid")

    notification_id: uuid.UUID
    kind: Literal["fee_reminder"]
    enrollment_id: uuid.UUID | None = None
    batch_name: str
    period: str | None = Field(default=None, pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    amount: MoneyField | None = None
    created_at: dt.datetime
    read: bool


class InboxResponse(BaseModel):
    """The reader's inbox, newest first.

    :ivar items: The messages
    :ivar unread: How many have not been seen, over the whole inbox
    """

    model_config = ConfigDict(extra="forbid")

    items: list[NotificationResponse] = Field(default_factory=list)
    unread: int = Field(ge=0)
