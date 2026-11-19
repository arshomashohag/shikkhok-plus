"""The join-requests switch as a FastAPI dependency and its documented response.

A gated route lists :func:`require_enquiries_on` **before** any lens,
target or ownership dependency, so an off switch answers
``HUB_ENQUIRIES_OFF`` and never ``NOT_AVAILABLE`` or
``ENQUIRY_TARGET_NOT_FOUND``. The switch never gates a deletion: a
guardian's own list, their withdrawal, account deletion and the retention
purge all work while it is off.
"""

from __future__ import annotations

from typing import Any, Final

from app.errors import AuthorizationError
from app.hub.public.settings import enquiries_enabled
from app.schemas.errors import ErrorEnvelope

__all__ = [
    "ENQUIRIES_OFF_DESCRIPTION",
    "ENQUIRIES_OFF_RESPONSES",
    "enquiries_off",
    "enquiries_off_responses",
    "require_enquiries_on",
]

#: How every gated route's 404 begins.
ENQUIRIES_OFF_DESCRIPTION: Final = "HUB_ENQUIRIES_OFF: join requests are switched off."


def enquiries_off_responses(*also: str) -> dict[int | str, dict[str, Any]]:
    """Build a gated route's documented 404, naming the switch first.

    Every gated join-request route merges this, or
    :data:`ENQUIRIES_OFF_RESPONSES`, into its ``responses``, so a route that
    also answers ``ENQUIRY_TARGET_NOT_FOUND`` or ``ENQUIRY_NOT_FOUND``
    documents both codes on the one 404.

    :param also: Further sentences for the same status, such as another
        code a route answers 404 with
    :return: The OpenAPI ``responses`` entry for 404
    """
    return {
        404: {
            "model": ErrorEnvelope,
            "description": " ".join((ENQUIRIES_OFF_DESCRIPTION, *also)),
        },
    }


#: The 404 of a gated route the switch is the only 404 of.
ENQUIRIES_OFF_RESPONSES: Final[dict[int | str, dict[str, Any]]] = (
    enquiries_off_responses()
)


def enquiries_off() -> AuthorizationError:
    """Build the response a gated route gives while join requests are off.

    :return: A 404 authorization error with the published message key
    """
    return AuthorizationError(
        code="HUB_ENQUIRIES_OFF",
        message_key="hub.enquiry.off",
        status=404,
    )


def require_enquiries_on() -> None:
    """Refuse the request unless join requests are switched on.

    :raises AuthorizationError: ``HUB_ENQUIRIES_OFF`` (404) while off
    """
    if not enquiries_enabled():
        raise enquiries_off()
