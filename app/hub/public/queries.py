"""The public hub's read service: search, owner page, batch page, sitemap.

The only code that reads the public views. Each function drops to the hub
reader before its first statement, so a query here that named any other
relation would fail on a missing grant rather than return a row; and each
reads only ``hub_public_owner``, ``hub_public_batch``,
``hub_public_teacher_name``, ``hub_public_area`` and ``hub_public_media``,
and -- through :mod:`app.hub.public.ratings`, only while reviews are on --
``hub_public_rating`` and ``hub_public_review``; and, only while join
requests are on, ``hub_public_enquirable``.

**The "Ask to join" link** [H5 Task 6] is offered on an owner page when
join requests are switched on and the owner is in ``hub_public_enquirable``,
and on a batch page when, besides, the batch's admissions are not
``closed``. While the switch is off no query here reads that view.

**Sort by rating** (Call 11) orders by the owner's Bayesian score over its
qualifying batches, then by the relevance order. While reviews are off a
``sort`` is ignored: the search reads no rating view and the page offers no
choice.

The views already apply every visibility rule -- the owner published, the
batch listing published, the batch active, a photo approved -- so nothing
here repeats them and nothing here can loosen them.

**Photos.** The owner page shows the owner's own photos only, those with
no batch; a batch's photos are on that batch's page alone, which is why a
hold on a batch photo invalidates only the batch page [Task 6].

The fee crosses from the database as text and becomes a ``Money`` through
the money module's own constructor, so no decimal is handled here.
"""

from __future__ import annotations

import functools
import math
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Any, Final, Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.hub.public.db import as_hub_reader
from app.hub.public.images import hub_image, image_alt, public_path
from app.hub.public.messages import LOCALES, Locale, t
from app.hub.public.normalise import query_terms
from app.hub.public.ratings import (
    SCORE_MILLI,
    batch_ratings,
    batch_reviews,
    owner_ratings,
)
from app.hub.public.settings import enquiries_enabled, reviews_enabled, site_url
from app.hub.public.views import (
    AreaNames,
    AreaOption,
    CityAreas,
    HubBatchCard,
    HubBatchPage,
    HubImage,
    HubOwnerCard,
    HubOwnerPage,
    HubSearchFilters,
    HubSearchPage,
    HubSitemap,
    PublicSlot,
    RatingSummary,
    SitemapAlternate,
    SitemapUrl,
)
from app.money import Money

__all__ = [
    "AREA_CODE",
    "CLASS_LEVELS",
    "MAX_SUBJECT_LENGTH",
    "PAGE_SIZE",
    "batch_page",
    "owner_page",
    "search",
    "sitemap",
]

#: Search results per page.
PAGE_SIZE: Final[int] = 20

#: The class levels the ``level`` filter accepts: the vocabulary the
#: listing editor validates ``class_levels`` against. Restated, because the
#: public import gate forbids ``app.db.models`` where the original lives;
#: ``tests/hub/test_public_queries.py`` asserts the two are equal.
CLASS_LEVELS: Final[tuple[str, ...]] = (
    *(f"class_{n}" for n in range(1, 13)),
    "ssc",
    "hsc",
    "admission",
    "o_level",
    "a_level",
    "other",
)

#: An area code's shape: two capitals and two to ten digits. A division or
#: district (``BD3026``), an upazila or city corporation (``BD30262500``),
#: a metropolitan thana (``MT3026250003``). A district or upazila filter is
#: uppercased and must match in full, so a value that is not a code never
#: reaches the query or the page's echo; ``tests/hub/test_public_queries.py``
#: holds it against every seeded code.
AREA_CODE: Final[re.Pattern[str]] = re.compile(r"[A-Z]{2}[0-9]{2,10}")

#: The longest subject a filter reads: the listing editor's tag limit, so
#: a longer one could match no tag and is ignored rather than echoed.
MAX_SUBJECT_LENGTH: Final[int] = 40

