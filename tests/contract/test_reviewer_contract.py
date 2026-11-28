"""What the review routes reach and document, asserted over the real app [H4].

Three properties no behavioural test can see in full, because each
violation *works*:

* **The reviewer lens reaches exactly** ``REVIEWER_ROUTES``. A route taking
  a :class:`~app.reviews.lens.ReviewerLens` that is not listed fails here,
  and so does a listed one that stopped taking it.
* **The switch runs before the lens** on every gated route, and appears on
  no other. An off switch must answer ``HUB_REVIEWS_OFF`` and never
  ``NOT_AVAILABLE``, which only the dependency order guarantees; and the
  switch never gates a deletion or the author's own read.
* **Every route documents the errors it can answer**, so a client reading
  ``openapi.json`` learns that a 404 or 409 carries the error envelope.
"""

from __future__ import annotations

from typing import Annotated, Final

import pytest
from fastapi import Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.api.deps import reviewer_lens
from app.authz.lenses import TeacherLens
from app.contract.privacy import lens_types_of
from app.contract.routes import (
    LENS_EXEMPT_AUTHENTICATED,
    PUBLIC_ROUTES,
    REVIEWER_ROUTES,
    _api_routes,
    reviewer_routes,
)
from app.reviews.lens import ReviewerLens
from app.reviews.switch import REVIEWS_OFF_DESCRIPTION, require_reviews_on

#: The one reviewer path: an author's review of one batch.
MY_REVIEW: Final = "/v1/hub/batches/{batch_id}/my-review"

#: The teacher's three review routes.
TEACHER_REVIEW_ROUTES: Final = frozenset(
    {
        ("GET", "/v1/hub/reviews"),
        ("PUT", "/v1/hub/reviews/{review_id}/reply"),
        ("DELETE", "/v1/hub/reviews/{review_id}/reply"),
    }
)

#: The routes the switch gates (global constraints, the off table).
GATED: Final = frozenset(
    {
        ("PUT", MY_REVIEW),
        ("GET", "/v1/hub/reviews"),
        ("PUT", "/v1/hub/reviews/{review_id}/reply"),
    }
)

#: The administrator's review routes, gated in the handler after the admin
#: lens (the queue only for ``kind=review``).
ADMIN_GATED: Final = frozenset(
    {
        ("GET", "/v1/admin/hub/queue"),
        ("GET", "/v1/admin/hub/reviews/{review_id}"),
        ("POST", "/v1/admin/hub/reviews/{review_id}/decision"),
    }
)

#: The review routes the switch never gates: both deletions, the author's
#: own read, and the reviewable list, which narrows instead of refusing.
UNGATED: Final = frozenset(
    {
        ("GET", MY_REVIEW),
        ("DELETE", MY_REVIEW),
        ("DELETE", "/v1/hub/reviews/{review_id}/reply"),
        ("GET", "/v1/hub/reviewable"),
    }
)

#: Each review route's documented error statuses, from the codes it can
#: answer (global constraints, the error-code table):
#:
#: * 401 for every route: no credential, or an expired one;
#: * 403 ``NOT_AVAILABLE`` from the reviewer lens, ``NO_TEACHER_LENS``
#:   from the teacher lens;
#: * 404 ``HUB_REVIEWS_OFF`` on every gated route, ``REVIEW_NOT_FOUND`` on
#:   a reply;
#: * 400 ``REVIEW_CONTAINS_CONTACT``;
#: * 409 ``REVIEW_NOT_YET_ELIGIBLE``, ``REVIEW_EDIT_CLOSED`` and
#:   ``HUB_REVIEW_CEILING`` on a review; ``HUB_LISTING_SUSPENDED`` and
#:   ``HUB_WRITE_CEILING`` on a reply.
DOCUMENTED: Final[dict[tuple[str, str], frozenset[str]]] = {
    ("GET", "/v1/hub/reviewable"): frozenset({"401"}),
    ("GET", MY_REVIEW): frozenset({"401", "403"}),
    ("PUT", MY_REVIEW): frozenset({"400", "401", "403", "404", "409"}),
    ("DELETE", MY_REVIEW): frozenset({"401", "403"}),
    ("GET", "/v1/hub/reviews"): frozenset({"401", "403", "404"}),
    ("PUT", "/v1/hub/reviews/{review_id}/reply"): frozenset(
        {"400", "401", "403", "404", "409"}
    ),
    ("DELETE", "/v1/hub/reviews/{review_id}/reply"): frozenset({"401", "403"}),
}

#: The codes each documented status must name in its description.
NAMED_CODES: Final[dict[tuple[str, str], dict[str, tuple[str, ...]]]] = {
    ("GET", MY_REVIEW): {"403": ("NOT_AVAILABLE",)},
    ("PUT", MY_REVIEW): {
        "400": ("REVIEW_CONTAINS_CONTACT",),
        "403": ("NOT_AVAILABLE",),
        "404": ("HUB_REVIEWS_OFF",),
        "409": (
            "REVIEW_NOT_YET_ELIGIBLE",
            "REVIEW_EDIT_CLOSED",
            "HUB_REVIEW_CEILING",
        ),
    },
    ("DELETE", MY_REVIEW): {"403": ("NOT_AVAILABLE",)},
    ("GET", "/v1/hub/reviews"): {"404": ("HUB_REVIEWS_OFF",)},
    ("PUT", "/v1/hub/reviews/{review_id}/reply"): {
        "400": ("REVIEW_CONTAINS_CONTACT",),
        "404": ("HUB_REVIEWS_OFF", "REVIEW_NOT_FOUND"),
        "409": ("HUB_LISTING_SUSPENDED", "HUB_WRITE_CEILING"),
    },
}


