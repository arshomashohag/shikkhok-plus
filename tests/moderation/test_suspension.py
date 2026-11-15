"""Suspension: hiding batches, notifying managers, the event and the way back."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.authz.admin import PLATFORM_ADMIN_PHONES_ENV
from app.authz.lenses import PlatformAdminLens
from app.errors import AuthorizationError, ValidationError
from app.moderation import suspension
from app.notifications.inbox import HUB_LISTING_SUSPENDED, LEGACY_KINDS
from tests.batches.conftest import make_teacher
from tests.conftest import bearer
from tests.help.conftest import People, phone_of
from tests.hub.support import add_member, centre_with_manager
from tests.moderation.conftest import admin_headers
from tests.moderation.support import publish_batch, publish_owner, status_of

NOW = dt.datetime(2026, 11, 14, 9, 0, tzinfo=dt.UTC)


def _admin(session: Session) -> PlatformAdminLens:
    """Make an administrator's lens over a fresh account.

    :param session: An arranging session
    :return: The lens
    """
    return PlatformAdminLens(account_id=make_teacher(session).account_id)


def test_suspension_hides_batches_notifies_managers_and_logs_event(
    owner_session: Session, restricted_session: Session
) -> None:
    """A centre suspended: listing suspended, batches hidden, managers told."""
    centre = centre_with_manager(owner_session)
    _, second_manager = add_member(
        owner_session, centre.owner_id, role="manager", name="Salma"
    )
    _, plain_teacher = add_member(owner_session, centre.owner_id, role="teacher")
    _, revoked = add_member(
        owner_session, centre.owner_id, role="manager", revoked=True
    )
    publish_owner(owner_session, centre.owner_id, name="Udoy Coaching")
    publish_batch(owner_session, centre.owner_id, centre.batch_id)
    admin = _admin(owner_session)

    suspension.set(
        restricted_session, admin, centre.owner_id, True, "child_safety", NOW
    )

    assert (
        status_of(owner_session, "owner_listing", "owner_id", centre.owner_id)
        == "suspended"
    )
    assert (
        status_of(owner_session, "batch_listing", "batch_id", centre.batch_id)
        == "hidden"
    )
    row = owner_session.execute(
        sa.text(
            "SELECT suspended_at, suspension_reason_code FROM owner_listing "
            "WHERE owner_id = :o"
        ),
        {"o": centre.owner_id},
    ).one()
    assert row.suspended_at == NOW
    assert row.suspension_reason_code == "child_safety"
    notified = set(
        owner_session.execute(
            sa.text(
                "SELECT account_id FROM notification WHERE kind = :k "
                "AND batch_name = 'Udoy Coaching'"
            ),
            {"k": HUB_LISTING_SUSPENDED},
        ).scalars()
    )
    assert notified == {centre.manager_account_id, second_manager}
    assert plain_teacher not in notified
    assert revoked not in notified
    event = owner_session.execute(
        sa.text(
            "SELECT event, target_kind, target_id, actor_admin_account_id, "
            "decision_code FROM hub_moderation_event"
        )
    ).one()
    assert tuple(event) == (
        "listing_suspended",
        "owner_listing",
        centre.owner_id,
        admin.account_id,
        "child_safety",
    )
    assert HUB_LISTING_SUSPENDED == "hub_listing_suspended"
    assert HUB_LISTING_SUSPENDED not in LEGACY_KINDS


def test_solo_owner_is_notified(
    owner_session: Session, restricted_session: Session
) -> None:
    """A solo tutor's own account gets the notice."""
    teacher = make_teacher(owner_session)
    publish_owner(owner_session, teacher.owner_id)

    suspension.set(
        restricted_session, _admin(owner_session), teacher.owner_id, True, "fake", NOW
    )

    got = owner_session.execute(
        sa.text("SELECT account_id FROM notification WHERE kind = :k"),
        {"k": HUB_LISTING_SUSPENDED},
    ).scalars()
    assert list(got) == [teacher.account_id]


def test_unsuspend_returns_owner_listing_to_hidden_not_published(
    owner_session: Session, restricted_session: Session
) -> None:
    """Lifting a suspension never republishes anything."""
    teacher = make_teacher(owner_session)
    publish_owner(owner_session, teacher.owner_id)
    publish_batch(owner_session, teacher.owner_id, teacher.batch_id)
    admin = _admin(owner_session)
    suspension.set(restricted_session, admin, teacher.owner_id, True, "abusive", NOW)

    suspension.set(restricted_session, admin, teacher.owner_id, False, "abusive", NOW)

    assert (
        status_of(owner_session, "owner_listing", "owner_id", teacher.owner_id)
        == "hidden"
    )
    assert (
        status_of(owner_session, "batch_listing", "batch_id", teacher.batch_id)
        == "hidden"
    )
    row = owner_session.execute(
        sa.text("SELECT suspended_at, suspension_reason_code FROM owner_listing")
    ).one()
    assert (row.suspended_at, row.suspension_reason_code) == (None, None)
    events = owner_session.execute(
        sa.text("SELECT event FROM hub_moderation_event")
    ).scalars()
    assert set(events) == {"listing_suspended", "listing_unsuspended"}