#: An owner page's columns, with the owner's district and finer area.
_OWNER_SELECT: Final[str] = (
    "SELECT o.owner_id, o.slug, o.public_name, o.kind::text AS kind, "
    "o.runs_classes, o.headline_en, o.headline_bn, o.bio_en, o.bio_bn, "
    "o.qualifications, CAST(o.teaching_mode AS text[]) AS teaching_mode, "
    "o.street_address, o.public_contact_phone, "
    "d.name_en AS district_en, d.name_bn AS district_bn, "
    "u.name_en AS area_en, u.name_bn AS area_bn "
    "FROM hub_public_owner o "
    "LEFT JOIN hub_public_area d ON d.code = o.district_code "
    "LEFT JOIN hub_public_area u ON u.code = o.upazila_code"
)

#: The batch card's columns. The fee is read as text so it reaches
#: ``Money`` without passing through a decimal outside the money module.
_BATCH_SELECT: Final[str] = (
    "SELECT b.batch_id, b.owner_slug, b.slug, b.public_title, "
    "b.subject_tags, b.class_levels, b.curriculum, b.mode::text AS mode, "
    "b.admissions::text AS admissions, b.fee::text AS fee, b.schedule, "
    "b.description_en, b.description_bn, b.syllabus_en, b.syllabus_bn "
    "FROM hub_public_batch b"
)

#: A gallery's approved photos, in the owner's order. ``:batch`` is NULL
#: for the owner's own gallery, which ``IS NOT DISTINCT FROM`` matches to
#: the owner-level rows only.
_MEDIA: Final[str] = (
    "SELECT media_id, public_key, width, height, widths, alt_en, alt_bn "
    "FROM hub_public_media WHERE owner_slug = :owner "
    "AND batch_slug IS NOT DISTINCT FROM CAST(:batch AS text) "
    "ORDER BY position, media_id"
)

#: Every district, for the search form's district choice.
_DISTRICTS: Final[str] = (
    "SELECT code, name_en, name_bn FROM hub_public_area WHERE kind = 'district'"
)

#: A district's upazilas and city corporations, and each city corporation's
#: metropolitan thanas, for the search form's area choice.
_DISTRICT_AREAS: Final[str] = """
SELECT a.code, a.kind::text AS kind, a.parent_code, a.name_en, a.name_bn
FROM hub_public_area a
WHERE (a.parent_code = :district AND a.kind IN ('upazila', 'city_corporation'))
   OR (a.kind = 'metro_thana' AND a.parent_code IN (
        SELECT c.code FROM hub_public_area c
        WHERE c.parent_code = :district AND c.kind = 'city_corporation'))
"""

#: Past this page number a search is past the end without asking, so the
#: offset stays far inside ``bigint`` whatever page a URL names.
MAX_PAGE: Final[int] = 1_000_000

