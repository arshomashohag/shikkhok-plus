"""Time-based one-time passwords (RFC 6238), as authenticator apps use them.

**Standard parameters, because every authenticator app assumes them**:
HMAC-SHA1, six digits, a thirty-second step. Google Authenticator,
Microsoft Authenticator, Authy and 1Password all read an ``otpauth://``
URI with these defaults, and several ignore any other values silently,
which would produce codes that never match. SHA-1 here is HMAC-SHA1 over
a random 160-bit key, which RFC 6238 specifies and which no known attack
on SHA-1 collisions reaches.

**One step of drift either side is accepted**, so a phone clock thirty
seconds out still works. The caller passes the last step it accepted so
a code can never be used twice, including a code from the step before.

Written against the standard library: the algorithm is twenty lines, and
a dependency for it would be a supply-chain surface for no gain.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import Final
from urllib.parse import quote, urlencode

__all__ = [
    "DIGITS",
    "STEP_SECONDS",
    "code_at",
    "matching_step",
    "new_secret",
    "otpauth_uri",
]

#: Seconds per code.
STEP_SECONDS: Final = 30

#: Digits per code.
DIGITS: Final = 6

#: Steps of clock drift accepted on either side of now.
_DRIFT: Final = 1

#: 160 bits, the key length RFC 4226 recommends for HMAC-SHA1.
_SECRET_BYTES: Final = 20


def new_secret() -> str:
    """Generate a fresh shared secret.

    :return: The secret as unpadded base32, the form apps accept
    """
    raw = secrets.token_bytes(_SECRET_BYTES)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _key(secret: str) -> bytes:
    """Decode a base32 secret, tolerating missing padding and spaces.

    :param secret: The base32 secret
    :return: The raw key
    """
    compact = secret.replace(" ", "").upper()
    return base64.b32decode(compact + "=" * (-len(compact) % 8))


def code_at(secret: str, step: int) -> str:
    """Compute the code for one time step (RFC 4226 dynamic truncation).

    :param secret: The base32 secret
    :param step: The time step: seconds since the epoch over 30
    :return: The zero-padded code
    """
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


def matching_step(
    secret: str,
    code: str,
    last_used_step: int | None,
    now: float | None = None,
) -> int | None:
    """Find the step a presented code belongs to, refusing replays.

    Every candidate step is compared in constant time, and all of them
    are compared, so the response time does not say which one matched.

    :param secret: The base32 secret
    :param code: The code the person typed
    :param last_used_step: The newest step already accepted, or None
    :param now: Seconds since the epoch, or None for the clock
    :return: The matching step, or None when nothing matches or it was
        already used
    """
    typed = code.strip().replace(" ", "")
    if len(typed) != DIGITS or not typed.isdigit():
        return None
    current = int((time.time() if now is None else now) // STEP_SECONDS)
    found: int | None = None
    for step in range(current - _DRIFT, current + _DRIFT + 1):
        if hmac.compare_digest(code_at(secret, step), typed) and found is None:
            found = step
    if found is None or (last_used_step is not None and found <= last_used_step):
        return None
    return found


def otpauth_uri(secret: str, account_label: str, issuer: str) -> str:
    """Build the URI an authenticator app scans or opens.

    :param secret: The base32 secret
    :param account_label: What the app shows under the issuer
    :param issuer: The service name
    :return: An ``otpauth://totp/...`` URI
    """
    label = quote(f"{issuer}:{account_label}", safe="")
    query = urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": DIGITS,
            "period": STEP_SECONDS,
        }
    )
    return f"otpauth://totp/{label}?{query}"
