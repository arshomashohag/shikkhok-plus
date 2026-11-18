"""Approved photos on the public owner and batch pages, and in the preview.

Rows are arranged as the table owner; each page is fetched through the real
application, so the public pages read ``hub_public_media`` as the hub
reader and the preview reads ``listing_media`` as the application role.

What a photo becomes on a page is exact: ``/m/{public_key}/{w}.webp`` for
each stored width, relative on the site and absolute on the site's origin
in the preview (shown on the app host, which serves no ``/m/``); ``src`` is
the 960 variant, else the largest; ``width`` and ``height`` are that
variant's own pixels, which the sanitiser writes at ``min(w, source)``
wide and in the source's proportions, so the box is reserved before the
image arrives.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Final

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.hub_media import media_store
from app.errors import TransientError
from app.hub.public import render
from app.hub.public.messages import t
from tests.batches.conftest import make_teacher
from tests.conftest import bearer
from tests.hub.media.fakes import URL, FakeMediaStore
from tests.hub.test_public_routes import (
    PAGE_CSP,
    SITE,
    WEB_APP,
    _batch_listing,
    _client,
    _new_batch,
    _owner_listing,
    _parse,
    _published_tutor,
)

#: The ``sizes`` every gallery image carries: one column on a phone, three
#: across the page's 880-pixel column on anything wider.
SIZES: Final[str] = "(min-width: 600px) 280px, calc(100vw - 32px)"

#: Every status a photo can be in and still not be public.
NOT_PUBLIC: Final[tuple[str, ...]] = (
    "awaiting_upload",
    "processing",
    "pending_review",
    "rejected",
    "withdrawn",
    "held",
)


def _photo(
    session: Session,
    owner_id: uuid.UUID,
    *,
    alt_en: str | None,
    alt_bn: str | None = None,
    status: str = "approved",
    batch_id: uuid.UUID | None = None,
    position: int = 0,
    width: int = 1200,
    height: int = 800,
    widths: list[int] | None = None,
) -> tuple[uuid.UUID, str | None]:
    """Insert one photo with the fields a page renders.

    :param session: An arranging session
    :param owner_id: The owner
    :param alt_en: Its English alt text
    :param alt_bn: Its Bangla alt text
    :param status: Its status; an approved photo gets a public key
    :param batch_id: Its batch, or None for the owner's own gallery
    :param position: Its place in its gallery
    :param width: The decoded source's width
    :param height: The decoded source's height
    :param widths: The variants written; 320 and 960 when not given
    :return: The media id and its public key, None unless approved
    """
    media_id = uuid.uuid4()
    key = uuid.uuid4().hex if status == "approved" else None
    session.execute(
        sa.text(
            "INSERT INTO listing_media (id, owner_id, batch_id, status, "
            "content_type, byte_size, public_key, width, height, widths, "
            "alt_en, alt_bn, position) VALUES (:id, :o, :b, "
            "CAST(:st AS media_status), 'image/jpeg', 2048, :key, :w, :h, :ws, "
            ":en, :bn, :pos)"
        ),
        {
            "id": media_id,
            "o": owner_id,
            "b": batch_id,
            "st": status,
            "key": key,
            "w": width,
            "h": height,
            "ws": [320, 960] if widths is None else widths,
            "en": alt_en,
            "bn": alt_bn,
            "pos": position,
        },
    )
    session.commit()
    return media_id, key


def _images(body: str) -> list[dict[str, str | None]]:
    """List every ``<img>`` of a page, in document order.

    :param body: The HTML
    :return: Each image's attributes
    """
    return _parse(body).find("img")


@pytest.fixture
def fake_store(api_client: TestClient) -> Iterator[FakeMediaStore]:
    """Serve the preview's presigned URLs from an in-memory bucket.

    :param api_client: The test client
    :return: The fake bucket, removed again after the test
    """
    store = FakeMediaStore()
    overrides = api_client.app.dependency_overrides  # type: ignore[attr-defined]
    overrides[media_store] = lambda: store
    yield store
    overrides.pop(media_store, None)


def test_owner_and_batch_pages_show_only_approved_photos_in_order(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Approved owner photos by position on the owner page; batch ones apart.

    The owner page shows owner-level photos only and the batch page its own
    batch's only, which is what lets a hold on a batch photo invalidate the
    batch page alone [Task 6]. No other status reaches either page.
    """
    client = _client(api_client, monkeypatch)
    _, owner_id, batch_id = _published_tutor(owner_session)
    for position, alt in ((2, "Third"), (0, "First"), (1, "Second")):
        _photo(owner_session, owner_id, alt_en=alt, position=position)
    _photo(owner_session, owner_id, alt_en="Batch one", batch_id=batch_id)
    _photo(owner_session, owner_id, alt_en="Batch two", batch_id=batch_id, position=1)
    for status in NOT_PUBLIC:
        _photo(owner_session, owner_id, alt_en=f"Owner {status}", status=status)
        _photo(
            owner_session,
            owner_id,
            alt_en=f"Batch {status}",
            status=status,
            batch_id=batch_id,
        )

    owner = client.get("/hub/en/t/rahim-sir")
    batch = client.get("/hub/en/t/rahim-sir/class-9-maths")

    assert owner.status_code == 200, owner.text
    assert batch.status_code == 200, batch.text
    assert [i["alt"] for i in _images(owner.text)] == ["First", "Second", "Third"]
    assert [i["alt"] for i in _images(batch.text)] == ["Batch one", "Batch two"]
    for status in NOT_PUBLIC:
        for alt in (f"Owner {status}", f"Batch {status}"):
            assert alt not in owner.text + batch.text


