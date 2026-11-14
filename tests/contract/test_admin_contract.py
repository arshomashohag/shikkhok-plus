"""The platform administrator boundary, as a contract [TC-14, D-6].

Three properties, each a way the boundary could erode without any
endpoint failing:

* **the lens reaches exactly the listed routes**, in both directions --
  a new route taking ``PlatformAdminLens`` must be added to
  ``PLATFORM_ADMIN_ROUTES`` deliberately;
* **every ``/v1/admin`` route takes the lens** -- an administration
  route reachable by any signed-in account is the failure the lens
  exists to prevent, and the generic route gate would not catch it if
  the route resolved some other lens;
* **no administration response carries a contact detail, a profile
  field or an account id**, walked over the generated schema rather than
  per endpoint, so a field added to a nested model is checked too. A
  student's or guardian's name is excluded by construction (the only
  ``name`` fields belong to teachers and centres), and the integration
  suite asserts that behaviour against real rows.
"""

from __future__ import annotations

import typing

import pytest
from fastapi import FastAPI

from app.contract.privacy import FORBIDDEN_ACCOUNT_ID_FIELDS, OWNER_PRIVATE_FIELDS
from app.contract.routes import (
    LENS_EXEMPT_AUTHENTICATED,
    PLATFORM_ADMIN_ROUTES,
    PUBLIC_ROUTES,
    _api_routes,
    platform_admin_routes,
)

#: Name fragments no administration response field may contain.
FORBIDDEN_TOKENS = (
    "phone",
    "email",
    "address",
    "house",
    "road",
    "city",
    "postcode",
    "photo",
    "display_name",
    "child",
    "enrollment",
    "student_id",
    "amount",
    "fee",
)


def test_recorded_emails_are_forbidden_in_every_admin_response() -> None:
    """The teacher- and centre-written addresses never reach an administrator.

    [U2: NFR3.3] A token match rather than a list of names, so this pins
    that each of the three is caught by it.

    :return: None
    """
    for field in ("student_email", "guardian_email", "invited_email"):
        assert any(token in field for token in FORBIDDEN_TOKENS), field


#: Fields that name a person. Allowed only on the two models whose name
#: is a teacher's or a centre's.
NAME_FIELDS = frozenset({"name", "centre"})
NAMED_MODELS = frozenset({"AdminWorkspace", "AdminRequester"})


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


def test_exactly_the_listed_routes_take_the_admin_lens(app: FastAPI) -> None:
    """The registered set equals the allowlist, in both directions.

    :param app: The application
    :return: None
    """
    assert platform_admin_routes(app) == PLATFORM_ADMIN_ROUTES


#: The admin sign-in routes [0028]: no bearer token yet, so not lensed.
ADMIN_SIGN_IN_ROUTES = frozenset(
    {
        ("POST", "/v1/admin/auth/otp"),
        ("POST", "/v1/admin/auth/verify"),
        ("POST", "/v1/admin/auth/mfa"),
    }
)


def test_every_admin_path_takes_the_admin_lens(app: FastAPI) -> None:
    """Under ``/v1/admin``, only the three sign-in steps lack the lens.

    :param app: The application
    :return: None
    """
    admin_paths = {
        (method, route.path)
        for route in _api_routes(app)
        if route.path.startswith("/v1/admin")
        for method in route.methods or set()
    }
    assert admin_paths == PLATFORM_ADMIN_ROUTES | ADMIN_SIGN_IN_ROUTES


def test_no_admin_route_is_public_or_lens_exempt() -> None:
    """The administration routes appear in neither exemption list.

    :return: None
    """
    assert not (PLATFORM_ADMIN_ROUTES & (PUBLIC_ROUTES | LENS_EXEMPT_AUTHENTICATED))