def test_suspending_an_owner_without_a_listing_is_not_found(
    owner_session: Session, restricted_session: Session
) -> None:
    """No listing, nothing to suspend."""
    teacher = make_teacher(owner_session)
    with pytest.raises(AuthorizationError) as caught:
        suspension.set(
            restricted_session,
            _admin(owner_session),
            teacher.owner_id,
            True,
            "fake",
            NOW,
        )
    assert caught.value.status == 404
    with pytest.raises(AuthorizationError):
        suspension.set(
            restricted_session, _admin(owner_session), uuid.uuid4(), True, "fake", NOW
        )


def test_reason_code_must_be_in_the_fixed_set(
    owner_session: Session, restricted_session: Session
) -> None:
    """A free-form reason is refused before any write."""
    teacher = make_teacher(owner_session)
    publish_owner(owner_session, teacher.owner_id)
    with pytest.raises(ValidationError):
        suspension.set(
            restricted_session,
            _admin(owner_session),
            teacher.owner_id,
            True,
            "because i said so",
            NOW,
        )
    assert (
        status_of(owner_session, "owner_listing", "owner_id", teacher.owner_id)
        == "published"
    )


def test_non_admin_cannot_reach_admin_hub_routes(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even a signed-in teacher with an admin-shaped token gets 403."""
    monkeypatch.setenv(
        PLATFORM_ADMIN_PHONES_ENV, phone_of(owner_session, people.stranger)
    )
    headers = admin_headers(owner_session, people.teacher.account_id)
    rid = uuid.uuid4()
    calls = (
        api_client.get("/v1/admin/hub/queue?kind=report", headers=headers),
        api_client.post(
            f"/v1/admin/hub/reports/{rid}/decision",
            json={"decision": "upheld"},
            headers=headers,
        ),
        api_client.put(
            f"/v1/admin/hub/owners/{rid}/suspension",
            json={"suspended": True, "reason_code": "fake"},
            headers=headers,
        ),
    )
    assert [c.status_code for c in calls] == [403, 403, 403]
    app_headers = bearer(owner_session, people.stranger)
    owner_session.commit()
    assert api_client.get(
        "/v1/admin/hub/queue?kind=report", headers=app_headers
    ).status_code in {401, 404}


def test_admin_suspends_decides_and_lists_over_http(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The three admin routes end to end."""
    monkeypatch.setenv(
        PLATFORM_ADMIN_PHONES_ENV, phone_of(owner_session, people.stranger)
    )
    target = make_teacher(owner_session)
    publish_owner(owner_session, target.owner_id)
    owner_session.commit()
    reporter = bearer(owner_session, people.student)
    filed = api_client.post(
        "/v1/hub/reports",
        json={
            "target_kind": "owner_listing",
            "target_id": str(target.owner_id),
            "reason": "child_safety",
        },
        headers=reporter,
    )
    assert filed.status_code == 202
    owner_session.commit()
    headers = admin_headers(owner_session, people.stranger)
    report_id = api_client.get(
        "/v1/admin/hub/queue?kind=report", headers=headers
    ).json()["items"][0]["report_id"]

    decided = api_client.post(
        f"/v1/admin/hub/reports/{report_id}/decision",
        json={"decision": "upheld"},
        headers=headers,
    )
    again = api_client.post(
        f"/v1/admin/hub/reports/{report_id}/decision",
        json={"decision": "dismissed"},
        headers=headers,
    )
    suspended = api_client.put(
        f"/v1/admin/hub/owners/{target.owner_id}/suspension",
        json={"suspended": True, "reason_code": "child_safety"},
        headers=headers,
    )
    listed = api_client.get("/v1/admin/hub/queue?kind=listing", headers=headers)
    empty = api_client.get("/v1/admin/hub/queue?kind=report", headers=headers)

    assert decided.status_code == 200
    assert decided.json() == {"report_id": report_id, "status": "upheld"}
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "REPORT_ALREADY_DECIDED"
    assert suspended.status_code == 200
    assert suspended.json()["suspended"] is True
    assert [i["target_id"] for i in listed.json()["items"]] == [str(target.owner_id)]
    assert listed.json()["items"][0]["reason"] == "child_safety"
    assert empty.json()["items"] == []


def test_suspending_a_draft_listing_is_refused_cleanly(
    owner_session: Session, restricted_session: Session
) -> None:
    """A never-published draft cannot be suspended, and is not a 500."""
    teacher = make_teacher(owner_session)
    publish_owner(owner_session, teacher.owner_id, status="draft")
    with pytest.raises(AuthorizationError) as caught:
        suspension.set(
            restricted_session,
            _admin(owner_session),
            teacher.owner_id,
            True,
            "fake",
            NOW,
        )
    assert caught.value.code == "HUB_ADMIN_TARGET_NOT_FOUND"
    assert caught.value.status == 404
    assert (
        status_of(owner_session, "owner_listing", "owner_id", teacher.owner_id)
        == "draft"
    )


def test_hidden_listing_can_be_suspended(
    owner_session: Session, restricted_session: Session
) -> None:
    """A hidden listing is still suspendable."""
    teacher = make_teacher(owner_session)
    publish_owner(owner_session, teacher.owner_id, status="hidden")
    suspension.set(
        restricted_session, _admin(owner_session), teacher.owner_id, True, "fake", NOW
    )
    assert (
        status_of(owner_session, "owner_listing", "owner_id", teacher.owner_id)
        == "suspended"
    )