#: The search, as one static statement once ``/*score*/`` is replaced by one
#: of the two constants below. ``:terms`` is the normalised term
#: list; each term holds only letters, marks and digits
#: (:func:`app.hub.public.normalise.query_terms`), so ``term || ':*'`` is a
#: prefix query that cannot carry query syntax. Every term must match the
#: owner's text, any of its batches' text, or one of the owner's area
#: names [R12]: its district, its upazila, city corporation or metropolitan
#: thana, and a thana's city corporation, each in English and Bangla and
#: normalised by ``hub_search_norm`` as the listing text is. An area match
#: adds nothing to the rank. A NULL filter is off. Returns one row even past
#: the end: the total, and NULL owner columns.
_SEARCH: Final[str] = """
WITH q AS (
    SELECT CAST(:terms AS text[]) AS terms,
           CAST(:district AS text) AS district,
           CAST(:upazila AS text) AS upazila,
           CAST(:subject AS text) AS subject,
           CAST(:level AS varchar) AS level
), ranked AS (
    SELECT o.owner_id, o.slug, o.public_name, o.kind::text AS kind,
           o.runs_classes, o.published_at, o.district_code, o.upazila_code,
           /*score*/ AS score_milli,
           CASE WHEN cardinality(q.terms) = 0 THEN 0 ELSE (
               SELECT sum(
                   ts_rank(o.search_text, to_tsquery('simple', term || ':*'))
                   + coalesce((
                       SELECT max(ts_rank(
                           b.search_text, to_tsquery('simple', term || ':*')))
                       FROM hub_public_batch b WHERE b.owner_slug = o.slug
                   ), 0)
               ) FROM unnest(q.terms) AS term
           ) END AS rank
    FROM hub_public_owner o CROSS JOIN q
    WHERE NOT EXISTS (
        SELECT 1 FROM unnest(q.terms) AS term
        WHERE NOT (
            o.search_text @@ to_tsquery('simple', term || ':*')
            OR EXISTS (
                SELECT 1 FROM hub_public_batch b
                WHERE b.owner_slug = o.slug
                  AND b.search_text @@ to_tsquery('simple', term || ':*')
            )
            OR EXISTS (
                SELECT 1 FROM hub_public_area a
                WHERE a.code IN (
                    o.district_code,
                    o.upazila_code,
                    (SELECT t.parent_code FROM hub_public_area t
                     WHERE t.code = o.upazila_code AND t.kind = 'metro_thana')
                )
                AND to_tsvector(
                    'simple', hub_search_norm(a.name_en || ' ' || a.name_bn)
                ) @@ to_tsquery('simple', term || ':*')
            )
        )
    )
    AND (q.district IS NULL OR o.district_code = q.district)
    AND (
        q.upazila IS NULL OR o.upazila_code = q.upazila
        OR o.upazila_code IN (
            SELECT a.code FROM hub_public_area a
            WHERE a.parent_code = q.upazila AND a.kind = 'metro_thana'
        )
    )
    AND (
        (q.subject IS NULL AND q.level IS NULL)
        OR EXISTS (
            SELECT 1 FROM hub_public_batch b
            WHERE b.owner_slug = o.slug
              AND (q.subject IS NULL OR EXISTS (
                  SELECT 1 FROM unnest(b.subject_tags) AS tag
                  WHERE lower(tag) = lower(q.subject)
              ))
              AND (q.level IS NULL OR q.level = ANY(b.class_levels))
        )
    )
), counted AS (
    SELECT count(*) AS total FROM ranked
)
SELECT counted.total, page.owner_id, page.slug, page.public_name, page.kind,
       page.runs_classes, d.name_en AS district_en, d.name_bn AS district_bn,
       u.name_en AS area_en, u.name_bn AS area_bn
FROM counted
LEFT JOIN LATERAL (
    SELECT * FROM ranked
    ORDER BY score_milli DESC, rank DESC, published_at DESC NULLS LAST, slug
    LIMIT :limit OFFSET :offset
) AS page ON true
LEFT JOIN hub_public_area d ON d.code = page.district_code
LEFT JOIN hub_public_area u ON u.code = page.upazila_code
ORDER BY page.score_milli DESC, page.rank DESC, page.published_at DESC NULLS LAST,
         page.slug
"""

#: The search ordered by relevance: every owner scores the same, so the
#: order is rank, then newest published, then slug. Reads no rating view.
_SEARCH_BY_RELEVANCE: Final[str] = _SEARCH.replace("/*score*/", "0")

#: The search ordered by rating: the Bayesian score first, then relevance.
_SEARCH_BY_RATING: Final[str] = _SEARCH.replace("/*score*/", SCORE_MILLI)


def _localised(row: Any, field: str, locale: Locale) -> str | None:
    """Read a field in the page's locale, else in the other one.

    :param row: A row holding ``<field>_en`` and ``<field>_bn``
    :param field: The field's stem
    :param locale: The page's locale
    :return: The text, or None when neither locale has any
    """
    other: Locale = "bn" if locale == "en" else "en"
    for candidate in (locale, other):
        value = getattr(row, f"{field}_{candidate}")
        if value:
            return str(value)
    return None


