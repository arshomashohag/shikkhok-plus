"""The hub's page-view counts [0050]: a number per page per day, owner-only.

What is asserted:

* a public owner or batch page carries one counting image, and the search
  page and the owner's preview carry none;
* the image's answer is the same bytes, uncached, for a published page,
  an unpublished one, an unknown id and a malformed path, and only a
  published page's load adds a view;
* a request over the read ceiling, and a HEAD, count nothing;
* the table holds the page, the day and the count -- no column a reader
  could be found from -- and the hub reader cannot see it;
* the owner reads their own pages' counts in two windows, and nobody
  else's.
"""

from __future__ import annotations

import datetime as dt
import time
import uuid
from typing import Final

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.hub_public import VIEW_PIXEL
from app.local_time import bangladesh_today
from tests.batches.conftest import make_teacher
from tests.conftest import bearer
from tests.hub.test_public_routes import (
    _batch_listing,
    _client,
    _new_batch,
    _parse,
    _published_tutor,
)

#: The table's whole column set: nothing about who viewed a page.
COLUMNS: Final[set[str]] = {"page_kind", "page_id", "day", "views"}


def _views(session: Session, kind: str, page_id: uuid.UUID) -> int:
    """Sum a page's counted views across every day.

    :param session: An arranging session
    :param kind: ``owner`` or ``batch``
    :param page_id: The page's id
    :return: The views counted
    """
    return int(
        session.execute(
            sa.text(
                "SELECT COALESCE(sum(views), 0) FROM hub_page_view "
                "WHERE page_kind = CAST(:k AS hub_page_kind) AND page_id = :i"
            ),
            {"k": kind, "i": page_id},
        ).scalar_one()
    )


def _assert_pixel(response: object) -> None:
    """Assert an answer is the counting image, uncached.

    :param response: The response
    :return: None
    """
    assert response.status_code == 200  # type: ignore[attr-defined]
    assert response.content == VIEW_PIXEL  # type: ignore[attr-defined]
    headers = response.headers  # type: ignore[attr-defined]
    assert headers["content-type"] == "image/gif"
    assert headers["cache-control"] == "no-store"
    assert headers["x-content-type-options"] == "nosniff"
    assert "set-cookie" not in headers


def test_public_pages_carry_one_counting_image_and_search_and_preview_none(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Owner and batch pages name their own image; search and preview do not."""
    client = _client(api_client, monkeypatch)
    account, owner_id, batch_id = _published_tutor(owner_session)

    for locale in ("en", "bn"):
        for path, src in (
            (f"/hub/{locale}/t/rahim-sir", f"/hub/v/o/{owner_id}.gif"),
            (f"/hub/{locale}/t/rahim-sir/class-9-maths", f"/hub/v/b/{batch_id}.gif"),
        ):
            page = _parse(client.get(path).text)
            pixels = page.find("img", **{"class": "view-pixel"})
            assert pixels == [
                {
                    "class": "view-pixel",
                    "src": src,
                    "alt": "",
                    "width": "1",
                    "height": "1",
                }
            ], path
        search = _parse(client.get(f"/hub/{locale}").text)
        assert search.find("img", **{"class": "view-pixel"}) == []

    preview = client.get(
        "/v1/hub/listing/preview?locale=en", headers=bearer(owner_session, account)
    )
    assert preview.status_code == 200, preview.text
    assert "/hub/v/" not in preview.text


def test_a_published_page_load_adds_one_view_and_nothing_else_counts(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every answer is the same image; only a published page's adds a view."""
    client = _client(api_client, monkeypatch)
    _, owner_id, batch_id = _published_tutor(owner_session)
    draft = _new_batch(owner_session, owner_id)
    _batch_listing(owner_session, draft, owner_id, slug="draft", status="draft")
    elsewhere = make_teacher(owner_session)

    for path in (
        f"/hub/v/o/{owner_id}.gif",
        f"/hub/v/o/{owner_id}.gif",
        f"/hub/v/b/{batch_id}.gif",
        f"/hub/v/b/{draft}.gif",
        f"/hub/v/o/{elsewhere.owner_id}.gif",
        f"/hub/v/b/{owner_id}.gif",
        f"/hub/v/o/{uuid.uuid4()}.gif",
        f"/hub/v/x/{owner_id}.gif",
        "/hub/v/o/not-a-uuid.gif",
    ):
        _assert_pixel(client.get(path))

    assert _views(owner_session, "owner", owner_id) == 2
    assert _views(owner_session, "batch", batch_id) == 1
    rows = owner_session.execute(
        sa.text("SELECT page_kind::text, page_id, day, views FROM hub_page_view")
    ).all()
    assert sorted((r[0], r[1], r[3]) for r in rows) == sorted(
        [("owner", owner_id, 2), ("batch", batch_id, 1)]
    )
    assert {r[2] for r in rows} == {bangladesh_today()}


def test_a_refused_read_and_a_head_count_nothing(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Over the ceiling the image still answers; a HEAD is refused outright."""
    client = _client(api_client, monkeypatch)
    _, owner_id, _ = _published_tutor(owner_session)

    assert client.head(f"/hub/v/o/{owner_id}.gif").status_code == 405
    # Keep the seeded window and the request inside one wall-clock minute.
    second = dt.datetime.now(tz=dt.UTC).second
    if second >= 50:
        time.sleep(61 - second)
    window = dt.datetime.now(tz=dt.UTC).replace(second=0, microsecond=0)
    owner_session.execute(
        sa.text(
            "INSERT INTO rate_limit_counter (id, scope_kind, scope_value, "
            "window_start, count) VALUES (gen_random_uuid(), 'hub_read_min', "
            "'192.0.2.0/24', :w, 120)"
        ),
        {"w": window},
    )
    owner_session.commit()
    viewer = {"CloudFront-Viewer-Address": "192.0.2.7:46532"}
    _assert_pixel(client.get(f"/hub/v/o/{owner_id}.gif", headers=viewer))

    assert _views(owner_session, "owner", owner_id) == 0


def test_the_table_holds_no_reader_and_the_hub_reader_cannot_see_it(
    owner_session: Session,
) -> None:
    """Four columns, none about a person; granted to the app role only."""
    columns = set(
        owner_session.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'hub_page_view'"
            )
        ).scalars()
    )
    assert columns == COLUMNS
    granted = set(
        owner_session.execute(
            sa.text(
                "SELECT grantee FROM information_schema.role_table_grants "
                "WHERE table_name = 'hub_page_view'"
            )
        ).scalars()
    )
    assert "shikkhok_app" in granted
    assert "shikkhok_hub_reader" not in granted


def _seed(
    session: Session, kind: str, page_id: uuid.UUID, days_ago: int, views: int
) -> None:
    """Arrange one day's count for a page.

    :param session: An arranging session
    :param kind: ``owner`` or ``batch``
    :param page_id: The page
    :param days_ago: How many days before today
    :param views: The count
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO hub_page_view (page_kind, page_id, day, views) "
            "VALUES (CAST(:k AS hub_page_kind), :i, :d, :v)"
        ),
        {
            "k": kind,
            "i": page_id,
            "d": bangladesh_today() - dt.timedelta(days=days_ago),
            "v": views,
        },
    )
    session.commit()


