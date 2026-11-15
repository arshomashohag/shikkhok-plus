"""Reports: filing, refusal shapes, the ceiling and the admin queue."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.ceilings import HUB_REPORT_ACCOUNT_DAILY, CeilingBreach
from app.authz.admin import PLATFORM_ADMIN_PHONES_ENV
from app.authz.lenses import PlatformAdminLens
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.help.identity import requester_ref
from app.moderation import reports
from tests.batches.conftest import make_teacher
from tests.conftest import bearer
from tests.help.conftest import People, phone_of
from tests.moderation.conftest import admin_headers
from tests.moderation.support import publish_batch, publish_owner, status_of

NOW = dt.datetime(2026, 11, 14, 9, 0, tzinfo=dt.UTC)


def _reporter(session: Session) -> uuid.UUID:
    """Create a reporting account.

    :param session: An arranging session
    :return: Its id
    """
    return make_teacher(session).account_id


def test_report_never_changes_listing_status(
    owner_session: Session, restricted_session: Session
) -> None:
    """Filing records the complaint and the event, and nothing else."""
    target = make_teacher(owner_session)
    publish_owner(owner_session, target.owner_id)
    publish_batch(owner_session, target.owner_id, target.batch_id)
    reporter = _reporter(owner_session)

    reports.file(
        restricted_session, reporter, "listing", target.owner_id, "abusive", None, NOW
    )
    reports.file(
        restricted_session, reporter, "listing", target.batch_id, "fake", "no", NOW
    )

    assert status_of(owner_session, "owner_listing", "owner_id", target.owner_id) == (
        "published"
    )
    assert status_of(owner_session, "batch_listing", "batch_id", target.batch_id) == (
        "published"
    )
    events = owner_session.execute(
        sa.text("SELECT event, actor_admin_account_id FROM hub_moderation_event")
    ).all()
    assert [e.event for e in events] == ["report_filed", "report_filed"]
    assert all(e.actor_admin_account_id is None for e in events)


@pytest.mark.parametrize("status", ["draft", "hidden", "suspended"])
def test_report_on_draft_or_missing_listing_is_identical_refusal(
    owner_session: Session, restricted_session: Session, status: str
) -> None:
    """Draft, hidden, suspended, missing and unbuilt kinds all read the same."""
    target = make_teacher(owner_session)
    publish_owner(owner_session, target.owner_id, status=status)
    reporter = _reporter(owner_session)
    refusals = []
    for kind, target_id in (
        ("listing", target.owner_id),
        ("listing", uuid.uuid4()),
        ("media", target.owner_id),
        ("review", uuid.uuid4()),
        ("reply", uuid.uuid4()),
    ):
        with pytest.raises(AuthorizationError) as caught:
            reports.file(
                restricted_session, reporter, kind, target_id, "other", None, NOW
            )
        restricted_session.rollback()
        refusals.append(
            (caught.value.code, caught.value.message_key, caught.value.status)
        )

    assert len(set(refusals)) == 1
    assert refusals[0] == (
        "REPORT_TARGET_NOT_FOUND",
        "hub.report_target_not_found",
        404,
    )
    assert (
        owner_session.execute(sa.text("SELECT count(*) FROM hub_report")).scalar_one()
        == 0
    )


def test_second_report_same_target_is_conflict(
    owner_session: Session, restricted_session: Session
) -> None:
    """One reporter, one target, one report."""
    target = make_teacher(owner_session)
    publish_owner(owner_session, target.owner_id)
    reporter = _reporter(owner_session)
    reports.file(
        restricted_session, reporter, "listing", target.owner_id, "fake", None, NOW
    )

    with pytest.raises(ConflictError) as caught:
        reports.file(
            restricted_session,
            reporter,
            "listing",
            target.owner_id,
            "abusive",
            None,
            NOW,
        )

    assert caught.value.code == "REPORT_ALREADY_FILED"
    assert caught.value.message_key == "hub.report_already_filed"


def test_eleventh_report_in_a_day_is_ceiling(
    owner_session: Session, restricted_session: Session
) -> None:
    """Ten reports a day per account; the eleventh is HUB_WRITE_CEILING."""
    assert HUB_REPORT_ACCOUNT_DAILY == 10
    reporter = _reporter(owner_session)
    for _ in range(HUB_REPORT_ACCOUNT_DAILY):
        target = make_teacher(owner_session)
        publish_owner(owner_session, target.owner_id)
        reports.file(
            restricted_session, reporter, "listing", target.owner_id, "fake", None, NOW
        )
    last = make_teacher(owner_session)
    publish_owner(owner_session, last.owner_id)

    with pytest.raises(CeilingBreach) as caught:
        reports.file(
            restricted_session, reporter, "listing", last.owner_id, "fake", None, NOW
        )

    assert caught.value.code == "HUB_WRITE_CEILING"
    assert caught.value.message_key == "hub.write_ceiling"


def test_report_note_with_phone_number_is_refused(
    owner_session: Session, restricted_session: Session
) -> None:
    """A note carrying a number is refused before anything is written."""
    target = make_teacher(owner_session)
    publish_owner(owner_session, target.owner_id)
    reporter = _reporter(owner_session)

    with pytest.raises(ValidationError) as caught:
        reports.file(
            restricted_session,
            reporter,
            "listing",
            target.owner_id,
            "personal_info",
            "call me on 01712345678",
            NOW,
        )

    assert caught.value.code == "HUB_TEXT_CONTAINS_CONTACT"


def test_admin_queue_has_no_reporter_phone_or_name(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The queue shows the target's text and an opaque reporter label."""
    monkeypatch.setenv(
        PLATFORM_ADMIN_PHONES_ENV, phone_of(owner_session, people.stranger)
    )
    target = make_teacher(owner_session)
    publish_owner(owner_session, target.owner_id, name="Rahim Sir")
    reporter = people.student
    owner_session.commit()
    response = api_client.post(
        "/v1/hub/reports",
        json={
            "target_kind": "listing",
            "target_id": str(target.owner_id),
            "reason": "misleading",
            "note": "Not who they say",
        },
        headers=bearer(owner_session, reporter),
    )
    assert response.status_code == 202, response.text
    owner_session.commit()

    headers = admin_headers(owner_session, people.stranger)
    queue = api_client.get("/v1/admin/hub/queue?kind=report", headers=headers)

    assert queue.status_code == 200, queue.text
    items = queue.json()["items"]
    assert len(items) == 1
    assert items[0]["reporter_ref"] == requester_ref(reporter)
    assert items[0]["title"] == "Rahim Sir"
    assert items[0]["reason"] == "misleading"
    assert items[0]["note"] == "Not who they say"
    assert items[0]["waited_hours"] >= 0
    raw = queue.text
    assert phone_of(owner_session, reporter) not in raw
    assert str(reporter) not in raw
    assert "reporter_account_id" not in raw
    schema = api_client.get("/openapi.json").json()
    names = {
        name.lower()
        for comp in schema["components"]["schemas"].values()
        if comp.get("title", "").startswith("AdminHub")
        for name in comp.get("properties", {})
    }
    assert names, "no AdminHub* schema found"
    assert not names & {"phone", "name", "reporter_account_id", "account_id"}


