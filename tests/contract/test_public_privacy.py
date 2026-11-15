"""The public-facing audience of the privacy gate.

Written before the implementation: a field leaked onto an anonymous page is
a disclosure with no authentication in front of it.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from app.contract.privacy import (
    FORBIDDEN_ACCOUNT_ID_FIELDS,
    OWNER_PRIVATE_FIELDS,
    PUBLIC_FORBIDDEN_FIELDS,
    STAFF_PRIVATE_FIELDS,
    public_field_leaks,
)
from app.hub.public import registry
from app.hub.public.registry import register_view, registered_views
from app.main import create_app
from tests.contract.fixtures.public_leak_app import (
    PUBLIC_LEAK_FIELD,
    PUBLIC_LEAK_PATH,
    build_public_leak_app,
)


class _Nested(BaseModel):
    """A nested model holding a forbidden field.

    :ivar display_name: Forbidden on a public surface
    """

    display_name: str


class _PlantedView(BaseModel):
    """A view model whose nested model leaks.

    :ivar nested: The leaking child
    """

    nested: _Nested


def test_public_forbidden_set_is_the_spec_union() -> None:
    """The set is exactly the three existing sets plus the public extras."""
    assert PUBLIC_FORBIDDEN_FIELDS == (
        OWNER_PRIVATE_FIELDS
        | FORBIDDEN_ACCOUNT_ID_FIELDS
        | STAFF_PRIVATE_FIELDS
        | {
            "phone",
            "student_phone",
            "guardian_phone",
            "invited_phone",
            "collection_number",
            "display_name",
            "enrollment_id",
            "student_id",
            "self_name",
        }
    )


def test_real_app_has_no_public_leaks() -> None:
    """The real application serves nothing forbidden publicly."""
    assert public_field_leaks(create_app(), registered_views()) == []


def test_fixture_view_model_leak_is_caught() -> None:
    """A nested forbidden field in a view model is reported."""
    leaks = public_field_leaks(create_app(), [_PlantedView])
    assert ("view:_PlantedView", "_Nested", "display_name") in leaks


def test_fixture_public_route_leak_is_caught() -> None:
    """A forbidden field on a PUBLIC_ROUTES response is reported."""
    leaks = public_field_leaks(build_public_leak_app(), [])
    assert [leak[2] for leak in leaks] == [PUBLIC_LEAK_FIELD]
    assert PUBLIC_LEAK_PATH in leaks[0][0]


def test_register_view_appends_in_place_and_rejects_duplicates() -> None:
    """The decorator returns its argument, appends, and refuses a repeat."""
    before = list(registry.PUBLIC_VIEW_MODELS)
    try:
        assert register_view(_Nested) is _Nested
        assert registered_views() == (*before, _Nested)
        with pytest.raises(ValueError, match="already registered"):
            register_view(_Nested)
    finally:
        registry.PUBLIC_VIEW_MODELS[:] = before


def test_public_route_returning_a_list_is_caught() -> None:
    """A ``list[Leaky]`` response, which has no class name, is still walked."""
    app = FastAPI()

    class _Leaky(BaseModel):
        """A model carrying a forbidden field.

        :ivar collection_number: Forbidden publicly
        """

        collection_number: str

    @app.get("/health", response_model=list[_Leaky])
    def _health() -> list[dict[str, str]]:
        """Return nothing.

        :return: An empty list
        """
        return []

    assert [leak[2] for leak in public_field_leaks(app, [])] == ["collection_number"]


def test_unresolvable_public_response_raises() -> None:
    """A public route whose schema is not in the document fails closed."""
    app = FastAPI()

    @app.get("/health", response_model=dict[str, str])
    def _health() -> dict[str, str]:
        """Return nothing.

        :return: An empty mapping
        """
        return {}

    app.openapi = lambda: {"paths": {}, "components": {"schemas": {}}}  # type: ignore[method-assign]
    with pytest.raises(LookupError, match="no resolvable"):
        public_field_leaks(app, [])
