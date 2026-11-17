"""The hub listing routes: the owner's page, the batch pages, member consent.

Each route is exercised through the real application against the restricted
database role, so a grant the application role lacks fails here and not in
production.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.ceilings import HUB_LISTING_OWNER_DAILY
from app.db.models import HUB_CLASS_LEVELS, HUB_CURRICULA, BatchSubject, OwnerMember
from app.hub.listings.consent import HUB_CONSENT_VERSION
from tests.batches.conftest import make_teacher
from tests.conftest import bearer
from tests.hub.support import (
    add_member,
    areas,
    assign_slot,
    centre_with_manager,
)

_FILL_OWNER = {
    "slug": "rahim-sir",
    "public_name": "Rahim Sir",
    "headline_en": "Maths for SSC",
    "bio_en": "Twelve years of teaching.",
}


def _solo(session: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Arrange a solo tutor whose batch has a subject.

    :param session: An arranging session
    :return: ``(account_id, owner_id, batch_id)``
    """
    teacher = make_teacher(session)
    session.add(BatchSubject(batch_id=teacher.batch_id, name="Maths"))
    session.commit()
    return teacher.account_id, teacher.owner_id, teacher.batch_id


def _complete_owner(
    client: TestClient, headers: dict[str, str], session: Session
) -> None:
    """Fill every required field of the owner's listing through the API.

    :param client: The test client
    :param headers: The request headers
    :param session: Any session, to pick real area codes
    :return: None
    """
    district, upazila, _ = areas(session)
    response = client.put(
        "/v1/hub/listing",
        json={**_FILL_OWNER, "district_code": district, "upazila_code": upazila},
        headers=headers,
    )
    assert response.status_code == 200, response.text


def _publish_owner(
    client: TestClient, headers: dict[str, str], session: Session
) -> None:
    """Complete and publish the owner's listing.

    :param client: The test client
    :param headers: The request headers
    :param session: Any session, to pick real area codes
    :return: None
    """
    _complete_owner(client, headers, session)
    response = client.post(
        "/v1/hub/listing/publish",
        json={"consent_version": HUB_CONSENT_VERSION},
        headers=headers,
    )
    assert response.status_code == 200, response.text


_BATCH_FILL = {
    "slug": "class-9-maths",
    "public_title": "Class 9 Maths",
    "description_en": "Weekly maths",
    "class_levels": ["class_9"],
    "mode": "in_person",
    "show_fee": True,
    "show_schedule": False,
}


def test_get_listing_returns_a_draft_with_its_checklist(
    api_client: TestClient, owner_session: Session
) -> None:
    """A first read creates a draft and says what it still needs."""
    account, _, _ = _solo(owner_session)

    response = api_client.get("/v1/hub/listing", headers=bearer(owner_session, account))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "draft"
    assert body["publishable"] is False
    assert body["runs_classes"] is False
    assert body["consent_version_current"] == HUB_CONSENT_VERSION
    keys = {item["key"]: item["done"] for item in body["checklist"]}
    assert keys["slug"] is False
    assert keys["contact_or_none"] is True


