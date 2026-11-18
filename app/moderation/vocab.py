"""The closed vocabularies moderation shares.

One reason set for reports and for suspensions, so a suspension's code reads
as the report reason that prompted it. A photo has its own rejection codes,
and two of the report reasons hold a reported photo at once.
"""

from __future__ import annotations

from typing import Final, Literal

__all__ = [
    "HOLD_REASONS",
    "MEDIA_REJECTION_CODES",
    "REASONS",
    "REPORT_REJECTION_CODES",
    "TARGET_KINDS",
    "MediaRejectionCode",
    "Reason",
    "TargetKind",
]

Reason = Literal[
    "personal_info", "child_safety", "abusive", "fake", "misleading", "other"
]
TargetKind = Literal["owner_listing", "batch_listing", "media", "review", "reply"]
MediaRejectionCode = Literal[
    "identifiable_child", "personal_info", "not_relevant", "low_quality", "other"
]

#: Every reason a report or a suspension may carry.
REASONS: Final[tuple[str, ...]] = (
    "personal_info",
    "child_safety",
    "abusive",
    "fake",
    "misleading",
    "other",
)

#: Every report target kind.
TARGET_KINDS: Final[tuple[str, ...]] = (
    "owner_listing",
    "batch_listing",
    "media",
    "review",
    "reply",
)

#: Why an administrator may reject a photo.
MEDIA_REJECTION_CODES: Final[tuple[str, ...]] = (
    "identifiable_child",
    "personal_info",
    "not_relevant",
    "low_quality",
    "other",
)

#: The report reasons that take a reported photo down before any admin acts
#: [H3 deviation 2]: the harm of leaving it up outweighs a wrongful hold.
HOLD_REASONS: Final[frozenset[str]] = frozenset({"child_safety", "personal_info"})

#: The rejection code an upheld photo report records, by report reason
#: [R11]; any reason not named here records ``other``.
REPORT_REJECTION_CODES: Final[dict[str, str]] = {
    "child_safety": "identifiable_child",
    "personal_info": "personal_info",
}
