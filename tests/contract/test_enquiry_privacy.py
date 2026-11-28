"""No join-request response carries who sent it, beyond what consent allows [H5].

A request is read by the people who run a listing and by the guardian who
sent it. Neither side's response may carry an account id, the guardian's
own name for themselves, or a bare ``phone``/``email``: the owner sees the
guardian's contact only as ``guardian_phone``/``guardian_email``, and only
when the guardian ticked "share" (the contact predicate, asserted by value
in ``tests/enquiries``). The responses of every join-request route are
walked from the generated document, so a field added to a shared model
later fails here rather than in a pilot.

The walk is shared with the review walk [F13], and both fail closed on a
listed route whose body names no fields, such as a handler annotated
``-> dict[str, str]`` [H4 residual New-2].
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any, Final

import pytest
from fastapi import FastAPI, Response, status
from pydantic import BaseModel

from app.contract.privacy import (
    ENQUIRY_FORBIDDEN_FIELDS,
    ENQUIRY_GUARDIAN_FORBIDDEN_FIELDS,
    ENQUIRY_GUARDIAN_ROUTES,
    ENQUIRY_ROUTES,
    FORBIDDEN_ACCOUNT_ID_FIELDS,
    OWNER_PRIVATE_FIELDS,
    enquiry_field_leaks,
    review_field_leaks,
)
from app.contract.routes import _api_routes
from app.main import create_app

#: One listed path of each walk, for planting.
_ENQUIRY_LISTED: Final = "/v1/hub/enquiries"
_REVIEW_LISTED: Final = "/v1/hub/reviews"

#: Each walk and a route it covers.
WALKS: Final = [
    pytest.param(enquiry_field_leaks, _ENQUIRY_LISTED, id="enquiry"),
    pytest.param(review_field_leaks, _REVIEW_LISTED, id="review"),
]


def test_enquiry_forbidden_set_is_profile_ids_and_identity() -> None:
    """The set is the profile set, account ids and the guardian's identity."""
    assert ENQUIRY_FORBIDDEN_FIELDS == (
        OWNER_PRIVATE_FIELDS
        | FORBIDDEN_ACCOUNT_ID_FIELDS
        | {
            "enquirer_account_id",
            "self_name",
            "phone",
            "email",
            "student_phone",
            "display_name",
        }
    )


def test_the_walk_covers_the_thirteen_routes() -> None:
    """The comment says thirteen; this is what holds it to thirteen.

    The seven join-request routes [H5] and the six interest routes [0049].
    """
    assert len(ENQUIRY_ROUTES) == 13
    assert {
        ("GET", "/v1/hub/owners/{owner_slug}/batches/{batch_id}/interest-target"),
        ("POST", "/v1/hub/owners/{owner_slug}/batches/{batch_id}/interest"),
        ("GET", "/v1/me/hub/interests"),
        ("DELETE", "/v1/me/hub/interests/{interest_id}"),
        ("GET", "/v1/hub/interests"),
        ("POST", "/v1/hub/interests/{interest_id}/close"),
        ("GET", "/v1/hub/owners/{owner_slug}/enquiry-target"),
        ("POST", "/v1/hub/owners/{owner_slug}/enquiries"),
        ("GET", "/v1/me/hub/enquiries"),
        ("DELETE", "/v1/me/hub/enquiries/{enquiry_id}"),
        ("GET", "/v1/hub/enquiries"),
        ("GET", "/v1/hub/enquiries/{enquiry_id}"),
        ("POST", "/v1/hub/enquiries/{enquiry_id}/close"),
    } == ENQUIRY_ROUTES


def test_every_walked_route_is_registered() -> None:
    """The walk is not vacuous: each listed route exists in the real app."""
    registered = {
        (method, route.path)
        for route in _api_routes(create_app())
        for method in route.methods or ()
    }
    assert ENQUIRY_ROUTES <= registered, sorted(ENQUIRY_ROUTES - registered)


def test_no_enquiry_response_carries_identity_fields() -> None:
    """The real application's join-request responses are clean."""
    assert enquiry_field_leaks(create_app()) == []


class _Guardian(BaseModel):
    """A nested model naming who sent a request.

    :ivar enquirer_account_id: Forbidden on any join-request response
    """

    enquirer_account_id: uuid.UUID


class _LeakyEnquiry(BaseModel):
    """A request whose nested sender leaks.

    :ivar student_name: A permitted field
    :ivar sender: The leaking child
    """

    student_name: str
    sender: _Guardian


class _PhonedEnquiry(BaseModel):
    """A list item carrying the guardian's bare phone.

    :ivar phone: Forbidden: the owner sees only ``guardian_phone``
    """

    phone: str


def test_fixture_leak_is_caught() -> None:
    """A nested ``enquirer_account_id`` and a list item's phone are reported."""
    planted = FastAPI()

    @planted.get("/v1/hub/enquiries/{enquiry_id}", response_model=_LeakyEnquiry)
    def _one(enquiry_id: uuid.UUID) -> dict[str, object]:
        """Return nothing.

        :param enquiry_id: The request
        :return: An empty payload
        """
        del enquiry_id
        return {}

    @planted.get("/v1/me/hub/enquiries", response_model=list[_PhonedEnquiry])
    def _mine() -> list[dict[str, str]]:
        """Return nothing.

        :return: An empty list
        """
        return []

    @planted.get("/elsewhere", response_model=_LeakyEnquiry)
    def _elsewhere() -> dict[str, object]:
        """Return nothing on a route the walk does not cover.

        :return: An empty payload
        """
        return {}

    assert sorted(enquiry_field_leaks(planted)) == [
        ("GET /v1/hub/enquiries/{enquiry_id}", "_Guardian", "enquirer_account_id"),
        ("GET /v1/me/hub/enquiries", "_PhonedEnquiry", "phone"),
    ]


