"""The public hub pages, served: search, owner, batch, sitemap, and the preview.

Every request goes through the real application against the restricted
database role. Rows are arranged as the table owner, so the only grants a
page exercises are the hub reader's (public pages) and the application
role's (the owner's preview).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
import uuid
from html.parser import HTMLParser
from typing import Final

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.html import HUB_PAGE_CSP
from app.auth.ceilings import (
    HUB_PUBLIC_READ_IP_MINUTE,
    CeilingBreach,
    CeilingChecker,
)
from app.hub.public import render
from app.hub.public.messages import MESSAGES, t
from app.hub.public.settings import SITE_URL_ENV, WEB_APP_URL_ENV
from app.hub.public.views import HubOwnerCard
from tests.batches.conftest import make_teacher
from tests.conftest import bearer
from tests.hub.support import add_member, areas, assign_slot, centre_with_manager

SITE: Final[str] = "https://site.example.test"
WEB_APP: Final[str] = "https://app.example.test"

#: What each kind of public page is cached for, verbatim.
OWNER_OR_BATCH_CACHE: Final[str] = "public, max-age=60, s-maxage=600"
SEARCH_CACHE: Final[str] = "public, max-age=60, s-maxage=300"
SITEMAP_CACHE: Final[str] = "public, s-maxage=3600"
NOT_FOUND_CACHE: Final[str] = "public, s-maxage=60"

#: The page CSP, verbatim from the plan's global constraints.
PAGE_CSP: Final[str] = (
    "default-src 'none'; style-src 'self'; img-src 'self'; font-src 'self'; "
    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)

#: Dhaka district, its northern city corporation, and Mirpur within it.
DHAKA: Final[str] = "BD3026"
DNCC: Final[str] = "BD30262500"
MIRPUR: Final[str] = "MT3026250003"

#: One ``<option>``: its value, whether it is selected, and its text.
_OPTION: Final[re.Pattern[str]] = re.compile(
    r'<option value="([^"]*)"( selected)?>([^<]*)</option>'
)

#: The public name carries markup, so escaping is exercised on every page.
TUTOR_NAME: Final[str] = "Rahim <Sir> & Co"


def _owner_listing(
    session: Session,
    owner_id: uuid.UUID,
    *,
    slug: str,
    status: str = "published",
    name: str = TUTOR_NAME,
) -> None:
    """Insert one owner listing.

    :param session: An arranging session
    :param owner_id: The owner
    :param slug: The slug
    :param status: The listing status
    :param name: The public name
    :return: None
    """
    district, upazila, _ = areas(session)
    session.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, slug, status, public_name, "
            "headline_en, headline_bn, bio_en, qualifications, district_code, "
            "upazila_code, public_contact_phone, published_at) VALUES "
            "(:o, :slug, CAST(:st AS hub_listing_status), :name, "
            "'Maths for SSC', 'এসএসসির গণিত', 'Teaching since 2010', 'MSc', "
            ":d, :u, '+8801711000000', now())"
        ),
        {
            "o": owner_id,
            "slug": slug,
            "st": status,
            "name": name,
            "d": district,
            "u": upazila,
        },
    )
    session.commit()


def _batch_listing(
    session: Session,
    batch_id: uuid.UUID,
    owner_id: uuid.UUID,
    *,
    slug: str = "class-9-maths",
    status: str = "published",
    title: str | None = "Class 9 maths",
) -> None:
    """Insert one batch listing that shows its fee.

    :param session: An arranging session
    :param batch_id: The batch
    :param owner_id: The batch's owner
    :param slug: The slug
    :param status: The listing status
    :param title: The public title
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO batch_listing (batch_id, owner_id, slug, status, "
            "public_title, description_en, class_levels, subject_tags, mode, "
            "show_fee, show_schedule, published_at) VALUES "
            "(:b, :o, :slug, CAST(:st AS hub_listing_status), :title, "
            "'Weekly practice', ARRAY['class_9']::varchar[], "
            "ARRAY['maths']::varchar[], 'in_person', true, true, now())"
        ),
        {"b": batch_id, "o": owner_id, "slug": slug, "st": status, "title": title},
    )
    session.commit()


