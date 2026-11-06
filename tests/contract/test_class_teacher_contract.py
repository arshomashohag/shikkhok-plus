"""What a centre teacher's lens reaches, asserted over the real app [C4].

Two properties no runtime test can see in full, because each violation
*works*:

* **The routes are an allowlist.** A ``ClassTeacherLens`` reaches exactly
  the routes in ``CLASS_TEACHER_ROUTES``; a route accepting it that is not
  listed fails here, so opening a route to centre teachers is a reviewed
  diff, never an accident.
* **The responses carry names and marks only** [D2]. No schema a centre
  teacher reads may hold a phone, an email, a guardian, a fee, an amount
  or an address, in any nesting, so a later field added to a shared
  response type cannot reach them unnoticed.
"""

from __future__ import annotations

import typing

import pytest
from fastapi import FastAPI

from app.contract.routes import CLASS_TEACHER_ROUTES, _api_routes, class_teacher_routes

#: Name fragments no class-teacher response field may contain.
FORBIDDEN_TOKENS = (
    "phone",
    "email",
    "guardian",
    "fee",
    "amount",
    "address",
    "house",
    "road",
    "city",
    "postcode",
    "self_name",
)


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


def test_exactly_the_listed_routes_accept_a_class_teacher_lens(app: FastAPI) -> None:
    """The registered set equals the allowlist, in both directions.

    :param app: The application
    :return: None
    """
    assert class_teacher_routes(app) == CLASS_TEACHER_ROUTES


def _fields(schema: dict, definitions: dict, seen: frozenset[str]) -> set[str]:
    """Collect every property name reachable from a schema.

    :param schema: The schema node
    :param definitions: The document's components
    :param seen: Components already walked, the cycle guard
    :return: The property names
    """
    ref = schema.get("$ref")
    if isinstance(ref, str):
        name = ref.rsplit("/", 1)[-1]
        if name in seen or name not in definitions:
            return set()
        return _fields(definitions[name], definitions, seen | {name})
    found: set[str] = set()
    for field, child in (schema.get("properties") or {}).items():
        found.add(field)
        if isinstance(child, dict):
            found |= _fields(child, definitions, seen)
    for key in ("items", "additionalProperties"):
        if isinstance(schema.get(key), dict):
            found |= _fields(schema[key], definitions, seen)
    for key in ("allOf", "anyOf", "oneOf"):
        for branch in schema.get(key) or []:
            if isinstance(branch, dict):
                found |= _fields(branch, definitions, seen)
    return found


def test_no_class_teacher_response_carries_contact_guardian_or_money(
    app: FastAPI,
) -> None:
    """Names and marks only, over every route the lens reaches and its listing.

    :param app: The application
    :return: None
    """
    document = app.openapi()
    definitions = document["components"]["schemas"]
    reached = {path for _, path in CLASS_TEACHER_ROUTES} | {
        "/v1/me/classes",
        "/v1/me/exams",
    }
    offenders: list[tuple[str, str]] = []
    for route in _api_routes(app):
        if route.path not in reached or route.response_model is None:
            continue
        model = route.response_model
        if typing.get_origin(model) is list:
            model = typing.get_args(model)[0]
        name = getattr(model, "__name__", None)
        component = definitions.get(name or "")
        assert component is not None, route.path
        for field in _fields(component, definitions, frozenset({name or ""})):
            if any(token in field for token in FORBIDDEN_TOKENS):
                offenders.append((route.path, field))
    assert offenders == []


def test_the_gate_would_fire_on_a_forbidden_field() -> None:
    """Guard the check itself: a planted phone field is found.

    :return: None
    """
    schema = {"properties": {"seats": {"items": {"$ref": "#/components/schemas/S"}}}}
    definitions = {"S": {"properties": {"guardian_phone": {"type": "string"}}}}
    fields = _fields(schema, definitions, frozenset())
    assert any("phone" in field for field in fields)