def test_the_owner_reads_their_own_counts_in_two_windows(
    api_client: TestClient, owner_session: Session
) -> None:
    """Seven days and thirty, today included; older and others' left out."""
    account, owner_id, batch_id = _published_tutor(owner_session)
    quiet = _new_batch(owner_session, owner_id)
    other = make_teacher(owner_session)
    _seed(owner_session, "owner", owner_id, 0, 3)
    _seed(owner_session, "owner", owner_id, 6, 2)
    _seed(owner_session, "owner", owner_id, 7, 5)
    _seed(owner_session, "owner", owner_id, 29, 1)
    _seed(owner_session, "owner", owner_id, 30, 100)
    _seed(owner_session, "batch", batch_id, 1, 4)
    _seed(owner_session, "batch", batch_id, 20, 6)
    _seed(owner_session, "owner", other.owner_id, 0, 50)
    _seed(owner_session, "batch", other.batch_id, 0, 50)

    response = api_client.get(
        "/v1/hub/listing/views", headers=bearer(owner_session, account)
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "owner_page": {"last_7_days": 5, "last_30_days": 11},
        "batches": [{"batch_id": str(batch_id), "last_7_days": 4, "last_30_days": 10}],
    }
    assert str(quiet) not in response.text

    theirs = api_client.get(
        "/v1/hub/listing/views", headers=bearer(owner_session, other.account_id)
    )
    assert theirs.json() == {
        "owner_page": {"last_7_days": 50, "last_30_days": 50},
        "batches": [
            {"batch_id": str(other.batch_id), "last_7_days": 50, "last_30_days": 50}
        ],
    }


def test_an_owner_with_no_views_reads_zero_and_others_are_refused(
    api_client: TestClient, owner_session: Session
) -> None:
    """No rows reads as zero; an account managing nothing gets no counts."""
    teacher = make_teacher(owner_session)
    empty = api_client.get(
        "/v1/hub/listing/views", headers=bearer(owner_session, teacher.account_id)
    )
    assert empty.status_code == 200
    assert empty.json() == {
        "owner_page": {"last_7_days": 0, "last_30_days": 0},
        "batches": [],
    }

    stranger = owner_session.execute(
        sa.text(
            "INSERT INTO account (id, phone, created_at) VALUES "
            "(gen_random_uuid(), '+8801711005050', now()) RETURNING id"
        )
    ).scalar_one()
    owner_session.commit()
    refused = api_client.get(
        "/v1/hub/listing/views", headers=bearer(owner_session, stranger)
    )
    assert refused.status_code == 403
    assert api_client.get("/v1/hub/listing/views").status_code == 401