def test_the_guardian_side_also_forbids_the_guardians_contact() -> None:
    """The contact predicate, as the gate holds it [review M3].

    The guardian's contact may appear only on the owner's side, and only
    as consent allows; on the four guardian-side routes it may never
    appear at all, so a guardian's own response cannot be the way a
    contact field reaches a client.
    """
    assert ENQUIRY_GUARDIAN_ROUTES == {
        ("GET", "/v1/hub/owners/{owner_slug}/batches/{batch_id}/interest-target"),
        ("POST", "/v1/hub/owners/{owner_slug}/batches/{batch_id}/interest"),
        ("GET", "/v1/me/hub/interests"),
        ("DELETE", "/v1/me/hub/interests/{interest_id}"),
        ("GET", "/v1/hub/owners/{owner_slug}/enquiry-target"),
        ("POST", "/v1/hub/owners/{owner_slug}/enquiries"),
        ("GET", "/v1/me/hub/enquiries"),
        ("DELETE", "/v1/me/hub/enquiries/{enquiry_id}"),
    }
    assert ENQUIRY_GUARDIAN_ROUTES < ENQUIRY_ROUTES
    assert ENQUIRY_GUARDIAN_FORBIDDEN_FIELDS == ENQUIRY_FORBIDDEN_FIELDS | {
        "guardian_phone",
        "guardian_email",
    }


class _Contacted(BaseModel):
    """A request carrying the guardian's shared contact.

    :ivar guardian_phone: The owner's side only
    :ivar guardian_email: The owner's side only
    """

    guardian_phone: str | None
    guardian_email: str | None


def test_a_guardian_side_contact_is_caught_and_an_owner_side_one_is_not() -> None:
    """The same model leaks on the guardian's list and is allowed on the owner's."""
    planted = FastAPI()

    @planted.get("/v1/me/hub/enquiries", response_model=list[_Contacted])
    def _mine() -> list[dict[str, str]]:
        """Return nothing.

        :return: An empty list
        """
        return []

    @planted.get("/v1/hub/enquiries", response_model=list[_Contacted])
    def _owners() -> list[dict[str, str]]:
        """Return nothing.

        :return: An empty list
        """
        return []

    assert sorted(enquiry_field_leaks(planted)) == [
        ("GET /v1/me/hub/enquiries", "_Contacted", "guardian_email"),
        ("GET /v1/me/hub/enquiries", "_Contacted", "guardian_phone"),
    ]


def test_a_listed_route_with_no_response_model_fails_closed() -> None:
    """A join-request route answering 200 with a bare body is an error."""
    planted = FastAPI()

    @planted.get(_ENQUIRY_LISTED, response_model=None)
    def _bare() -> dict[str, str]:
        """Return a body no model describes.

        :return: A payload carrying the sender
        """
        return {"enquirer_account_id": str(uuid.uuid4())}

    with pytest.raises(LookupError, match="GET /v1/hub/enquiries answers 200"):
        enquiry_field_leaks(planted)


#: Return annotations whose inferred response schema names no field: a
#: mapping of any keys, a list of them, and the untyped spellings, whose
#: schema is ``{}`` or a list of ``{}`` [H4 residual New-2, review I-1].
UNWALKABLE: Final = [
    pytest.param(dict[str, str], id="dict-str-str"),
    pytest.param(list[dict[str, str]], id="list-of-dict"),
    pytest.param(list, id="bare-list"),
    pytest.param(list[Any], id="list-any"),
    pytest.param(Any, id="any"),
]


@pytest.mark.parametrize("returns", UNWALKABLE)
@pytest.mark.parametrize(("walk", "path"), WALKS)
def test_a_listed_route_whose_body_names_no_field_fails_closed(
    walk: Callable[[FastAPI], list[tuple[str, str, str]]],
    path: str,
    returns: object,
) -> None:
    """A handler annotated ``-> dict[str, str]``, ``-> list`` or ``-> Any`` is an error.

    FastAPI infers the response model from the annotation, so the route has
    one, but its schema names no field: walking field names finds nothing
    to report, and passing it would pass whatever key the handler returned.
    """
    planted = FastAPI()

    def _untyped() -> object:
        """Return a body whose keys no schema names.

        :return: A payload carrying an account id
        """
        return [{"enquirer_account_id": str(uuid.uuid4())}]

    _untyped.__annotations__["return"] = returns
    planted.get(path)(_untyped)

    with pytest.raises(
        LookupError, match=f"GET {path} answers 200 with a body naming no field"
    ):
        walk(planted)


def test_a_listed_204_route_with_no_model_is_skipped() -> None:
    """A withdrawal answering 204 has no body, so it is the one allowed skip."""
    planted = FastAPI()

    @planted.delete(
        "/v1/me/hub/enquiries/{enquiry_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
    )
    def _withdraw(enquiry_id: uuid.UUID) -> Response:
        """Withdraw nothing.

        :param enquiry_id: The request
        :return: An empty 204
        """
        del enquiry_id
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    assert enquiry_field_leaks(planted) == []
