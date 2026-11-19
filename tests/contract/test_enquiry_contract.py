"""What the join-request routes reach and document, over the real app [H5].

Three structural properties no behavioural test sees in full, because each
violation *works* [F3]:

* **The switch runs first** on every gated route and appears on no other.
  An off switch must answer ``HUB_ENQUIRIES_OFF`` and never
  ``ENQUIRY_TARGET_NOT_FOUND``, ``ENQUIRY_NOT_FOUND`` or
  ``NO_TEACHER_LENS``, which only the dependency order guarantees; and the
  switch never gates the guardian's own list or their withdrawal.
* **Every gated 404 opens with one sentence**,
  :data:`~app.hub.enquiries.switch.ENQUIRIES_OFF_DESCRIPTION`, so a route
  that also answers a second 404 code documents both on the one status.
* **The wire mirrors the services one to one**, so a field added to a
  service result is either published deliberately or fails here.
"""

from __future__ import annotations

import dataclasses
import typing
from typing import Final

import pytest
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.authz.lenses import TeacherLens
from app.contract.privacy import ENQUIRY_ROUTES, lens_types_of
from app.contract.routes import LENS_EXEMPT_AUTHENTICATED, PUBLIC_ROUTES, _api_routes
from app.db.models import HUB_ENQUIRY_OUTCOME_VALUES
from app.hub.enquiries import owner, sending
from app.hub.enquiries.switch import ENQUIRIES_OFF_DESCRIPTION, require_enquiries_on
from app.schemas.enquiries import (
    EnquiryClose,
    EnquiryTargetResponse,
    MyEnquiryWire,
    OwnerEnquiryWire,
)

#: The guardian's target and send routes.
TARGET: Final = "/v1/hub/owners/{owner_slug}/enquiry-target"
SEND: Final = "/v1/hub/owners/{owner_slug}/enquiries"

#: The guardian's own requests.
MINE: Final = "/v1/me/hub/enquiries"
WITHDRAW: Final = "/v1/me/hub/enquiries/{enquiry_id}"

#: The owner's three.
OWNER_LIST: Final = "/v1/hub/enquiries"
OWNER_ONE: Final = "/v1/hub/enquiries/{enquiry_id}"
OWNER_CLOSE: Final = "/v1/hub/enquiries/{enquiry_id}/close"

#: The routes the switch gates (global constraints, the off table).
GATED: Final = frozenset(
    {
        ("GET", TARGET),
        ("POST", SEND),
        ("GET", OWNER_LIST),
        ("GET", OWNER_ONE),
        ("POST", OWNER_CLOSE),
    }
)

#: The routes it never gates: the guardian's own list and withdrawal.
UNGATED: Final = frozenset({("GET", MINE), ("DELETE", WITHDRAW)})

#: The four lens-exempt routes; each acts as the authenticated account.
EXEMPT: Final = frozenset(
    {("GET", TARGET), ("POST", SEND), ("GET", MINE), ("DELETE", WITHDRAW)}
)

#: The owner's three, each resolving the owner's teacher lens.
TEACHER: Final = frozenset(
    {("GET", OWNER_LIST), ("GET", OWNER_ONE), ("POST", OWNER_CLOSE)}
)

#: Each route's documented error statuses, from the codes it can answer
#: (global constraints, the error-code table).
DOCUMENTED: Final[dict[tuple[str, str], frozenset[str]]] = {
    ("GET", TARGET): frozenset({"401", "404"}),
    ("POST", SEND): frozenset({"400", "401", "404", "409"}),
    ("GET", MINE): frozenset({"401"}),
    ("DELETE", WITHDRAW): frozenset({"401"}),
    ("GET", OWNER_LIST): frozenset({"401", "403", "404"}),
    ("GET", OWNER_ONE): frozenset({"401", "403", "404"}),
    ("POST", OWNER_CLOSE): frozenset({"400", "401", "403", "404", "409"}),
}

