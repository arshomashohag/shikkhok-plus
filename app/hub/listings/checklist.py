"""What an owner's listing still needs before it can be published."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.db.models import OwnerListing

__all__ = ["ChecklistItem", "owner_checklist", "owner_publishable"]


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