def test_report_route_returns_202_and_conflicts_on_repeat(
    api_client: TestClient, owner_session: Session, people: People
) -> None:
    """The route answers 202, then 409 with its own code."""
    target = make_teacher(owner_session)
    publish_owner(owner_session, target.owner_id)
    owner_session.commit()
    headers = bearer(owner_session, people.student)
    body = {
        "target_kind": "listing",
        "target_id": str(target.owner_id),
        "reason": "fake",
    }

    first = api_client.post("/v1/hub/reports", json=body, headers=headers)
    second = api_client.post("/v1/hub/reports", json=body, headers=headers)
    missing = api_client.post(
        "/v1/hub/reports",
        json={**body, "target_id": str(uuid.uuid4())},
        headers=headers,
    )

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "REPORT_ALREADY_FILED"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "REPORT_TARGET_NOT_FOUND"


def test_decide_sets_status_and_second_decision_conflicts(
    owner_session: Session, restricted_session: Session
) -> None:
    """Upholding records who decided; deciding again is a conflict."""
    target = make_teacher(owner_session)
    publish_owner(owner_session, target.owner_id)
    reporter = _reporter(owner_session)
    admin_id = _reporter(owner_session)
    reports.file(
        restricted_session, reporter, "listing", target.owner_id, "fake", None, NOW
    )
    report_id = owner_session.execute(sa.text("SELECT id FROM hub_report")).scalar_one()
    admin = PlatformAdminLens(account_id=admin_id)

    reports.decide(restricted_session, admin, report_id, "upheld", NOW)

    row = owner_session.execute(
        sa.text("SELECT status, decided_by_account_id FROM hub_report")
    ).one()
    assert (row.status, row.decided_by_account_id) == ("upheld", admin_id)
    events = owner_session.execute(
        sa.text("SELECT event FROM hub_moderation_event ORDER BY at, event")
    ).scalars()
    assert set(events) == {"report_filed", "report_upheld"}
    with pytest.raises(ConflictError) as caught:
        reports.decide(restricted_session, admin, report_id, "dismissed", NOW)
    assert caught.value.code == "REPORT_ALREADY_DECIDED"
