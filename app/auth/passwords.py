"""Hashing and checking passwords.

**scrypt, from the standard library**, as the recovery codes already
are (:mod:`app.auth.mfa_crypto`). The parameters are one of OWASP's
equivalent scrypt configurations -- N=2^14, r=8, p=5 -- chosen over the
N=2^17 one because they cost 16 MiB per hash rather than 128 MiB, on a
2 GB host running two workers. Roughly a quarter of a second per hash:
nothing to a person signing in, the full work factor per guess to
anyone holding a dump.

**The stored form names its own parameters** (``scrypt$N$r$p$salt$hash``),
so raising them later rehashes on the next successful sign-in instead of
needing a migration that nobody can run without the passwords.

**The policy is NIST SP 800-63B's**: a length floor, a generous ceiling,
no composition rules, and a refusal of passwords known to be common.
Length is counted in Unicode code points, so a Bangla password is
measured the way the person sees it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Final

from app.errors import ValidationError

__all__ = [
    "MAX_LENGTH",
    "MIN_LENGTH",
    "check_policy",
    "hash_password",
    "needs_rehash",
    "verify_nothing",
    "verify_password",
]

#: NIST SP 800-63B's floor for a password the person chose.
MIN_LENGTH: Final = 8

#: Long enough for any passphrase; short enough that a hash request is
#: not a way to make the server hash a megabyte.
MAX_LENGTH: Final = 128

_N: Final = 2**14
_R: Final = 8
_P: Final = 5
_SALT_BYTES: Final = 16
_HASH_BYTES: Final = 32
_SCHEME: Final = "scrypt"

#: The most common passwords in public breach corpora, plus the ones this
#: product's own name and market invite. Matched case-insensitively. A
#: short list on purpose: its job is to refuse the guesses an attacker
#: tries first, not to be a dictionary.
_COMMON: Final = frozenset(
    {
        "00000000",
        "11111111",
        "12121212",
        "12341234",
        "12344321",
        "123456789",
        "1234567890",
        "12345678",
        "123123123",
        "1q2w3e4r",
        "1qaz2wsx",
        "87654321",
        "88888888",
        "99999999",
        "abc12345",
        "abcd1234",
        "abcdefgh",
        "asdfasdf",
        "asdfghjk",
        "bangladesh",
        "bangladesh1",
        "baseball",
        "dhaka123",
        "football",
        "iloveyou",
        "password",
        "password1",
        "password123",
        "passw0rd",
        "princess",
        "qwerty123",
        "qwertyui",
        "qwertyuiop",
        "shikkhok",
        "shikkhok123",
        "shikkhokplus",
        "sunshine",
        "superman",
        "teacher123",
        "welcome1",
        "welcome123",
    }
)


def check_policy(password: str) -> None:
    """Refuse a password the policy does not allow.

    :param password: The password as typed
    :return: None
    :raises ValidationError: Too short, too long, or common
    """
    length = len(password)
    # Keys spelled literally, for the message-key contract gate.
    if length < MIN_LENGTH:
        raise ValidationError(
            code="PASSWORD_TOO_SHORT", message_key="auth.password.too_short"
        )
    if length > MAX_LENGTH:
        raise ValidationError(
            code="PASSWORD_TOO_LONG", message_key="auth.password.too_long"
        )
    if password.strip().lower() in _COMMON or len(set(password)) == 1:
        raise ValidationError(
            code="PASSWORD_TOO_COMMON", message_key="auth.password.too_common"
        )


def hash_password(password: str) -> str:
    """Hash a password for storage.

    :param password: The password
    :return: ``scrypt$N$r$p$salt$hash``, both base64
    """
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = _derive(password, salt, _N, _R, _P)
    return "$".join(
        (
            _SCHEME,
            str(_N),
            str(_R),
            str(_P),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored hash, in constant time.

    :param password: The password presented
    :param stored: What :func:`hash_password` produced
    :return: True when it matches; False for a mismatch or a malformed hash
    """
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != _SCHEME:
            return False
        expected = base64.b64decode(digest)
        actual = _derive(password, base64.b64decode(salt), int(n), int(r), int(p))
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


def verify_nothing(password: str) -> None:
    """Spend what a real check spends, for an account with no password.

    :param password: The password presented, checked against nothing
    :return: None
    """
    _derive(password, b"\x00" * _SALT_BYTES, _N, _R, _P)


def needs_rehash(stored: str) -> bool:
    """Report whether a hash was made with other parameters than today's.

    :param stored: A stored hash
    :return: True when it should be replaced on the next sign-in
    """
    return not stored.startswith(f"{_SCHEME}${_N}${_R}${_P}$")


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    """Run scrypt with enough memory headroom for its parameters.

    :param password: The password
    :param salt: The salt
    :param n: CPU and memory cost
    :param r: Block size
    :param p: Parallelism
    :return: The derived key
    """
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        maxmem=256 * n * r,
        dklen=_HASH_BYTES,
    )
