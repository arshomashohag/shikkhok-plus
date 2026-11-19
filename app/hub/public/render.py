"""Rendering the public hub's pages from registered view models.

**A page is rendered only from a model the privacy gate walks.**
:func:`page` and :func:`sitemap_xml` refuse any model not in
:func:`app.hub.public.registry.registered_views`, so a field can reach a
public page only by being on a model the gate has already checked against
the public forbidden set.

One Jinja2 environment, loaded once, with ``autoescape`` on and
``StrictUndefined``: every value is escaped on output, and a misspelt
variable is an error rather than an empty string on a cached page.

The one value inserted unescaped is the JSON-LD data block, which is
serialised here with ``<``, ``>`` and ``&`` written as JSON unicode escapes, so
no text an owner typed can close the ``<script>`` element it sits in.

The stylesheet's URL is computed from its content at import:
``/hub-assets/hub.<first 12 hex of its SHA-256>.css``. ``site/build.mjs``
copies the same file under the same name, and its test asserts the two
names agree.
"""

from __future__ import annotations

import functools
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, TypeVar
from urllib.parse import urlencode

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup
from pydantic import BaseModel

from app.hub.public.messages import LOCALES, MESSAGES, Locale, t
from app.hub.public.registry import registered_views
from app.hub.public.settings import site_url, web_app_url
from app.hub.public.views import (
    AreaOption,
    CityAreas,
    HubBatchCard,
    HubBatchPage,
    HubImage,
    HubOwnerCard,
    HubOwnerPage,
    HubReview,
    HubSearchPage,
    HubSitemap,
)

__all__ = [
    "STYLESHEET_FILE",
    "STYLESHEET_PATH",
    "not_found_page",
    "page",
    "sitemap_xml",
    "too_many_page",
]

_HERE: Final[Path] = Path(__file__).parent

#: The one stylesheet every hub page links.
STYLESHEET_FILE: Final[Path] = _HERE / "static" / "hub.css"

#: Its public URL, named by its content so a change is a new URL.
STYLESHEET_PATH: Final[str] = (
    "/hub-assets/hub."
    + hashlib.sha256(STYLESHEET_FILE.read_bytes()).hexdigest()[:12]
    + ".css"
)

#: The template each page model renders through. A model that is
#: registered but not listed here -- a card -- is not a page.
_PAGE_TEMPLATES: Final[dict[type[BaseModel], str]] = {
    HubOwnerPage: "owner.html",
    HubBatchPage: "batch.html",
    HubSearchPage: "search.html",
}

#: Weekday keys, Monday first, as ``PublicSlot.weekday`` counts.
_WEEKDAYS: Final[tuple[str, ...]] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

#: How much of a headline or description becomes the meta description.
_DESCRIPTION_LENGTH: Final[int] = 160

_ENV: Final[Environment] = Environment(
    loader=FileSystemLoader(_HERE / "templates"),
    autoescape=True,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)
_ENV.globals.update(t=t, locales=LOCALES, stylesheet=STYLESHEET_PATH)


#: What :func:`_helpers`' ``by_name`` sorts: area choices, or city
#: corporations with their thanas, each named by its own choice.
_Named = TypeVar("_Named", AreaOption, CityAreas)


def _option_of(item: AreaOption | CityAreas) -> AreaOption:
    """Find the area choice that names an item.

    :param item: An area choice, or a city corporation with its thanas
    :return: The choice itself, or the city corporation's
    """
    return item.city if isinstance(item, CityAreas) else item


@dataclass(frozen=True, slots=True)
class _Meta:
    """What a page's head and chrome say about it.

    :ivar title: The ``<title>``
    :ivar description: The meta description
    :ivar canonical: The page's absolute URL
    :ivar alternates: ``(hreflang, href)`` for en, bn and x-default
    :ivar other_locale: The twin page's locale
    :ivar other_href: The twin page's path, for the language switch
    :ivar noindex: Whether crawlers are asked not to index the page
    :ivar json_ld: The escaped JSON-LD block, or None
    :ivar report_href: The report form's URL for this page, or None
    """

    title: str
    description: str
    canonical: str
    alternates: tuple[tuple[str, str], ...]
    other_locale: Locale
    other_href: str
    noindex: bool
    json_ld: Markup | None
    report_href: str | None


def _require_registered(view: BaseModel) -> None:
    """Refuse a model the privacy gate does not walk.

    :param view: The model about to be rendered
    :return: None
    :raises TypeError: The model's class is not registered
    """
    if type(view) not in registered_views():
        msg = f"{type(view).__name__} is not a registered public view model"
        raise TypeError(msg)


