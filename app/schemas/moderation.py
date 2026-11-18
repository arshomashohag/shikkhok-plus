"""Wire shapes for hub reports and the administrator's moderation routes.

**No reporter identity crosses the admin boundary.** A queue item carries only
``reporter_ref``, the opaque label from :mod:`app.help.identity`; there is no
phone, name or account id field here to leak.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.moderation.vocab import MediaRejectionCode, Reason, TargetKind

__all__ = [
    "AdminHubDecisionRequest",
    "AdminHubField",
    "AdminHubMediaDecided",
    "AdminHubMediaDecisionRequest",
    "AdminHubMediaDetail",
    "AdminHubMediaPreview",
    "AdminHubQueueItem",
    "AdminHubQueueResponse",
    "AdminHubReportDecided",
    "AdminHubSuspensionRequest",
    "AdminHubSuspensionState",
    "HubReportRequest",
]


class HubReportRequest(BaseModel):
    """A reader's report about one hub target.

    :ivar target_kind: ``owner_listing``, ``batch_listing``, ``media``,
        ``review`` or ``reply``
    :ivar target_id: The target's id: an owner id for an owner listing, a
        batch id for a batch listing, a media id for a photo
    :ivar reason: A closed reason
    :ivar note: An optional note; it may not carry a phone number
    """

    model_config = ConfigDict(extra="forbid")

    target_kind: TargetKind
    target_id: uuid.UUID
    reason: Reason
    note: str | None = Field(default=None, max_length=500)


#: Every field a queue item may show; each is something an owner submitted
#: for display on the hub, never anything a teacher keeps privately.
AdminHubFieldKey = Literal[
    "public_name",
    "headline_en",
    "headline_bn",
    "bio_en",
    "bio_bn",
    "qualifications",
    "street_address",
    "public_contact_phone",
    "area_en",
    "area_bn",
    "public_title",
    "description_en",
    "description_bn",
    "syllabus_en",
    "syllabus_bn",
    "subject_tags",
    "alt_en",
    "alt_bn",
]

#: Which queue: open reports, suspended listings, or photos to decide.
AdminHubQueueKind = Literal["report", "listing", "media"]


class AdminHubField(BaseModel):
    """One submitted public field of a moderated target.

    :ivar key: Which field
    :ivar value: What the owner submitted
    """

    key: AdminHubFieldKey
    value: str


class AdminHubQueueItem(BaseModel):
    """One row of the moderation queue.

    :ivar kind: ``report``, ``listing`` or ``media``
    :ivar report_id: The report, for a report row
    :ivar target_kind: What was reported or suspended
    :ivar target_id: The target's id
    :ivar owner_id: The owner the listing belongs to, when known
    :ivar title: The target's public name: an owner's public name or a
        batch's public title
    :ivar fields: Everything the owner submitted for display on the target
    :ivar reason: The report reason, the suspension reason code, or why a
        held photo was held; None for a photo waiting for review
    :ivar note: The reporter's note, for a report row
    :ivar reporter_ref: The opaque reporter label, for a report row
    :ivar waited_hours: Whole hours since the report, the suspension, the
        hold or the upload
    """

    kind: AdminHubQueueKind
    report_id: uuid.UUID | None
    target_kind: str
    target_id: uuid.UUID
    owner_id: uuid.UUID | None
    title: str | None
    fields: list[AdminHubField]
    reason: str | None
    note: str | None
    reporter_ref: str | None
    waited_hours: int


class AdminHubQueueResponse(BaseModel):
    """The moderation queue, oldest first.

    :ivar kind: Which queue this is
    :ivar items: Its rows
    """

    kind: AdminHubQueueKind
    items: list[AdminHubQueueItem]


class AdminHubDecisionRequest(BaseModel):
    """An administrator's decision on a report.

    :ivar decision: ``upheld`` or ``dismissed``
    """

    model_config = ConfigDict(extra="forbid")

    decision: Literal["upheld", "dismissed"]


class AdminHubSuspensionRequest(BaseModel):
    """Suspend or restore an owner's listing.

    :ivar suspended: True to suspend, False to lift
    :ivar reason_code: A closed reason
    """

    model_config = ConfigDict(extra="forbid")

    suspended: bool
    reason_code: Reason


class AdminHubReportDecided(BaseModel):
    """A report after its decision.

    :ivar report_id: The report
    :ivar status: ``upheld`` or ``dismissed``
    """

    report_id: uuid.UUID
    status: Literal["upheld", "dismissed"]


class AdminHubSuspensionState(BaseModel):
    """An owner's listing after a suspension change.

    :ivar owner_id: The owner
    :ivar suspended: Whether the listing is suspended now
    """

    owner_id: uuid.UUID
    suspended: bool


class AdminHubMediaPreview(BaseModel):
    """One variant of a photo, signed for a five-minute look.

    :ivar width: The variant's width in pixels
    :ivar url: A signed GET of the variant in the photo bucket
    """

    width: int
    url: str


class AdminHubMediaDetail(BaseModel):
    """One photo as an administrator reviews it.

    Names the page it is for -- the owner's public name, the batch's public
    title -- and nothing about the account that uploaded it.

    :ivar media_id: The photo
    :ivar status: ``pending_review``, ``held`` or ``approved``
    :ivar width: The decoded width in pixels
    :ivar height: The decoded height in pixels
    :ivar previews: One signed URL per variant, narrowest first
    :ivar alt_en: English alt text
    :ivar alt_bn: Bangla alt text
    :ivar public_name: The owner listing's public name
    :ivar public_title: The batch listing's public title, for a batch photo
    :ivar report_count: How many reports name this photo
    """

    media_id: uuid.UUID
    status: Literal["pending_review", "held", "approved"]
    width: int | None
    height: int | None
    previews: list[AdminHubMediaPreview]
    alt_en: str | None
    alt_bn: str | None
    public_name: str | None
    public_title: str | None
    report_count: int


class AdminHubMediaDecisionRequest(BaseModel):
    """An administrator's decision on a photo.

    :ivar decision: ``approve`` or ``reject``
    :ivar code: Why, for a rejection; omitted for an approval
    """

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    code: MediaRejectionCode | None = None


class AdminHubMediaDecided(BaseModel):
    """A photo after its decision.

    :ivar media_id: The photo
    :ivar status: ``approved`` or ``rejected``
    """

    media_id: uuid.UUID
    status: Literal["approved", "rejected"]