#: The codes each documented status must name in its description.
NAMED_CODES: Final[dict[tuple[str, str], dict[str, tuple[str, ...]]]] = {
    ("GET", TARGET): {"404": ("HUB_ENQUIRIES_OFF", "ENQUIRY_TARGET_NOT_FOUND")},
    ("POST", SEND): {
        "400": ("ENQUIRY_CONTAINS_CONTACT",),
        "404": ("HUB_ENQUIRIES_OFF", "ENQUIRY_TARGET_NOT_FOUND"),
        "409": ("ENQUIRY_ALREADY_OPEN", "HUB_ENQUIRY_CEILING"),
    },
    ("GET", OWNER_LIST): {"403": ("NO_TEACHER_LENS",), "404": ("HUB_ENQUIRIES_OFF",)},
    ("GET", OWNER_ONE): {
        "403": ("NO_TEACHER_LENS",),
        "404": ("HUB_ENQUIRIES_OFF", "ENQUIRY_NOT_FOUND"),
    },
    ("POST", OWNER_CLOSE): {
        "400": ("ENQUIRY_OUTCOME_INVALID",),
        "403": ("NO_TEACHER_LENS",),
        "404": ("HUB_ENQUIRIES_OFF", "ENQUIRY_NOT_FOUND"),
        "409": ("ENQUIRY_ALREADY_CLOSED",),
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


def test_the_seven_routes_are_the_gated_five_and_the_ungated_two() -> None:
    """The walked set, the gated set and the ungated set agree."""
    assert len(GATED) == 5
    assert GATED | UNGATED == ENQUIRY_ROUTES
    assert not GATED & UNGATED


def test_lens_exempt_set_exact() -> None:
    """Exactly four join-request routes are lens-exempt, and none is public."""
    exempt = {entry for entry in LENS_EXEMPT_AUTHENTICATED if "enquir" in entry[1]}
    assert exempt == EXEMPT
    assert not EXEMPT & PUBLIC_ROUTES
    assert not any("enquir" in path for _, path in PUBLIC_ROUTES)


def test_teacher_enquiry_routes_resolve_teacher_lens(app: FastAPI) -> None:
    """The owner's three each resolve a TeacherLens, and nothing wider."""
    for method, path in TEACHER:
        lenses = lens_types_of(_route(app, method, path))
        assert lenses == {TeacherLens}, (method, path, lenses)
        assert (method, path) not in LENS_EXEMPT_AUTHENTICATED
    for method, path in EXEMPT:
        assert lens_types_of(_route(app, method, path)) == set(), (method, path)


def test_gated_routes_list_the_switch_first(app: FastAPI) -> None:
    """The switch is each gated route's first dependency [Ordering]."""
    for method, path in GATED:
        dependant = _route(app, method, path).dependant
        assert dependant.dependencies[0].call is require_enquiries_on, (method, path)


def test_the_switch_gates_neither_the_guardians_list_nor_withdrawal(
    app: FastAPI,
) -> None:
    """The guardian can always see and withdraw what they sent."""
    for method, path in UNGATED:
        calls = _calls(_route(app, method, path).dependant)
        assert require_enquiries_on not in calls, (method, path)


def test_off_response_documented_in_openapi(app: FastAPI) -> None:
    """Each gated 404 is the error envelope and opens with the one sentence."""
    paths = app.openapi()["paths"]
    for method, path in GATED:
        documented = paths[path][method.lower()]["responses"]["404"]
        assert documented["description"].startswith(ENQUIRIES_OFF_DESCRIPTION), (
            method,
            path,
            documented["description"],
        )
        schema = documented["content"]["application/json"]["schema"]
        assert schema == {"$ref": "#/components/schemas/ErrorEnvelope"}


def test_each_route_documents_the_statuses_it_can_answer(app: FastAPI) -> None:
    """Every status a route can answer is documented, naming its codes."""
    paths = app.openapi()["paths"]
    assert set(DOCUMENTED) == ENQUIRY_ROUTES
    for (method, path), statuses in DOCUMENTED.items():
        responses = paths[path][method.lower()]["responses"]
        assert statuses <= set(responses), (method, path, sorted(responses))
        for status, codes in NAMED_CODES.get((method, path), {}).items():
            description = responses[status]["description"]
            for code in codes:
                assert code in description, (method, path, status, code)


def test_send_answers_201_and_withdraw_204(app: FastAPI) -> None:
    """A send creates; a withdrawal has no body."""
    assert _route(app, "POST", SEND).status_code == 201
    assert _route(app, "DELETE", WITHDRAW).status_code == 204


def _names(cls: type) -> set[str]:
    """Name a dataclass's fields.

    :param cls: The dataclass
    :return: Its field names
    """
    return {field.name for field in dataclasses.fields(cls)}


def test_the_wire_mirrors_the_services_one_to_one() -> None:
    """Each response model carries exactly its service result's fields."""
    assert set(EnquiryTargetResponse.model_fields) == _names(sending.EnquiryTarget)
    assert set(MyEnquiryWire.model_fields) == _names(sending.MyEnquiry)
    assert set(OwnerEnquiryWire.model_fields) == _names(owner.OwnerEnquiry)


def test_owner_public_name_is_nullable_on_the_guardians_list(app: FastAPI) -> None:
    """A request whose listing is gone still lists, with no owner name."""
    schema = app.openapi()["components"]["schemas"]["MyEnquiryWire"]
    field = schema["properties"]["owner_public_name"]
    assert {"type": "null"} in field["anyOf"], field
    assert "owner_public_name" in schema["required"]


def test_outcome_spellings_agree() -> None:
    """The service, the owner's order, the model and the wire name one set."""
    spelled = typing.get_args(sending.EnquiryOutcome)
    assert spelled == owner.OUTCOMES == HUB_ENQUIRY_OUTCOME_VALUES
    assert typing.get_args(EnquiryClose.model_fields["outcome"].annotation) == spelled