def _new_batch(
    session: Session, owner_id: uuid.UUID, *, active: bool = True
) -> uuid.UUID:
    """Give an owner one more batch, with a private name.

    :param session: An arranging session
    :param owner_id: The owner
    :param active: Whether the batch runs
    :return: The batch id
    """
    return session.execute(
        sa.text(
            "INSERT INTO batch (id, owner_id, name, default_fee, fee_due_day, "
            "marksheet_visible, active, created_at) VALUES (gen_random_uuid(), "
            ":o, 'Private batch name', 1500.00, 10, true, :a, now()) RETURNING id"
        ),
        {"o": owner_id, "a": active},
    ).scalar_one()


def _published_tutor(session: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Arrange the published tutor with one published batch.

    :param session: An arranging session
    :return: ``(account_id, owner_id, batch_id)``
    """
    teacher = make_teacher(session, name="Private batch name")
    _owner_listing(session, teacher.owner_id, slug="rahim-sir")
    _batch_listing(session, teacher.batch_id, teacher.owner_id)
    return teacher.account_id, teacher.owner_id, teacher.batch_id


def _hidden_world(session: Session, owner_id: uuid.UUID) -> None:
    """Arrange every shape that must not be public.

    Under the published tutor: a draft batch, a hidden batch, a suspended
    batch and a published listing on an inactive batch. Elsewhere: a draft
    owner, a hidden owner and a suspended owner, and a published batch
    under the draft owner.

    :param session: An arranging session
    :param owner_id: The published tutor
    :return: None
    """
    for slug, status in (
        ("draft-batch", "draft"),
        ("hidden-batch", "hidden"),
        ("suspended-batch", "suspended"),
    ):
        _batch_listing(
            session, _new_batch(session, owner_id), owner_id, slug=slug, status=status
        )
    _batch_listing(
        session,
        _new_batch(session, owner_id, active=False),
        owner_id,
        slug="inactive-batch",
    )
    for slug, status in (
        ("draft-owner", "draft"),
        ("hidden-owner", "hidden"),
        ("suspended-owner", "suspended"),
    ):
        other = make_teacher(session)
        _owner_listing(session, other.owner_id, slug=slug, status=status)
        _batch_listing(session, other.batch_id, other.owner_id, slug="orphan-batch")


def _client(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Point the page settings at distinctive origins.

    :param api_client: The test client
    :param monkeypatch: The patcher
    :return: The same client
    """
    monkeypatch.setenv(SITE_URL_ENV, SITE)
    monkeypatch.setenv(WEB_APP_URL_ENV, WEB_APP)
    return api_client


class _Page(HTMLParser):
    """Collect what the page tests look at, as a browser would parse it."""

    def __init__(self) -> None:
        """Start empty."""
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.scripts: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record a start tag.

        :param tag: The tag name
        :param attrs: Its attributes
        :return: None
        """
        self.tags.append((tag, dict(attrs)))
        self._in_script = tag == "script"
        if self._in_script:
            self.scripts.append("")

    def handle_endtag(self, tag: str) -> None:
        """Leave a script.

        :param tag: The tag name
        :return: None
        """
        if tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        """Keep a script's text.

        :param data: The text
        :return: None
        """
        if self._in_script:
            self.scripts[-1] += data

    def find(self, tag: str, **wanted: str) -> list[dict[str, str | None]]:
        """List the attributes of every matching tag.

        :param tag: The tag name
        :param wanted: Attribute values that must match
        :return: The matching tags' attributes
        """
        return [
            attrs
            for name, attrs in self.tags
            if name == tag and all(attrs.get(k) == v for k, v in wanted.items())
        ]


def _parse(body: str) -> _Page:
    """Parse a page.

    :param body: The HTML
    :return: The parsed page
    """
    page = _Page()
    page.feed(body)
    page.close()
    return page


def _public_paths() -> list[str]:
    """List the four public pages in both locales.

    :return: The paths
    """
    return [
        path
        for locale in ("en", "bn")
        for path in (
            f"/hub/{locale}",
            f"/hub/{locale}?q=maths",
            f"/hub/{locale}?district={DHAKA}&upazila={MIRPUR}",
            f"/hub/{locale}/t/rahim-sir",
            f"/hub/{locale}/t/rahim-sir/class-9-maths",
        )
    ]


def test_four_public_routes_render_both_locales(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each page answers 200 in English and in Bangla, in its own language."""
    client = _client(api_client, monkeypatch)
    _published_tutor(owner_session)

    for locale in ("en", "bn"):
        search = client.get(f"/hub/{locale}?q=maths")
        owner = client.get(f"/hub/{locale}/t/rahim-sir")
        batch = client.get(f"/hub/{locale}/t/rahim-sir/class-9-maths")
        for response in (search, owner, batch):
            assert response.status_code == 200, response.text
            assert response.headers["content-type"].startswith("text/html")
            assert f'<html lang="{locale}">' in response.text
            assert "Rahim &lt;Sir&gt; &amp; Co" in response.text
            assert TUTOR_NAME not in response.text
            assert render.STYLESHEET_PATH in response.text
        assert t("search_title", locale) in search.text
        assert "Class 9 maths" in owner.text and "Class 9 maths" in batch.text
        assert "Private batch name" not in owner.text + batch.text
        assert t("hub_level_class_9", locale) in batch.text
        headline = "Maths for SSC" if locale == "en" else "এসএসসির গণিত"
        assert headline in owner.text
        assert "+8801711000000" in owner.text

    sitemap = client.get("/hub/sitemap.xml")
    assert sitemap.status_code == 200
    assert sitemap.headers["content-type"].startswith("application/xml")
    assert f"<loc>{SITE}/hub/bn/t/rahim-sir/class-9-maths</loc>" in sitemap.text
    assert sitemap.text.startswith('<?xml version="1.0" encoding="UTF-8"?>')


def test_unknown_locale_and_missing_slug_return_byte_identical_404(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every page that is not public answers the same bytes, echoing nothing."""
    client = _client(api_client, monkeypatch)
    _, owner_id, _ = _published_tutor(owner_session)
    _hidden_world(owner_session, owner_id)

    paths = [
        "/hub/fr",
        "/hub/EN",
        "/hub/fr/t/rahim-sir",
        "/hub/fr/t/rahim-sir/class-9-maths",
        "/hub/en/t/no-such-owner",
        "/hub/en/t/no-such-owner/class-9-maths",
        "/hub/en/t/rahim-sir/no-such-batch",
        "/hub/bn/t/rahim-sir/draft-batch",
        "/hub/en/t/rahim-sir/hidden-batch",
        "/hub/en/t/rahim-sir/suspended-batch",
        "/hub/en/t/rahim-sir/inactive-batch",
        "/hub/en/t/draft-owner",
        "/hub/bn/t/hidden-owner",
        "/hub/en/t/suspended-owner",
        "/hub/en/t/draft-owner/orphan-batch",
        "/hub/en/t/suspended-owner/orphan-batch",
    ]
    bodies = set()
    for path in paths:
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.headers["cache-control"] == NOT_FOUND_CACHE, path
        assert response.headers["content-security-policy"] == PAGE_CSP, path
        assert response.headers["content-type"].startswith("text/html"), path
        bodies.add(response.content)
    assert len(bodies) == 1
    (body,) = bodies
    for echoed in ("fr", "no-such", "draft-", "hidden-", "orphan", "suspended"):
        assert echoed.encode() not in body
    assert body == render.not_found_page().encode()


def test_cache_control_headers_exact(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each page carries exactly its row of the Cache-Control table."""
    client = _client(api_client, monkeypatch)
    _published_tutor(owner_session)

    expected = {
        "/hub/en": SEARCH_CACHE,
        "/hub/bn?q=maths&page=2": SEARCH_CACHE,
        "/hub/en/t/rahim-sir": OWNER_OR_BATCH_CACHE,
        "/hub/bn/t/rahim-sir/class-9-maths": OWNER_OR_BATCH_CACHE,
        "/hub/sitemap.xml": SITEMAP_CACHE,
        "/hub/en/t/nobody": NOT_FOUND_CACHE,
    }
    for path, header in expected.items():
        response = client.get(path)
        assert response.headers["cache-control"] == header, path
        assert response.headers.get_list("cache-control") == [header], path


def test_csp_exact_and_no_script_or_inline_style(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every page carries the page CSP and nothing a browser would run."""
    client = _client(api_client, monkeypatch)
    account, _, _ = _published_tutor(owner_session)
    preview = client.get(
        "/v1/hub/listing/preview?locale=en", headers=bearer(owner_session, account)
    )
    responses = [client.get(path) for path in [*_public_paths(), "/hub/en/t/x"]]
    responses.append(preview)

    assert HUB_PAGE_CSP == PAGE_CSP
    for response in responses:
        # The preview is shown on the app host, which serves no
        # /hub-assets/, so only it names the site's origin [R11].
        stylesheet = render.STYLESHEET_PATH
        if response is preview:
            stylesheet = SITE + render.STYLESHEET_PATH
        assert response.headers["content-security-policy"] == PAGE_CSP
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        page = _parse(response.text)
        assert page.find("style") == []
        for tag, attrs in page.tags:
            if tag == "script":
                assert attrs == {"type": "application/ld+json"}
            assert "style" not in attrs, tag
            assert not [name for name in attrs if name.startswith("on")], tag
        stylesheets = page.find("link", rel="stylesheet")
        assert stylesheets == [{"rel": "stylesheet", "href": stylesheet}]


def test_unknown_query_keys_are_ignored(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the six allowlisted keys reach the page, each at its first value."""
    client = _client(api_client, monkeypatch)
    _published_tutor(owner_session)

    plain = client.get("/hub/en?q=maths").content
    assert b"rahim-sir" in plain
    assert client.get("/hub/en?q=maths&utm_source=x&fbclid=y").content == plain
    assert client.get("/hub/en?utm_source=x&q=maths").content == plain
    assert client.get("/hub/en?q=maths&q=zzzz").content == plain
    assert b"rahim-sir" not in client.get("/hub/en?q=zzzz&q=maths").content

    capped = client.get("/hub/en?q=" + "a" * 200).content
    assert client.get("/hub/en?q=" + "a" * 5000).content == capped
    assert ("a" * 201).encode() not in capped

    for junk in ("page=-3", "page=abc", "page=" + "9" * 50, "page=১"):
        assert client.get(f"/hub/en?{junk}").status_code == 200, junk


def _links(page: _Page) -> dict[str, str | None]:
    """Map each alternate's hreflang, and the canonical, to its href.

    :param page: A parsed page
    :return: ``hreflang`` (or ``canonical``) to href
    """
    found: dict[str, str | None] = {
        str(attrs["hreflang"]): attrs["href"]
        for attrs in page.find("link", rel="alternate")
    }
    (canonical,) = page.find("link", rel="canonical")
    found["canonical"] = canonical["href"]
    return found


def test_hreflang_pairs_and_canonical(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each page links itself and its twin, with English as the default."""
    client = _client(api_client, monkeypatch)
    _, owner_id, batch_id = _published_tutor(owner_session)

    for locale in ("en", "bn"):
        for path, kind, report_id in (
            ("/t/rahim-sir", "owner_listing", owner_id),
            ("/t/rahim-sir/class-9-maths", "batch_listing", batch_id),
        ):
            page = _parse(client.get(f"/hub/{locale}{path}").text)
            assert _links(page) == {
                "canonical": f"{SITE}/hub/{locale}{path}",
                "en": f"{SITE}/hub/en{path}",
                "bn": f"{SITE}/hub/bn{path}",
                "x-default": f"{SITE}/hub/en{path}",
            }
            report = f"{WEB_APP}/ui/hub-report?kind={kind}&id={report_id}"
            assert page.find("a", href=report), (locale, path)
            assert page.find("meta", name="robots") == []

        search = _parse(client.get(f"/hub/{locale}").text)
        assert _links(search) == {
            "canonical": f"{SITE}/hub/{locale}",
            "en": f"{SITE}/hub/en",
            "bn": f"{SITE}/hub/bn",
            "x-default": f"{SITE}/hub/en",
        }
        assert search.find("meta", name="robots", content="noindex")
        for attrs in search.find("meta", name="description"):
            assert attrs["content"]
        assert search.find("title")


def test_no_aggregate_rating_markup(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The JSON-LD names the owner or the course, escaped, and rates nothing."""
    client = _client(api_client, monkeypatch)
    _published_tutor(owner_session)

    expected = {
        "/t/rahim-sir": "EducationalOrganization",
        "/t/rahim-sir/class-9-maths": "Course",
    }
    for locale in ("en", "bn"):
        for path in _public_paths():
            assert "aggregaterating" not in client.get(path).text.lower()
        for path, kind in expected.items():
            body = client.get(f"/hub/{locale}{path}").text
            (script,) = _parse(body).scripts
            assert "<" not in script
            data = json.loads(script)
            assert data["@context"] == "https://schema.org"
            assert data["@type"] == kind
            assert data["url"] == f"{SITE}/hub/{locale}{path}"
            named = data["name"] if kind != "Course" else data["provider"]["name"]
            assert named == TUTOR_NAME
            assert "aggregateRating" not in json.dumps(data)
    assert _parse(client.get("/hub/en").text).scripts == []


def test_preview_shows_draft_with_banner_and_no_store(
    api_client: TestClient, owner_session: Session
) -> None:
    """The owner sees their draft, batches included, marked as not public."""
    teacher = make_teacher(owner_session, name="Private batch name")
    _owner_listing(owner_session, teacher.owner_id, slug="draft-tutor", status="draft")
    _batch_listing(
        owner_session,
        teacher.batch_id,
        teacher.owner_id,
        status="draft",
        title="Draft physics",
    )
    _batch_listing(
        owner_session,
        _new_batch(owner_session, teacher.owner_id, active=False),
        teacher.owner_id,
        slug="retired",
        title="Retired batch",
    )
    headers = bearer(owner_session, teacher.account_id)

    for locale, banner in (
        ("en", "Preview — not public yet"),
        ("bn", "প্রিভিউ — এখনও প্রকাশিত নয়"),
    ):
        response = api_client.get(
            f"/v1/hub/listing/preview?locale={locale}", headers=headers
        )
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["content-security-policy"] == PAGE_CSP
        assert banner in response.text
        assert "Draft physics" in response.text
        assert "Rahim &lt;Sir&gt; &amp; Co" in response.text
        assert "Private batch name" not in response.text
        assert "Retired batch" not in response.text
        assert _parse(response.text).find("meta", name="robots", content="noindex")

    assert api_client.get("/hub/en/t/draft-tutor").status_code == 404


def test_preview_links_its_stylesheet_on_the_site_origin(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The preview names the stylesheet absolutely; public pages do not.

    The preview is displayed on the app host -- a sandboxed frame on the
    web, a WebView on Android -- and the app host serves no /hub-assets/,
    so a relative link would leave the preview unstyled [R11]. Public
    pages stay relative, which ``style-src 'self'`` covers on the site.
    """
    client = _client(api_client, monkeypatch)
    account, _, _ = _published_tutor(owner_session)

    preview = client.get(
        "/v1/hub/listing/preview?locale=bn", headers=bearer(owner_session, account)
    )
    public = client.get("/hub/bn/t/rahim-sir")
    assert public.status_code == 200, public.text

    assert preview.status_code == 200, preview.text
    assert _parse(preview.text).find("link", rel="stylesheet") == [
        {"rel": "stylesheet", "href": f"{SITE}{render.STYLESHEET_PATH}"}
    ]
    assert _parse(public.text).find("link", rel="stylesheet") == [
        {"rel": "stylesheet", "href": render.STYLESHEET_PATH}
    ]


def test_preview_names_only_consented_centre_teachers(
    api_client: TestClient, owner_session: Session
) -> None:
    """A centre's preview names nobody who did not agree to be named."""
    centre = centre_with_manager(owner_session, name="Udoy Coaching")
    member, _ = add_member(owner_session, centre.owner_id, name="Karim Unconsented")
    assign_slot(owner_session, centre.batch_id, member)
    _owner_listing(
        owner_session, centre.owner_id, slug="udoy", status="draft", name="Udoy"
    )
    _batch_listing(owner_session, centre.batch_id, centre.owner_id, status="draft")
    headers = bearer(owner_session, centre.manager_account_id)
    headers["X-Workspace-Id"] = str(centre.owner_id)

    for locale in ("en", "bn"):
        response = api_client.get(
            f"/v1/hub/listing/preview?locale={locale}", headers=headers
        )
        assert response.status_code == 200, response.text
        assert "Karim Unconsented" not in response.text
        assert t("centre_faculty", locale) in response.text
        assert "+88018" not in response.text


def test_preview_refuses_other_owner_and_class_teacher(
    api_client: TestClient, owner_session: Session
) -> None:
    """Neither another owner nor a centre's class teacher can preview a page."""
    mine = make_teacher(owner_session)
    _owner_listing(
        owner_session, mine.owner_id, slug="mine", status="draft", name="Mine"
    )
    theirs = make_teacher(owner_session)
    _owner_listing(
        owner_session,
        theirs.owner_id,
        slug="theirs",
        status="draft",
        name="Theirs Secret",
    )
    centre = centre_with_manager(owner_session)
    _owner_listing(
        owner_session,
        centre.owner_id,
        slug="centre",
        status="draft",
        name="Centre Secret",
    )
    _, class_teacher = add_member(
        owner_session, centre.owner_id, role="teacher", name="Karim"
    )

    other = bearer(owner_session, mine.account_id)
    other["X-Workspace-Id"] = str(theirs.owner_id)
    response = api_client.get("/v1/hub/listing/preview", headers=other)
    assert response.status_code == 403
    assert "Theirs Secret" not in response.text

    teacher = bearer(owner_session, class_teacher)
    assert api_client.get("/v1/hub/listing/preview", headers=teacher).status_code == 403
    teacher["X-Workspace-Id"] = str(centre.owner_id)
    response = api_client.get("/v1/hub/listing/preview", headers=teacher)
    assert response.status_code == 403
    assert "Centre Secret" not in response.text

    assert api_client.get("/v1/hub/listing/preview").status_code == 401


def test_public_read_ceiling_120_per_minute(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 121st read in a minute from one address is refused with a page."""
    assert HUB_PUBLIC_READ_IP_MINUTE == 120
    moment = dt.datetime(2026, 11, 17, 9, 30, 15, tzinfo=dt.UTC)
    checker = CeilingChecker(restricted_session)
    for _ in range(120):
        checker.check_and_consume_hub_public_read("203.0.113.0/24", moment)
    with pytest.raises(CeilingBreach):
        checker.check_and_consume_hub_public_read("203.0.113.0/24", moment)
    checker.check_and_consume_hub_public_read(
        "203.0.113.0/24", moment + dt.timedelta(minutes=1)
    )
    checker.check_and_consume_hub_public_read("198.51.100.0/24", moment)

    client = _client(api_client, monkeypatch)
    _published_tutor(owner_session)
    # Keep the seeded window and the requests inside one wall-clock minute.
    second = dt.datetime.now(tz=dt.UTC).second
    if second >= 50:
        time.sleep(61 - second)
    window = dt.datetime.now(tz=dt.UTC).replace(second=0, microsecond=0)
    owner_session.execute(
        sa.text(
            "INSERT INTO rate_limit_counter (id, scope_kind, scope_value, "
            "window_start, count) VALUES (gen_random_uuid(), 'hub_read_min', "
            "'192.0.2.0/24', :w, 119)"
        ),
        {"w": window},
    )
    owner_session.commit()
    viewer = {"CloudFront-Viewer-Address": "192.0.2.7:46532"}

    assert client.get("/hub/en/t/rahim-sir", headers=viewer).status_code == 200
    refused = client.get("/hub/en/t/rahim-sir", headers=viewer)
    assert refused.status_code == 429
    assert refused.headers["content-type"].startswith("text/html")
    assert refused.headers["content-security-policy"] == PAGE_CSP
    assert refused.headers["cache-control"] == "no-store"
    assert refused.text == render.too_many_page()
    assert client.get("/hub/sitemap.xml", headers=viewer).status_code == 429
    other = {"CloudFront-Viewer-Address": "2001:db8:1:2::9:443"}
    assert client.get("/hub/en/t/rahim-sir", headers=other).status_code == 200


def test_render_refuses_an_unregistered_view() -> None:
    """A model the privacy gate does not walk can never become a page."""
    from pydantic import BaseModel

    class Unregistered(BaseModel):
        """Not registered."""

        slug: str

    with pytest.raises(TypeError):
        render.page(Unregistered(slug="x"), "owner.html", "en")
    card = HubOwnerCard(
        report_id=uuid.uuid4(),
        slug="x",
        public_name="x",
        kind="teacher",
        area_names=None,
        runs_classes=False,
    )
    with pytest.raises(ValueError):
        render.page(card, "owner.html", "en")


def test_stylesheet_path_is_the_content_hash() -> None:
    """The stylesheet's URL names the first twelve hex of its SHA-256."""
    import hashlib

    digest = hashlib.sha256(render.STYLESHEET_FILE.read_bytes()).hexdigest()
    assert render.STYLESHEET_PATH == f"/hub-assets/hub.{digest[:12]}.css"
    css = render.STYLESHEET_FILE.read_text(encoding="utf-8")
    assert "@font-face" not in css
    assert '"Noto Sans Bengali", "Noto Sans", system-ui, sans-serif' in css
    assert "overflow-wrap: anywhere" in css


def test_vocabulary_labels_match_the_app_bundles() -> None:
    """Each label the pages share with the apps reads the same in both."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "web" / "src" / "i18n" / "generated"
    shared = (
        "hub_level_",
        "hub_mode_",
        "hub_batch_admissions_",
        "hub_curriculum_",
        "weekday_",
    )
    keys = [key for key in MESSAGES if key.startswith(shared)]
    assert len(keys) == 18 + 3 + 3 + 5 + 7
    for locale in ("en", "bn"):
        bundle = json.loads(
            (root / f"strings.{locale}.json").read_text(encoding="utf-8")
        )
        for key in keys:
            assert MESSAGES[key][locale] == bundle[key], (locale, key)


def _select(body: str, name: str) -> list[tuple[str, bool, str]]:
    """Read one select's options, in order.

    :param body: The page
    :param name: The select's ``name``
    :return: ``(value, selected, text)`` per option; empty when absent
    """
    found = re.search(rf'<select id="{name}" name="{name}">(.*?)</select>', body, re.S)
    if found is None:
        return []
    return [(v, bool(sel), text) for v, sel, text in _OPTION.findall(found[1])]


def test_search_form_chooses_a_district_then_an_area(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The form offers every district, then the chosen district's areas [R12].

    Both choices are plain selects in the GET form, so they work with no
    script; each keeps the reader's choice, and a filter no select shows
    rides along as a hidden input.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param monkeypatch: The patcher
    :return: None
    """
    client = _client(api_client, monkeypatch)
    _published_tutor(owner_session)

    for locale, dhaka in (("en", "Dhaka"), ("bn", "ঢাকা")):
        body = client.get(f"/hub/{locale}").text
        districts = _select(body, "district")
        assert districts[0] == ("", False, t("search_any_district", locale))
        names = [text for _, _, text in districts[1:]]
        assert len(names) == 64
        assert names == sorted(names)
        assert (DHAKA, False, dhaka) in districts
        assert _select(body, "upazila") == []
        assert f'<label for="district">{t("search_district", locale)}</label>' in body

    body = client.get(f"/hub/en?district={DHAKA}&upazila={MIRPUR}&level=class_9").text
    assert (DHAKA, True, "Dhaka") in _select(body, "district")
    areas = _select(body, "upazila")
    assert areas[0] == ("", False, "All areas")
    assert [value for value, selected, _ in areas if selected] == [MIRPUR]
    assert (DNCC, False, "All of Dhaka North City Corporation") in areas
    assert ("BD30260072", False, "Savar") in areas
    assert '<optgroup label="Dhaka North City Corporation">' in body
    assert '<optgroup label="Upazilas">' in body
    hidden = _parse(body).find("input", type="hidden")
    assert hidden == [{"type": "hidden", "name": "level", "value": "class_9"}]
    assert t("search_clear_filters", "en") in body

    bn = client.get(f"/hub/bn?district={DHAKA}").text
    assert (DNCC, False, "ঢাকা উত্তর সিটি কর্পোরেশন-এর সব এলাকা") in _select(bn, "upazila")

    # An area with no district chosen has no select to keep it, so it
    # rides along hidden rather than being lost on the next search.
    alone = client.get(f"/hub/en?upazila={MIRPUR}").text
    assert _select(alone, "upazila") == []
    assert _parse(alone).find("input", type="hidden", name="upazila") == [
        {"type": "hidden", "name": "upazila", "value": MIRPUR}
    ]
