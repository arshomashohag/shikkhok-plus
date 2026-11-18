"""Targeted probes over the real public hub pages and the owner preview.

The canary walk proves no seeded private string appears anywhere. These
tests name each rule the seeded world exists to exercise, so a failure says
which rule broke, and each also asserts the thing that SHOULD be public, so
a page that renders nothing cannot pass for a page that hides everything.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.hub_media import media_store
from app.contract.routes import PUBLIC_CACHEABLE_ROUTES
from app.db.models import Owner
from app.hub.public.messages import t
from tests.conftest import bearer
from tests.hub.media.fakes import FakeMediaStore
from tests.privacy.canary import (
    LOCALES,
    CanaryWorld,
    canary_leaks,
    seed_canaries,
    walk_cacheable_routes,
)


def _walk(
    owner_session: Session, api_client: TestClient
) -> tuple[CanaryWorld, dict[str, str]]:
    """Seed the world and render every cacheable public page.

    :param owner_session: A session able to arrange the seeded world
    :param api_client: A client over the real application
    :return: The world and the bodies keyed by path
    """
    world = seed_canaries(owner_session)
    return world, walk_cacheable_routes(api_client, world, PUBLIC_CACHEABLE_ROUTES)


def _everywhere(bodies: dict[str, str], needle: str) -> list[str]:
    """List the paths whose body contains a string, case-insensitively.

    :param bodies: Body text keyed by path
    :param needle: The string to look for
    :return: The paths that contain it
    """
    return [p for p, body in bodies.items() if needle.lower() in body.lower()]


def test_draft_canary_never_public(
    owner_session: Session, api_client: TestClient
) -> None:
    """A never-published owner's name and slug appear on no public body.

    Its batch listing is published, so this also proves an owner's draft
    status hides the batch.

    :param owner_session: A session able to arrange the seeded world
    :param api_client: A client over the real application
    :return: None
    """
    world, bodies = _walk(owner_session, api_client)

    # Positive controls: search and sitemap list the seeded listings, so an
    # empty list cannot make the absence checks below pass.
    for locale in LOCALES:
        assert world.owner_slug in bodies[f"/hub/{locale}"]
        assert world.centre_slug in bodies[f"/hub/{locale}"]
    assert world.owner_slug in bodies["/hub/sitemap.xml"]
    assert world.centre_slug in bodies["/hub/sitemap.xml"]
    assert _everywhere(bodies, world.draft_name) == []
    assert _everywhere(bodies, world.draft_slug) == []
    for locale in LOCALES:
        response = api_client.get(f"/hub/{locale}/t/{world.draft_slug}")
        assert response.status_code == 404
        assert world.draft_name not in response.text


def test_unconsented_member_name_and_phone_never_public(
    owner_session: Session, api_client: TestClient
) -> None:
    """Only the consent rule keeps an assigned member off a published batch.

    :param owner_session: A session able to arrange the seeded world
    :param api_client: A client over the real application
    :return: None
    """
    world, bodies = _walk(owner_session, api_client)

    assert _everywhere(bodies, world.member_name) == []
    assert _everywhere(bodies, world.member_phone) == []
    for locale in LOCALES:
        page = bodies[f"/hub/{locale}/t/{world.centre_slug}/{world.centre_batch_slug}"]
        assert world.consented_name in page


def test_account_phone_never_public_but_public_contact_is(
    owner_session: Session, api_client: TestClient
) -> None:
    """The published contact number shows; the account phone never does.

    :param owner_session: A session able to arrange the seeded world
    :param api_client: A client over the real application
    :return: None
    """
    world, bodies = _walk(owner_session, api_client)

    assert world.public_phone != world.account_phone
    for locale in LOCALES:
        assert world.public_phone in bodies[f"/hub/{locale}/t/{world.owner_slug}"]
    assert _everywhere(bodies, world.account_phone) == []


def test_batch_name_never_public(
    owner_session: Session, api_client: TestClient
) -> None:
    """``batch.name`` is private; the public title is what pages show.

    :param owner_session: A session able to arrange the seeded world
    :param api_client: A client over the real application
    :return: None
    """
    world, bodies = _walk(owner_session, api_client)

    assert _everywhere(bodies, world.batch_name) == []
    for locale in LOCALES:
        page = bodies[f"/hub/{locale}/t/{world.owner_slug}/{world.batch_slug}"]
        assert "Canary public title" in page


def test_preview_route_carries_no_other_owner_canary(
    owner_session: Session, api_client: TestClient
) -> None:
    """The owner's preview shows their page and none of another owner's.

    The centre's and the draft's canaries are other owners' private values.

    :param owner_session: A session able to arrange the seeded world
    :param api_client: A client over the real application
    :return: None
    """
    world = seed_canaries(owner_session)
    owner = owner_session.get(Owner, world.owner_id)
    assert owner is not None
    account_id = owner.account_id
    assert account_id is not None
    headers = bearer(owner_session, account_id)
    store = FakeMediaStore()
    api_client.app.dependency_overrides[media_store] = lambda: store  # type: ignore[attr-defined]
    for locale in LOCALES:
        response = api_client.get(
            f"/v1/hub/listing/preview?locale={locale}", headers=headers
        )
        assert response.status_code == 200, response.text
        assert "Canary Tutor" in response.text
        assert "Canary public title" in response.text
        body = response.text.lower()
        assert [s for s in world.other_owner_strings if s.lower() in body] == []
        # The owner's OWN student, guardian and private batch data too:
        # nothing a student or guardian writes reaches the teacher's page.
        # The owner's own pending photo is the one canary the preview
        # shows, marked; the held and rejected photos it does not.
        leaks = canary_leaks({f"preview/{locale}": response.text}, world)
        assert [
            canary for _, canary in leaks if canary not in world.pending_photo_strings
        ] == []
        assert {canary for _, canary in leaks} <= world.pending_photo_strings
        assert leaks != []
        assert t("photo_awaiting_review", locale) in response.text
