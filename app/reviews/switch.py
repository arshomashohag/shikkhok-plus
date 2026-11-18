"""The reviews switch as a FastAPI dependency and its documented response.

A gated route lists :func:`require_reviews_on` **before** any lens
dependency, so an off switch answers ``HUB_REVIEWS_OFF`` and never
``NOT_AVAILABLE``. The switch never gates a deletion.
"""

from __future__ import annotations

from typing import Any

from app.errors import AuthorizationError
from app.hub.public.settings import reviews_enabled
from app.schemas.errors import ErrorEnvelope

__all__ = ["REVIEWS_OFF_RESPONSES", "require_reviews_on", "reviews_off"]

#: The OpenAPI ``responses`` entry every gated route merges in.
REVIEWS_OFF_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {
        "model": ErrorEnvelope,
        "description": "Reviews are switched off (HUB_REVIEWS_OFF)",
    },
}


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
