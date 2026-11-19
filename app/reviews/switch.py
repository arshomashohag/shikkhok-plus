"""The reviews switch as a FastAPI dependency and its documented response.

A gated route lists :func:`require_reviews_on` **before** any lens
dependency, so an off switch answers ``HUB_REVIEWS_OFF`` and never
``NOT_AVAILABLE``. The switch never gates a deletion.
"""

from __future__ import annotations

from typing import Any, Final

from app.errors import AuthorizationError
from app.hub.public.settings import reviews_enabled
from app.schemas.errors import ErrorEnvelope

__all__ = [
    "REVIEWS_OFF_DESCRIPTION",
    "REVIEWS_OFF_RESPONSES",
    "require_reviews_on",
    "reviews_off",
    "reviews_off_responses",
]

#: How every gated route's 404 begins.
REVIEWS_OFF_DESCRIPTION: Final = "HUB_REVIEWS_OFF: reviews are switched off."


def reviews_off_responses(*also: str) -> dict[int | str, dict[str, Any]]:
    """Build a gated route's documented 404, naming the switch first.

    Every gated route in ``app/api/hub_reviews.py`` and ``app/api/admin.py``
    merges this, or :data:`REVIEWS_OFF_RESPONSES`, into its ``responses``;
    ``tests/contract/test_reviewer_contract.py`` holds each to it.

    :param also: Further sentences for the same status, such as another
        code a route answers 404 with
    :return: The OpenAPI ``responses`` entry for 404
    """
    return {
        404: {
            "model": ErrorEnvelope,
            "description": " ".join((REVIEWS_OFF_DESCRIPTION, *also)),
        },
    }


#: The 404 of a gated route the switch is the only 404 of.
REVIEWS_OFF_RESPONSES: Final[dict[int | str, dict[str, Any]]] = reviews_off_responses()


def reviews_off() -> AuthorizationError:
    """Build the response a gated route gives while reviews are off.

    :return: A 404 authorization error with the published message key
    """
    return AuthorizationError(
        code="HUB_REVIEWS_OFF",
        message_key="hub.review.off",
        status=404,
    )


def require_reviews_on() -> None:
    """Refuse the request unless reviews are switched on.

    :raises AuthorizationError: ``HUB_REVIEWS_OFF`` (404) while off
    """
    if not reviews_enabled():
        raise reviews_off()
