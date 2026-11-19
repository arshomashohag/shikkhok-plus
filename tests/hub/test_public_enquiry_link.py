"""The "Ask to join" link on the public pages and in the owner's preview [H5].

Every request goes through the real application against the restricted
database role, and a public page learns that an owner accepts join requests
only from ``hub_public_enquirable`` as the hub reader. Rows are arranged as
the table owner.

The link is shown only while the switch is on and the owner accepts
requests; a batch page shows it only while the batch's admissions are not
``closed``. With the switch off no public page and no preview carries it,
whatever the owner chose [global constraints: the off behaviour].
"""

from __future__ import annotations

import uuid
from html.parser import HTMLParser
from typing import Final
from urllib.parse import parse_qsl, urlsplit

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.html import HUB_PAGE_CSP
from app.hub.public.messages import LOCALES, Locale, t
from app.hub.public.settings import HUB_ENQUIRIES_ENV, SITE_URL_ENV, WEB_APP_URL_ENV
from tests.conftest import bearer
from tests.enquiries.support import EnquirableWorld, enquirable_owner

SITE: Final[str] = "https://site.example.test"
WEB_APP: Final[str] = "https://app.example.test"

#: The form's path on the web app; no page may name it while the switch is off.
FORM: Final[str] = "/ui/hub-enquiry"

#: The page CSP, verbatim from the plan's global constraints.
PAGE_CSP: Final[str] = (
    "default-src 'none'; style-src 'self'; img-src 'self'; font-src 'self'; "
    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)


