"""The canary probe: a private value must not appear on any public page.

The real probe walks ``PUBLIC_CACHEABLE_ROUTES`` over a seeded world of a
solo tutor, a draft and a centre. The fixture test below proves the same
collection and assertion functions fire on a planted leak, so a green probe
is not a green probe over nothing.

**Every probe here runs with reviews switched on** [F12]: the seeded world
holds published reviews on the solo batch, so the walk renders a review
section, and below-threshold and unpublished reviews beside them, so the
walk proves the threshold and the status keep their canaries off.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.contract.routes import PUBLIC_CACHEABLE_ROUTES
from app.hub.public.messages import t
from tests.privacy.canary import (
    LOCALES,
    CanaryWorld,
    _resolve,
    canary_leaks,
    rendered_public_bodies,
    seed_canaries,
    walk_cacheable_routes,
)

pytestmark = pytest.mark.usefixtures("reviews_on")


def test_no_canary_on_any_cacheable_public_page(
    owner_session: Session, api_client: TestClient
) -> None:
    """No seeded private string appears in any cacheable public body.

    :param owner_session: A session able to arrange the seeded world
    :param api_client: A client over the real application
    :return: None
    """
    world = seed_canaries(owner_session)

    bodies = walk_cacheable_routes(api_client, world, PUBLIC_CACHEABLE_ROUTES)

    # Search twice (locales); owner and batch pages 2 locales x 2 pairs
    # each (solo and centre); the sitemap once: 2 + 4 + 4 + 1.
    assert len(PUBLIC_CACHEABLE_ROUTES) == 4
    assert len(bodies) == 11
    assert f"/hub/en/t/{world.owner_slug}/{world.batch_slug}" in bodies
    assert f"/hub/bn/t/{world.centre_slug}/{world.centre_batch_slug}" in bodies
    assert canary_leaks(bodies, world) == []


def test_canary_alt_of_unapproved_photos_never_public(
    owner_session: Session, api_client: TestClient
) -> None:
    """A pending, held or rejected photo is on no public page or the sitemap.

    Each carries canary alt texts and its id is a canary; the approved
    photo beside them is on its owner page, in that page's language, so a
    walk that rendered no photos at all could not pass.

    :param owner_session: A session able to arrange the seeded world
    :param api_client: A client over the real application
    :return: None
    """
    world = seed_canaries(owner_session)

    bodies = walk_cacheable_routes(api_client, world, PUBLIC_CACHEABLE_ROUTES)

    # Three photos, each two alt texts and its id in two spellings.
    assert len(world.unapproved_photo_strings) == 12
    assert "/hub/sitemap.xml" in bodies
    leaked = [
        (path, canary)
        for path, canary in canary_leaks(bodies, world)
        if canary in world.unapproved_photo_strings
    ]
    assert leaked == []
    for locale, alt in (("en", world.approved_alt_en), ("bn", world.approved_alt_bn)):
        owner_page = bodies[f"/hub/{locale}/t/{world.owner_slug}"]
        assert f'alt="{alt}"' in owner_page


def test_canary_review_text_of_unpublished_or_below_threshold_never_public(
    owner_session: Session, api_client: TestClient
) -> None:
    """No unpublished or below-threshold review, nor any author, is public.

    The solo batch's pending, approved, held and rejected reviews sit beside
    three published ones, so only their status keeps them off; the centre
    batch's two reviews are published, so only the threshold keeps their
    bodies -- and their count -- off its page. The solo batch's average is
    4.3 over 3, which any of the four rated-1 reviews would have moved.

    :param owner_session: A session able to arrange the seeded world
    :param api_client: A client over the real application
    :return: None
    """
    world = seed_canaries(owner_session)

    bodies = walk_cacheable_routes(api_client, world, PUBLIC_CACHEABLE_ROUTES)

    # Each author: account phone, guardian phone, seat name, seat id in two
    # spellings (5). Four unpublished reviews (body, id twice, author: 8
    # each), the pending reply, two below-threshold reviews (8 each) and the
    # three published reviews' authors (5 each).
    assert len(world.review_strings) == 4 * 8 + 1 + 2 * 8 + 3 * 5
    assert len(world.below_threshold_strings) == 2 * 8
    assert len(bodies) == 11
    leaked = [
        (path, canary)
        for path, canary in canary_leaks(bodies, world)
        if canary in world.review_strings
    ]
    assert leaked == []
    for locale in LOCALES:
        centre = bodies[
            f"/hub/{locale}/t/{world.centre_slug}/{world.centre_batch_slug}"
        ]
        assert t("reviews_below_threshold", locale) in centre
        assert t("reviews_count", locale, count=2) not in centre
        assert t("rating_out_of", locale, average="1.0") not in centre
        solo = bodies[f"/hub/{locale}/t/{world.owner_slug}/{world.batch_slug}"]
        summary = t("rating_out_of", locale, average="4.3")
        assert f"{summary} · {t('reviews_count', locale, count=3)}" in solo


def test_canary_published_review_does_appear(
    owner_session: Session, api_client: TestClient
) -> None:
    """The published reviews and reply are on the solo batch page.

    The positive control for the probe above: the same walk renders the
    review section, so a page that showed no reviews at all could not pass
    for one that hides the right ones.

    :param owner_session: A session able to arrange the seeded world
    :param api_client: A client over the real application
    :return: None
    """
    world = seed_canaries(owner_session)

    bodies = walk_cacheable_routes(api_client, world, PUBLIC_CACHEABLE_ROUTES)

    assert len(world.published_review_bodies) == 3
    for locale in LOCALES:
        page = bodies[f"/hub/{locale}/t/{world.owner_slug}/{world.batch_slug}"]
        for body in world.published_review_bodies:
            assert body in page
        assert world.published_reply_body in page
        for review_id in world.published_review_ids:
            assert f"kind=review&amp;id={review_id}" in page
    assert canary_leaks(bodies, world) == []


def test_canary_probe_fires_on_planted_page(owner_session: Session) -> None:
    """A page echoing a seeded ``collection_number`` is caught.

    :param owner_session: A session able to arrange the seeded world
    :return: None
    """
    world = seed_canaries(owner_session)
    number = owner_session.execute(
        sa.text("SELECT collection_number FROM batch WHERE owner_id = :o"),
        {"o": world.owner_id},
    ).scalar_one()
    app = FastAPI()

    @app.get("/hub/en")
    def _hub() -> dict[str, str]:
        """Echo the seeded collection number, as a leaking page would.

        :return: A payload carrying the private value
        """
        return {"body": f"pay to {number}"}

    bodies = rendered_public_bodies(TestClient(app), ["/hub/en"])

    leaks = canary_leaks(bodies, world)
    assert leaks == [("/hub/en", number)]


def test_unknown_placeholder_is_refused_not_skipped(owner_session: Session) -> None:
    """A path with a placeholder the resolver cannot fill raises.

    :param owner_session: A session able to arrange the seeded world
    :return: None
    """
    world = seed_canaries(owner_session)

    with pytest.raises(NotImplementedError, match="review_id"):
        _resolve("/hub/{locale}/r/{review_id}", world)


def test_resolve_expands_both_locales(owner_session: Session) -> None:
    """``{locale}`` resolves to ``en`` and ``bn``.

    :param owner_session: A session able to arrange the seeded world
    :return: None
    """
    world: CanaryWorld = seed_canaries(owner_session)

    assert _resolve("/hub/{locale}", world) == ["/hub/en", "/hub/bn"]
    assert _resolve("/hub/{locale}/t/{owner_slug}/{batch_slug}", world) == [
        f"/hub/en/t/{world.owner_slug}/{world.batch_slug}",
        f"/hub/en/t/{world.centre_slug}/{world.centre_batch_slug}",
        f"/hub/bn/t/{world.owner_slug}/{world.batch_slug}",
        f"/hub/bn/t/{world.centre_slug}/{world.centre_batch_slug}",
    ]
    assert _resolve("/hub/{locale}/t/{owner_slug}", world) == [
        f"/hub/en/t/{world.owner_slug}",
        f"/hub/en/t/{world.centre_slug}",
        f"/hub/bn/t/{world.owner_slug}",
        f"/hub/bn/t/{world.centre_slug}",
    ]


def _planted(render: str) -> FastAPI:
    """Build an app whose ``/hub/en`` renders the given text.

    :param render: The page body
    :return: The application
    """
    app = FastAPI()

    @app.get("/hub/en")
    def _hub() -> dict[str, str]:
        """Render the planted text.

        :return: The payload
        """
        return {"body": render}

    return app


def _phone(world: CanaryWorld) -> str:
    """Pick the seeded ``+880`` number out of the world.

    :param world: The seeded world
    :return: A canonical phone canary
    """
    return next(s for s in sorted(world.strings) if s.startswith("+880"))


@pytest.mark.parametrize(
    "render",
    [
        lambda p, _e: "call " + "0" + p[4:],
        lambda p, _e: "call %2B" + p[1:],
        lambda p, _e: "call " + p[1:5] + " " + p[5:9] + "-" + p[9:],
        lambda _p, e: e.replace("-", "").upper(),
    ],
    ids=["national", "percent-encoded", "spaced", "uppercase-hex-id"],
)
def test_probe_catches_normalised_forms(
    owner_session: Session, render: Callable[[str, str], str]
) -> None:
    """A phone or id in a disguised form is still caught.

    :param owner_session: A session able to arrange the seeded world
    :param render: Builds the page text from a phone and an enrollment id
    :return: None
    """
    world = seed_canaries(owner_session)
    phone = _phone(world)
    enrollment_id = next(s for s in world.strings if len(s) == 36)

    bodies = rendered_public_bodies(
        TestClient(_planted(render(phone, enrollment_id))), ["/hub/en"]
    )

    assert canary_leaks(bodies, world) != []


def test_non_200_public_page_is_refused(owner_session: Session) -> None:
    """A 404 page cannot read as 'no leak'.

    :param owner_session: A session able to arrange the seeded world
    :return: None
    """
    seed_canaries(owner_session)

    with pytest.raises(AssertionError, match=r"/hub/xx.*404"):
        rendered_public_bodies(TestClient(_planted("x")), ["/hub/xx"])
