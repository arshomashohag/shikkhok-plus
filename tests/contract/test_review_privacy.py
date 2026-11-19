"""No review response carries who wrote it, or when to the second [H4].

A review is shown with a tenure bucket and a month, never with a name, an
account, a seat or a timestamp: any of those lets a teacher who knows which
family just became eligible guess the author. The responses of every review
route are walked from the generated document, so a field added to a shared
model three tasks later fails here rather than in a pilot.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI, Response, status
from pydantic import BaseModel

from app.contract.privacy import (
    PUBLIC_FORBIDDEN_FIELDS,
    REVIEW_FORBIDDEN_FIELDS,
    REVIEW_RESPONSE_ROUTES,
    review_field_leaks,
)
from app.contract.routes import REVIEWER_ROUTES, _api_routes
from app.main import create_app


def test_review_forbidden_set_is_the_public_set_plus_identity_and_times() -> None:
    """The set is the public one plus authorship, decision and time fields."""
    assert REVIEW_FORBIDDEN_FIELDS == PUBLIC_FORBIDDEN_FIELDS | {
        "author_account_id",
        "submitted_at",
        "approved_at",
        "edited_at",
        "decided_at",
        "joined_on",
        "written_by_account_id",
        "decided_by_account_id",
    }
    # The three the spec names outright, through the public set.
    assert {"account_id", "enrollment_id", "display_name"} <= REVIEW_FORBIDDEN_FIELDS


def test_the_walk_covers_every_review_route() -> None:
    """The walked set is the reviewer, teacher and reviewable routes."""
    assert (
        REVIEWER_ROUTES
        | {
            ("GET", "/v1/hub/reviews"),
            ("PUT", "/v1/hub/reviews/{review_id}/reply"),
            ("DELETE", "/v1/hub/reviews/{review_id}/reply"),
            ("GET", "/v1/hub/reviewable"),
        }
        == REVIEW_RESPONSE_ROUTES
    )


def test_every_walked_route_is_registered() -> None:
    """The walk is not vacuous: each listed route exists in the real app."""
    registered = {
        (method, route.path)
        for route in _api_routes(create_app())
        for method in route.methods or ()
    }
    assert registered >= REVIEW_RESPONSE_ROUTES


def test_no_review_response_carries_identity_fields() -> None:
    """The real application's review responses are clean."""
    assert review_field_leaks(create_app()) == []


class _Author(BaseModel):
    """A nested model naming its author.

    :ivar author_account_id: Forbidden on any review response
    """

    author_account_id: uuid.UUID


class _LeakyReview(BaseModel):
    """A review response whose nested author leaks.

    :ivar rating: A harmless field
    :ivar author: The leaking child
    """

    rating: int
    author: _Author


class _TimedReview(BaseModel):
    """A review list item carrying its exact submit time.

    :ivar submitted_at: Forbidden on any review response
    """

    submitted_at: str


def test_fixture_leak_is_caught() -> None:
    """A nested ``author_account_id`` and a list item's time are both reported."""
    planted = FastAPI()

    @planted.get("/v1/hub/batches/{batch_id}/my-review", response_model=_LeakyReview)
    def _mine(batch_id: uuid.UUID) -> dict[str, object]:
        """Return nothing.

        :param batch_id: The batch
        :return: An empty payload
        """
        del batch_id
        return {}

    @planted.get("/v1/hub/reviews", response_model=list[_TimedReview])
    def _theirs() -> list[dict[str, str]]:
        """Return nothing.

        :return: An empty list
        """
        return []

    @planted.get("/elsewhere", response_model=_LeakyReview)
    def _elsewhere() -> dict[str, object]:
        """Return nothing on a route the review walk does not cover.

        :return: An empty payload
        """
        return {}

    leaks = review_field_leaks(planted)
    assert sorted(leaks) == [
        ("GET /v1/hub/batches/{batch_id}/my-review", "_Author", "author_account_id"),
        ("GET /v1/hub/reviews", "_TimedReview", "submitted_at"),
    ]


def test_a_listed_route_with_no_response_model_fails_closed() -> None:
    """A review route answering 200 with a bare body cannot be walked: error.

    FastAPI documents such a route with no schema, so a field it returns is
    invisible to the walk; skipping it would pass whatever it leaked.
    """
    planted = FastAPI()

    @planted.get("/v1/hub/reviews", response_model=None)
    def _bare() -> dict[str, str]:
        """Return a body no model describes.

        :return: A payload carrying the author
        """
        return {"author_account_id": str(uuid.uuid4())}

    with pytest.raises(LookupError, match="GET /v1/hub/reviews answers 200"):
        review_field_leaks(planted)


def test_a_listed_204_route_with_no_model_is_skipped() -> None:
    """A delete answering 204 has no body, so it is the one allowed skip."""
    planted = FastAPI()

    @planted.delete(
        "/v1/hub/reviews/{review_id}/reply",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
    )
    def _delete(review_id: uuid.UUID) -> Response:
        """Delete nothing.

        :param review_id: The review
        :return: An empty 204
        """
        del review_id
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    assert review_field_leaks(planted) == []