def test_put_listing_saves_the_edits(
    api_client: TestClient, owner_session: Session
) -> None:
    """An edit is returned back, and the checklist follows it."""
    account, _, _ = _solo(owner_session)
    headers = bearer(owner_session, account)

    response = api_client.put("/v1/hub/listing", json=_FILL_OWNER, headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["slug"] == "rahim-sir"
    assert body["headline_en"] == "Maths for SSC"
    done = {item["key"]: item["done"] for item in body["checklist"]}
    assert done["slug"] and done["bio"] and done["headline"] and done["public_name"]
    assert done["area"] is False


def test_put_listing_round_trips_the_latin_name(
    api_client: TestClient, owner_session: Session
) -> None:
    """``public_name_latin`` is optional, at most 120 characters, and echoed."""
    account, _, _ = _solo(owner_session)
    headers = bearer(owner_session, account)

    assert (
        api_client.get("/v1/hub/listing", headers=headers).json()["public_name_latin"]
        is None
    )
    saved = api_client.put(
        "/v1/hub/listing", json={"public_name_latin": "Rahim Sir"}, headers=headers
    )
    too_long = api_client.put(
        "/v1/hub/listing", json={"public_name_latin": "a" * 121}, headers=headers
    )

    assert saved.status_code == 200, saved.text
    assert saved.json()["public_name_latin"] == "Rahim Sir"
    assert too_long.status_code == 422


def test_publish_and_unpublish_round_trip(
    api_client: TestClient, owner_session: Session
) -> None:
    """Publishing needs the current consent text; hiding keeps the data."""
    account, _, _ = _solo(owner_session)
    headers = bearer(owner_session, account)
    _complete_owner(api_client, headers, owner_session)

    stale = api_client.post(
        "/v1/hub/listing/publish", json={"consent_version": "1999"}, headers=headers
    )
    assert stale.status_code == 400
    assert stale.json()["error"]["code"] == "HUB_CONSENT_OUTDATED"

    published = api_client.post(
        "/v1/hub/listing/publish",
        json={"consent_version": HUB_CONSENT_VERSION},
        headers=headers,
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    assert published.json()["publishable"] is True

    hidden = api_client.post("/v1/hub/listing/unpublish", headers=headers)
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["status"] == "hidden"
    assert hidden.json()["slug"] == "rahim-sir"


def test_publish_refuses_an_incomplete_listing(
    api_client: TestClient, owner_session: Session
) -> None:
    """The refusal names what is missing."""
    account, _, _ = _solo(owner_session)

    response = api_client.post(
        "/v1/hub/listing/publish",
        json={"consent_version": HUB_CONSENT_VERSION},
        headers=bearer(owner_session, account),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HUB_LISTING_INCOMPLETE"


def test_slug_availability_for_a_free_a_taken_and_a_malformed_slug(
    api_client: TestClient, owner_session: Session
) -> None:
    """Another owner's slug is taken; the caller's own is not."""
    mine, _, _ = _solo(owner_session)
    other, _, _ = _solo(owner_session)
    api_client.put(
        "/v1/hub/listing",
        json={"slug": "taken-slug"},
        headers=bearer(owner_session, other),
    )
    headers = bearer(owner_session, mine)

    free = api_client.get("/v1/hub/slugs/free-slug", headers=headers)
    taken = api_client.get("/v1/hub/slugs/taken-slug", headers=headers)
    bad = api_client.get("/v1/hub/slugs/No", headers=headers)

    assert free.json() == {"slug": "free-slug", "available": True}
    assert taken.json() == {"slug": "taken-slug", "available": False}
    assert bad.json() == {"slug": "No", "available": False}


def test_areas_lists_divisions_then_children(
    api_client: TestClient, owner_session: Session
) -> None:
    """No parent gives divisions; a parent gives its direct children."""
    account, _, _ = _solo(owner_session)
    headers = bearer(owner_session, account)

    divisions = api_client.get("/v1/hub/areas", headers=headers)
    assert divisions.status_code == 200, divisions.text
    rows = divisions.json()
    assert rows and {row["kind"] for row in rows} == {"division"}
    assert set(rows[0]) == {"code", "kind", "name_en", "name_bn"}

    children = api_client.get(
        "/v1/hub/areas", params={"parent": rows[0]["code"]}, headers=headers
    )
    assert children.status_code == 200
    assert {row["kind"] for row in children.json()} == {"district"}

    unknown = api_client.get(
        "/v1/hub/areas", params={"parent": "no-such-code"}, headers=headers
    )
    assert unknown.status_code == 200
    assert unknown.json() == []


def test_batch_listing_lifecycle(
    api_client: TestClient, owner_session: Session
) -> None:
    """List, save, publish and hide one batch listing."""
    account, _, batch_id = _solo(owner_session)
    headers = bearer(owner_session, account)
    _publish_owner(api_client, headers, owner_session)

    listed = api_client.get("/v1/hub/batch-listings", headers=headers)
    assert listed.status_code == 200, listed.text
    assert [row["batch_id"] for row in listed.json()] == [str(batch_id)]
    assert listed.json()[0]["status"] == "draft"
    assert listed.json()[0]["subjects"] == ["Maths"]

    saved = api_client.put(
        f"/v1/batches/{batch_id}/listing", json=_BATCH_FILL, headers=headers
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "draft"
    assert saved.json()["slug"] == "class-9-maths"
    assert saved.json()["public_title"] == "Class 9 Maths"

    published = api_client.post(
        f"/v1/batches/{batch_id}/listing/publish", headers=headers
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"

    hidden = api_client.post(
        f"/v1/batches/{batch_id}/listing/unpublish", headers=headers
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["status"] == "hidden"


def test_batch_listing_publish_needs_a_published_owner(
    api_client: TestClient, owner_session: Session
) -> None:
    """A batch cannot be public under an owner who is not."""
    account, _, batch_id = _solo(owner_session)
    headers = bearer(owner_session, account)
    api_client.put(f"/v1/batches/{batch_id}/listing", json=_BATCH_FILL, headers=headers)

    response = api_client.post(
        f"/v1/batches/{batch_id}/listing/publish", headers=headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HUB_OWNER_NOT_PUBLISHED"


def test_fee_is_a_json_string_only_when_shown(
    api_client: TestClient, owner_session: Session
) -> None:
    """``fee`` is the batch's default fee as a string, or null when hidden."""
    account, _, batch_id = _solo(owner_session)
    headers = bearer(owner_session, account)

    shown = api_client.put(
        f"/v1/batches/{batch_id}/listing", json=_BATCH_FILL, headers=headers
    )
    assert shown.json()["fee"] == "1500.00"
    assert isinstance(shown.json()["fee"], str)

    hidden = api_client.put(
        f"/v1/batches/{batch_id}/listing",
        json={"show_fee": False},
        headers=headers,
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["fee"] is None
    assert hidden.json()["show_fee"] is False


def test_a_solo_tutor_is_named_by_their_public_name(
    api_client: TestClient, owner_session: Session
) -> None:
    """With no members, the teacher shown is the owner's public name."""
    account, _, batch_id = _solo(owner_session)
    headers = bearer(owner_session, account)
    api_client.put("/v1/hub/listing", json=_FILL_OWNER, headers=headers)

    saved = api_client.put(
        f"/v1/batches/{batch_id}/listing", json=_BATCH_FILL, headers=headers
    )

    assert saved.json()["teacher_names"] == ["Rahim Sir"]


def test_unconsented_member_is_centre_faculty(
    api_client: TestClient, owner_session: Session
) -> None:
    """Only a consenting, live member is named; everyone else is faculty."""
    centre = centre_with_manager(owner_session)
    headers = {
        **bearer(owner_session, centre.manager_account_id),
        "X-Workspace-Id": str(centre.owner_id),
    }
    quiet, _ = add_member(owner_session, centre.owner_id, name="Quiet Sir")
    assign_slot(owner_session, centre.batch_id, quiet)

    undeclared = api_client.put(
        f"/v1/batches/{centre.batch_id}/listing", json=_BATCH_FILL, headers=headers
    )
    assert undeclared.status_code == 200, undeclared.text
    assert undeclared.json()["teacher_names"] == ["Centre faculty"]

    loud, _ = add_member(
        owner_session, centre.owner_id, name="Loud Sir", consented=True
    )
    gone, _ = add_member(
        owner_session,
        centre.owner_id,
        name="Gone Sir",
        consented=True,
        revoked=True,
    )
    assign_slot(owner_session, centre.batch_id, loud)
    assign_slot(owner_session, centre.batch_id, gone)

    named = api_client.put(
        f"/v1/batches/{centre.batch_id}/listing", json={}, headers=headers
    )
    assert named.json()["teacher_names"] == ["Loud Sir"]


def test_manager_can_edit_centre_listing_with_workspace_header(
    api_client: TestClient, owner_session: Session
) -> None:
    """A manager reaches the centre's listing by naming the workspace."""
    centre = centre_with_manager(owner_session)
    headers = {
        **bearer(owner_session, centre.manager_account_id),
        "X-Workspace-Id": str(centre.owner_id),
    }

    response = api_client.put(
        "/v1/hub/listing",
        json={"public_name": "Udoy Coaching Centre", "street_address": "12 Road"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["public_name"] == "Udoy Coaching Centre"


def test_class_teacher_cannot_edit_centre_listing(
    api_client: TestClient, owner_session: Session
) -> None:
    """A teacher-role member has no teacher lens on the centre."""
    centre = centre_with_manager(owner_session)
    _, teacher = add_member(owner_session, centre.owner_id, role="teacher")
    headers = {
        **bearer(owner_session, teacher),
        "X-Workspace-Id": str(centre.owner_id),
    }

    read = api_client.get("/v1/hub/listing", headers=headers)
    write = api_client.put(
        "/v1/hub/listing", json={"public_name": "Mine now"}, headers=headers
    )

    assert read.status_code == 403
    assert write.status_code == 403


def test_listing_update_ceiling_is_50_per_day(
    api_client: TestClient, owner_session: Session
) -> None:
    """The 51st update in a day is refused, on either PUT route."""
    account, _, batch_id = _solo(owner_session)
    headers = bearer(owner_session, account)
    assert HUB_LISTING_OWNER_DAILY == 50

    for i in range(HUB_LISTING_OWNER_DAILY - 1):
        ok = api_client.put(
            "/v1/hub/listing", json={"headline_en": f"h{i}"}, headers=headers
        )
        assert ok.status_code == 200, ok.text
    last = api_client.put(
        f"/v1/batches/{batch_id}/listing", json=_BATCH_FILL, headers=headers
    )
    assert last.status_code == 200, last.text

    refused = api_client.put(
        "/v1/hub/listing", json={"headline_en": "one more"}, headers=headers
    )
    refused_batch = api_client.put(
        f"/v1/batches/{batch_id}/listing", json={"show_fee": False}, headers=headers
    )

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "HUB_WRITE_CEILING"
    assert refused.json()["error"]["message_key"] == "hub.write_ceiling"
    assert refused.json()["error"]["retryable"] is False
    assert refused_batch.status_code == 409


def test_member_consents_and_withdraws(
    api_client: TestClient, owner_session: Session
) -> None:
    """True stamps the moment; false clears it; both answer 204."""
    centre = centre_with_manager(owner_session)
    member, account = add_member(owner_session, centre.owner_id)
    headers = bearer(owner_session, account)
    url = f"/v1/centres/{centre.owner_id}/members/me/public-name-consent"

    given = api_client.put(url, json={"consent": True}, headers=headers)
    assert given.status_code == 204, given.text
    owner_session.expire_all()
    stamped = owner_session.get(OwnerMember, member)
    assert stamped is not None and stamped.public_name_consent_at is not None
    assert dt.datetime.now(tz=dt.UTC) - stamped.public_name_consent_at < dt.timedelta(
        minutes=5
    )

    withdrawn = api_client.put(url, json={"consent": False}, headers=headers)
    assert withdrawn.status_code == 204, withdrawn.text
    owner_session.expire_all()
    cleared = owner_session.get(OwnerMember, member)
    assert cleared is not None and cleared.public_name_consent_at is None


def test_consent_route_refuses_pending_or_revoked_member(
    api_client: TestClient, owner_session: Session
) -> None:
    """Only an accepted, unrevoked member of that centre may consent."""
    centre = centre_with_manager(owner_session)
    other = centre_with_manager(owner_session, name="Other Centre")
    _, pending = add_member(owner_session, centre.owner_id, decision="pending")
    _, revoked = add_member(owner_session, centre.owner_id, revoked=True)
    _, declined = add_member(owner_session, centre.owner_id, decision="declined")
    url = f"/v1/centres/{centre.owner_id}/members/me/public-name-consent"

    for account in (pending, revoked, declined, other.manager_account_id):
        refused = api_client.put(
            url, json={"consent": True}, headers=bearer(owner_session, account)
        )
        assert refused.status_code == 403, refused.text

    stamped = owner_session.execute(
        sa.select(sa.func.count())
        .select_from(OwnerMember)
        .where(OwnerMember.public_name_consent_at.is_not(None))
    ).scalar_one()
    assert stamped == 0


def test_listing_refusals_surface_with_their_own_codes(
    api_client: TestClient, owner_session: Session
) -> None:
    """Area, phone-in-text and suspension refusals reach the client by code."""
    account, owner_id, _ = _solo(owner_session)
    headers = bearer(owner_session, account)
    district, _, other = areas(owner_session)
    upazila_elsewhere = owner_session.execute(
        sa.text(
            "SELECT code FROM bd_area WHERE kind = 'upazila' "
            "AND parent_code <> :d ORDER BY code LIMIT 1"
        ),
        {"d": district},
    ).scalar_one()

    mismatch = api_client.put(
        "/v1/hub/listing",
        json={"district_code": district, "upazila_code": upazila_elsewhere},
        headers=headers,
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["error"]["code"] == "HUB_AREA_MISMATCH"

    contact = api_client.put(
        "/v1/hub/listing",
        json={"bio_en": "Call me on 01711234567"},
        headers=headers,
    )
    assert contact.status_code == 400
    assert contact.json()["error"]["code"] == "HUB_TEXT_CONTAINS_CONTACT"

    api_client.put("/v1/hub/listing", json=_FILL_OWNER, headers=headers)
    owner_session.execute(
        sa.text(
            "UPDATE owner_listing SET status = 'suspended', suspended_at = now(), "
            "suspension_reason_code = 'fake' WHERE owner_id = :o"
        ),
        {"o": owner_id},
    )
    owner_session.commit()
    suspended = api_client.put(
        "/v1/hub/listing", json={"headline_en": "x"}, headers=headers
    )
    assert suspended.status_code == 409
    assert suspended.json()["error"]["code"] == "HUB_LISTING_SUSPENDED"
    assert other != district


def test_listing_says_whether_the_owner_is_a_centre(
    api_client: TestClient, owner_session: Session
) -> None:
    """``is_centre`` follows the owner's kind, so only centres get an address field."""
    solo_account, _, _ = _solo(owner_session)
    centre = centre_with_manager(owner_session)

    solo = api_client.get(
        "/v1/hub/listing", headers=bearer(owner_session, solo_account)
    )
    organisation = api_client.get(
        "/v1/hub/listing",
        headers={
            **bearer(owner_session, centre.manager_account_id),
            "X-Workspace-Id": str(centre.owner_id),
        },
    )

    assert solo.json()["is_centre"] is False
    assert organisation.json()["is_centre"] is True


def test_centre_memberships_list_only_my_accepted_live_ones_with_consent(
    api_client: TestClient, owner_session: Session
) -> None:
    """The caller sees their own accepted, unrevoked memberships and consent state."""
    centre = centre_with_manager(owner_session, name="Udoy Coaching")
    other = centre_with_manager(owner_session, name="Other Centre")
    member, account = add_member(owner_session, centre.owner_id, consented=True)
    add_member(owner_session, other.owner_id, account_id=account, consented=False)
    add_member(owner_session, centre.owner_id, decision="pending", account_id=account)
    add_member(owner_session, other.owner_id, revoked=True, account_id=account)
    # Someone else's membership never appears.
    add_member(owner_session, centre.owner_id, consented=True)

    response = api_client.get(
        "/v1/me/centre-memberships", headers=bearer(owner_session, account)
    )

    assert response.status_code == 200, response.text
    rows = {r["centre_name"]: r for r in response.json()}
    assert set(rows) == {"Udoy Coaching", "Other Centre"}
    assert rows["Udoy Coaching"] == {
        "member_id": str(member),
        "centre_id": str(centre.owner_id),
        "centre_name": "Udoy Coaching",
        "role": "teacher",
        "public_name_consent": True,
        "name_shown": "Karim Sir",
    }
    assert rows["Other Centre"]["public_name_consent"] is False


def test_batch_vocabularies_are_closed_in_the_contract(
    api_client: TestClient, owner_session: Session
) -> None:
    """Class levels and curriculum are enums on the wire, and "9" is refused.

    A free-text "9, 10" would pass any client and fail the database's
    closed vocabulary, so the contract carries the vocabulary itself.
    """
    schema = api_client.get("/openapi.json").json()["components"]["schemas"]
    request = schema["BatchListingUpdateRequest"]["properties"]
    levels = request["class_levels"]["anyOf"][0]["items"]
    assert tuple(_enum_of(schema, levels)) == HUB_CLASS_LEVELS
    curricula = {
        value
        for option in request["curriculum"]["anyOf"]
        for value in _enum_of(schema, option)
    }
    assert curricula == {*HUB_CURRICULA, ""}

    account, _, batch_id = _solo(owner_session)
    headers = bearer(owner_session, account)
    for bad in ({"class_levels": ["9"]}, {"curriculum": "ib"}):
        refused = api_client.put(
            f"/v1/batches/{batch_id}/listing",
            json={**_BATCH_FILL, **bad},
            headers=headers,
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "REQUEST_INVALID"


def _enum_of(schema: dict[str, dict], node: dict) -> list[str]:
    """Read the enum values of a schema node, following a reference.

    :param schema: The document's component schemas
    :param node: A property schema
    :return: Its enum values, or none
    """
    if "$ref" in node:
        node = schema[node["$ref"].rsplit("/", 1)[-1]]
    if "const" in node:
        return [node["const"]]
    return list(node.get("enum", []))
