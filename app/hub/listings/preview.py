"""The owner's preview of their own public page, drafts included.

Builds the same registered :class:`~app.hub.public.views.HubOwnerPage` a
reader would see, so the privacy gate walks what the preview shows and the
preview renders through the public page's own template. The difference is
where the rows come from: the owner's own ``owner_listing`` and
``batch_listing`` rows, read as the application role and scoped by the
lens's owner id, in ``draft`` as well as ``published`` -- never the public
views, which show nothing until a listing is published.

What it shows is still only what publishing would show: the public title
and never ``batch.name``; the fee only where the listing shows it; the
timetable only where the listing shows it; a centre's teachers only where
they agreed to be named, otherwise "Centre faculty"; a street address for a
centre only. A batch listing that could not be public whatever its status
-- hidden, suspended, or on an inactive batch -- is left out.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.hub.listings.names import CENTRE_FACULTY, teacher_names
from app.hub.listings.owner import get_or_draft
from app.hub.public.messages import LOCALES, Locale, t
from app.hub.public.views import (
    AreaNames,
    HubBatchCard,
    HubOwnerCard,
    HubOwnerPage,
    PublicSlot,
)
from app.money import Money

__all__ = ["owner_page"]

_KIND: Final = sa.text("SELECT kind::text FROM owner WHERE id = :owner")

_AREAS: Final = sa.text(
    "SELECT code, name_en, name_bn FROM bd_area WHERE code = ANY(:codes)"
)

#: The owner's batch listings a publish could make public. The fee is read
#: as text so it reaches ``Money`` without a decimal outside the money
#: module, and only where the listing shows it.
_BATCHES: Final = sa.text(
    "SELECT bl.batch_id, bl.slug, bl.public_title, bl.subject_tags, "
    "bl.class_levels, bl.curriculum, bl.mode::text AS mode, "
    "bl.admissions::text AS admissions, bl.show_schedule, "
    "CASE WHEN bl.show_fee THEN bt.default_fee::text END AS fee "
    "FROM batch_listing bl JOIN batch bt ON bt.id = bl.batch_id "
    "WHERE bl.owner_id = :owner AND bt.owner_id = :owner AND bt.active "
    "AND bl.status IN ('draft', 'published') "
    "ORDER BY bl.public_title NULLS LAST, bl.slug NULLS LAST, bl.batch_id"
)

_SLOTS: Final = sa.text(
    "SELECT batch_id, weekday, to_char(start_time, 'HH24:MI') AS start_at, "
    "to_char(end_time, 'HH24:MI') AS end_at FROM schedule_slot "
    "WHERE batch_id = ANY(:batches) ORDER BY weekday, start_time, end_time"
)


def _localised(values: dict[Locale, str | None], locale: Locale) -> str | None:
    """Pick the page locale's text, else the other locale's.

    :param values: The text per locale
    :param locale: The page's locale
    :return: The text, or None when neither has any
    """
    other: Locale = "bn" if locale == "en" else "en"
    for candidate in (locale, other):
        if values[candidate]:
            return values[candidate]
    return None


def _area_names(
    session: Session, district: str | None, upazila: str | None
) -> AreaNames | None:
    """Name the owner's area as the public card does: finest, then district.

    :param session: The session
    :param district: The district code
    :param upazila: The finer area's code
    :return: Both languages, or None when no area is set
    """
    codes = [code for code in (upazila, district) if code]
    if not codes:
        return None
    rows = {row.code: row for row in session.execute(_AREAS, {"codes": codes})}
    names: dict[Locale, str] = {}
    for locale in LOCALES:
        parts = [
            getattr(rows[code], f"name_{locale}") for code in codes if code in rows
        ]
        names[locale] = ", ".join(part for part in parts if part)
    if not names["en"] and not names["bn"]:
        return None
    return AreaNames(en=names["en"], bn=names["bn"])


def _schedules(
    session: Session, batch_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[PublicSlot]]:
    """Read the weekly times of some batches.

    :param session: The session
    :param batch_ids: The batches whose listing shows its timetable
    :return: Each batch's times; a batch with none maps to an empty list
    """
    slots: dict[uuid.UUID, list[PublicSlot]] = {b: [] for b in batch_ids}
    if not batch_ids:
        return slots
    for row in session.execute(_SLOTS, {"batches": batch_ids}):
        slots[row.batch_id].append(
            PublicSlot(weekday=row.weekday, start=row.start_at, end=row.end_at)
        )
    return slots


def _batch_card(
    row: Any,
    owner_slug: str,
    teachers: list[str],
    schedule: list[PublicSlot] | None,
    locale: Locale,
) -> HubBatchCard:
    """Build one batch's card from the owner's own listing row.

    :param row: A row of :data:`_BATCHES`
    :param owner_slug: The owner's slug, or an empty string while unset
    :param teachers: The names the card may show
    :param schedule: The weekly times, or None when not shown
    :param locale: The page's locale
    :return: The card
    """
    fee = None if row.fee is None else Money(row.fee)
    return HubBatchCard(
        report_id=row.batch_id,
        owner_slug=owner_slug,
        slug=row.slug or "",
        public_title=row.public_title or "",
        subjects=list(row.subject_tags),
        class_levels=list(row.class_levels),
        curriculum=row.curriculum,
        mode=row.mode,
        admissions=row.admissions,
        fee=fee,
        fee_display=None if fee is None else fee.format(locale),
        schedule=schedule,
        teacher_names=[
            t("centre_faculty", locale) if name == CENTRE_FACULTY else name
            for name in teachers
        ],
    )


def owner_page(session: Session, lens: TeacherLens, locale: Locale) -> HubOwnerPage:
    """Build the owner's page as it would read once published.

    Drafts the owner listing on first use, as the editor's own read does.

    :param session: The request-scoped session, as the application role
    :param lens: The owner's lens; every row read is this owner's
    :param locale: The page's locale
    :return: The page, in the public page's own model
    """
    listing = get_or_draft(session, lens)
    kind: str = session.execute(_KIND, {"owner": lens.owner_id}).scalar_one()
    owner = HubOwnerCard(
        report_id=lens.owner_id,
        slug=listing.slug or "",
        public_name=listing.public_name,
        kind="organisation" if kind == "organisation" else "teacher",
        area_names=_area_names(session, listing.district_code, listing.upazila_code),
        runs_classes=listing.runs_classes,
    )
    rows = session.execute(_BATCHES, {"owner": lens.owner_id}).all()
    batch_ids = [row.batch_id for row in rows]
    names = teacher_names(session, lens.owner_id, batch_ids)
    schedules = _schedules(session, [row.batch_id for row in rows if row.show_schedule])
    return HubOwnerPage(
        owner=owner,
        headline=_localised(
            {"en": listing.headline_en, "bn": listing.headline_bn}, locale
        ),
        bio=_localised({"en": listing.bio_en, "bn": listing.bio_bn}, locale),
        qualifications=listing.qualifications,
        teaching_mode=list(listing.teaching_mode),
        street_address=listing.street_address if kind == "organisation" else None,
        public_contact_phone=listing.public_contact_phone,
        batches=[
            _batch_card(
                row,
                owner.slug,
                names[row.batch_id],
                schedules.get(row.batch_id) if row.show_schedule else None,
                locale,
            )
            for row in rows
        ],
    )