def _area_names(row: Any) -> AreaNames | None:
    """Name where an owner teaches: the finest area, then the district.

    :param row: An owner row from :data:`_OWNER_SELECT` or :data:`_SEARCH`
    :return: Both languages, or None when the owner gave no area
    """
    names: dict[str, str] = {}
    for locale in LOCALES:
        finest = getattr(row, f"area_{locale}")
        district = getattr(row, f"district_{locale}")
        names[locale] = ", ".join(part for part in (finest, district) if part)
    if not names["en"] and not names["bn"]:
        return None
    return AreaNames(en=names["en"], bn=names["bn"])


def _owner_card(row: Any, rating: RatingSummary | None = None) -> HubOwnerCard:
    """Build an owner card from an owner row.

    :param row: An owner row from :data:`_OWNER_SELECT` or :data:`_SEARCH`
    :param rating: The owner's rating, or None
    :return: The card
    """
    return HubOwnerCard(
        report_id=row.owner_id,
        slug=row.slug,
        public_name=row.public_name,
        kind=row.kind,
        area_names=_area_names(row),
        runs_classes=row.runs_classes,
        rating=rating,
    )


def _teacher_names(
    session: Session, batch_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """Read the consented teacher names of some batches.

    :param session: A session already reading as the hub reader
    :param batch_ids: The batches
    :return: Each batch's names, sorted; a batch with none is absent
    """
    if not batch_ids:
        return {}
    rows = session.execute(
        sa.text(
            "SELECT batch_id, name FROM hub_public_teacher_name "
            "WHERE batch_id = ANY(:ids) ORDER BY name"
        ),
        {"ids": list(batch_ids)},
    )
    names: dict[uuid.UUID, list[str]] = {}
    for row in rows:
        names.setdefault(row.batch_id, []).append(row.name)
    return names


def _batch_card(
    row: Any,
    owner: HubOwnerCard,
    names: Mapping[uuid.UUID, list[str]],
    locale: Locale,
    ratings: Mapping[uuid.UUID, RatingSummary],
) -> HubBatchCard:
    """Build a batch card from a batch row.

    :param row: A batch row from :data:`_BATCH_SELECT`
    :param owner: The batch's owner
    :param names: Consented teacher names by batch
    :param locale: The page's locale
    :param ratings: Ratings by batch; empty while reviews are off
    :return: The card
    """
    if owner.kind == "organisation":
        teachers = names.get(row.batch_id) or [t("centre_faculty", locale)]
    else:
        teachers = [owner.public_name]
    fee = None if row.fee is None else Money(row.fee)
    schedule = (
        None
        if row.schedule is None
        else [PublicSlot.model_validate(slot) for slot in row.schedule]
    )
    return HubBatchCard(
        report_id=row.batch_id,
        owner_slug=row.owner_slug,
        slug=row.slug,
        public_title=row.public_title,
        subjects=list(row.subject_tags),
        class_levels=list(row.class_levels),
        curriculum=row.curriculum,
        mode=row.mode,
        admissions=row.admissions,
        fee=fee,
        fee_display=None if fee is None else fee.format(locale),
        schedule=schedule,
        teacher_names=teachers,
        rating=ratings.get(row.batch_id),
    )


def _sort(value: str | None) -> Literal["relevance", "rating"]:
    """Read the sort key; anything but ``rating`` is relevance.

    Read only while reviews are on, so an off switch ignores it.

    :param value: ``sort`` as sent, or None
    :return: The order to apply
    """
    if value is not None and value.strip().lower() == "rating" and reviews_enabled():
        return "rating"
    return "relevance"


def _images(
    session: Session, locale: Locale, owner_slug: str, batch_slug: str | None
) -> list[HubImage]:
    """Read one gallery's approved photos.

    :param session: A session already reading as the hub reader
    :param locale: The page's locale
    :param owner_slug: The owner's slug
    :param batch_slug: The batch's slug, or None for the owner's own photos
    :return: The photos, by position
    """
    rows = session.execute(
        sa.text(_MEDIA), {"owner": owner_slug, "batch": batch_slug}
    ).all()
    return [
        hub_image(
            media_id=row.media_id,
            widths=row.widths,
            width=row.width,
            height=row.height,
            alt=image_alt(row.alt_en, row.alt_bn, locale),
            url=functools.partial(public_path, row.public_key),
        )
        for row in rows
    ]


def _clean(value: str | None) -> str | None:
    """Strip a filter value, treating blank as absent.

    :param value: The value as given
    :return: The stripped value, or None
    """
    if value is None:
        return None
    return value.strip() or None


def _area_code(value: str | None) -> str | None:
    """Read an area filter as a code, whatever case the reader sent.

    :param value: The value as given
    :return: The uppercased code, or None when blank or not code-shaped
    """
    cleaned = _clean(value)
    if cleaned is None:
        return None
    code = cleaned.upper()
    return code if AREA_CODE.fullmatch(code) else None


def _subject(value: str | None) -> str | None:
    """Read a subject filter, ignoring one no tag could equal.

    :param value: The value as given
    :return: The stripped subject, or None when blank or too long
    """
    cleaned = _clean(value)
    if cleaned is None or len(cleaned) > MAX_SUBJECT_LENGTH:
        return None
    return cleaned


def _option(row: Any) -> AreaOption:
    """Build one area choice from an area row.

    :param row: A row with ``code``, ``name_en`` and ``name_bn``
    :return: The choice
    """
    return AreaOption(code=row.code, en=row.name_en, bn=row.name_bn)


def _district_areas(
    session: Session, district: str | None
) -> tuple[list[AreaOption], list[CityAreas]]:
    """Read the areas a chosen district offers beneath it.

    :param session: A session already reading as the hub reader
    :param district: The chosen district's code, or None
    :return: Its upazilas, and its city corporations with their thanas;
        both empty when no district is chosen or the code names none
    """
    if district is None:
        return [], []
    rows = session.execute(sa.text(_DISTRICT_AREAS), {"district": district}).all()
    upazilas = [_option(row) for row in rows if row.kind == "upazila"]
    thanas: dict[str, list[AreaOption]] = {}
    for row in rows:
        if row.kind == "metro_thana":
            thanas.setdefault(row.parent_code, []).append(_option(row))
    cities = [
        CityAreas(city=_option(row), thanas=thanas.get(row.code, []))
        for row in rows
        if row.kind == "city_corporation"
    ]
    return upazilas, cities


def search(
    session: Session,
    *,
    locale: Locale,
    q: str | None,
    district: str | None,
    upazila: str | None,
    subject: str | None,
    level: str | None,
    page: int,
    sort: str | None = None,
) -> HubSearchPage:
    """Search published owners by text and by structured filters.

    Each term of ``q`` must match, as a prefix, either the owner's own
    text or the text of any of its published batches; terms may match in
    different places. ``district`` matches the owner's district;
    ``upazila`` matches the owner's finer area, and a city corporation code
    also matches every metropolitan thana within it. ``subject`` (any
    case) and ``level`` must both hold for one and the same published
    batch; a ``level`` outside :data:`CLASS_LEVELS` is ignored. Area codes
    are read in any case, and a ``district`` or ``upazila`` that is not
    shaped like one (:data:`AREA_CODE`), an ``upazila`` outside a chosen
    ``district``, or a ``subject`` longer than :data:`MAX_SUBJECT_LENGTH`,
    is ignored too. The page also carries the form's area choices.

    Ranked by each term's ``ts_rank`` against the owner and its best
    batch, summed; then newest published; then slug. With ``sort`` of
    ``rating`` and reviews on, the owner's Bayesian score
    (:data:`~app.hub.public.ratings.SCORE_MILLI`) comes first. A page past
    the end is empty, never an error.

    :param session: The application's session; left reading as the hub reader
    :param locale: The page's locale; owner cards carry both languages, so
        it changes nothing yet and is kept for the call shape every page shares
    :param q: The text query, or None
    :param district: A district code, or None
    :param upazila: An upazila, city corporation or metro thana code, or None
    :param subject: A subject tag, or None
    :param level: A class level, or None
    :param page: The page number, from 1; less than 1 reads as 1
    :param sort: ``rating`` to order by rating; anything else, or reviews
        off, is relevance
    :return: The page of results
    """
    del locale
    as_hub_reader(session)
    district_code = _area_code(district)
    upazila_code = _area_code(upazila)
    districts = [_option(row) for row in session.execute(sa.text(_DISTRICTS))]
    upazilas, cities = _district_areas(session, district_code)
    if district_code is not None and upazila_code is not None:
        # A choice left over from another district would AND the search
        # into nothing; the form cannot clear it without a script.
        within = {area.code for area in upazilas} | {
            area.code for city in cities for area in (city.city, *city.thanas)
        }
        if upazila_code not in within:
            upazila_code = None
    filters = HubSearchFilters(
        district=district_code,
        upazila=upazila_code,
        subject=_subject(subject),
        level=level if level in CLASS_LEVELS else None,
    )
    number = max(1, page)
    order = _sort(sort)
    statement = _SEARCH_BY_RATING if order == "rating" else _SEARCH_BY_RELEVANCE
    rows = session.execute(
        sa.text(statement),
        {
            "terms": query_terms(q) if q else [],
            "district": filters.district,
            "upazila": filters.upazila,
            "subject": filters.subject,
            "level": filters.level,
            "limit": PAGE_SIZE,
            "offset": (min(number, MAX_PAGE) - 1) * PAGE_SIZE,
        },
    ).all()
    total = int(rows[0].total)
    past_end = number > MAX_PAGE
    shown = [row for row in rows if row.slug is not None and not past_end]
    ratings = owner_ratings(session, [row.slug for row in shown])
    return HubSearchPage(
        query=q,
        filters=filters,
        districts=districts,
        upazilas=upazilas,
        cities=cities,
        results=[_owner_card(row, ratings.get(row.slug)) for row in shown],
        page=number,
        pages=max(1, math.ceil(total / PAGE_SIZE)),
        total=total,
        sort=order,
        offers_sort=reviews_enabled(),
    )


def _owner_row(session: Session, owner_slug: str) -> Any:
    """Read one published owner by slug.

    :param session: A session already reading as the hub reader
    :param owner_slug: The owner's slug
    :return: The row, or None
    """
    return session.execute(
        sa.text(f"{_OWNER_SELECT} WHERE o.slug = :slug"), {"slug": owner_slug}
    ).one_or_none()


def _enquirable(session: Session, owner_slug: str) -> bool:
    """Say whether an owner's pages offer the "Ask to join" link.

    Reads ``hub_public_enquirable`` only while join requests are on, so an
    off switch reaches no join-request view at all.

    :param session: A session already reading as the hub reader
    :param owner_slug: The owner's slug
    :return: True when the switch is on and the owner accepts requests
    """
    if not enquiries_enabled():
        return False
    return bool(
        session.execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM hub_public_enquirable WHERE slug = :slug)"
            ),
            {"slug": owner_slug},
        ).scalar_one()
    )