def _json_ld(data: dict[str, Any]) -> Markup:
    """Serialise a JSON-LD block so it cannot end its ``<script>``.

    :param data: The structured data
    :return: The JSON text, safe to insert as is
    """
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for raw, escaped in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026")):
        text = text.replace(raw, escaped)
    return Markup(text)  # noqa: S704 -- every markup character is escaped above


def _area(card: HubOwnerCard, locale: Locale) -> str | None:
    """Name where an owner teaches, in the page's locale.

    :param card: The owner card
    :param locale: The page's locale
    :return: The area, or None when the owner gave none
    """
    if card.area_names is None:
        return None
    return (card.area_names.en if locale == "en" else card.area_names.bn) or None


def _summary(text: str | None, fallback: str) -> str:
    """Cut a text to a meta description's length.

    :param text: The owner's own text, or None
    :param fallback: What to say when there is none
    :return: The description
    """
    flat = " ".join((text or "").split())
    if not flat:
        return fallback
    if len(flat) <= _DESCRIPTION_LENGTH:
        return flat
    return flat[: _DESCRIPTION_LENGTH - 1].rstrip() + "…"


def _search_query(view: HubSearchPage, page_number: int) -> str:
    """Build a search page's query string from what the search applied.

    Only the allowlisted keys, in a fixed order, and only those set, so
    one search has one URL. ``sort`` is written only when it is ``rating``,
    which a search reports only while reviews are on.

    :param view: The search page
    :param page_number: The page to link to
    :return: ``?…``, or an empty string when nothing is set
    """
    pairs = [
        (key, value)
        for key, value in (
            ("q", view.query),
            ("district", view.filters.district),
            ("upazila", view.filters.upazila),
            ("subject", view.filters.subject),
            ("level", view.filters.level),
            ("sort", "rating" if view.sort == "rating" else None),
            ("page", str(page_number) if page_number > 1 else None),
        )
        if value
    ]
    return "?" + urlencode(pairs) if pairs else ""