@pytest.fixture(scope="module")
def app() -> FastAPI:
    """Build the real application once.

    :return: The application
    """
    mp = pytest.MonkeyPatch()
    mp.setenv("SHIKKHOKPLUS_OTP_HMAC_KEY", "x")
    mp.setenv("SHIKKHOKPLUS_JWT_KEYS", "k1:test-signing-key-padded-to-thirty-two")
    mp.setenv("SHIKKHOKPLUS_JWT_ACTIVE_KID", "k1")
    from app.main import create_app

    built = create_app()
    mp.undo()
    return built


def _route(app: FastAPI, method: str, path: str) -> APIRoute:
    """Find one registered route.

    :param app: The application
    :param method: The HTTP method
    :param path: The declared path
    :return: The route
    """
    for route in _api_routes(app):
        if route.path == path and method in (route.methods or set()):
            return route
    msg = f"{method} {path} is not registered"
    raise LookupError(msg)


def _calls(dependant: Dependant) -> list[object]:
    """List every dependency callable in a tree, depth first.

    :param dependant: The root
    :return: The callables
    """
    found: list[object] = []
    for sub in dependant.dependencies:
        if sub.call is not None:
            found.append(sub.call)
        found.extend(_calls(sub))
    return found


def test_reviewer_routes_resolve_reviewer_lens(app: FastAPI) -> None:
    """The registered set equals the allowlist, in both directions."""
    assert len(REVIEWER_ROUTES) == 3
    assert {
        ("GET", MY_REVIEW),
        ("PUT", MY_REVIEW),
        ("DELETE", MY_REVIEW),
    } == REVIEWER_ROUTES
    assert reviewer_routes(app) == REVIEWER_ROUTES


def test_reviewer_routes_fires_on_an_unlisted_route() -> None:
    """The enumeration is not vacuous: a planted reviewer route is found."""
    planted = FastAPI()

    @planted.get("/elsewhere/{batch_id}")
    def _elsewhere(lens: Annotated[ReviewerLens, Depends(reviewer_lens)]) -> None:
        """Take the reviewer lens on a route nobody listed.

        :param lens: The lens
        :return: None
        """
        del lens

    assert reviewer_routes(planted) == {("GET", "/elsewhere/{batch_id}")}


def test_lens_exempt_count_and_reviewable_entry() -> None:
    """The reviewable list is the one exemption H4 adds, and it is not public."""
    assert ("GET", "/v1/hub/reviewable") in LENS_EXEMPT_AUTHENTICATED
    # +4 join requests [H5], +4 interest [0049]
    assert len(LENS_EXEMPT_AUTHENTICATED) == 43
    assert ("GET", "/v1/hub/reviewable") not in PUBLIC_ROUTES
    assert len(PUBLIC_ROUTES) == 20


def test_teacher_review_routes_take_the_teacher_lens(app: FastAPI) -> None:
    """The three teacher routes each resolve a TeacherLens, and nothing wider."""
    for method, path in TEACHER_REVIEW_ROUTES:
        lenses = lens_types_of(_route(app, method, path))
        assert lenses == {TeacherLens}, (method, path, lenses)
        assert (method, path) not in LENS_EXEMPT_AUTHENTICATED


def test_gated_routes_list_the_switch_before_the_lens(app: FastAPI) -> None:
    """The switch is each gated route's first dependency [Ordering]."""
    for method, path in GATED:
        dependant = _route(app, method, path).dependant
        assert dependant.dependencies[0].call is require_reviews_on, (method, path)


def test_the_switch_gates_no_deletion_and_no_read_of_ones_own(app: FastAPI) -> None:
    """Neither deletion, the author's read nor the list depends on the switch."""
    for method, path in UNGATED:
        calls = _calls(_route(app, method, path).dependant)
        assert require_reviews_on not in calls, (method, path)


def test_off_response_documented_in_openapi(app: FastAPI) -> None:
    """Each gated route documents its 404 as the error envelope, named."""
    paths = app.openapi()["paths"]
    for method, path in GATED:
        documented = paths[path][method.lower()]["responses"]["404"]
        assert "HUB_REVIEWS_OFF" in documented["description"], (method, path)
        schema = documented["content"]["application/json"]["schema"]
        assert schema == {"$ref": "#/components/schemas/ErrorEnvelope"}


def test_every_gated_route_documents_the_switch_from_one_place(app: FastAPI) -> None:
    """Every gated 404, reviewer, teacher and admin, opens with one sentence.

    Each route merges :func:`~app.reviews.switch.reviews_off_responses`, so
    the description begins with the shared text rather than a hand-written
    copy of it that could drift.
    """
    paths = app.openapi()["paths"]
    for method, path in GATED | ADMIN_GATED:
        documented = paths[path][method.lower()]["responses"]["404"]
        assert documented["description"].startswith(REVIEWS_OFF_DESCRIPTION), (
            method,
            path,
            documented["description"],
        )


def test_each_review_route_documents_the_statuses_it_can_answer(
    app: FastAPI,
) -> None:
    """Every status a route can answer is documented, naming its codes."""
    paths = app.openapi()["paths"]
    for (method, path), statuses in DOCUMENTED.items():
        responses = paths[path][method.lower()]["responses"]
        assert statuses <= set(responses), (method, path, sorted(responses))
        for status, codes in NAMED_CODES.get((method, path), {}).items():
            description = responses[status]["description"]
            for code in codes:
                assert code in description, (method, path, status, code)