def owner_page(
    session: Session, locale: Locale, owner_slug: str
) -> HubOwnerPage | None:
    """Read a published owner's page with its published batches.

    :param session: The application's session; left reading as the hub reader
    :param locale: The page's locale
    :param owner_slug: The owner's slug
    :return: The page, or None when no published owner has that slug
    """
    as_hub_reader(session)
    row = _owner_row(session, owner_slug)
    if row is None:
        return None
    owner = _owner_card(row, owner_ratings(session, [owner_slug]).get(owner_slug))
    batches = session.execute(
        sa.text(
            f"{_BATCH_SELECT} WHERE b.owner_slug = :slug "
            "ORDER BY b.public_title, b.slug"
        ),
        {"slug": owner_slug},
    ).all()
    names = _teacher_names(session, [b.batch_id for b in batches])
    ratings = batch_ratings(session, [b.batch_id for b in batches])
    return HubOwnerPage(
        owner=owner,
        headline=_localised(row, "headline", locale),
        bio=_localised(row, "bio", locale),
        qualifications=row.qualifications,
        teaching_mode=list(row.teaching_mode),
        street_address=row.street_address,
        public_contact_phone=row.public_contact_phone,
        batches=[_batch_card(b, owner, names, locale, ratings) for b in batches],
        images=_images(session, locale, owner_slug, None),
        enquiry_open=_enquirable(session, owner_slug),
    )


