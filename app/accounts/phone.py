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

__all__ = ["canonical_phone", "contains_phone"]

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
        # The key is written LITERALLY, not through a constant: the
        # message-key contract gate finds raised keys by matching the
        # keyword with a quoted string, and a constant here hid this one
        # from it, leaving it unpublished and untested on the client.
        raise ValidationError(code="PHONE_INVALID", message_key="phone.invalid")
    return f"+880{text[1:]}"


#: A run of digits with the separators people type between them, long enough
#: to hold a whole mobile number.
_DIGIT_RUN: Final = re.compile(r"\+?\d(?:[\s\-().]*\d){9,}")

#: A mobile number inside a bare digit string, with or without the country
#: code, built from the same pattern sign-in uses.
_EMBEDDED_MOBILE: Final = re.compile(r"(?:880|0)" + _LOCAL_MOBILE.pattern[1:])


def _group_starts(run: str) -> tuple[str, list[int]]:
    """Strip a digit run of separators and note where each digit group begins.

    :param run: A run of digits and the separators typed between them
    :return: The bare digits, and the index in them where each group starts
    """
    digits: list[str] = []
    starts: list[int] = []
    fresh = True
    for char in run:
        if char.isdigit():
            if fresh:
                starts.append(len(digits))
                fresh = False
            digits.append(char)
        elif char in " \t\n-().":
            fresh = True
    return "".join(digits), starts


def contains_phone(text: str) -> bool:
    """Say whether free text holds a Bangladeshi mobile number.

    Uses the same reading of digits and separators as
    :func:`canonical_phone`, so a number written in Bangla digits, with
    dashes, or with the country code is found as readily as a plain one. A
    match must begin at the start of a digit group, so a list of years or
    fees whose digits merely happen to contain a number is not flagged.

    :param text: Any free text
    :return: True when a mobile number appears anywhere in it
    """
    for run in _DIGIT_RUN.findall(_latin_digits(text)):
        digits, starts = _group_starts(run)
        if any(_EMBEDDED_MOBILE.match(digits, start) for start in starts):
            return True
    return False


def _latin_digits(text: str) -> str:
    """Read Bangla digits as their Latin counterparts.

    :param text: Any text
    :return: The text with each Bangla digit replaced
    """
    return "".join(
        str(ord(char) - _BANGLA_ZERO) if 0 <= ord(char) - _BANGLA_ZERO <= 9 else char
        for char in text
    )
