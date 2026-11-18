"""The six photo-editor routes, through the real app and restricted role."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Final

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.hub_media import media_store
from app.auth.ceilings import HUB_LISTING_OWNER_DAILY
from app.contract.routes import PUBLIC_ROUTES, _api_routes
from app.errors import ValidationError
from app.hub.public.settings import site_url
from app.main import app as real_app
from app.schemas.media import MediaResponse
from tests.batches.conftest import make_teacher
from tests.conftest import bearer
from tests.hub.media.fakes import URL, FakeMediaStore
from tests.hub.media.support import media_row
from tests.hub.support import add_member, centre_with_manager

OK: Final[dict[str, object]] = {
    "ok": True,
    "width": 1600,
    "height": 1200,
    "widths": [320, 960, 1600],
}
ALT: Final[dict[str, str]] = {"alt_en": "A classroom", "alt_bn": "একটি শ্রেণিকক্ষ"}
ROUTES: Final[tuple[tuple[str, str], ...]] = (
    ("POST", "/v1/hub/media/uploads"),
    ("POST", "/v1/hub/media/{media_id}/complete"),
    ("GET", "/v1/hub/media"),
    ("PATCH", "/v1/hub/media/{media_id}"),
    ("PUT", "/v1/hub/media/order"),
    ("DELETE", "/v1/hub/media/{media_id}"),
)


@pytest.fixture
def store(api_client: TestClient) -> Iterator[FakeMediaStore]:
    fake = FakeMediaStore()
    api_client.app.dependency_overrides[media_store] = lambda: fake  # type: ignore[attr-defined]
    yield fake
    api_client.app.dependency_overrides.pop(media_store, None)  # type: ignore[attr-defined]


def _auth(session: Session) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    teacher = make_teacher(session)
    return bearer(session, teacher.account_id), teacher.owner_id, teacher.batch_id


def _count(session: Session, owner_id: uuid.UUID) -> int:
    session.rollback()
    return int(
        session.execute(
            sa.text("SELECT count(*) FROM listing_media WHERE owner_id = :o"),
            {"o": owner_id},
        ).scalar_one()
    )


def test_six_routes_require_teacher_lens() -> None:
    """Each route is registered, none is public, and each resolves a lens."""
    registered = {
        (method, route.path)
        for route in _api_routes(real_app)
        for method in route.methods
        if route.path.startswith("/v1/hub/media")
    }
    assert registered == set(ROUTES)
    assert not any(p.startswith("/v1/hub/media") for _, p in PUBLIC_ROUTES)


def test_class_teacher_and_other_owner_refused(
    api_client: TestClient, owner_session: Session, store: FakeMediaStore
) -> None:
    """A class teacher has no lens; another owner's photo reads as absent."""
    centre = centre_with_manager(owner_session)
    _, member = add_member(owner_session, centre.owner_id, role="teacher")
    teacher_headers = {
        **bearer(owner_session, member),
        "X-Workspace-Id": str(centre.owner_id),
    }
    assert api_client.get("/v1/hub/media", headers=teacher_headers).status_code == 403
    assert (
        api_client.post(
            "/v1/hub/media/uploads",
            json={"content_type": "image/png", "byte_size": 10},
            headers=teacher_headers,
        ).status_code
        == 403
    )

    mine, _, _ = _auth(owner_session)
    _, other_owner, _ = _auth(owner_session)
    theirs = media_row(owner_session, other_owner)
    for resp in (
        api_client.patch(f"/v1/hub/media/{theirs}", json=ALT, headers=mine),
        api_client.delete(f"/v1/hub/media/{theirs}", headers=mine),
        api_client.post(f"/v1/hub/media/{theirs}/complete", json=ALT, headers=mine),
    ):
        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["code"] == "MEDIA_NOT_FOUND"


