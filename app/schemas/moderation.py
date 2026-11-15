"""Wire shapes for hub reports and the administrator's moderation routes.

**No reporter identity crosses the admin boundary.** A queue item carries only
``reporter_ref``, the opaque label from :mod:`app.help.identity`; there is no
phone, name or account id field here to leak.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.moderation.vocab import Reason, TargetKind

__all__ = [
    "AdminHubDecisionRequest",
    "AdminHubQueueItem",
    "AdminHubQueueResponse",
    "AdminHubReportDecided",
    "AdminHubSuspensionRequest",
    "AdminHubSuspensionState",
    "HubReportRequest",
]


class HubReportRequest(BaseModel):
    """A reader's report about one hub target.

    :ivar target_kind: ``listing``, ``media``, ``review`` or ``reply``
    :ivar target_id: The target's id
    :ivar reason: A closed reason
    :ivar note: An optional note; it may not carry a phone number
    """

    model_config = ConfigDict(extra="forbid")

    target_kind: TargetKind
    target_id: uuid.UUID
    reason: Reason
    note: str | None = Field(default=None, max_length=500)


class AdminHubQueueItem(BaseModel):
    """One row of the moderation queue.

    :ivar kind: ``report`` or ``listing``
    :ivar report_id: The report, for a report row
    :ivar target_kind: What was reported or suspended
    :ivar target_id: The target's id
    :ivar owner_id: The owner the listing belongs to, when known
    :ivar title: The target's public name
    :ivar text: The target's public text
    :ivar reason: The report reason or the suspension reason code
    :ivar note: The reporter's note, for a report row
    :ivar reporter_ref: The opaque reporter label, for a report row
    :ivar waited_hours: Whole hours since the report or the suspension
    """

    kind: Literal["report", "listing"]
    report_id: uuid.UUID | None
    target_kind: str
    target_id: uuid.UUID
    owner_id: uuid.UUID | None
    title: str | None
    text: str | None
    reason: str | None
    note: str | None
    reporter_ref: str | None
    waited_hours: int


class AdminHubQueueResponse(BaseModel):
    """The moderation queue, oldest first.

    :ivar kind: Which queue this is
    :ivar items: Its rows
    """

    kind: Literal["report", "listing"]
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
