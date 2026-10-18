"""The OTP body, and the assertion that it fits one segment.

**English GSM-7 at 160 characters per segment, not 70.** Code 1012
(masking sender requires a Bangla body) does not apply to OTP traffic, so
the body stays English and keeps the larger segment [BR5.5].

The SMS Retriever app hash consumes 11 characters plus its leading
space, which is easy to forget until the invoice arrives: exceeding one
segment **silently doubles the per-OTP cost with no error and no
signal**. So the check is a build-time assertion rather than a comment.

The hash is required by the SMS Retriever API, which is how the client
reads the code **without any SMS read permission** [TC-5]. The number is
always typed by the user and never read from the SIM.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "APP_HASH_LENGTH",
    "GSM7_SEGMENT",
    "OTP_TEMPLATE",
    "render_otp_message",
]

#: One GSM-7 segment. Exceeding it doubles the cost of every OTP.
GSM7_SEGMENT: Final = 160

#: The SMS Retriever app hash is exactly 11 characters.
APP_HASH_LENGTH: Final = 11

#: The body. ``<#>`` is the SMS Retriever prefix and the hash closes it.
OTP_TEMPLATE: Final = (
    "<#> {code} is your ShikhokPlus code. It expires in 5 minutes. "
    "Do not share it. {app_hash}"
)

#: Every character GSM-7 encodes in one septet. A character outside this
#: set forces UCS-2 and a 70-character segment, which is the other way
#: the cost silently doubles.
_GSM7_CHARSET: Final = frozenset(
    "@£$¥èéùìòÇØøÅå_ÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
    "\n\r"
)

#: Characters costing two septets rather than one.
_GSM7_EXTENDED: Final = frozenset("^{}\\[~]|€")


def gsm7_length(text: str) -> int:
    """Count a string's length in GSM-7 septets.

    Not ``len()``: the extended characters cost two septets each, so a
    naive length check passes on a body that needs two segments.

    :param text: The body to measure
    :return: The septet count
    :raises ValueError: The text contains a non-GSM-7 character
    """
    total = 0
    for character in text:
        if character in _GSM7_EXTENDED:
            total += 2
        elif character in _GSM7_CHARSET:
            total += 1
        else:
            raise ValueError(
                f"{character!r} is not GSM-7, so the whole body would "
                "encode as UCS-2 at 70 characters per segment"
            )
    return total


def render_otp_message(code: str, app_hash: str) -> str:
    """Render the OTP body for one code.

    :param code: The six-digit code
    :param app_hash: The 11-character SMS Retriever app hash
    :return: The body to send
    :raises ValueError: The rendered body exceeds one GSM-7 segment
    """
    body = OTP_TEMPLATE.format(code=code, app_hash=app_hash)
    length = gsm7_length(body)
    if length > GSM7_SEGMENT:
        raise ValueError(
            f"the rendered OTP body is {length} septets, over the "
            f"{GSM7_SEGMENT}-septet segment: this doubles the cost of "
            "every OTP with no error and no signal [BR5.5]"
        )
    return body
