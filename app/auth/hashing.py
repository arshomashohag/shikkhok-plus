"""The one chokepoint an OTP and a refresh token pass through.

**HMAC under a server-held key, not a work-factor hash** -- and this
design reversed under measurement, with the first version reading as the
more rigorous one. "Use bcrypt" is the instinct. Measured:

=============== ============ ===========================
Scheme          Per issue    Offline exhaustion of 10^6
=============== ============ ===========================
SHA-256         ~0.1 us      **0.07 s**
bcrypt(8)       15 ms        4 h
bcrypt(10)      58 ms        16 h
**HMAC+key**    **~1 us**    **not without the key**
=============== ============ ===========================

bcrypt slows an attacker who will get there anyway; HMAC stops one who has
only the database. The attempt ceiling already defends the online path
[BR2.3], so the offline path is the whole question -- and a six-digit
space is far too small for work-factor delay to be the answer.

**The key is read from the environment, never from the database**, so a
``SELECT *`` on ``otp_request`` yields values that cannot be reversed
without a second, separately-held secret.

Rotating this key **invalidates every in-flight code**, because stored
digests were computed under the old one. With a five-minute expiry that is
five minutes of sign-ins, which makes rotation deliberate rather than
routine -- and is why the JWT key needs ``kid`` and this one does not.
"""

from __future__ import annotations

import hmac
import os
import secrets
from hashlib import sha256
from typing import Final

__all__ = [
    "OTP_HMAC_KEY_ENV",
    "generate_code",
    "generate_refresh_token",
    "hash_otp",
    "hash_refresh_token",
    "verify_otp",
]

#: Names the environment variable holding the OTP HMAC key. One of the
#: four secrets; never a literal in the repository or an image.
OTP_HMAC_KEY_ENV: Final = "SHIKKHOKPLUS_OTP_HMAC_KEY"

#: Six digits, which is what a person can read from an SMS and retype.
CODE_DIGITS: Final = 6


def _key() -> bytes:
    """Read the HMAC key from the environment.

    :return: The key as bytes
    :raises RuntimeError: The environment names no key
    """
    value = os.environ.get(OTP_HMAC_KEY_ENV)
    if not value:
        raise RuntimeError(
            f"{OTP_HMAC_KEY_ENV} is unset. The OTP key is never hardcoded "
            "and never read from the database."
        )
    return value.encode()


def generate_code() -> str:
    """Generate one OTP.

    ``secrets`` rather than ``random``: the latter is seeded predictably
    and a predicted code defeats every control downstream of it.

    :return: A zero-padded six-digit code
    """
    return f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"


def generate_refresh_token() -> str:
    """Generate one opaque refresh token.

    :return: A URL-safe random token
    """
    return secrets.token_urlsafe(32)


def hash_otp(code: str, phone: str) -> str:
    """Hash a code for storage, binding it to its number.

    Binding the number into the message means a digest captured for one
    number cannot be replayed against another, even with the key.

    :param code: The transmitted code
    :param phone: The number it was issued for
    :return: The hex digest to store
    """
    return hmac.new(_key(), f"{phone}:{code}".encode(), sha256).hexdigest()


def verify_otp(code: str, phone: str, stored: str) -> bool:
    """Compare a presented code against a stored digest.

    ``compare_digest`` rather than ``==``: a short-circuiting comparison
    leaks position information through timing, and this is the one
    comparison an attacker can drive repeatedly.

    :param code: The presented code
    :param phone: The number it was issued for
    :param stored: The digest read from the database
    :return: True when the code matches
    """
    return hmac.compare_digest(hash_otp(code, phone), stored)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage.

    Same shape as the OTP: a leaked table yields no usable session
    [BR4.2].

    :param token: The opaque token handed to the client
    :return: The hex digest to store
    """
    return hmac.new(_key(), token.encode(), sha256).hexdigest()
