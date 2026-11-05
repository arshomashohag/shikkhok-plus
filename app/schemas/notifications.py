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

__all__ = [
    "ExamBlock",
    "InboxResponse",
    "NoticeBlock",
    "NotificationDetailResponse",
    "NotificationResponse",
    "PaymentBlock",
]


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
    :ivar source_id: The record that produced it, if any
    :ivar child_name: Which child it is about, for a guardian's copy
    :ivar preview: A short line of its content, if any
    """

    model_config = ConfigDict(extra="forbid")

    notification_id: uuid.UUID
    kind: Literal[
        "fee_reminder",
        "payment_approved",
        "payment_partial",
        "payment_rejected",
        "payment_recorded",
        "notice",
        "exam_scheduled",
        "marks_available",
        "claim_to_verify",
    ]
    enrollment_id: uuid.UUID | None = None
    batch_name: str
    period: str | None = Field(default=None, pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    amount: MoneyField | None = None
    created_at: dt.datetime
    read: bool
    source_id: uuid.UUID | None = None
    child_name: str | None = None
    preview: str | None = None


class InboxResponse(BaseModel):
    """The reader's inbox, newest first.

    :ivar items: The messages
    :ivar unread: How many have not been seen, over the whole inbox
    """

    model_config = ConfigDict(extra="forbid")

    items: list[NotificationResponse] = Field(default_factory=list)
    unread: int = Field(ge=0)


class NoticeBlock(BaseModel):
    """A notice as it reads now.

    :ivar body: The current text
    :ivar posted_at: When it was posted
    :ivar edited_at: When it was last edited, if ever
    """

    model_config = ConfigDict(extra="forbid")

    body: str
    posted_at: dt.datetime
    edited_at: dt.datetime | None = None


class ExamBlock(BaseModel):
    """An exam as it stands now.

    :ivar exam_id: The exam
    :ivar title: The teacher's name for it
    :ivar date: When it is held
    :ivar subject_name: The subject
    :ivar total_marks: The denominator
    :ivar topics: What it covers
    """

    model_config = ConfigDict(extra="forbid")

    exam_id: uuid.UUID
    title: str
    date: dt.date
    subject_name: str
    total_marks: int
    topics: list[str]


class PaymentBlock(BaseModel):
    """A payment claim and how it was decided.

    :ivar claim_id: The claim
    :ivar period: The period it paid toward, as ``YYYY-MM``
    :ivar claimed: What was claimed
    :ivar approved: What the teacher accepted, once decided
    :ivar outcome: Where the decision stands
    :ivar reason: Why it was rejected, if it was
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: uuid.UUID
    period: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    claimed: MoneyField
    approved: MoneyField | None = None
    outcome: Literal["approved", "partial", "rejected", "pending"]
    reason: str | None = None


class NotificationDetailResponse(NotificationResponse):
    """One message and what it opens to, as its source stands now.

    :ivar available: False once the source is gone or the seat unreachable
    :ivar notice: Set for an available notice
    :ivar exam: Set for an available exam
    :ivar payment: Set for an available payment result
    """

    available: bool
    notice: NoticeBlock | None = None
    exam: ExamBlock | None = None
    payment: PaymentBlock | None = None
