"""An owner's own public listing: draft, edit, consent, publish, hide.

**Nothing here makes a listing public except** :func:`publish`, which needs
the current consent text, a complete listing and a listing no moderator has
suspended. A draft is created silently and stays a draft, so an owner who
never opens the hub is never listed [Review Focus 1].
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session, object_session

from app.accounts.phone import canonical_phone
from app.authz.lenses import TeacherLens
from app.db.models import OwnerListing
from app.errors import ConflictError, ValidationError
from app.hub.listings.badge import runs_classes
from app.hub.listings.checklist import owner_checklist
from app.hub.listings.consent import HUB_CONSENT_VERSION
from app.hub.listings.shared import (
    SLUG,
    flush_slug_unique,
    refuse_phone_in,
    refuse_suspended,
    require_slug_shape,
)
from app.local_time import bangladesh_today

__all__ = [
    "OwnerListingUpdate",
    "get_or_draft",
    "publish",
    "slug_available",
    "unpublish",
    "update",
]

#: The owner's own free-text columns, which may not carry a phone number.
_FREE_TEXT: Final = (
    "public_name",
    "public_name_latin",
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
    :ivar public_name_latin: The owner's Latin spelling of the name
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
    public_name_latin: str | None = None
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
    if not SLUG.fullmatch(slug):
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

    ``upazila`` is an upazila or a city corporation whose parent is the
    district, or a metropolitan thana whose city corporation's parent is
    the district. A city corporation stands for the whole city when the
    owner's thana is not in the vocabulary; it is never a district.

    :param session: The session
    :param district: The district code, if any
    :param upazila: The upazila, city corporation or metropolitan thana
        code, if any
    :raises ValidationError: An area is unknown or not nested
    """
    if district is None and upazila is None:
        return
    rows = {
        r.code: r
        for r in session.execute(
            sa.text(
                "SELECT a.code, a.kind::text AS kind, a.parent_code, "
                "p.parent_code AS grandparent_code FROM bd_area a "
                "LEFT JOIN bd_area p ON p.code = a.parent_code "
                "WHERE a.code = ANY(:codes)"
            ),
            {"codes": [c for c in (district, upazila) if c is not None]},
        )
    }
    bad = district is not None and (
        district not in rows or rows[district].kind != "district"
    )
    if upazila is not None:
        found = rows.get(upazila)
        nested = found is not None and (
            (
                found.kind in ("upazila", "city_corporation")
                and found.parent_code == district
            )
            or (found.kind == "metro_thana" and found.grandparent_code == district)
        )
        bad = bad or district is None or not nested
    if bad:
        raise ValidationError(code="HUB_AREA_MISMATCH", message_key="hub.area_mismatch")


def _next_area(
    listing: OwnerListing, changes: OwnerListingUpdate
) -> tuple[str | None, str | None]:
    """Work out the area an edit leaves the listing in.

    An omitted code keeps its value and an empty one clears it. A district
    that changes without an upazila being given drops the old upazila, which
    lay in the old district.

    :param listing: The listing before the edit
    :param changes: The edits
    :return: ``(district, upazila)``, either of which may be None
    """
    district = (
        listing.district_code
        if changes.district_code is None
        else changes.district_code or None
    )
    if changes.upazila_code is not None:
        upazila = changes.upazila_code or None
    elif district != listing.district_code:
        upazila = None
    else:
        upazila = listing.upazila_code
    return district, upazila


def update(
    session: Session, lens: TeacherLens, changes: OwnerListingUpdate
) -> OwnerListing:
    """Apply an owner's edits to their listing, and store the badge anew.

    The stored badge is what the public views show, so every save
    recomputes it from :func:`~app.hub.listings.badge.runs_classes`.

    :param session: The session
    :param lens: The owner's lens
    :param changes: The edits; ``None`` fields are left alone
    :return: The updated listing
    :raises ConflictError: The listing is suspended or the slug is taken
    :raises ValidationError: A value is malformed, in the wrong place, or
        carries a phone number outside the public contact field
    """
    listing = _load(session, lens)
    refuse_suspended(listing)

    refuse_phone_in((n, getattr(changes, n)) for n in (*_FREE_TEXT, "slug"))

    if changes.slug is not None:
        require_slug_shape(changes.slug)
        if not slug_available(session, changes.slug, lens):
            raise ConflictError(code="HUB_SLUG_TAKEN", message_key="hub.slug_taken")
        listing.slug = changes.slug

    if changes.district_code is not None or changes.upazila_code is not None:
        district, upazila = _next_area(listing, changes)
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
    if listing.status != "draft":
        _require_complete(listing)
    flush_slug_unique(session, "uq_owner_listing_slug")
    # After the guarded flush, so the badge's read cannot autoflush a slug
    # collision past the translation above.
    listing.runs_classes = runs_classes(session, lens.owner_id, bangladesh_today())
    session.commit()
    return listing


def _require_complete(listing: OwnerListing) -> None:
    """Refuse a listing that would be live but incomplete.

    :param listing: The listing, with any edits applied
    :raises ValidationError: Something required is missing; the rejected
        edits are rolled back
    """
    missing = [i.key for i in owner_checklist(listing) if not i.done]
    if missing:
        session = object_session(listing)
        if session is not None:
            session.rollback()
        raise ValidationError(
            code="HUB_LISTING_INCOMPLETE",
            message_key="hub.listing_incomplete",
            details={"missing": ",".join(missing)},
        )


def publish(
    session: Session, lens: TeacherLens, consent_version: str, now: dt.datetime
) -> OwnerListing:
    """Make the owner's listing public, recording consent and the badge.

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
    refuse_suspended(listing)
    if consent_version != HUB_CONSENT_VERSION:
        raise ValidationError(
            code="HUB_CONSENT_OUTDATED", message_key="hub.consent_outdated"
        )
    refuse_phone_in((n, getattr(listing, n)) for n in _FREE_TEXT)
    _require_complete(listing)
    listing.status = "published"
    listing.consent_version = consent_version
    listing.consent_at = now
    listing.consent_by_account_id = lens.account_id
    listing.published_at = now
    listing.updated_at = now
    listing.runs_classes = runs_classes(session, lens.owner_id, bangladesh_today(now))
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
    refuse_suspended(listing)
    if listing.status == "published":
        listing.status = "hidden"
        listing.updated_at = now
        session.commit()
    return listing
