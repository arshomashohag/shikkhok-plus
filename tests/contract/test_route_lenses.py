"""The route-enumeration gate: every route resolves a lens.

Written before the implementation [NFR14.5-14.7]: a wrong answer here is an
authorization error that passes silently, which is the team's test-first
predicate.

The failure mode this guards against is not a *wrong* lens -- it is a
**forgotten** one. A dependency nobody added produces an endpoint that works
perfectly and authorizes nothing, and review cannot reliably catch an
absence.

The gate runs against the real application object at test collection time,
so an unlensed endpoint reddens CI on the commit that adds it rather than
when someone remembers to look.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI

from app.authz.lenses import GuardianLens, TeacherLens
from app.contract.routes import (
    LENS_EXEMPT_AUTHENTICATED,
    PUBLIC_ROUTES,
    unlensed_routes,
)
from app.main import app as real_app


def _teacher_lens() -> TeacherLens:
    """Stand in for U3's teacher-lens resolver.

    :return: A teacher lens
    """
    return TeacherLens(account_id=UUID(int=1), owner_id=UUID(int=2))


def _composed_dependency(
    lens: Annotated[TeacherLens, Depends(_teacher_lens)],
) -> TeacherLens:
    """Nest a lens inside another dependency.

    The harness must walk ``route.dependant`` recursively, because this is
    an ordinary shape rather than an exotic one.

    :param lens: The nested lens
    :return: The same lens
    """
    return lens


def _dual_lens() -> TeacherLens | GuardianLens:
    """Stand in for the dual-lens account of AC10.1.8.

    :return: Either lens
    """
    raise NotImplementedError


def test_public_routes_has_exactly_five_entries() -> None:
    """``PUBLIC_ROUTES`` is a fixed set of exactly five.

    The length assertion is the control: a sixth entry is a diff against a
    stated number rather than a line appended to a growing list.

    :return: None
    """
    assert len(PUBLIC_ROUTES) == 5


def test_public_routes_contains_the_contracted_entries() -> None:
    """The five are the ones the contract fixes.

    :return: None
    """
    assert ("POST", "/v1/auth/otp") in PUBLIC_ROUTES
    assert ("POST", "/v1/auth/verify") in PUBLIC_ROUTES
    assert ("GET", "/health") in PUBLIC_ROUTES
    assert ("GET", "/account-deletion") in PUBLIC_ROUTES
    assert ("POST", "/account-deletion") in PUBLIC_ROUTES


def test_lens_exempt_set_has_exactly_one_entry() -> None:
    """``LENS_EXEMPT_AUTHENTICATED`` holds the refresh route alone.

    Kept separate from ``PUBLIC_ROUTES`` for a concrete reason: with one
    combined list, whoever first hits a failing refresh route takes the
    cheapest green edit and adds it to the public set, after which nothing
    records that the route must stay authenticated.

    :return: None
    """
    assert len(LENS_EXEMPT_AUTHENTICATED) == 1
    assert ("POST", "/v1/auth/refresh") in LENS_EXEMPT_AUTHENTICATED


def test_the_two_allowlists_are_disjoint() -> None:
    """No route is both public and authenticated-but-lens-exempt.

    :return: None
    """
    assert not (PUBLIC_ROUTES & LENS_EXEMPT_AUTHENTICATED)


def test_unlensed_route_is_reported_by_path() -> None:
    """A route resolving no lens is reported, naming its path.

    :return: None
    """
    app = FastAPI()

    @app.get("/v1/batches")
    def _read_batches() -> dict[str, str]:
        return {}

    violations = unlensed_routes(app)

    assert [violation.path for violation in violations] == ["/v1/batches"]


def test_lensed_route_is_not_reported() -> None:
    """A route whose dependency returns a lens passes.

    :return: None
    """
    app = FastAPI()

    @app.get("/v1/batches")
    def _read_batches(
        lens: Annotated[TeacherLens, Depends(_teacher_lens)],
    ) -> dict[str, str]:
        return {}

    assert unlensed_routes(app) == []


def test_nested_lens_dependency_is_found() -> None:
    """A lens nested inside a composed dependency counts.

    :return: None
    """
    app = FastAPI()

    @app.get("/v1/batches")
    def _read_batches(
        lens: Annotated[TeacherLens, Depends(_composed_dependency)],
    ) -> dict[str, str]:
        return {}

    assert unlensed_routes(app) == []


def test_union_lens_dependency_is_found() -> None:
    """A union of lens types counts, since every member qualifies.

    :return: None
    """
    app = FastAPI()

    @app.get("/v1/enrollments")
    def _read_enrollments(
        lens: Annotated[TeacherLens | GuardianLens, Depends(_dual_lens)],
    ) -> dict[str, str]:
        return {}

    assert unlensed_routes(app) == []


def test_public_route_is_exempt() -> None:
    """An unlensed route on the public allowlist is not reported.

    :return: None
    """
    app = FastAPI()

    @app.get("/health")
    def _health() -> dict[str, str]:
        return {}

    assert unlensed_routes(app) == []


def test_refresh_route_is_exempt_without_being_public() -> None:
    """The refresh route passes via the authenticated-exempt set.

    :return: None
    """
    app = FastAPI()

    @app.post("/v1/auth/refresh")
    def _refresh() -> dict[str, str]:
        return {}

    assert unlensed_routes(app) == []
    assert ("POST", "/v1/auth/refresh") not in PUBLIC_ROUTES


def test_unresolvable_annotation_fails_naming_the_route() -> None:
    """An unresolvable dependency annotation fails the build loudly.

    It is never swallowed: a resolver error that returned a default would
    make this entire gate pass universally.

    :return: None
    """
    app = FastAPI()

    def _broken_resolver() -> None:
        raise NotImplementedError

    _broken_resolver.__annotations__["return"] = "NoSuchLensType"

    @app.get("/v1/broken")
    def _broken(
        lens: Annotated[object, Depends(_broken_resolver)],
    ) -> dict[str, str]:
        return {}

    with pytest.raises(Exception, match="/v1/broken"):
        unlensed_routes(app)


def test_the_real_app_has_no_unlensed_routes() -> None:
    """The real application object passes the gate.

    In B2 this iterates an empty route set, which is exactly why the
    committed violation fixtures exist: a passing test and a vacuous test
    are the same colour.

    :return: None
    """
    assert unlensed_routes(real_app) == []
