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
from typing import Final

import pytest
from fastapi import FastAPI, Response, status
from pydantic import BaseModel

from app.contract.privacy import (
    ENQUIRY_FORBIDDEN_FIELDS,
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


def test_the_walk_covers_the_seven_routes() -> None:
    """The comment says seven; this is what holds it to seven."""
    assert len(ENQUIRY_ROUTES) == 7
    assert {
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


@pytest.mark.parametrize(("walk", "path"), WALKS)
def test_a_listed_route_returning_a_bare_mapping_fails_closed(
    walk: Callable[[FastAPI], list[tuple[str, str, str]]], path: str
) -> None:
    """A handler annotated ``-> dict[str, str]`` names no field: error.

    FastAPI infers the response model from the annotation, so the route has
    one, and its schema is an object of any keys. Walking field names finds
    nothing to report, and passing it would pass whatever key it returned.
    """
    planted = FastAPI()

    @planted.get(path)
    def _mapping() -> dict[str, str]:
        """Return a body whose keys no schema names.

        :return: A payload carrying an account id
        """
        return {"account_id": str(uuid.uuid4())}

    with pytest.raises(LookupError, match=f"GET {path} answers 200 with an object"):
        walk(planted)


@pytest.mark.parametrize(("walk", "path"), WALKS)
def test_a_listed_route_returning_a_list_of_mappings_fails_closed(
    walk: Callable[[FastAPI], list[tuple[str, str, str]]], path: str
) -> None:
    """The same opaque object one level down, as a list's items, is an error."""
    planted = FastAPI()

    @planted.get(path)
    def _mappings() -> list[dict[str, str]]:
        """Return items whose keys no schema names.

        :return: An empty list
        """
        return []

    with pytest.raises(LookupError, match=f"GET {path} answers 200 with an object"):
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
