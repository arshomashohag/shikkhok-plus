"""What an owner's listing still needs before it can be published."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from app.db.models import BatchListing, OwnerListing

__all__ = [
    "BATCH_REQUIRED",
    "ChecklistItem",
    "batch_checklist",
    "owner_checklist",
    "owner_publishable",
]


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    """One requirement and whether the listing meets it.

    :ivar key: The requirement's stable name
    :ivar done: Whether it is met
    """

    key: str
    done: bool


def _filled(value: str | None) -> bool:
    """Say whether a text value holds anything but whitespace.

    :param value: The value
    :return: True when it has content
    """
    return value is not None and value.strip() != ""


#: The fewest characters a batch's public title may have, as the database
#: checks it (``ck_batch_listing_public_title_when_live``).
TITLE_MIN: Final = 3


def _titled(value: str | None) -> bool:
    """Say whether a public title is long enough to publish under.

    :param value: The title
    :return: True when it has at least :data:`TITLE_MIN` characters once
        trimmed
    """
    return value is not None and len(value.strip()) >= TITLE_MIN


def owner_checklist(listing: OwnerListing) -> list[ChecklistItem]:
    """List the six requirements in their fixed order.

    ``contact_or_none`` is always met: a public phone is optional and the
    listing has no separate marker for choosing none, so having no number is
    itself a complete answer.

    :param listing: The owner's listing
    :return: The checklist items
    """
    return [
        ChecklistItem("public_name", _filled(listing.public_name)),
        ChecklistItem("slug", _filled(listing.slug)),
        ChecklistItem("area", _filled(listing.district_code)),
        ChecklistItem(
            "headline", _filled(listing.headline_en) or _filled(listing.headline_bn)
        ),
        ChecklistItem("bio", _filled(listing.bio_en) or _filled(listing.bio_bn)),
        ChecklistItem("contact_or_none", True),
    ]


def owner_publishable(items: Iterable[ChecklistItem]) -> bool:
    """Say whether every item is met.

    :param items: The checklist
    :return: True when nothing is missing
    """
    return all(item.done for item in items)


#: The batch checklist keys that block publishing, in order: every item.
BATCH_REQUIRED: tuple[str, ...] = (
    "public_title",
    "slug",
    "description",
    "class_levels",
    "subjects",
    "mode",
)


def batch_checklist(
    listing: BatchListing | None, subject_count: int
) -> list[ChecklistItem]:
    """List the requirements of one batch listing in their fixed order.

    :param listing: The batch listing, or None when none exists yet
    :param subject_count: How many subjects the batch has
    :return: The checklist items
    """
    if listing is None:
        return [
            ChecklistItem("public_title", False),
            ChecklistItem("slug", False),
            ChecklistItem("description", False),
            ChecklistItem("class_levels", False),
            ChecklistItem("subjects", subject_count > 0),
            ChecklistItem("mode", False),
        ]
    return [
        ChecklistItem("public_title", _titled(listing.public_title)),
        ChecklistItem("slug", _filled(listing.slug)),
        ChecklistItem(
            "description",
            _filled(listing.description_en) or _filled(listing.description_bn),
        ),
        ChecklistItem("class_levels", len(listing.class_levels) > 0),
        ChecklistItem("subjects", subject_count > 0),
        ChecklistItem("mode", listing.mode is not None),
    ]
