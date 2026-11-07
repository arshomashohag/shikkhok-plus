"""Encrypting authenticator secrets, and hashing recovery codes.

**A TOTP secret is encrypted, not hashed**, because checking a code needs
the secret itself. AES-256-GCM, with a random 96-bit nonce per secret and
the account id as associated data, so a ciphertext copied onto another
account's row fails to decrypt instead of granting that account a factor.

**Keys are a keyring, like the JWT keys** (``SHIKKHOKPLUS_MFA_KEYS``,
``kid:base64`` pairs, comma-separated, and ``SHIKKHOKPLUS_MFA_ACTIVE_KID``).
Each row records the kid that encrypted it, so a key can be rotated by
adding a new one, making it active, and keeping the old one until every
row has been re-encrypted or re-enrolled.

**Recovery codes are hashed with scrypt and a per-code salt.** They are
used rarely and checked against at most ten rows, so a deliberately slow
hash costs a person well under a second and costs anyone holding a
database dump the full work factor per guess.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import uuid
from dataclasses import dataclass
from typing import Final

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

__all__ = [
    "MFA_ACTIVE_KID_ENV",
    "MFA_KEYS_ENV",
    "RECOVERY_CODE_COUNT",
    "EncryptedSecret",
    "MfaKeyError",
    "decrypt_secret",
    "encrypt_secret",
    "hash_recovery_code",
    "keyring_configured",
    "new_recovery_codes",
    "normalise_recovery_code",
    "recovery_code_matches",
]

#: ``kid:base64key`` pairs, comma-separated; each key is 32 random bytes.
MFA_KEYS_ENV: Final = "SHIKKHOKPLUS_MFA_KEYS"

#: Which kid encrypts new secrets.
MFA_ACTIVE_KID_ENV: Final = "SHIKKHOKPLUS_MFA_ACTIVE_KID"

#: Recovery codes issued at enrollment.
RECOVERY_CODE_COUNT: Final = 10

#: Ten characters from a 32-letter alphabet: 50 bits per code.
_RECOVERY_ALPHABET: Final = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_RECOVERY_LENGTH: Final = 10

#: scrypt parameters: 16 MiB and roughly 50 ms per hash.
_SCRYPT_N: Final = 2**14
_SCRYPT_R: Final = 8
_SCRYPT_P: Final = 1

_NONCE_BYTES: Final = 12


class MfaKeyError(RuntimeError):
    """The MFA keyring is missing or malformed.

    A deployment fault rather than a request fault, so deliberately not a
    :class:`~app.errors.TaxonomyError`; the startup check reports it
    before any request can reach it.
    """


@dataclass(frozen=True, slots=True)
class EncryptedSecret:
    """One encrypted authenticator secret.

    :ivar kid: The key that encrypted it
    :ivar ciphertext: The nonce followed by the AES-GCM output
    """

    kid: str
    ciphertext: bytes


def _keyring() -> dict[str, bytes]:
    """Read the configured keys.

    :return: Key bytes by kid
    :raises MfaKeyError: A key is missing, malformed or not 32 bytes
    """
    keys: dict[str, bytes] = {}
    for pair in os.environ.get(MFA_KEYS_ENV, "").split(","):
        if not pair.strip():
            continue
        kid, sep, encoded = pair.strip().partition(":")
        if not sep or not kid:
            raise MfaKeyError(f"{MFA_KEYS_ENV} entries must be kid:base64key")
        try:
            key = base64.b64decode(encoded, validate=True)
        except ValueError as error:
            raise MfaKeyError(f"{MFA_KEYS_ENV} key {kid!r} is not base64") from error
        if len(key) != 32:
            raise MfaKeyError(f"{MFA_KEYS_ENV} key {kid!r} is not 32 bytes")
        keys[kid] = key
    return keys


def _active() -> tuple[str, bytes]:
    """Return the key new secrets are encrypted with.

    :return: The active kid and its key
    :raises MfaKeyError: No keyring, or the active kid is not in it
    """
    keys = _keyring()
    kid = os.environ.get(MFA_ACTIVE_KID_ENV, "")
    if kid not in keys:
        raise MfaKeyError(
            f"{MFA_ACTIVE_KID_ENV}={kid!r} names no key in {MFA_KEYS_ENV}"
        )
    return kid, keys[kid]


def keyring_configured() -> bool:
    """Report whether secrets can be encrypted right now.

    :return: True when the keyring parses and the active kid is in it
    """
    try:
        _active()
    except MfaKeyError:
        return False
    return True


def encrypt_secret(secret: str, account_id: uuid.UUID) -> EncryptedSecret:
    """Encrypt an authenticator secret for one account.

    :param secret: The base32 secret
    :param account_id: The owner, bound in as associated data
    :return: The kid and the ciphertext
    :raises MfaKeyError: The keyring is not configured
    """
    kid, key = _active()
    nonce = secrets.token_bytes(_NONCE_BYTES)
    sealed = AESGCM(key).encrypt(nonce, secret.encode("ascii"), account_id.bytes)
    return EncryptedSecret(kid=kid, ciphertext=nonce + sealed)


def decrypt_secret(sealed: EncryptedSecret, account_id: uuid.UUID) -> str:
    """Decrypt an authenticator secret.

    :param sealed: What :func:`encrypt_secret` produced
    :param account_id: The account the row belongs to
    :return: The base32 secret
    :raises MfaKeyError: The kid is unknown
    :raises cryptography.exceptions.InvalidTag: The ciphertext was
        altered or belongs to another account
    """
    key = _keyring().get(sealed.kid)
    if key is None:
        raise MfaKeyError(f"no key {sealed.kid!r} in {MFA_KEYS_ENV}")
    nonce, body = sealed.ciphertext[:_NONCE_BYTES], sealed.ciphertext[_NONCE_BYTES:]
    return AESGCM(key).decrypt(nonce, body, account_id.bytes).decode("ascii")


def new_recovery_codes() -> list[str]:
    """Generate one set of recovery codes, shown to the person once.

    :return: Codes formatted ``XXXXX-XXXXX``
    """
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(
            secrets.choice(_RECOVERY_ALPHABET) for _ in range(_RECOVERY_LENGTH)
        )
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def normalise_recovery_code(typed: str) -> str:
    """Read a recovery code the way a person might type it.

    :param typed: The code, with or without the dash, any case
    :return: The ten characters, upper-case, or "" when implausible
    """
    compact = "".join(typed.split()).replace("-", "").upper()
    if len(compact) != _RECOVERY_LENGTH or any(
        c not in _RECOVERY_ALPHABET for c in compact
    ):
        return ""
    return compact


def hash_recovery_code(code: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Hash one recovery code for storage.

    :param code: The code, as issued or typed
    :param salt: A salt to reuse when checking, or None for a new one
    :return: The hash and the salt
    """
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        normalise_recovery_code(code).encode("ascii"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
    )
    return digest, salt


def recovery_code_matches(typed: str, stored_hash: bytes, salt: bytes) -> bool:
    """Check a typed recovery code against one stored hash.

    :param typed: What the person typed
    :param stored_hash: The stored hash
    :param salt: Its salt
    :return: True on a match
    """
    if not normalise_recovery_code(typed):
        return False
    digest, _ = hash_recovery_code(typed, salt)
    return hmac.compare_digest(digest, stored_hash)