def batch_page(
    session: Session, locale: Locale, owner_slug: str, batch_slug: str
) -> HubBatchPage | None:
    """Read a published batch's page under its published owner.

    :param session: The application's session; left reading as the hub reader
    :param locale: The page's locale
    :param owner_slug: The owner's slug
    :param batch_slug: The batch's slug
    :return: The page, or None when the owner or the batch is not public
    """
    as_hub_reader(session)
    row = _owner_row(session, owner_slug)
    if row is None:
        return None
    batch = session.execute(
        sa.text(f"{_BATCH_SELECT} WHERE b.owner_slug = :owner AND b.slug = :slug"),
        {"owner": owner_slug, "slug": batch_slug},
    ).one_or_none()
    if batch is None:
        return None
    owner = _owner_card(row, owner_ratings(session, [owner_slug]).get(owner_slug))
    names = _teacher_names(session, [batch.batch_id])
    ratings = batch_ratings(session, [batch.batch_id])
    return HubBatchPage(
        owner=owner,
        batch=_batch_card(batch, owner, names, locale, ratings),
        description=_localised(batch, "description", locale),
        syllabus=_localised(batch, "syllabus", locale),
        images=_images(session, locale, owner_slug, batch_slug),
        enquiry_open=batch.admissions != "closed" and _enquirable(session, owner_slug),
        reviews=batch_reviews(session, batch.batch_id, locale),
    )


