"""The public-facing audience of the privacy gate.

Written before the implementation: a field leaked onto an anonymous page is
a disclosure with no authentication in front of it.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.contract.privacy import (
    FORBIDDEN_ACCOUNT_ID_FIELDS,
    OWNER_PRIVATE_FIELDS,
    PUBLIC_FORBIDDEN_FIELDS,
    STAFF_PRIVATE_FIELDS,
    public_field_leaks,
)
from app.hub.public.registry import PUBLIC_VIEW_MODELS, register_view
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
    assert public_field_leaks(create_app(), PUBLIC_VIEW_MODELS) == []


def test_fixture_view_model_leak_is_caught() -> None:
    """A nested forbidden field in a view model is reported."""
    leaks = public_field_leaks(create_app(), [_PlantedView])
    assert ("view:_PlantedView", "_Nested", "display_name") in leaks


def test_fixture_public_route_leak_is_caught() -> None:
    """A forbidden field on a PUBLIC_ROUTES response is reported."""
    leaks = public_field_leaks(build_public_leak_app(), [])
    assert [leak[2] for leak in leaks] == [PUBLIC_LEAK_FIELD]
    assert PUBLIC_LEAK_PATH in leaks[0][0]


def test_register_view_appends_and_returns_the_model() -> None:
    """The decorator returns its argument and adds it to the registry."""
    from app.hub.public import registry

    before = registry.PUBLIC_VIEW_MODELS
    try:
        assert register_view(_Nested) is _Nested
        assert registry.PUBLIC_VIEW_MODELS == (*before, _Nested)
    finally:
        registry.PUBLIC_VIEW_MODELS = before
