"""Request and response bodies for guardian reviews [H4].

**Nothing here says who wrote a review, or when to the day** [spec §8].
A review carries a rating, its words, a tenure bucket and a month: never
an account, a seat, a name or a timestamp. The author's own state carries
no seat and no exact time either -- the edit window is sent as the last
day an edit is accepted, not as the moment of the first submit [T3-e,
T4-b]. ``tests/contract/test_review_privacy.py`` walks every review route's
response against :data:`~app.contract.privacy.REVIEW_FORBIDDEN_FIELDS`.

**Months are** ``YYYY-MM`` **strings**, rendered by the routes from the
first of the month the database stores, so no client is handed a day it
could show. The routes also render the average [F13], so no client formats
a business figure.

**Text is bounded after stripping** [F14]: the schema strips surrounding
whitespace before it counts, so a blank reply is the standard validation
error and a padded 1000-character body is accepted, as the services count.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.reviews.authoring import MAX_BODY, ReviewStatus
from app.reviews.eligibility import Standing, Tenure, WaitingOn
from app.reviews.owner import MAX_REPLY

__all__ = [
    "MyReviewBody",
    "MyReviewResponse",
    "OwnerBatchRatingWire",
    "OwnerReviewWire",
    "OwnerReviewsResponse",
    "ReplyStatus",
    "ReplyWrite",
    "ReviewWrite",
    "ReviewableBatch",
    "ReviewableState",
]

#: What the reviewable list says of a batch.
ReviewableState = Literal["eligible", "not_yet", "reviewed"]

#: A reply's statuses; a reply publishes on approval, so no ``approved``.
ReplyStatus = Literal["pending", "published", "rejected", "removed", "held"]

#: A month as the wire carries it.
_MONTH: Final = r"^\d{4}-(0[1-9]|1[0-2])$"


class ReviewWrite(BaseModel):
    """Write or edit the caller's review of a batch.

    :ivar rating: 1 to 5
    :ivar body: Optional words, at most 1000 characters once stripped; a
        blank body is stored as none
    """

    model_config = ConfigDict(extra="forbid")

    rating: int = Field(ge=1, le=5)
    body: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_BODY)]
        | None
    ) = None


class ReplyWrite(BaseModel):
    """Write or replace the owner's reply to a review.

    :ivar body: 1 to 1000 characters once stripped
    """

    model_config = ConfigDict(extra="forbid")

    body: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_REPLY),
    ]


class ReviewableBatch(BaseModel):
    """One batch the caller may review, is waiting to, or has reviewed.

    :ivar batch_id: The batch
    :ivar batch_title: Its public title
    :ivar owner_public_name: Its owner's public name
    :ivar state: ``eligible``, ``not_yet``, or ``reviewed`` once the caller
        wrote a review, whatever their standing now
    :ivar eligible_from: The day a ``not_yet`` caller's tenure is met,
        sent only when tenure alone is unmet [FR-c]; None otherwise
    """

    batch_id: uuid.UUID
    batch_title: str
    owner_public_name: str
    state: ReviewableState
    eligible_from: dt.date | None


class MyReviewBody(BaseModel):
    """The caller's own review, as its author sees it.

    :ivar rating: 1 to 5
    :ivar body: The words, or None
    :ivar status: Where it is in moderation
    :ivar rejection_code: Why it was rejected or removed
    :ivar tenure: The tenure bucket frozen at the first submit
    :ivar published_month: ``YYYY-MM`` once published, else None
    :ivar reply_body: The owner's reply while it is published
    """

    rating: int
    body: str | None
    status: ReviewStatus
    rejection_code: str | None
    tenure: Tenure
    published_month: str | None = Field(pattern=_MONTH)
    reply_body: str | None


class MyReviewResponse(BaseModel):
    """Where the caller stands with one batch's review.

    :ivar standing: ``eligible``, ``not_yet``, ``closed`` or ``author_only``
    :ivar waiting_on: What a ``not_yet`` caller still needs
    :ivar eligible_from: The day a ``not_yet`` caller's tenure is met,
        sent only when tenure alone is unmet [FR-c]: never while classes
        are also needed, nor on a closed window [T3-b]
    :ivar can_write: Whether a write now would be accepted
    :ivar edit_until: The last day, in Bangladesh, an edit is accepted
    :ivar review: The caller's review, or None
    """

    standing: Standing
    waiting_on: WaitingOn | None
    eligible_from: dt.date | None
    can_write: bool
    edit_until: dt.date | None
    review: MyReviewBody | None


class OwnerBatchRatingWire(BaseModel):
    """One of the owner's published batches, with its rating over the threshold.

    Below three published reviews every figure is None, the count included
    [T2-a]: such a batch reads exactly like one nobody has reviewed.

    :ivar batch_id: The batch
    :ivar batch_title: Its public title
    :ivar review_count: Published reviews, or None below the threshold
    :ivar average_tenths: The average in tenths (43 is 4.3), or None
    :ivar average_label: The average as shown, ``"4.3"``, or None;
        clients show this and never format ``average_tenths`` [F13]. Not
        named ``*_display``: that suffix is reserved for the rendering of a
        money amount, and the money gate refuses one without its amount
    :ivar distribution: Reviews per star from one to five, or None
    """

    batch_id: uuid.UUID
    batch_title: str | None
    review_count: int | None
    average_tenths: int | None
    average_label: str | None
    distribution: list[int] | None


class OwnerReviewWire(BaseModel):
    """One published review of the owner's batch, with the owner's reply.

    :ivar id: The review, to reply to
    :ivar batch_id: The batch
    :ivar rating: 1 to 5
    :ivar body: The words, or None
    :ivar tenure: The author's tenure bucket
    :ivar published_month: ``YYYY-MM``
    :ivar reply_body: The reply as the public sees it, while published
    :ivar reply_month: ``YYYY-MM`` the reply was published in, or None
    :ivar my_reply_status: The owner's reply's status, or None without one
    :ivar my_reply_body: The owner's reply's words in any status
    :ivar my_reply_rejection_code: Why the reply was rejected or removed
    """

    id: uuid.UUID
    batch_id: uuid.UUID
    rating: int
    body: str | None
    tenure: Tenure
    published_month: str = Field(pattern=_MONTH)
    reply_body: str | None
    reply_month: str | None = Field(pattern=_MONTH)
    my_reply_status: ReplyStatus | None
    my_reply_body: str | None
    my_reply_rejection_code: str | None


class OwnerReviewsResponse(BaseModel):
    """The owner's published batches' ratings and their reviews.

    :ivar batches: One row per published batch listing, reviewed or not
    :ivar reviews: Published reviews over the threshold, newest month first
    """

    batches: list[OwnerBatchRatingWire]
    reviews: list[OwnerReviewWire]