def _links(path: str, locale: Locale) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Build a page's canonical URL and its language alternates.

    :param path: The path below ``/hub/{locale}``, with any query string
    :param locale: The page's locale
    :return: The canonical URL and ``(hreflang, href)`` pairs
    """
    origin = site_url()
    href = {each: f"{origin}/hub/{each}{path}" for each in LOCALES}
    alternates = (
        *((each, href[each]) for each in LOCALES),
        ("x-default", href["en"]),
    )
    return href[locale], alternates


def _report_href(kind: str, report_id: object) -> str:
    """Build the report form's URL for one listing, photo, review or reply.

    :param kind: ``owner_listing``, ``batch_listing``, ``media``, ``review``
        or ``reply``; a reply is reported by its review's id
    :param report_id: The id ``POST /v1/hub/reports`` expects [R2]
    :return: The URL on the web app
    """
    query = urlencode({"kind": kind, "id": str(report_id)})
    return f"{web_app_url()}/ui/hub-report?{query}"


def _ld_image(images: Sequence[HubImage]) -> str | None:
    """Name a page's first approved photo for its structured data.

    Its ``src`` -- the 960 variant, else the largest -- on the site's
    origin: a public page names it relative to the site, and the preview
    already names it there. A photo awaiting review, which only the preview
    shows, is never named.

    :param images: The page's photos, in order
    :return: The absolute URL, or None when there is no approved photo
    """
    for image in images:
        if not image.awaiting_review:
            src = image.src
            return site_url() + src if src.startswith("/") else src
    return None


def _owner_ld(view: HubOwnerPage, url: str, locale: Locale) -> dict[str, Any]:
    """Describe an owner as a schema.org ``EducationalOrganization``.

    :param view: The owner page
    :param url: The page's canonical URL
    :param locale: The page's locale
    :return: The structured data
    """
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "EducationalOrganization",
        "name": view.owner.public_name,
        "url": url,
    }
    if view.headline:
        data["description"] = view.headline
    image = _ld_image(view.images)
    if image:
        data["image"] = image
    if view.public_contact_phone:
        data["telephone"] = view.public_contact_phone
    area = _area(view.owner, locale)
    if area or view.street_address:
        address: dict[str, str] = {"@type": "PostalAddress", "addressCountry": "BD"}
        if area:
            address["addressLocality"] = area
        if view.street_address:
            address["streetAddress"] = view.street_address
        data["address"] = address
    return data


def _meta(view: BaseModel, locale: Locale, *, preview: bool) -> _Meta:
    """Work out a page's head, links and structured data.

    :param view: An owner, batch or search page
    :param locale: The page's locale
    :param preview: Whether this is the owner's own preview
    :return: The page's meta
    """
    other: Locale = "bn" if locale == "en" else "en"

    def m(key: str, **fields: object) -> str:
        """Look up one message in the page's locale.

        :param key: The message key
        :param fields: The message's fields
        :return: The text
        """
        return t(key, locale, **fields)

    hub = m("hub_name")
    json_ld: Markup | None = None
    report: str | None = None
    if isinstance(view, HubOwnerPage):
        owner = view.owner
        path = f"/t/{owner.slug}"
        canonical, alternates = _links(path, locale)
        title = f"{owner.public_name} · {hub}"
        fallback = m("owner_description", name=owner.public_name)
        description = _summary(view.headline or view.bio, fallback)
        json_ld = _json_ld(_owner_ld(view, canonical, locale))
        report = _report_href("owner_listing", owner.report_id)
        noindex = preview
    elif isinstance(view, HubBatchPage):
        owner, batch = view.owner, view.batch
        path = f"/t/{owner.slug}/{batch.slug}"
        canonical, alternates = _links(path, locale)
        owner_url, _ = _links(f"/t/{owner.slug}", locale)
        title = f"{batch.public_title} · {owner.public_name} · {hub}"
        fallback = m(
            "batch_description", title=batch.public_title, name=owner.public_name
        )
        description = _summary(view.description, fallback)
        course: dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "Course",
            "name": batch.public_title,
            "url": canonical,
            "provider": {
                "@type": "EducationalOrganization",
                "name": owner.public_name,
                "url": owner_url,
            },
        }
        if view.description:
            course["description"] = view.description
        image = _ld_image(view.images)
        if image:
            course["image"] = image
        json_ld = _json_ld(course)
        report = _report_href("batch_listing", batch.report_id)
        noindex = preview
    elif isinstance(view, HubSearchPage):
        path = _search_query(view, view.page)
        canonical, alternates = _links(path, locale)
        title = f"{m('search_title')} · {hub}"
        description = m("search_description")
        noindex = True
    else:
        msg = f"{type(view).__name__} is not a page"
        raise ValueError(msg)
    return _Meta(
        title=title,
        description=description,
        canonical=canonical,
        alternates=alternates,
        other_locale=other,
        other_href=f"/hub/{other}{path}",
        noindex=noindex,
        json_ld=json_ld,
        report_href=report,
    )


def _helpers(locale: Locale) -> dict[str, Any]:
    """Build the functions a page template calls, bound to its locale.

    :param locale: The page's locale
    :return: The template's helper functions
    """

    def m(key: str, **fields: object) -> str:
        """Look up one message in the page's locale.

        :param key: The message key
        :param fields: The message's fields
        :return: The text
        """
        return t(key, locale, **fields)

    def label(prefix: str, value: str) -> str:
        """Name one vocabulary value, or show it as stored if unknown.

        :param prefix: The vocabulary's key prefix, e.g. ``hub_level_``
        :param value: The stored value
        :return: The label
        """
        key = f"{prefix}{value}"
        return t(key, locale) if key in MESSAGES else value

    def labels(prefix: str, values: list[str]) -> str:
        """Name several vocabulary values, comma separated.

        :param prefix: The vocabulary's key prefix
        :param values: The stored values
        :return: The labels
        """
        return ", ".join(label(prefix, value) for value in values)

    def weekday(number: int) -> str:
        """Name a weekday, Monday as 0.

        :param number: The weekday
        :return: Its short name
        """
        return t(f"weekday_{_WEEKDAYS[number]}", locale)

    def area(card: HubOwnerCard) -> str | None:
        """Name where an owner teaches.

        :param card: The owner card
        :return: The area, or None
        """
        return _area(card, locale)

    def area_name(option: AreaOption) -> str:
        """Name an area choice in the page's locale.

        :param option: The choice
        :return: Its name
        """
        return option.en if locale == "en" else option.bn

    def by_name(options: Sequence[_Named]) -> list[_Named]:
        """Order area choices by their name in the page's locale.

        :param options: Area choices, or city corporations with their thanas
        :return: The same, sorted
        """
        return sorted(options, key=lambda item: area_name(_option_of(item)))

    def report_photo(image: HubImage) -> str:
        """Build the report form's URL for one photo.

        :param image: The photo
        :return: The URL, ``kind=media`` with the photo's id
        """
        return _report_href("media", image.media_id)

    def report_review(review: HubReview) -> str:
        """Build the report form's URL for one review.

        :param review: The review
        :return: The URL, ``kind=review`` with the review's id
        """
        return _report_href("review", review.review_id)

    def report_reply(review: HubReview) -> str:
        """Build the report form's URL for a review's reply.

        :param review: The review the reply answers
        :return: The URL, ``kind=reply`` with the review's id
        """
        return _report_href("reply", review.review_id)

    def title(batch: HubBatchCard) -> str:
        """Name a batch by its public title, never by ``batch.name``.

        :param batch: The batch card
        :return: Its title, or a placeholder while a draft has none
        """
        return batch.public_title or t("batch_untitled", locale)

    return {
        "m": m,
        "label": label,
        "labels": labels,
        "weekday": weekday,
        "area": area,
        "area_name": area_name,
        "by_name": by_name,
        "report_photo": report_photo,
        "report_review": report_review,
        "report_reply": report_reply,
        "title": title,
    }


def _search_context(view: HubSearchPage, locale: Locale) -> dict[str, Any]:
    """Build what only the search page needs: its filters and its pager.

    A district or area the form's choices already show is carried by its
    select; any other applied filter rides along as a hidden input, so
    searching again from the box keeps it.

    :param view: The search page
    :param locale: The page's locale
    :return: The extra template context
    """
    base = f"/hub/{locale}"
    shown = {
        "district": {area.code for area in view.districts},
        "upazila": {area.code for area in view.upazilas}
        | {area.code for city in view.cities for area in (city.city, *city.thanas)},
    }
    applied = {
        key: value
        for key, value in view.filters.model_dump().items()
        if value is not None
    }
    hidden = [
        (key, value)
        for key, value in applied.items()
        if value not in shown.get(key, set())
    ]
    # Clearing the filters keeps what was typed and how it is sorted.
    kept = [
        (key, value)
        for key, value in (
            ("q", view.query),
            ("sort", "rating" if view.sort == "rating" else None),
        )
        if value
    ]
    clear = base + ("?" + urlencode(kept) if kept else "")
    # Past the end, "previous" is the last page that has results.
    previous = min(view.page - 1, view.pages) if view.page > 1 else None
    following = view.page + 1 if view.page < view.pages else None
    return {
        "hidden_filters": hidden,
        "filtered": bool(applied),
        "clear_href": clear,
        "previous_href": None
        if previous is None
        else base + _search_query(view, previous),
        "next_href": None
        if following is None
        else base + _search_query(view, following),
    }


def page(
    view: BaseModel, template: str, locale: Locale, *, preview: bool = False
) -> str:
    """Render a public page from its registered view model.

    :param view: An owner, batch or search page model
    :param template: The page's template, which must be its model's
    :param locale: The page's locale
    :param preview: Render the owner's own preview: a banner, noindex, and
        the stylesheet named on the site's origin, since the preview is shown
        on the app host, which serves no ``/hub-assets/`` [R11]
    :return: The HTML
    :raises TypeError: The model is not registered with the privacy gate
    :raises ValueError: The model is not a page, or not this template's
    """
    _require_registered(view)
    if _PAGE_TEMPLATES.get(type(view)) != template:
        msg = f"{type(view).__name__} does not render through {template}"
        raise ValueError(msg)
    context: dict[str, Any] = {
        "view": view,
        "locale": locale,
        "meta": _meta(view, locale, preview=preview),
        "preview": preview,
        **_helpers(locale),
    }
    if preview:
        context["stylesheet"] = site_url() + STYLESHEET_PATH
    if isinstance(view, HubSearchPage):
        context.update(_search_context(view, locale))
    return _ENV.get_template(template).render(context)


def sitemap_xml(view: HubSitemap) -> str:
    """Render the sitemap from its registered view model.

    :param view: The sitemap
    :return: The XML
    :raises TypeError: The model is not registered with the privacy gate
    """
    _require_registered(view)
    return _ENV.get_template("sitemap.xml").render(view=view)


@functools.cache
def not_found_page() -> str:
    """Render the one 404 page every hidden or missing page answers.

    Built once and echoing nothing from the request -- no locale, no slug
    -- so a draft, a suspended listing and a slug nobody ever used are
    indistinguishable byte for byte.

    :return: The HTML
    """
    return _ENV.get_template("not_found.html").render()


@functools.cache
def too_many_page() -> str:
    """Render the page a read over the per-network ceiling answers.

    :return: The HTML
    """
    return _ENV.get_template("too_many.html").render()
