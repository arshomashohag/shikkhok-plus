"""The interest routes over HTTP [0049]: the wire, the switch and the lens.

The service's predicates are in ``test_interest.py``; here, what crosses
the wire on each side, that an off switch answers the same 404 on every
gated route and never hides the family's own list, and that the owner's
routes need the owner's lens.
"""

from __future__ import annotations

from typing import Final

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from markupsafe import escape
from sqlalchemy.orm import Session

from app.hub.public.messages import t
from app.hub.public.settings import HUB_ENQUIRIES_ENV
from tests.conftest import bearer
from tests.enquiries.support import EnquirableWorld, enquirable_owner, guardian

#: The family's target and share paths for one batch.
TARGET: Final = "/v1/hub/owners/{slug}/batches/{batch}/interest-target"
SHARE: Final = "/v1/hub/owners/{slug}/batches/{batch}/interest"

#: The family's own interests, and the owner's.
MINE: Final = "/v1/me/hub/interests"
OWNER: Final = "/v1/hub/interests"

#: The share's body: the adult-guardian declaration, and nothing else.
DECLARED: Final = {"declares_adult_guardian": True}

#: What each side's body may carry, and nothing else.
TARGET_FIELDS: Final = {
    "owner_public_name",
    "batch_title",
    "has_phone",
    "already_shared",
}
MY_FIELDS: Final = {"id", "owner_public_name", "batch_title", "status", "shared_on"}
OWNER_FIELDS: Final = {"id", "batch_id", "batch_title", "guardian_phone", "shared_on"}


@pytest.mark.usefixtures("enquiries_on")
def test_the_family_and_the_owner_each_see_only_their_own_fields(
    api_client: TestClient, owner_session: Session
) -> None:
    """The family is never shown a number; the owner is shown only the number.

    :param api_client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    world = enquirable_owner(owner_session)
    family = guardian(owner_session)
    headers = bearer(owner_session, family)
    path = {"slug": world.owner_slug, "batch": world.batch_id}

    target = api_client.get(TARGET.format(**path), headers=headers)
    assert target.status_code == 200, target.text
    assert set(target.json()) == TARGET_FIELDS
    assert target.json()["has_phone"] is True

    shared = api_client.post(SHARE.format(**path), json=DECLARED, headers=headers)
    assert shared.status_code == 201, shared.text
    assert set(shared.json()) == MY_FIELDS

    mine = api_client.get(MINE, headers=headers)
    assert [set(row) for row in mine.json()] == [MY_FIELDS]

    listed = api_client.get(OWNER, headers=bearer(owner_session, world.lens.account_id))
    assert listed.status_code == 200, listed.text
    [row] = listed.json()
    assert set(row) == OWNER_FIELDS
    assert row["guardian_phone"] == "+8801712345678"

    closed = api_client.post(
        f"{OWNER}/{row['id']}/close",
        headers=bearer(owner_session, world.lens.account_id),
    )
    assert closed.status_code == 204
    assert (
        api_client.get(
            OWNER, headers=bearer(owner_session, world.lens.account_id)
        ).json()
        == []
    )


@pytest.mark.usefixtures("enquiries_on")
def test_a_family_holds_no_lens_for_the_owners_list(
    api_client: TestClient, owner_session: Session
) -> None:
    """A family reading the owner's list is refused by the lens, not by data.

    :param api_client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    family = guardian(owner_session)
    response = api_client.get(OWNER, headers=bearer(owner_session, family))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NO_TEACHER_LENS"


@pytest.mark.usefixtures("enquiries_on")
def test_withdrawing_over_http_removes_it_from_both_lists(
    api_client: TestClient, owner_session: Session
) -> None:
    """A family's DELETE takes the interest off the owner's list too.

    :param api_client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    world = enquirable_owner(owner_session)
    family = guardian(owner_session)
    headers = bearer(owner_session, family)
    shared = api_client.post(
        SHARE.format(slug=world.owner_slug, batch=world.batch_id),
        json=DECLARED,
        headers=headers,
    ).json()

    assert (
        api_client.delete(f"{MINE}/{shared['id']}", headers=headers).status_code == 204
    )
    assert api_client.get(MINE, headers=headers).json() == []
    owner_headers = bearer(owner_session, world.lens.account_id)
    assert api_client.get(OWNER, headers=owner_headers).json() == []


@pytest.mark.usefixtures("enquiries_off")
def test_the_switch_off_answers_one_404_and_keeps_the_familys_own_list(
    api_client: TestClient, owner_session: Session
) -> None:
    """Every gated interest route answers HUB_ENQUIRIES_OFF; the family's list does not.

    :param api_client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    world = enquirable_owner(owner_session)
    family = guardian(owner_session)
    headers = bearer(owner_session, family)
    path = {"slug": world.owner_slug, "batch": world.batch_id}
    owner_headers = bearer(owner_session, world.lens.account_id)

    for response in (
        api_client.get(TARGET.format(**path), headers=headers),
        api_client.post(SHARE.format(**path), json=DECLARED, headers=headers),
        api_client.get(OWNER, headers=owner_headers),
        api_client.post(
            f"{OWNER}/00000000-0000-0000-0000-000000000000/close", headers=owner_headers
        ),
    ):
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "HUB_ENQUIRIES_OFF"

    assert api_client.get(MINE, headers=headers).status_code == 200


@pytest.mark.usefixtures("enquiries_on")
@pytest.mark.parametrize(
    "body",
    [{}, {"declares_adult_guardian": False}, {"declares_adult_guardian": 1}],
    ids=["missing", "false", "one"],
)
def test_sharing_needs_the_adult_guardian_declaration(
    api_client: TestClient, owner_session: Session, body: dict[str, object]
) -> None:
    """Without a JSON true, nothing is shared: a child's number never goes out.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param body: A body that does not declare
    :return: None
    """
    world = enquirable_owner(owner_session)
    family = guardian(owner_session)
    response = api_client.post(
        SHARE.format(slug=world.owner_slug, batch=world.batch_id),
        json=body,
        headers=bearer(owner_session, family),
    )
    assert response.status_code == 422
    owner_headers = bearer(owner_session, world.lens.account_id)
    assert api_client.get(OWNER, headers=owner_headers).json() == []


def _batch_page(owner_session: Session, world: EnquirableWorld) -> str:
    """Build a world's public batch page path, in English.

    :param owner_session: An arranging session
    :param world: The enquirable world
    :return: The path
    """
    slug = owner_session.execute(
        sa.text("SELECT slug FROM batch_listing WHERE batch_id = :b"),
        {"b": world.batch_id},
    ).scalar_one()
    return f"/hub/en/t/{world.owner_slug}/{slug}"


def test_the_batch_page_offers_interest_even_when_admissions_are_closed(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A full batch shows "I'm interested" and no "Ask to join"; off shows neither.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param monkeypatch: The patcher
    :return: None
    """
    world = enquirable_owner(owner_session, admissions="closed")
    path = _batch_page(owner_session, world)
    monkeypatch.setenv(HUB_ENQUIRIES_ENV, "on")

    page = api_client.get(path).text
    href = f"/ui/hub-interest?owner={world.owner_slug}&amp;batch={world.batch_id}"
    assert href in page
    assert str(escape(t("interest_link", "en"))) in page
    assert "hub-enquiry" not in page

    monkeypatch.setenv(HUB_ENQUIRIES_ENV, "off")
    off = api_client.get(path).text
    assert "hub-interest" not in off
    assert str(escape(t("interest_link", "en"))) not in off
