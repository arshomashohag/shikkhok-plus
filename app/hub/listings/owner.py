"""An owner's own public listing: draft, edit, consent, publish, hide.

**Nothing here makes a listing public except** :func:`publish`, which needs
the current consent text, a complete listing and a listing no moderator has
suspended. A draft is created silently and stays a draft, so an owner who
never opens the hub is never listed [Review Focus 1].
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.accounts.phone import canonical_phone, contains_phone
from app.authz.lenses import TeacherLens
from app.db.models import OwnerListing
from app.errors import ConflictError, ValidationError
from app.hub.listings.checklist import owner_checklist
from app.hub.listings.consent import HUB_CONSENT_VERSION

__all__ = [
    "OwnerListingUpdate",
    "get_or_draft",
    "publish",
    "slug_available",
    "unpublish",
    "update",
]

_SLUG: Final = re.compile(r"[a-z0-9-]{3,60}")

#: The owner's own free-text columns, which may not carry a phone number.
_FREE_TEXT: Final = (
    "public_name",
    "headline_en",
    "headline_bn",
    "bio_en",
    "bio_bn",
    "qualifications",
    "street_address",
)

#: Nullable text columns, where an empty string clears the value.
_CLEARABLE: Final = frozenset(_FREE_TEXT) - {"public_name"}

_PREFILL_NAME: Final = sa.text(
    "SELECT CASE WHEN o.kind = 'organisation' THEN o.name ELSE "
    "(SELECT b.teacher_display_name FROM batch b WHERE b.owner_id = o.id "
    "AND b.teacher_display_name IS NOT NULL "
    "AND length(trim(b.teacher_display_name)) > 0 "
    "ORDER BY b.created_at, b.id LIMIT 1) END FROM owner o WHERE o.id = :owner"
)


@dataclass(frozen=True, slots=True)
class OwnerListingUpdate:
    """The columns an owner may edit; ``None`` leaves a column unchanged.

    An empty string clears a nullable text column.

    :ivar slug: The public path segment
    :ivar public_name: The name shown publicly
    :ivar headline_en: The English headline
    :ivar headline_bn: The Bangla headline
    :ivar bio_en: The English biography
    :ivar bio_bn: The Bangla biography
    :ivar qualifications: Qualifications
    :ivar teaching_mode: Teaching modes
    :ivar district_code: The district
    :ivar upazila_code: The upazila, which must lie in the district
    :ivar street_address: A centre's street address
    :ivar public_contact_phone: The one public phone number
    """

    slug: str | None = None
    public_name: str | None = None
    headline_en: str | None = None
    headline_bn: str | None = None
    bio_en: str | None = None
    bio_bn: str | None = None
    qualifications: str | None = None
    teaching_mode: list[str] | None = None
    district_code: str | None = None
    upazila_code: str | None = None
    street_address: str | None = None
    public_contact_phone: str | None = None


def _load(session: Session, lens: TeacherLens) -> OwnerListing:
    """Read the owner's listing, locking it against a concurrent edit.

    :param session: The session
    :param lens: The owner's lens
    :return: The listing, created if absent
    """
    listing = session.execute(
        sa.select(OwnerListing)
        .where(OwnerListing.owner_id == lens.owner_id)
        .with_for_update()
    ).scalar_one_or_none()
    return listing if listing is not None else get_or_draft(session, lens)


def _refuse_suspended(listing: OwnerListing) -> None:
    """Refuse any owner action on a suspended listing.

    :param listing: The listing
    :raises ConflictError: It is suspended
    """
    if listing.status == "suspended":
        raise ConflictError(
            code="HUB_LISTING_SUSPENDED", message_key="hub.listing_suspended"
        )


def get_or_draft(session: Session, lens: TeacherLens) -> OwnerListing:
    """Return the owner's listing, creating a draft on first call.

    The draft's name comes from the centre's name, or a solo tutor's first
    non-blank batch display name; it never reads ``profile``.

    :param session: The session
    :param lens: The owner's lens
    :return: The listing
    """
    session.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, public_name) "
            "VALUES (:owner, coalesce(("
            + str(_PREFILL_NAME)
            + "), '')) ON CONFLICT (owner_id) DO NOTHING"
        ),
        {"owner": lens.owner_id},
    )
    listing = session.execute(
        sa.select(OwnerListing)
        .where(OwnerListing.owner_id == lens.owner_id)
        .execution_options(populate_existing=True)
    ).scalar_one()
    session.commit()
    return listing


def slug_available(session: Session, slug: str, lens: TeacherLens) -> bool:
    """Say whether this owner may claim a slug.

    :param session: The session
    :param slug: The wanted slug
    :param lens: The asking owner
    :return: True when it is well formed and nobody else holds it
    """
    if not _SLUG.fullmatch(slug):
        return False
    taken = session.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM owner_listing "
            "WHERE slug = :slug AND owner_id <> :owner)"
        ),
        {"slug": slug, "owner": lens.owner_id},
    ).scalar_one()
    return not taken


def _check_area(session: Session, district: str | None, upazila: str | None) -> None:
    """Check the area codes name real, nested areas.

    :param session: The session
    :param district: The district code, if any
    :param upazila: The upazila code, if any
    :raises ValidationError: An area is unknown or not nested
    """
    if district is None and upazila is None:
        return
    rows = {
        r.code: r
        for r in session.execute(
            sa.text(
                "SELECT code, kind::text AS kind, parent_code FROM bd_area "
                "WHERE code = ANY(:codes)"
            ),
            {"codes": [c for c in (district, upazila) if c is not None]},
        )
    }
    bad = district is not None and (
        district not in rows or rows[district].kind != "district"
    )
    if upazila is not None:
        found = rows.get(upazila)
        bad = bad or found is None or found.kind != "upazila"
        bad = (
            bad
            or district is None
            or (found is not None and found.parent_code != district)
        )
    if bad:
        raise ValidationError(code="HUB_AREA_MISMATCH", message_key="hub.area_mismatch")


def update(
    session: Session, lens: TeacherLens, changes: OwnerListingUpdate
) -> OwnerListing:
    """Apply an owner's edits to their listing.

    :param session: The session
    :param lens: The owner's lens
    :param changes: The edits; ``None`` fields are left alone
    :return: The updated listing
    :raises ConflictError: The listing is suspended or the slug is taken
    :raises ValidationError: A value is malformed, in the wrong place, or
        carries a phone number outside the public contact field
    """
    listing = _load(session, lens)
    _refuse_suspended(listing)

    for name in _FREE_TEXT:
        value = getattr(changes, name)
        if value is not None and contains_phone(value):
            raise ValidationError(
                code="HUB_TEXT_CONTAINS_CONTACT",
                message_key="hub.text_contains_contact",
                details={"field": name},
            )

    if changes.slug is not None:
        if not _SLUG.fullmatch(changes.slug):
            raise ValidationError(
                code="HUB_SLUG_INVALID", message_key="hub.slug_invalid"
            )
        if not slug_available(session, changes.slug, lens):
            raise ConflictError(code="HUB_SLUG_TAKEN", message_key="hub.slug_taken")
        listing.slug = changes.slug

    if changes.district_code is not None or changes.upazila_code is not None:
        district = changes.district_code or listing.district_code
        upazila = changes.upazila_code or listing.upazila_code
        _check_area(session, district, upazila)
        listing.district_code = district
        listing.upazila_code = upazila

    if changes.street_address:
        kind = session.execute(
            sa.text("SELECT kind::text FROM owner WHERE id = :o"),
            {"o": lens.owner_id},
        ).scalar_one()
        if kind != "organisation":
            raise ValidationError(
                code="HUB_ADDRESS_CENTRE_ONLY",
                message_key="hub.address_centre_only",
            )

    for name in _FREE_TEXT:
        value = getattr(changes, name)
        if value is None:
            continue
        setattr(listing, name, (value or None) if name in _CLEARABLE else value)
    if changes.teaching_mode is not None:
        listing.teaching_mode = list(changes.teaching_mode)
    if changes.public_contact_phone is not None:
        listing.public_contact_phone = (
            canonical_phone(changes.public_contact_phone)
            if changes.public_contact_phone
            else None
        )
    listing.updated_at = dt.datetime.now(tz=dt.UTC)
    session.commit()
    return listing


def publish(
    session: Session, lens: TeacherLens, consent_version: str, now: dt.datetime
) -> OwnerListing:
    """Make the owner's listing public, recording their consent.

    :param session: The session
    :param lens: The owner's lens
    :param consent_version: The consent text version the owner agreed to
    :param now: The moment of consent
    :return: The published listing
    :raises ConflictError: The listing is suspended
    :raises ValidationError: The consent text is out of date, or the
        listing is incomplete (``details["missing"]`` lists the keys)
    """
    listing = _load(session, lens)
    _refuse_suspended(listing)
    if consent_version != HUB_CONSENT_VERSION:
        raise ValidationError(
            code="HUB_CONSENT_OUTDATED", message_key="hub.consent_outdated"
        )
    missing = [i.key for i in owner_checklist(listing) if not i.done]
    if missing:
        raise ValidationError(
            code="HUB_LISTING_INCOMPLETE",
            message_key="hub.listing_incomplete",
            details={"missing": ",".join(missing)},
        )
    listing.status = "published"
    listing.consent_version = consent_version
    listing.consent_at = now
    listing.consent_by_account_id = lens.account_id
    listing.published_at = now
    listing.updated_at = now
    session.commit()
    return listing


def unpublish(session: Session, lens: TeacherLens, now: dt.datetime) -> OwnerListing:
    """Hide a published listing; a draft stays a draft.

    :param session: The session
    :param lens: The owner's lens
    :param now: The moment of the change
    :return: The listing
    :raises ConflictError: The listing is suspended
    """
    listing = _load(session, lens)
    _refuse_suspended(listing)
    if listing.status == "published":
        listing.status = "hidden"
        listing.updated_at = now
        session.commit()
    return listing
