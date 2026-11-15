"""The closed vocabularies moderation shares.

One reason set for reports and for suspensions, so a suspension's code reads
as the report reason that prompted it.
"""

from __future__ import annotations

from typing import Final, Literal

__all__ = ["REASONS", "TARGET_KINDS", "Reason", "TargetKind"]

Reason = Literal[
    "personal_info", "child_safety", "abusive", "fake", "misleading", "other"
]
TargetKind = Literal["owner_listing", "batch_listing", "media", "review", "reply"]

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
