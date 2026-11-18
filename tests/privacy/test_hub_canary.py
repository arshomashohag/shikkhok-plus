"""The canary probe: a private value must not appear on any public page.

The real probe walks ``PUBLIC_CACHEABLE_ROUTES`` over a seeded world of a
solo tutor, a draft and a centre. The fixture test below proves the same
collection and assertion functions fire on a planted leak, so a green probe
is not a green probe over nothing.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.contract.routes import PUBLIC_CACHEABLE_ROUTES
from tests.privacy.canary import (
    CanaryWorld,
    _resolve,
    canary_leaks,
    rendered_public_bodies,
    seed_canaries,
    walk_cacheable_routes,
)


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
