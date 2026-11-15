"""The no-auth gate for cacheable public routes.

A response a shared cache may serve to anyone must never depend on who is
asking. A cacheable route that resolves an authenticated dependency would
leak one viewer's response to the next, so the gate fails on the commit
that wires one in rather than when a cache first misbehaves.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, FastAPI

from app.api.deps import admin_gate, authenticated_account, token_subject
from app.contract.routes import (
    PUBLIC_CACHEABLE_ROUTES,
    PUBLIC_ROUTES,
    authenticated_cacheable_routes,
)
from app.main import create_app


def test_cacheable_set_is_subset_of_public() -> None:
    """Every cacheable route is a public route.

    :return: None
    """
    assert PUBLIC_CACHEABLE_ROUTES <= PUBLIC_ROUTES


def test_cacheable_routes_are_get_only() -> None:
    """A cacheable route is a read; only GET qualifies.

    :return: None
    """
    assert all(method == "GET" for method, _ in PUBLIC_CACHEABLE_ROUTES)


def test_real_app_has_no_authenticated_cacheable_route() -> None:
    """The real application has no cacheable route behind authentication.

    :return: None
    """
    assert authenticated_cacheable_routes(create_app()) == []


def _fixture_app(dependency: Callable[..., object]) -> FastAPI:
    """Build an app whose ``GET /health`` depends on the given callable.

    :param dependency: The dependency to attach
    :return: The fixture application
    """
    fixture = FastAPI()

    @fixture.get("/health", dependencies=[Depends(dependency)])
    def health() -> dict[str, str]:
        """Answer the probe.

        :return: A constant body
        """
        return {"ok": "yes"}

    return fixture


def test_fixture_cacheable_route_with_auth_is_caught() -> None:
    """A cacheable route routed through ``authenticated_account`` is flagged.

    :return: None
    """
    found = authenticated_cacheable_routes(
        _fixture_app(authenticated_account), cacheable=frozenset({("GET", "/health")})
    )
    assert found == [("GET", "/health")]


def test_fixture_token_subject_is_caught_and_uncacheable_is_ignored() -> None:
    """``token_subject`` is flagged too, and a non-cacheable route is not.

    :return: None
    """
    fixture = _fixture_app(token_subject)
    assert authenticated_cacheable_routes(
        fixture, cacheable=frozenset({("GET", "/health")})
    ) == [("GET", "/health")]
    assert authenticated_cacheable_routes(fixture, cacheable=frozenset()) == []


def test_fixture_admin_gate_is_caught() -> None:
    """A cacheable route behind ``admin_gate`` is flagged.

    :return: None
    """
    assert authenticated_cacheable_routes(
        _fixture_app(admin_gate), cacheable=frozenset({("GET", "/health")})
    ) == [("GET", "/health")]
