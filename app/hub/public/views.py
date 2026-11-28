"""The view models public hub pages render, each registered with the gate.

Every model here is filled only from the public views, as the hub
reader, by :mod:`app.hub.public.queries`. Registering each top-level model
lets :func:`app.contract.privacy.public_field_leaks` walk it, nested models
included, against the public forbidden set.

No field is named ``display_name``, ``name`` or ``phone``: the contact
number an owner chose to publish is ``public_contact_phone``, and the
teachers named on a batch are ``teacher_names``.

``report_id`` is the id ``POST /v1/hub/reports`` expects for the target
[R2]: the owner id on an owner card, the batch id on a batch card. Neither
is an account, enrollment or student id. A photo's ``media_id`` is the same
for a ``media`` report.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.hub.public.registry import register_view
from app.money import Money

__all__ = [
    "AreaNames",
    "AreaOption",
    "CityAreas",
    "HubBatchCard",
    "HubBatchPage",
    "HubImage",
    "HubOwnerCard",
    "HubOwnerPage",
    "HubReply",
    "HubReview",
    "HubSearchFilters",
    "HubSearchPage",
    "HubSitemap",
    "PublicSeats",
    "PublicSlot",
    "RatingSummary",
    "SitemapAlternate",
    "SitemapUrl",
]

_FROZEN = ConfigDict(frozen=True)


class AreaNames(BaseModel):
    """Where an owner teaches, in both languages.

    The owner's most specific area followed by its district, comma
    separated: ``Mirpur, Dhaka`` for a metropolitan thana, ``Savar, Dhaka``
    for an upazila, ``Dhaka North City Corporation, Dhaka`` for a city
    corporation, and the district alone when no finer area is given.

    :ivar en: The English form
    :ivar bn: The Bangla form
    """

    model_config = _FROZEN

    en: str
    bn: str


class RatingSummary(BaseModel):
    """What a page says about a batch's or an owner's rating.

    Read only from ``hub_public_rating``, which has no row for a batch below
    the threshold [T2-a]. Below it every figure is None, the count included
    [F18, T9-a]: a batch with 0, 1 or 2 published reviews reads the same.
    The average is integer tenths (43 is 4.3) and its label is rendered by
    integer operations, never through a float.

    :ivar state: ``shown`` at or over the threshold, else ``below_threshold``
    :ivar count: Published reviews, or None below the threshold
    :ivar average_tenths: The average in tenths, or None
    :ivar average_label: The average as shown, ``"4.3"``, or None
    :ivar distribution: Reviews per star from one to five, or None; an
        owner card carries none
    """

    model_config = _FROZEN

    state: Literal["below_threshold", "shown"]
    count: int | None = None
    average_tenths: int | None = None
    average_label: str | None = None
    distribution: list[int] | None = None


@register_view
class HubOwnerCard(BaseModel):
    """One published owner as a search result or a page header.

    :ivar report_id: The owner id, for the report link
    :ivar slug: The owner's public path segment
    :ivar public_name: The name the owner chose to show
    :ivar kind: ``teacher`` for a solo tutor, ``organisation`` for a centre
    :ivar area_names: Where the owner teaches, or None when unset
    :ivar runs_classes: The stored "Runs classes" badge
    :ivar rating: The rating over the owner's batches at the threshold
        only (Call 12); None while reviews are off or no batch qualifies
    """

    model_config = _FROZEN

    report_id: uuid.UUID
    slug: str
    public_name: str
    kind: Literal["teacher", "organisation"]
    area_names: AreaNames | None
    runs_classes: bool
    rating: RatingSummary | None = None


class PublicSlot(BaseModel):
    """One weekly class time of a batch.

    :ivar weekday: 0-6, Monday first
    :ivar start: ``HH:MM``
    :ivar end: ``HH:MM``
    """

    model_config = _FROZEN

    weekday: int
    start: str
    end: str


class PublicSeats(BaseModel):
    """A batch's seats, as its owner typed them and chose to show them.

    Never counted from enrollments: the owner states both numbers [0048].

    :ivar capacity: How many seats the batch has
    :ivar free: How many are free, from 0 to :attr:`capacity`
    :ivar updated_on: The day the owner last changed either number, in
        Bangladesh time
    """

    model_config = _FROZEN

    capacity: int
    free: int
    updated_on: dt.date


@register_view
class HubBatchCard(BaseModel):
    """One published batch of a published owner.

    :ivar report_id: The batch id, for the report link
    :ivar owner_slug: The owner's public path segment
    :ivar slug: The batch's public path segment
    :ivar public_title: The batch's public title, never ``batch.name``
    :ivar subjects: The subject tags
    :ivar class_levels: The class levels taught
    :ivar curriculum: The curriculum, if given
    :ivar mode: How the batch is taught, if given
    :ivar admissions: ``open``, ``waitlist`` or ``closed``
    :ivar fee: The default fee, or None unless the owner chose to show it
    :ivar fee_display: :attr:`fee` as ``Money.format`` renders it in the
        page's locale, or None with it
    :ivar schedule: The weekly times, or None unless the owner chose to
        show them
    :ivar teacher_names: Who teaches it: consented centre teachers, else
        "Centre faculty" in the page's locale; a solo tutor's public name
    :ivar rating: The batch's rating, ``below_threshold`` under three
        published reviews; None while reviews are off
    :ivar seats: The seats, or None unless the owner chose to show them
    """

    model_config = _FROZEN

    report_id: uuid.UUID
    owner_slug: str
    slug: str
    public_title: str
    subjects: list[str]
    class_levels: list[str]
    curriculum: str | None
    mode: str | None
    admissions: str
    fee: Money | None
    fee_display: str | None
    schedule: list[PublicSlot] | None
    teacher_names: list[str]
    rating: RatingSummary | None = None
    seats: PublicSeats | None = None


class HubReply(BaseModel):
    """The owner's published reply to a review.

    :ivar body: The reply's text
    :ivar month_label: The month it was published, e.g. ``Nov 2026``
    """

    model_config = _FROZEN

    body: str
    month_label: str


@register_view
class HubReview(BaseModel):
    """One published review of a batch at the threshold, as a page shows it.

    Read only from ``hub_public_review``. Its author is a tenure label,
    never a name, an initial, a class or a day; its date is a month
    [global constraints: Display]. ``review_id`` is what a ``review`` or
    ``reply`` report names, and is no account, seat or student id.

    :ivar review_id: The review, for the report links
    :ivar rating: 1 to 5
    :ivar body: The text, or None for a rating alone
    :ivar author_label: "Verified guardian · enrolled …" in the page's locale
    :ivar month_label: The month it was published, e.g. ``Nov 2026``
    :ivar reply: The owner's reply while it is published, else None
    """

    model_config = _FROZEN

    review_id: uuid.UUID
    rating: int
    body: str | None
    author_label: str
    month_label: str
    reply: HubReply | None


@register_view
class HubImage(BaseModel):
    """One approved photo, as an ``<img>`` renders it.

    The URLs name the stored WebP variants, ``/m/{public_key}/{w}.webp``,
    and only those the sanitiser wrote. :attr:`src` is the 960 variant, else
    the largest; :attr:`width` and :attr:`height` are that variant's own
    pixels, so the page reserves the photo's box before it arrives.

    :ivar media_id: The photo's id, for the report link
    :ivar src: The fallback URL
    :ivar srcset: Every variant's URL with its pixel width
    :ivar width: :attr:`src`'s width in pixels
    :ivar height: :attr:`src`'s height in pixels
    :ivar alt: The alt text in the page's locale, else the other locale's
    :ivar awaiting_review: Set only in the owner's own preview, for a photo
        moderation has not yet approved; a public page has none
    """

    model_config = _FROZEN

    media_id: uuid.UUID
    src: str
    srcset: str
    width: int
    height: int
    alt: str
    awaiting_review: bool = False


@register_view
class HubOwnerPage(BaseModel):
    """An owner's public page, in one locale.

    The headline and bio are the page locale's, falling back to the other
    locale's when the owner wrote only one.

    :ivar owner: The owner card
    :ivar headline: The headline
    :ivar bio: The biography
    :ivar qualifications: The qualifications
    :ivar teaching_mode: How the owner teaches
    :ivar street_address: A centre's address; always None for a tutor
    :ivar public_contact_phone: The number the owner chose to publish
    :ivar batches: The owner's published batches
    :ivar images: The owner's own approved photos, by position; never a
        batch's, which are on that batch's page only
    :ivar enquiry_open: Whether the page offers the "Ask to join" link:
        join requests are switched on and the owner accepts them
    """

    model_config = _FROZEN

    owner: HubOwnerCard
    headline: str | None
    bio: str | None
    qualifications: str | None
    teaching_mode: list[str]
    street_address: str | None
    public_contact_phone: str | None
    batches: list[HubBatchCard]
    images: list[HubImage]
    enquiry_open: bool


@register_view
class HubBatchPage(BaseModel):
    """A batch's public page, in one locale.

    The description and syllabus fall back across locales as the owner
    page's headline does.

    :ivar owner: The owner card
    :ivar batch: The batch card
    :ivar description: The description
    :ivar syllabus: The syllabus
    :ivar images: The batch's approved photos, by position
    :ivar reviews: The newest published reviews, at most
        :data:`~app.hub.public.ratings.MAX_REVIEWS`, newest month first then
        by id; empty below the threshold and while reviews are off
    :ivar enquiry_open: Whether the page offers the "Ask to join this
        class" link: join requests are switched on, the owner accepts them,
        and the batch's admissions are not ``closed``
    """

    model_config = _FROZEN

    owner: HubOwnerCard
    batch: HubBatchCard
    description: str | None
    syllabus: str | None
    images: list[HubImage]
    enquiry_open: bool
    reviews: list[HubReview] = []


class AreaOption(BaseModel):
    """One area the search form offers, by code, in both languages.

    :ivar code: The area code, as the ``district`` or ``upazila`` filter
        takes it
    :ivar en: The area's English name
    :ivar bn: The area's Bangla name
    """

    model_config = _FROZEN

    code: str
    en: str
    bn: str


class CityAreas(BaseModel):
    """A city corporation and the metropolitan thanas within it.

    :ivar city: The city corporation; choosing it covers all its thanas
    :ivar thanas: Its metropolitan thanas
    """

    model_config = _FROZEN

    city: AreaOption
    thanas: list[AreaOption]


class HubSearchFilters(BaseModel):
    """The structured filters a search applied.

    A filter that was blank, or a level outside the vocabulary, is None:
    it was ignored, so the echo does not claim otherwise.

    :ivar district: A district code
    :ivar upazila: An upazila, city corporation or metropolitan thana code
    :ivar subject: A subject tag
    :ivar level: A class level from the vocabulary
    """

    model_config = _FROZEN

    district: str | None
    upazila: str | None
    subject: str | None
    level: str | None


@register_view
class HubSearchPage(BaseModel):
    """One page of search results.

    The form's area choices come with it: every district, and once a
    district is chosen, that district's upazilas and city corporations,
    each city corporation with its metropolitan thanas. They are public
    reference data, the same for every reader.

    :ivar query: The query as typed, for the search box
    :ivar filters: The filters applied
    :ivar districts: Every district, for the district choice
    :ivar upazilas: The chosen district's upazilas, else empty
    :ivar cities: The chosen district's city corporations, else empty
    :ivar results: The owners on this page
    :ivar page: This page's number, from 1
    :ivar pages: How many pages there are, at least 1
    :ivar total: How many owners matched
    :ivar sort: ``rating`` when ordered by rating, else ``relevance``;
        always ``relevance`` while reviews are off
    :ivar offers_sort: Whether the form offers the sort choice: only while
        reviews are on
    """

    model_config = _FROZEN

    query: str | None
    filters: HubSearchFilters
    districts: list[AreaOption]
    upazilas: list[AreaOption]
    cities: list[CityAreas]
    results: list[HubOwnerCard]
    page: int
    pages: int
    total: int
    sort: Literal["relevance", "rating"] = "relevance"
    offers_sort: bool = False


class SitemapAlternate(BaseModel):
    """One language version of a sitemap URL.

    :ivar hreflang: ``en``, ``bn`` or ``x-default``
    :ivar href: The absolute URL
    """

    model_config = _FROZEN

    hreflang: str
    href: str


class SitemapUrl(BaseModel):
    """One page in the sitemap, with its language versions.

    :ivar loc: The absolute URL
    :ivar alternates: Every language version, this one included
    """

    model_config = _FROZEN

    loc: str
    alternates: list[SitemapAlternate]


@register_view
class HubSitemap(BaseModel):
    """Every public owner and batch page, in both locales.

    :ivar urls: The pages
    """

    model_config = _FROZEN

    urls: list[SitemapUrl]
