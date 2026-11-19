"""The "Pull reviews" measure on the admin overview (Call 17, spec section 9).

Three figures over a trailing 91 days, all computed in SQL: the reviews that
were public (published, held, or removed inside the window), the distinct
ones among them reported inside the window, and whether reported reviews
exceed 5% of public ones -- ``reported * 100 > public * 5``.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.admin.overview import overview
from app.authz.admin import PLATFORM_ADMIN_PHONES_ENV
from app.local_time import bangladesh_today
from tests.admin.conftest import admin_headers
from tests.help.conftest import People, phone_of
from tests.reviews.support import account, add_review, public_batch

NOW = dt.datetime.now(tz=dt.UTC)


def _review(
    session: Session,
    batch_id: uuid.UUID,
    status: str = "published",
    *,
    decided_at: dt.datetime | None = None,
) -> uuid.UUID:
    """Store a review in a status.

    :param session: An arranging session
    :param batch_id: The batch
    :param status: Its status
    :param decided_at: When moderation last decided it
    :return: The review id
    """
    review_id = add_review(session, batch_id, account(session))
    shown = status in ("published", "held")
    session.execute(
        sa.text(
            "UPDATE review SET status = CAST(:s AS hub_review_status), "
            "published_month = :m, rejection_code = :c, decided_at = :d "
            "WHERE id = :r"
        ),
        {
            "s": status,
            "m": bangladesh_today().replace(day=1) if shown else None,
            "c": "other" if status in ("removed", "rejected") else None,
            "d": decided_at,
            "r": review_id,
        },
    )
    session.commit()
    return review_id


def _report(
    session: Session,
    target: uuid.UUID,
    *,
    kind: str = "review",
    days_ago: int = 1,
) -> None:
    """Store a report on a review or reply, some days back.

    :param session: An arranging session
    :param target: The review id
    :param kind: ``review`` or ``reply``
    :param days_ago: How old the report is
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO hub_report (id, target_kind, target_id, "
            "reporter_account_id, reason, created_at) VALUES (gen_random_uuid(), "
            "CAST(:k AS hub_report_target), :t, :a, 'other', :c)"
        ),
        {
            "k": kind,
            "t": target,
            "a": account(session),
            "c": NOW - dt.timedelta(days=days_ago),
        },
    )
    session.commit()


def _figures(session: Session) -> tuple[int, int, bool]:
    """Read the three figures through the overview.

    :param session: The restricted session
    :return: ``(public, reported, pull bar)``
    """
    o = overview(session, NOW)
    return o.hub_reviews_public, o.hub_reviews_reported, o.hub_reviews_pull_bar


@pytest.mark.parametrize(
    ("public", "reported", "expected"),
    [(0, 0, False), (20, 1, False), (20, 2, True)],
    ids=["nothing", "five-percent", "over-five-percent"],
)
def test_pull_bar_figures(
    owner_session: Session,
    restricted_session: Session,
    public: int,
    reported: int,
    expected: bool,
) -> None:
    """The bar is crossed only strictly above 5%."""
    batch = public_batch(owner_session)
    ids = [_review(owner_session, batch.batch_id) for _ in range(public)]
    for target in ids[:reported]:
        _report(owner_session, target)

    assert _figures(restricted_session) == (public, reported, expected)


def test_pull_bar_counts_only_the_window_and_public_reviews(
    owner_session: Session, restricted_session: Session
) -> None:
    """What counts as public and as reported, and what the window leaves out."""
    batch = public_batch(owner_session)
    published = _review(owner_session, batch.batch_id)
    held = _review(owner_session, batch.batch_id, "held")
    removed = _review(
        owner_session, batch.batch_id, "removed", decided_at=NOW - dt.timedelta(days=5)
    )
    old_removed = _review(
        owner_session,
        batch.batch_id,
        "removed",
        decided_at=NOW - dt.timedelta(days=120),
    )
    pending = _review(owner_session, batch.batch_id, "pending")
    _review(owner_session, batch.batch_id, "rejected", decided_at=NOW)
    # Two reports on one review count it once; a report older than the
    # window, a report on a reply and a report on a review never public
    # count nothing.
    _report(owner_session, held)
    _report(owner_session, held, days_ago=3)
    _report(owner_session, removed, days_ago=90)
    _report(owner_session, published, days_ago=92)
    _report(owner_session, published, kind="reply")
    _report(owner_session, old_removed)
    _report(owner_session, pending)

    assert _figures(restricted_session) == (3, 2, True)


def test_overview_route_carries_the_review_figures(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The three figures cross the wire as plain numbers and a flag."""
    batch = public_batch(owner_session)
    target = _review(owner_session, batch.batch_id)
    _report(owner_session, target)
    monkeypatch.setenv(
        PLATFORM_ADMIN_PHONES_ENV, phone_of(owner_session, people.stranger)
    )

    response = api_client.get(
        "/v1/admin/overview", headers=admin_headers(owner_session, people.stranger)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (
        body["hub_reviews_public"],
        body["hub_reviews_reported"],
        body["hub_reviews_pull_bar"],
    ) == (1, 1, True)