def test_upload_flow_end_to_end_with_fake_store(
    api_client: TestClient, owner_session: Session, store: FakeMediaStore
) -> None:
    """Init, complete, list, edit, reorder and delete."""
    headers, owner_id, batch_id = _auth(owner_session)

    init = api_client.post(
        "/v1/hub/media/uploads",
        json={"batch_id": str(batch_id), "content_type": "image/jpeg", "byte_size": 99},
        headers=headers,
    )
    assert init.status_code == 200, init.text
    ticket = init.json()
    assert ticket["url"] == URL
    assert ticket["fields"]["key"] == f"quarantine/{ticket['media_id']}"
    media_id = uuid.UUID(ticket["media_id"])

    early = api_client.post(
        f"/v1/hub/media/{media_id}/complete", json=ALT, headers=headers
    )
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "MEDIA_NOT_UPLOADED"

    store.put_result(media_id, OK)
    done = api_client.post(
        f"/v1/hub/media/{media_id}/complete", json=ALT, headers=headers
    )
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "pending_review"
    assert (body["width"], body["height"]) == (1600, 1200)
    assert body["thumb_url"].startswith(URL + f"staged/{media_id}/320.webp")
    assert "X-Amz-Expires=300" in body["thumb_url"]

    listed = api_client.get(
        "/v1/hub/media", params={"batch_id": str(batch_id)}, headers=headers
    )
    assert [m["id"] for m in listed.json()] == [str(media_id)]
    assert api_client.get("/v1/hub/media", headers=headers).json() == []

    patched = api_client.patch(
        f"/v1/hub/media/{media_id}", json={"alt_en": "Desks"}, headers=headers
    )
    assert patched.json()["alt_en"] == "Desks"
    assert patched.json()["alt_bn"] == ALT["alt_bn"]

    second = media_row(owner_session, owner_id, batch_id=batch_id, position=5)
    ordered = api_client.put(
        "/v1/hub/media/order",
        json={"batch_id": str(batch_id), "ids": [str(second), str(media_id)]},
        headers=headers,
    )
    assert [m["id"] for m in ordered.json()] == [str(second), str(media_id)]
    assert [m["position"] for m in ordered.json()] == [0, 1]

    gone = api_client.delete(f"/v1/hub/media/{media_id}", headers=headers)
    assert gone.status_code == 204
    assert gone.content == b""
    after = api_client.get(
        "/v1/hub/media", params={"batch_id": str(batch_id)}, headers=headers
    )
    assert [m["id"] for m in after.json()] == [str(second)]