def test_every_admin_route_sits_behind_the_admin_gate(app: FastAPI) -> None:
    """Sign-in and lensed routes alike depend on ``admin_gate``.

    The gate is the lock that makes the admin hostname the only way in;
    a route under ``/v1/admin`` without it would answer on the public
    API host's origin to anyone who reached it.

    :param app: The application
    :return: None
    """
    from app.api.deps import admin_gate

    def gated(dependant: object) -> bool:
        call = getattr(dependant, "call", None)
        if call is admin_gate:
            return True
        if call is platform_admin_lens:
            return True
        return any(gated(sub) for sub in getattr(dependant, "dependencies", []))

    from app.api.deps import platform_admin_lens

    ungated = sorted(
        route.path
        for route in _api_routes(app)
        if route.path.startswith("/v1/admin") and not gated(route.dependant)
    )
    assert ungated == []


def _fields(
    schema: dict, definitions: dict, seen: frozenset[str], owner: str
) -> set[tuple[str, str]]:
    """Collect every ``(model, property)`` reachable from a schema.

    :param schema: The schema node
    :param definitions: The document's components
    :param seen: Components already walked, the cycle guard
    :param owner: The component the properties belong to
    :return: The pairs
    """
    ref = schema.get("$ref")
    if isinstance(ref, str):
        name = ref.rsplit("/", 1)[-1]
        if name in seen or name not in definitions:
            return set()
        return _fields(definitions[name], definitions, seen | {name}, name)
    found: set[tuple[str, str]] = set()
    for field, child in (schema.get("properties") or {}).items():
        found.add((owner, field))
        if isinstance(child, dict):
            found |= _fields(child, definitions, seen, owner)
    for key in ("items", "additionalProperties"):
        if isinstance(schema.get(key), dict):
            found |= _fields(schema[key], definitions, seen, owner)
    for key in ("allOf", "anyOf", "oneOf"):
        for branch in schema.get(key) or []:
            if isinstance(branch, dict):
                found |= _fields(branch, definitions, seen, owner)
    return found


def _offenders(pairs: set[tuple[str, str]]) -> list[tuple[str, str]]:
    """Name every pair outside the administrator boundary.

    :param pairs: ``(model, field)`` pairs
    :return: The offending pairs, sorted
    """
    bad: list[tuple[str, str]] = []
    for model, field in pairs:
        if field in OWNER_PRIVATE_FIELDS or field in FORBIDDEN_ACCOUNT_ID_FIELDS:
            bad.append((model, field))
        elif any(token in field for token in FORBIDDEN_TOKENS):
            bad.append((model, field))
        elif field in NAME_FIELDS and model not in NAMED_MODELS:
            bad.append((model, field))
    return sorted(bad)


def test_no_admin_response_crosses_the_boundary(app: FastAPI) -> None:
    """Counts, teacher and centre names, apps and support text only.

    :param app: The application
    :return: None
    """
    document = app.openapi()
    definitions = document["components"]["schemas"]
    walked = 0
    pairs: set[tuple[str, str]] = set()
    lensed = {path for _, path in PLATFORM_ADMIN_ROUTES}
    for route in _api_routes(app):
        if route.path not in lensed:
            continue
        model = route.response_model
        assert model is not None, route.path
        if typing.get_origin(model) is list:
            model = typing.get_args(model)[0]
        name = getattr(model, "__name__", "")
        component = definitions.get(name)
        assert component is not None, route.path
        pairs |= _fields(component, definitions, frozenset({name}), name)
        walked += 1
    assert walked == len(PLATFORM_ADMIN_ROUTES)
    assert _offenders(pairs) == []


def test_the_gate_would_fire_on_a_planted_field() -> None:
    """Guard the check itself: a phone, a profile field and a stray name.

    :return: None
    """
    schema = {
        "properties": {
            "requesters": {"items": {"$ref": "#/components/schemas/Row"}},
        }
    }
    definitions = {
        "Row": {
            "properties": {
                "guardian_phone": {"type": "string"},
                "self_name": {"type": "string"},
                "name": {"type": "string"},
            }
        }
    }
    found = _offenders(_fields(schema, definitions, frozenset(), "Top"))
    assert found == [("Row", "guardian_phone"), ("Row", "name"), ("Row", "self_name")]