def test_photos_of_a_hidden_batch_are_on_no_page(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A draft batch's approved photo shows on neither page."""
    client = _client(api_client, monkeypatch)
    _, owner_id, _ = _published_tutor(owner_session)
    draft = _new_batch(owner_session, owner_id)
    _batch_listing(owner_session, draft, owner_id, slug="draft", status="draft")
    _photo(owner_session, owner_id, alt_en="Draft batch photo", batch_id=draft)

    owner = client.get("/hub/en/t/rahim-sir")

    assert _images(owner.text) == []
    assert client.get("/hub/en/t/rahim-sir/draft").status_code == 404


def test_img_tags_have_dimensions_alt_and_srcset_from_stored_widths(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each variant stored, and only those, at its own pixel width.

    A source narrower than a target is never upscaled: its 960 variant is
    the source's own width, and the srcset says so rather than claiming 960.
    """
    client = _client(api_client, monkeypatch)
    _, owner_id, _ = _published_tutor(owner_session)
    _, wide = _photo(
        owner_session,
        owner_id,
        alt_en="Wide",
        width=2400,
        height=1600,
        widths=[320, 960, 1600],
    )
    _, narrow = _photo(
        owner_session,
        owner_id,
        alt_en="Narrow",
        width=500,
        height=375,
        widths=[320, 960],
        position=1,
    )
    _, tiny = _photo(
        owner_session,
        owner_id,
        alt_en="Tiny",
        width=300,
        height=199,
        widths=[320],
        position=2,
    )

    body = client.get("/hub/en/t/rahim-sir").text

    assert _images(body) == [
        {
            "src": f"/m/{wide}/960.webp",
            "srcset": f"/m/{wide}/320.webp 320w, /m/{wide}/960.webp 960w, "
            f"/m/{wide}/1600.webp 1600w",
            "sizes": SIZES,
            "width": "960",
            "height": "640",
            "alt": "Wide",
            "loading": "lazy",
        },
        {
            "src": f"/m/{narrow}/960.webp",
            "srcset": f"/m/{narrow}/320.webp 320w, /m/{narrow}/960.webp 500w",
            "sizes": SIZES,
            "width": "500",
            "height": "375",
            "alt": "Narrow",
            "loading": "lazy",
        },
        {
            "src": f"/m/{tiny}/320.webp",
            "srcset": f"/m/{tiny}/320.webp 300w",
            "sizes": SIZES,
            "width": "300",
            "height": "199",
            "alt": "Tiny",
            "loading": "lazy",
        },
    ]


def test_json_ld_image_is_the_first_photo_on_the_site_origin(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner and the course name their first photo, absolutely.

    Escaped as H2's JSON-LD is: an alt text carrying markup cannot close
    the script element, and it is not in the structured data at all.
    """
    client = _client(api_client, monkeypatch)
    _, owner_id, batch_id = _published_tutor(owner_session)
    _, second = _photo(owner_session, owner_id, alt_en="</script>", position=1)
    _, first = _photo(
        owner_session, owner_id, alt_en="<b>", widths=[320, 960, 1600], position=0
    )
    _, only = _photo(
        owner_session, owner_id, alt_en="x", batch_id=batch_id, widths=[320]
    )

    owner = client.get("/hub/en/t/rahim-sir").text
    batch = client.get("/hub/en/t/rahim-sir/class-9-maths").text

    (owner_ld,) = _parse(owner).scripts
    (batch_ld,) = _parse(batch).scripts
    assert "<" not in owner_ld + batch_ld
    assert json.loads(owner_ld)["image"] == f"{SITE}/m/{first}/960.webp"
    assert json.loads(batch_ld)["image"] == f"{SITE}/m/{only}/320.webp"
    assert second not in owner_ld
    assert "&lt;/script&gt;" in owner


def test_no_photos_means_no_gallery_and_no_json_ld_image(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A page without photos renders no empty gallery and names no image."""
    client = _client(api_client, monkeypatch)
    _published_tutor(owner_session)

    for path in ("/hub/en/t/rahim-sir", "/hub/en/t/rahim-sir/class-9-maths"):
        page = _parse(client.get(path).text)
        assert page.find("img") == []
        assert page.find("ul", **{"class": "gallery"}) == []
        assert "image" not in json.loads(page.scripts[0])


def test_locale_picks_alt_with_fallback(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The page locale's alt text, else the other locale's."""
    client = _client(api_client, monkeypatch)
    _, owner_id, _ = _published_tutor(owner_session)
    _photo(owner_session, owner_id, alt_en="Both, English", alt_bn="দুটোই, বাংলা")
    _photo(owner_session, owner_id, alt_en="English only", alt_bn=None, position=1)
    _photo(owner_session, owner_id, alt_en="", alt_bn="শুধু বাংলা", position=2)

    english = [i["alt"] for i in _images(client.get("/hub/en/t/rahim-sir").text)]
    bangla = [i["alt"] for i in _images(client.get("/hub/bn/t/rahim-sir").text)]

    assert english == ["Both, English", "English only", "শুধু বাংলা"]
    assert bangla == ["দুটোই, বাংলা", "English only", "শুধু বাংলা"]


def test_photo_report_link(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each photo links the report form with ``kind=media`` and its id."""
    client = _client(api_client, monkeypatch)
    _, owner_id, batch_id = _published_tutor(owner_session)
    owner_photo, _ = _photo(owner_session, owner_id, alt_en="Owner photo")
    batch_photo, _ = _photo(
        owner_session, owner_id, alt_en="Batch photo", batch_id=batch_id
    )

    for locale in ("en", "bn"):
        for path, media_id in (
            ("/t/rahim-sir", owner_photo),
            ("/t/rahim-sir/class-9-maths", batch_photo),
        ):
            page = _parse(client.get(f"/hub/{locale}{path}").text)
            href = f"{WEB_APP}/ui/hub-report?kind=media&id={media_id}"
            assert page.find("a", href=href), (locale, path)
        body = client.get(f"/hub/{locale}/t/rahim-sir").text
        assert t("report_photo", locale) in body


def test_page_csp_unchanged_and_no_inline_style(
    api_client: TestClient,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    fake_store: FakeMediaStore,
) -> None:
    """Photos add no CSP source, no inline style, and nothing executable.

    ``img-src 'self'`` covers ``/m/`` because a public page names its
    photos relative to the site. The preview names them elsewhere, but it
    is shown inside the app's own frame, whose CSP admits both [R1].
    """
    client = _client(api_client, monkeypatch)
    account, owner_id, batch_id = _published_tutor(owner_session)
    _photo(owner_session, owner_id, alt_en="Owner photo")
    _photo(owner_session, owner_id, alt_en="Pending", status="pending_review")
    _photo(owner_session, owner_id, alt_en="Batch photo", batch_id=batch_id)
    preview = client.get(
        "/v1/hub/listing/preview?locale=en", headers=bearer(owner_session, account)
    )
    responses = [
        client.get(f"/hub/{locale}{path}")
        for locale in ("en", "bn")
        for path in ("/t/rahim-sir", "/t/rahim-sir/class-9-maths")
    ]

    for response in [*responses, preview]:
        assert response.status_code == 200, response.text
        assert response.headers["content-security-policy"] == PAGE_CSP
        page = _parse(response.text)
        assert page.find("img"), response.url
        assert page.find("style") == []
        for tag, attrs in page.tags:
            assert "style" not in attrs, tag
            assert not [name for name in attrs if name.startswith("on")], tag
    for response in responses:
        for image in _images(response.text):
            assert str(image["src"]).startswith("/m/")
    assert ".gallery" in render.STYLESHEET_FILE.read_text(encoding="utf-8")


def test_preview_marks_pending_photos(
    api_client: TestClient,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    fake_store: FakeMediaStore,
) -> None:
    """The owner sees approved photos and pending ones, marked; nothing else.

    Approved photos are named on the site's origin, since the preview is
    shown on the app host; pending ones through five-minute signed GETs of
    the variants frozen in archive/ at completion [I1]. Rejected, withdrawn
    and held photos, and batch photos, are not on the owner's page.
    """
    client = _client(api_client, monkeypatch)
    teacher = make_teacher(owner_session, name="Private batch name")
    _owner_listing(owner_session, teacher.owner_id, slug="draft", status="draft")
    _, key = _photo(owner_session, teacher.owner_id, alt_en="Approved", position=0)
    pending, _ = _photo(
        owner_session,
        teacher.owner_id,
        alt_en="Pending",
        alt_bn="অপেক্ষমাণ",
        status="pending_review",
        position=1,
    )
    for status in ("rejected", "withdrawn", "held", "processing"):
        _photo(owner_session, teacher.owner_id, alt_en=status, status=status)
    _photo(
        owner_session,
        teacher.owner_id,
        alt_en="Pending batch photo",
        status="pending_review",
        batch_id=teacher.batch_id,
    )
    headers = bearer(owner_session, teacher.account_id)

    for locale, marker in (("en", "Awaiting review"), ("bn", "পর্যালোচনার অপেক্ষায়")):
        response = client.get(
            f"/v1/hub/listing/preview?locale={locale}", headers=headers
        )
        assert response.status_code == 200, response.text
        images = _images(response.text)
        assert [i["alt"] for i in images] == [
            "Approved",
            "Pending" if locale == "en" else "অপেক্ষমাণ",
        ]
        approved, waiting = images
        assert approved["src"] == f"{SITE}/m/{key}/960.webp"
        assert approved["srcset"] == (
            f"{SITE}/m/{key}/320.webp 320w, {SITE}/m/{key}/960.webp 960w"
        )
        frozen = f"{URL}archive/{pending}/"
        assert waiting["src"] == f"{frozen}960.webp?X-Amz-Expires=300"
        assert waiting["srcset"] == (
            f"{frozen}320.webp?X-Amz-Expires=300 320w, "
            f"{frozen}960.webp?X-Amz-Expires=300 960w"
        )
        assert t("photo_awaiting_review", locale) == marker
        assert response.text.count(marker) == 1
        # A pending photo cannot be reported: it is on no public page.
        assert f"kind=media&amp;id={pending}" not in response.text
        for status in ("rejected", "withdrawn", "held", "processing"):
            assert f'alt="{status}"' not in response.text
        assert "Pending batch photo" not in response.text


def test_preview_survives_a_bucket_that_cannot_sign(
    api_client: TestClient,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    fake_store: FakeMediaStore,
) -> None:
    """A pending photo the bucket cannot sign is left out, not a failed page."""
    client = _client(api_client, monkeypatch)
    account, owner_id, _ = _published_tutor(owner_session)
    _photo(owner_session, owner_id, alt_en="Approved")
    _photo(owner_session, owner_id, alt_en="Pending", status="pending_review")

    def unavailable(key: str) -> str:
        """Refuse to sign, as a bucket with no credentials does.

        :param key: The object
        :return: Never
        :raises TransientError: Always
        """
        raise TransientError(
            code="SERVICE_UNAVAILABLE", message_key="error.temporarily_unavailable"
        )

    monkeypatch.setattr(fake_store, "presign_get", unavailable)

    response = client.get(
        "/v1/hub/listing/preview?locale=en", headers=bearer(owner_session, account)
    )

    assert response.status_code == 200, response.text
    assert [i["alt"] for i in _images(response.text)] == ["Approved"]