def _client(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Point the page settings at distinctive origins.

    :param api_client: The test client
    :param monkeypatch: The patcher
    :return: The same client
    """
    monkeypatch.setenv(SITE_URL_ENV, SITE)
    monkeypatch.setenv(WEB_APP_URL_ENV, WEB_APP)
    return api_client


def _batch_slug(session: Session, batch_id: uuid.UUID) -> str:
    """Read a batch listing's slug.

    :param session: An arranging session
    :param batch_id: The batch
    :return: Its listing's slug
    """
    slug: str = session.execute(
        sa.text("SELECT slug FROM batch_listing WHERE batch_id = :b"),
        {"b": batch_id},
    ).scalar_one()
    return slug


def _pages(
    client: TestClient, session: Session, world: EnquirableWorld, locale: Locale
) -> tuple[str, str]:
    """Fetch an owner's page and its batch's page in one locale.

    :param client: The test client
    :param session: An arranging session
    :param world: The owner and batch
    :param locale: The locale
    :return: ``(owner page, batch page)``
    """
    owner = client.get(f"/hub/{locale}/t/{world.owner_slug}")
    batch = client.get(
        f"/hub/{locale}/t/{world.owner_slug}/{_batch_slug(session, world.batch_id)}"
    )
    assert owner.status_code == 200, owner.text
    assert batch.status_code == 200, batch.text
    return owner.text, batch.text


class _Anchors(HTMLParser):
    """Collect every start tag, and each link's href with its text."""

    def __init__(self) -> None:
        """Start empty."""
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    @property
    def names(self) -> set[str]:
        """Name every tag seen.

        :return: The tag names
        """
        return {name for name, _ in self.tags}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record a start tag, and begin a link's text.

        :param tag: The tag name
        :param attrs: Its attributes
        :return: None
        """
        found = dict(attrs)
        self.tags.append((tag, found))
        if tag == "a":
            self._href = found.get("href") or ""
            self._text = []

    def handle_data(self, data: str) -> None:
        """Collect text inside a link.

        :param data: The text
        :return: None
        """
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        """Finish a link.

        :param tag: The tag name
        :return: None
        """
        if tag == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._text).strip()))
            self._href = None


def _enquiry_links(body: str) -> list[tuple[str, str]]:
    """List the links a page carries to the join-request form.

    :param body: The page
    :return: ``(href, text)`` pairs, hrefs unescaped as a browser reads them
    """
    parser = _Anchors()
    parser.feed(body)
    return [(href, text) for href, text in parser.links if FORM in href]


@pytest.mark.usefixtures("enquiries_on")
def test_link_shown_only_when_switch_on_and_owner_accepts(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An accepting owner's pages link to the form; a declining owner's do not.

    The owner page names the owner; the batch page names the owner and the
    batch, and nothing else, so the form opens on the right target.
    """
    client = _client(api_client, monkeypatch)
    accepting = enquirable_owner(owner_session)
    waitlist = enquirable_owner(owner_session, admissions="waitlist")
    declining = enquirable_owner(owner_session, accepts=False)

    for locale in LOCALES:
        owner_page, batch_page = _pages(client, owner_session, accepting, locale)
        assert _enquiry_links(owner_page) == [
            (f"{WEB_APP}{FORM}?owner={accepting.owner_slug}", t("enquiry_link", locale))
        ]
        [(href, text)] = _enquiry_links(batch_page)
        assert text == t("enquiry_link_batch", locale)
        parts = urlsplit(href)
        assert f"{parts.scheme}://{parts.netloc}{parts.path}" == f"{WEB_APP}{FORM}"
        assert parse_qsl(parts.query) == [
            ("owner", accepting.owner_slug),
            ("batch", str(accepting.batch_id)),
        ]
        assert (
            f'href="{WEB_APP}{FORM}?owner={accepting.owner_slug}'
            f'&amp;batch={accepting.batch_id}"'
        ) in batch_page

        _, waitlist_batch = _pages(client, owner_session, waitlist, locale)
        assert len(_enquiry_links(waitlist_batch)) == 1

        for body in _pages(client, owner_session, declining, locale):
            assert FORM not in body
            assert t("enquiry_link", locale) not in body
            assert t("enquiry_link_batch", locale) not in body


@pytest.mark.usefixtures("enquiries_on")
def test_batch_link_hidden_when_admissions_closed_owner_link_kept(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A closed batch offers no link; its owner's page still does."""
    client = _client(api_client, monkeypatch)
    closed = enquirable_owner(owner_session, admissions="closed")

    for locale in LOCALES:
        owner_page, batch_page = _pages(client, owner_session, closed, locale)
        assert _enquiry_links(owner_page) == [
            (f"{WEB_APP}{FORM}?owner={closed.owner_slug}", t("enquiry_link", locale))
        ]
        assert FORM not in batch_page
        assert t("enquiry_link_batch", locale) not in batch_page


@pytest.mark.usefixtures("enquiries_off")
def test_switch_off_removes_link_on_every_page(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the switch off no public page names the form, in either locale.

    The owner accepts requests and its batch is open, so only the switch
    keeps the link off.
    """
    client = _client(api_client, monkeypatch)
    world = enquirable_owner(owner_session)
    batch_slug = _batch_slug(owner_session, world.batch_id)

    paths = ["/hub/sitemap.xml"]
    for locale in LOCALES:
        paths += [
            f"/hub/{locale}",
            f"/hub/{locale}?q=Rahim",
            f"/hub/{locale}/t/{world.owner_slug}",
            f"/hub/{locale}/t/{world.owner_slug}/{batch_slug}",
        ]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path
        assert "hub-enquiry" not in response.text, path
        for locale in LOCALES:
            assert t("enquiry_link", locale) not in response.text, path
            assert t("enquiry_link_batch", locale) not in response.text, path

    # The same pages carry it once the switch is on: the test is not vacuous.
    monkeypatch.setenv(HUB_ENQUIRIES_ENV, "on")
    assert FORM in client.get(f"/hub/en/t/{world.owner_slug}").text


@pytest.mark.usefixtures("enquiries_on")
def test_preview_shows_link_from_own_row(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The preview shows the link from the owner's own row, drafts included.

    The listing is a draft, which ``hub_public_enquirable`` does not hold,
    so a link here can come only from ``owner_listing.accepts_enquiries``.
    """
    client = _client(api_client, monkeypatch)
    world = enquirable_owner(owner_session)
    owner_session.execute(
        sa.text("UPDATE owner_listing SET status = 'draft' WHERE owner_id = :o"),
        {"o": world.lens.owner_id},
    )
    owner_session.commit()
    headers = bearer(owner_session, world.lens.account_id)

    def preview(locale: Locale) -> str:
        """Fetch the owner's preview.

        :param locale: The locale
        :return: The page
        """
        response = client.get(
            f"/v1/hub/listing/preview?locale={locale}", headers=headers
        )
        assert response.status_code == 200, response.text
        return response.text

    for locale in LOCALES:
        assert _enquiry_links(preview(locale)) == [
            (f"{WEB_APP}{FORM}?owner={world.owner_slug}", t("enquiry_link", locale))
        ]
    assert client.get(f"/hub/en/t/{world.owner_slug}").status_code == 404

    owner_session.execute(
        sa.text(
            "UPDATE owner_listing SET accepts_enquiries = false WHERE owner_id = :o"
        ),
        {"o": world.lens.owner_id},
    )
    owner_session.commit()
    for locale in LOCALES:
        assert FORM not in preview(locale)

    owner_session.execute(
        sa.text(
            "UPDATE owner_listing SET accepts_enquiries = true WHERE owner_id = :o"
        ),
        {"o": world.lens.owner_id},
    )
    owner_session.commit()
    monkeypatch.delenv(HUB_ENQUIRIES_ENV)
    for locale in LOCALES:
        assert FORM not in preview(locale)


@pytest.mark.usefixtures("enquiries_on", "reviews_on")
def test_page_csp_unchanged_and_no_inline_style(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pages with the link keep the CSP and carry no style or script of their own."""
    client = _client(api_client, monkeypatch)
    world = enquirable_owner(owner_session)
    batch_slug = _batch_slug(owner_session, world.batch_id)

    assert HUB_PAGE_CSP == PAGE_CSP
    for locale in LOCALES:
        for path in (
            f"/hub/{locale}/t/{world.owner_slug}",
            f"/hub/{locale}/t/{world.owner_slug}/{batch_slug}",
        ):
            response = client.get(path)
            assert response.headers["content-security-policy"] == PAGE_CSP, path
            assert len(_enquiry_links(response.text)) == 1, path
            page = _Anchors()
            page.feed(response.text)
            assert "style" not in page.names, path
            for name, attrs in page.tags:
                assert "style" not in attrs, (path, name)
                assert not [a for a in attrs if a.startswith("on")], (path, name)
                if name == "script":
                    assert attrs == {"type": "application/ld+json"}, path
