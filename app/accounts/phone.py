"""One canonical form for every phone number the server stores or compares.

**Why this exists.** Numbers were stored exactly as typed, on both the
client and the server. ``account.phone`` is unique on that raw string, so
one person signing in as ``01711111111`` and later as ``+8801711111111``
held two accounts; a teacher's ``01711-234567`` never matched the
guardian's account, so phone-based linking silently failed; and the
per-number OTP ceiling counted each spelling as a separate number, which
tripled what one phone could cost [D-33].

The canonical form is E.164: ``+8801XXXXXXXXX``. Every request schema that
takes a number canonicalises it on the way in (``app.schemas.phone``), so
nothing downstream sees any other spelling, and migration 0008 rewrote the
numbers already stored.
"""

from __future__ import annotations

import re
from typing import Final

from app.errors import ValidationError

__all__ = ["PHONE_INVALID_KEY", "canonical_phone"]

#: The client string resource for a number that cannot receive an OTP.
PHONE_INVALID_KEY: Final = "phone.invalid"

#: A Bangladeshi mobile number once the country code is removed: ``01``,
#: an operator digit 3-9, then eight more digits. ``012`` and the landline
#: ranges are excluded because a number that cannot receive an SMS cannot
#: complete sign-in.
_LOCAL_MOBILE: Final = re.compile(r"01[3-9][0-9]{8}")

#: Characters people type between digits, which carry no meaning.
_SEPARATORS: Final = re.compile(r"[\s\-().]")

#: Bangla digit zero; the nine that follow are contiguous in Unicode.
_BANGLA_ZERO: Final = 0x09E6


def canonical_phone(raw: str) -> str:
    """Return the one stored form of a Bangladeshi mobile number.

    Accepts ``01711234567``, ``8801711234567``, ``+8801711234567`` and
    ``008801711234567``, with spaces, dashes or brackets anywhere and in
    Latin or Bangla digits. Idempotent: a canonical number passes through.

    :param raw: The number as typed
    :return: The number as ``+8801XXXXXXXXX``
    :raises ValidationError: It is not a Bangladeshi mobile number
    """
    text = _SEPARATORS.sub("", _latin_digits(raw))
    if text.startswith("+"):
        text = text[1:]
    elif text.startswith("00"):
        text = text[2:]
    if text.startswith("880"):
        # E.164 drops the trunk zero: +880 1711... is local 01711...
        text = "0" + text[3:]
    if not _LOCAL_MOBILE.fullmatch(text):
        raise ValidationError(code="PHONE_INVALID", message_key=PHONE_INVALID_KEY)
    return f"+880{text[1:]}"


def _latin_digits(text: str) -> str:
    """Read Bangla digits as their Latin counterparts.

    :param text: Any text
    :return: The text with each Bangla digit replaced
    """
    return "".join(
        str(ord(char) - _BANGLA_ZERO) if 0 <= ord(char) - _BANGLA_ZERO <= 9 else char
        for char in text
    )
