"""What a review or a reply may say: no way to reach its author.

A review is anonymous on the public page (spec section 6); a phone number or
a web address in its text would undo that, and would let a review become an
advertisement. Text carrying either is refused, naming only the field.

Phone numbers are found by :func:`app.accounts.phone.contains_phone`, which
already reads Bangla digits and the separators people type. Web addresses
are found by :data:`URL`: a scheme or ``www.``, or a dotted host ending in
one of the listed top-level domains. A decimal such as ``4.5`` or ``4.30``
has no letters after its dot and is never a host.
"""

from __future__ import annotations

import re
from typing import Final

from app.accounts.phone import contains_phone
from app.errors import ValidationError

__all__ = ["URL", "contains_url", "refuse_contact"]

#: A web address: a scheme or ``www.``, or a host under a listed domain.
URL: Final = re.compile(
    r"(?i)\b(?:https?://|www\.)"
    r"|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*"
    r"\.(?:com|net|org|info|biz|bd|io|me|co|app|link|xyz|online|site|page)\b"
)


def contains_url(text: str) -> bool:
    """Say whether text holds a web address.

    :param text: Any free text
    :return: True when :data:`URL` matches anywhere in it
    """
    return URL.search(text) is not None


def refuse_contact(field: str, text: str | None) -> None:
    """Refuse text that carries a phone number or a web address.

    :param field: The field's name, returned to the client
    :param text: The text, or None for none
    :return: None
    :raises ValidationError: ``REVIEW_CONTAINS_CONTACT`` (400)
    """
    if text is None:
        return
    if contains_phone(text) or contains_url(text):
        raise ValidationError(
            code="REVIEW_CONTAINS_CONTACT",
            message_key="hub.review.contains_contact",
            details={"field": field},
        )