def _sitemap_urls(origin: str, path: str) -> list[SitemapUrl]:
    """Build a path's entry in each locale, each listing every alternate.

    :param origin: The site's origin
    :param path: The path below ``/hub/{locale}``, starting with ``/``
    :return: One entry per locale, English first
    """
    href = {locale: f"{origin}/hub/{locale}{path}" for locale in LOCALES}
    alternates = [
        *(SitemapAlternate(hreflang=locale, href=href[locale]) for locale in LOCALES),
        SitemapAlternate(hreflang="x-default", href=href["en"]),
    ]
    return [SitemapUrl(loc=href[locale], alternates=alternates) for locale in LOCALES]


def sitemap(session: Session) -> HubSitemap:
    """List every published owner and batch page, in both locales.

    Each owner is followed by its batches; owners and batches by slug.

    :param session: The application's session; left reading as the hub reader
    :return: The sitemap
    """
    as_hub_reader(session)
    owners = (
        session.execute(sa.text("SELECT slug FROM hub_public_owner ORDER BY slug"))
        .scalars()
        .all()
    )
    batches: dict[str, list[str]] = {}
    for row in session.execute(
        sa.text("SELECT owner_slug, slug FROM hub_public_batch ORDER BY slug")
    ):
        batches.setdefault(row.owner_slug, []).append(row.slug)
    origin = site_url()
    urls: list[SitemapUrl] = []
    for owner_slug in owners:
        urls.extend(_sitemap_urls(origin, f"/t/{owner_slug}"))
        for batch_slug in batches.get(owner_slug, []):
            urls.extend(_sitemap_urls(origin, f"/t/{owner_slug}/{batch_slug}"))
    return HubSitemap(urls=urls)
