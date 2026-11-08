"""What a person signs in with: a phone number or an email address.

**Exactly one per request, and the type says which** [0032]. Every code,
signup draft and sign-in names its destination through
:class:`Identifier`, so a function cannot be handed an email address
where it expects a number: the channel travels with the value, and the
two SQL columns it can select are fixed here rather than spelled at
each call site.

**An email address is compared lowercased.** RFC 5321 lets the local
part be case-sensitive, and no mail provider people in this market use
treats it so; storing it as typed would let ``Rahim@x.com`` and
``rahim@x.com`` become two accounts that receive the same mail, which is
the squatting problem verify-first signup exists to close [C-07].
"""

from __future__ import annotations

import enum
import hashlib
import re
from dataclasses import dataclass
from typing import Final, Literal

from app.accounts.phone import canonical_phone
from app.errors import ValidationError

__all__ = [
    "EMAIL_MAX_LENGTH",
    "Channel",
    "Identifier",
    "canonical_email",
]

#: RFC 5321's limit on a forward path; nothing longer can receive mail.
EMAIL_MAX_LENGTH: Final = 254

#: Deliberately loose: one ``@``, no whitespace, a dot in the domain.
#: Deliverability is proved by the code, not by a pattern, and a strict
#: pattern only refuses addresses that work.
_EMAIL: Final = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class Channel(enum.Enum):
    """How a code reaches a person, and which column holds the value."""

    PHONE = "phone"
    EMAIL = "email"


@dataclass(frozen=True, slots=True)
class Identifier:
    """A canonical phone number or email address, tagged with its channel.

    :ivar channel: Which kind of value this is
    :ivar value: ``+8801XXXXXXXXX`` or a lowercased address
    """

    channel: Channel
    value: str

    @classmethod
    def phone(cls, raw: str) -> Identifier:
        """Build a phone identifier, canonicalising the number.

        :param raw: The number as typed
        :return: The identifier
        :raises ValidationError: Not a Bangladeshi mobile number
        """
        return cls(Channel.PHONE, canonical_phone(raw))

    @classmethod
    def email(cls, raw: str) -> Identifier:
        """Build an email identifier, canonicalising the address.

        :param raw: The address as typed
        :return: The identifier
        :raises ValidationError: Not an email address
        """
        return cls(Channel.EMAIL, canonical_email(raw))

    @property
    def column(self) -> Literal["phone", "email"]:
        """Name the column this value is stored in.

        The only way a column name reaches SQL in the auth path: a
        literal from a closed set, never text from a request.

        :return: ``phone`` or ``email``
        """
        return "phone" if self.channel is Channel.PHONE else "email"

    @property
    def is_phone(self) -> bool:
        """Report whether this is a phone number.

        :return: True for a phone number
        """
        return self.channel is Channel.PHONE

    @property
    def rate_key(self) -> str:
        """Return the value a per-identifier rate-limit counter is keyed on.

        A phone number as it always was, so existing counters carry over.
        An address is hashed: ``rate_limit_counter.scope_value`` is 64
        characters, an address can be 254, and a counter table is no
        place to keep a list of everyone's email.

        :return: The counter key
        """
        if self.is_phone:
            return self.value
        return "e:" + hashlib.sha256(self.value.encode("utf-8")).hexdigest()[:62]

    def as_params(self) -> dict[str, str | None]:
        """Return both identifier columns, one set and one null.

        :return: ``{"phone": ..., "email": ...}``
        """
        return {
            "phone": self.value if self.is_phone else None,
            "email": None if self.is_phone else self.value,
        }


def canonical_email(raw: str) -> str:
    """Return the one stored form of an email address.

    :param raw: The address as typed
    :return: The address, trimmed and lowercased
    :raises ValidationError: It is not an email address
    """
    text = raw.strip().lower()
    if len(text) > EMAIL_MAX_LENGTH or not _EMAIL.fullmatch(text):
        # Literal key, for the message-key contract gate (see phone.py).
        raise ValidationError(code="EMAIL_INVALID", message_key="email.invalid")
    return text