def test_approved_thumb_is_absolute_public_url(
    api_client: TestClient,
    owner_session: Session,
    store: FakeMediaStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R1: an approved photo's thumb is on the site host; others get null."""
    monkeypatch.setenv("SHIKKHOKPLUS_SITE_URL", "https://site.example/")
    headers, owner_id, _ = _auth(owner_session)
    approved = media_row(owner_session, owner_id, status="approved")
    rejected = media_row(owner_session, owner_id, status="rejected", position=1)
    key = owner_session.execute(
        sa.text("SELECT public_key FROM listing_media WHERE id = :m"), {"m": approved}
    ).scalar_one()

    by_id = {
        m["id"]: m for m in api_client.get("/v1/hub/media", headers=headers).json()
    }

    assert site_url() == "https://site.example"
    assert by_id[str(approved)]["thumb_url"] == f"https://site.example/m/{key}/320.webp"
    assert by_id[str(rejected)]["thumb_url"] is None


def test_error_envelopes_for_five_codes(
    api_client: TestClient, owner_session: Session, store: FakeMediaStore
) -> None:
    """Type, size, limit, not-uploaded and unreadable each answer their code."""
    headers, owner_id, _ = _auth(owner_session)

    def post(content_type: str, size: int) -> object:
        return api_client.post(
            "/v1/hub/media/uploads",
            json={"content_type": content_type, "byte_size": size},
            headers=headers,
        )

    bad_type = post("image/gif", 10)
    big = post("image/png", 8_388_609)
    for resp, code, status_code in (
        (bad_type, "MEDIA_TYPE_NOT_ALLOWED", 400),
        (big, "MEDIA_TOO_LARGE", 400),
    ):
        assert resp.status_code == status_code  # type: ignore[attr-defined]
        error = resp.json()["error"]  # type: ignore[attr-defined]
        assert error["code"] == code
        assert error["message_key"] == f"hub.media.{code[6:].lower()}"
        assert error["retryable"] is False

    for i in range(12):
        media_row(owner_session, owner_id, position=i)
    full = post("image/png", 10)
    assert full.status_code == 409  # type: ignore[attr-defined]
    assert full.json()["error"]["code"] == "MEDIA_LIMIT_REACHED"  # type: ignore[attr-defined]

    headers2, _, _ = _auth(owner_session)
    ticket = api_client.post(
        "/v1/hub/media/uploads",
        json={"content_type": "image/png", "byte_size": 10},
        headers=headers2,
    ).json()
    url = f"/v1/hub/media/{ticket['media_id']}/complete"
    nope = api_client.post(url, json=ALT, headers=headers2)
    assert nope.json()["error"]["code"] == "MEDIA_NOT_UPLOADED"
    assert nope.status_code == 409
    store.put_result(
        uuid.UUID(ticket["media_id"]), {"ok": False, "reason": "unreadable"}
    )
    bad = api_client.post(url, json=ALT, headers=headers2)
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "MEDIA_UNREADABLE"
    assert bad.json()["error"]["message_key"] == "hub.media.unreadable"


def test_blank_alt_is_media_alt_invalid(
    api_client: TestClient, owner_session: Session, store: FakeMediaStore
) -> None:
    headers, owner_id, _ = _auth(owner_session)
    media_id = media_row(owner_session, owner_id)
    resp = api_client.patch(
        f"/v1/hub/media/{media_id}", json={"alt_en": "  "}, headers=headers
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "MEDIA_ALT_INVALID"


def test_validation_error_mid_route_leaves_no_row(
    api_client: TestClient,
    owner_session: Session,
    store: FakeMediaStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The row flushed before the refusal is rolled back by the app."""
    headers, owner_id, _ = _auth(owner_session)

    def boom(media_id: uuid.UUID, content_type: str) -> None:
        raise ValidationError(code="MEDIA_TOO_LARGE", message_key="hub.media.too_large")

    monkeypatch.setattr(store, "presign_upload", boom)
    resp = api_client.post(
        "/v1/hub/media/uploads",
        json={"content_type": "image/png", "byte_size": 10},
        headers=headers,
    )

    assert resp.status_code == 400
    assert _count(owner_session, owner_id) == 0
    counted = owner_session.execute(
        sa.text(
            "SELECT count(*) FROM rate_limit_counter "
            "WHERE scope_kind = 'hub_media_day' AND scope_value = :o"
        ),
        {"o": str(owner_id)},
    ).scalar_one()
    assert counted == 0


def test_suspended_owner_writes_refused_reads_allowed(
    api_client: TestClient, owner_session: Session, store: FakeMediaStore
) -> None:
    """R8: every write answers HUB_LISTING_SUSPENDED; GET still works."""
    headers, owner_id, _ = _auth(owner_session)
    media_id = media_row(owner_session, owner_id)
    owner_session.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, slug, status, public_name, "
            "suspended_at, suspension_reason_code) VALUES (:o, 'sus-owner', "
            "'suspended', 'T', now(), 'spam')"
        ),
        {"o": owner_id},
    )
    owner_session.commit()

    writes = (
        api_client.post(
            "/v1/hub/media/uploads",
            json={"content_type": "image/png", "byte_size": 10},
            headers=headers,
        ),
        api_client.post(
            f"/v1/hub/media/{media_id}/complete", json=ALT, headers=headers
        ),
        api_client.patch(f"/v1/hub/media/{media_id}", json=ALT, headers=headers),
        api_client.put("/v1/hub/media/order", json={"ids": []}, headers=headers),
        api_client.delete(f"/v1/hub/media/{media_id}", headers=headers),
    )
    for resp in writes:
        assert resp.status_code == 409, resp.text
        assert resp.json()["error"]["code"] == "HUB_LISTING_SUSPENDED"
    assert api_client.get("/v1/hub/media", headers=headers).status_code == 200
    assert _count(owner_session, owner_id) == 1


def test_writes_share_the_listing_ceiling_but_uploads_do_not(
    api_client: TestClient, owner_session: Session, store: FakeMediaStore
) -> None:
    """Edits spend HUB_LISTING_OWNER_DAILY; an upload init does not."""
    headers, owner_id, _ = _auth(owner_session)
    media_id = media_row(owner_session, owner_id)
    for _ in range(HUB_LISTING_OWNER_DAILY):
        ok = api_client.patch(
            f"/v1/hub/media/{media_id}", json={"alt_en": "same"}, headers=headers
        )
        assert ok.status_code == 200, ok.text

    refused = api_client.patch(
        f"/v1/hub/media/{media_id}", json={"alt_en": "same"}, headers=headers
    )
    upload = api_client.post(
        "/v1/hub/media/uploads",
        json={"content_type": "image/png", "byte_size": 10},
        headers=headers,
    )

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "HUB_WRITE_CEILING"
    assert upload.status_code == 200, upload.text


def test_media_response_has_no_private_fields() -> None:
    """No account id, phone or display name rides on a photo."""
    fields = set(MediaResponse.model_fields)
    assert fields == {
        "id",
        "batch_id",
        "status",
        "alt_en",
        "alt_bn",
        "position",
        "width",
        "height",
        "rejection_code",
        "thumb_url",
    }
    assert not {"owner_id", "account_id", "phone", "display_name"} & fields


def _spent(session: Session, owner_id: uuid.UUID) -> int:
    session.rollback()
    return int(
        session.execute(
            sa.text(
                "SELECT coalesce(sum(count), 0) FROM rate_limit_counter "
                "WHERE scope_kind = 'hub_owner_day' AND scope_value = :o"
            ),
            {"o": str(owner_id)},
        ).scalar_one()
    )


def test_polling_complete_spends_one_unit_on_success(
    api_client: TestClient, owner_session: Session, store: FakeMediaStore
) -> None:
    """R10: three NOT_UPLOADED polls spend nothing; the success spends one."""
    headers, owner_id, _ = _auth(owner_session)
    ticket = api_client.post(
        "/v1/hub/media/uploads",
        json={"content_type": "image/png", "byte_size": 10},
        headers=headers,
    ).json()
    url = f"/v1/hub/media/{ticket['media_id']}/complete"

    for _ in range(3):
        assert api_client.post(url, json=ALT, headers=headers).status_code == 409
    assert _spent(owner_session, owner_id) == 0

    store.put_result(uuid.UUID(ticket["media_id"]), OK)
    assert api_client.post(url, json=ALT, headers=headers).status_code == 200
    assert _spent(owner_session, owner_id) == 1

    assert api_client.post(url, json=ALT, headers=headers).status_code == 200
    assert _spent(owner_session, owner_id) == 1


def test_unreadable_complete_spends_one_unit(
    api_client: TestClient, owner_session: Session, store: FakeMediaStore
) -> None:
    headers, owner_id, _ = _auth(owner_session)
    ticket = api_client.post(
        "/v1/hub/media/uploads",
        json={"content_type": "image/png", "byte_size": 10},
        headers=headers,
    ).json()
    store.put_result(
        uuid.UUID(ticket["media_id"]), {"ok": False, "reason": "unreadable"}
    )

    bad = api_client.post(
        f"/v1/hub/media/{ticket['media_id']}/complete", json=ALT, headers=headers
    )

    assert bad.status_code == 400
    assert _spent(owner_session, owner_id) == 1
