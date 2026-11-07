"""Authenticator secrets encrypted per account; recovery codes hashed.

The account id is the AES-GCM associated data, so the property that
matters most is the one a test can state directly: a ciphertext moved
onto another account's row does not decrypt.
"""

from __future__ import annotations

import base64
import os
import uuid

import pytest
from cryptography.exceptions import InvalidTag

from app.auth.mfa_crypto import (
    MFA_ACTIVE_KID_ENV,
    MFA_KEYS_ENV,
    RECOVERY_CODE_COUNT,
    EncryptedSecret,
    MfaKeyError,
    decrypt_secret,
    encrypt_secret,
    hash_recovery_code,
    keyring_configured,
    new_recovery_codes,
    normalise_recovery_code,
    recovery_code_matches,
)


def _key() -> str:
    """Make one base64 key.

    :return: 32 random bytes, base64
    """
    return base64.b64encode(os.urandom(32)).decode()


@pytest.fixture
def keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure a two-key ring with k2 active.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(MFA_KEYS_ENV, f"k1:{_key()}, k2:{_key()}")
    monkeypatch.setenv(MFA_ACTIVE_KID_ENV, "k2")


def test_a_secret_round_trips_for_its_own_account(keyring: None) -> None:
    """Encrypted with the active key, decrypted back.

    :param keyring: The configured keys
    :return: None
    """
    account = uuid.uuid4()
    sealed = encrypt_secret("JBSWY3DPEHPK3PXP", account)
    assert sealed.kid == "k2"
    assert b"JBSWY3DPEHPK3PXP" not in sealed.ciphertext
    assert decrypt_secret(sealed, account) == "JBSWY3DPEHPK3PXP"


def test_a_ciphertext_moved_to_another_account_does_not_decrypt(keyring: None) -> None:
    """The account id is bound in as associated data.

    :param keyring: The configured keys
    :return: None
    """
    sealed = encrypt_secret("JBSWY3DPEHPK3PXP", uuid.uuid4())
    with pytest.raises(InvalidTag):
        decrypt_secret(sealed, uuid.uuid4())


def test_a_tampered_ciphertext_does_not_decrypt(keyring: None) -> None:
    """GCM authenticates every byte.

    :param keyring: The configured keys
    :return: None
    """
    account = uuid.uuid4()
    sealed = encrypt_secret("JBSWY3DPEHPK3PXP", account)
    flipped = bytes([sealed.ciphertext[0] ^ 1]) + sealed.ciphertext[1:]
    with pytest.raises(InvalidTag):
        decrypt_secret(EncryptedSecret(kid=sealed.kid, ciphertext=flipped), account)


def test_the_same_secret_encrypts_differently_each_time(keyring: None) -> None:
    """A fresh nonce per encryption.

    :param keyring: The configured keys
    :return: None
    """
    account = uuid.uuid4()
    first = encrypt_secret("JBSWY3DPEHPK3PXP", account)
    second = encrypt_secret("JBSWY3DPEHPK3PXP", account)
    assert first.ciphertext != second.ciphertext


def test_a_retired_key_still_decrypts_after_rotation(
    keyring: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rows sealed under the old kid keep working while it stays in the ring.

    :param keyring: The configured keys
    :param monkeypatch: The patcher
    :return: None
    """
    account = uuid.uuid4()
    sealed = encrypt_secret("JBSWY3DPEHPK3PXP", account)
    ring = os.environ[MFA_KEYS_ENV]
    monkeypatch.setenv(MFA_KEYS_ENV, f"{ring},k3:{_key()}")
    monkeypatch.setenv(MFA_ACTIVE_KID_ENV, "k3")
    assert decrypt_secret(sealed, account) == "JBSWY3DPEHPK3PXP"
    assert encrypt_secret("X", account).kid == "k3"


@pytest.mark.parametrize(
    ("keys", "active"),
    [
        ("", "k1"),
        ("k1:not-base64!", "k1"),
        (f"k1:{base64.b64encode(b'short').decode()}", "k1"),
        ("nocolon", "k1"),
        ("k1:" + base64.b64encode(os.urandom(32)).decode(), "k9"),
    ],
)
def test_a_bad_keyring_refuses_to_encrypt(
    keys: str, active: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing, malformed, short or unnamed keys fail loudly.

    :param keys: The keyring value
    :param active: The active kid
    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(MFA_KEYS_ENV, keys)
    monkeypatch.setenv(MFA_ACTIVE_KID_ENV, active)
    assert keyring_configured() is False
    with pytest.raises(MfaKeyError):
        encrypt_secret("X", uuid.uuid4())


def test_an_unknown_kid_refuses_to_decrypt(keyring: None) -> None:
    """A row sealed under a key that left the ring cannot be read.

    :param keyring: The configured keys
    :return: None
    """
    with pytest.raises(MfaKeyError):
        decrypt_secret(EncryptedSecret(kid="gone", ciphertext=b"x" * 40), uuid.uuid4())


def test_recovery_codes_are_ten_distinct_and_readable() -> None:
    """Ten codes, five-dash-five, from an alphabet without 0/O or 1/I.

    :return: None
    """
    codes = new_recovery_codes()
    assert len(codes) == RECOVERY_CODE_COUNT == len(set(codes))
    for code in codes:
        assert len(code) == 11 and code[5] == "-"
        assert not set(code.replace("-", "")) & set("01IO")


def test_a_recovery_code_matches_however_it_is_typed() -> None:
    """Case, spaces and the dash do not matter; a different code does.

    :return: None
    """
    code = new_recovery_codes()[0]
    digest, salt = hash_recovery_code(code)
    assert recovery_code_matches(code, digest, salt)
    assert recovery_code_matches(code.lower().replace("-", " "), digest, salt)
    assert not recovery_code_matches(new_recovery_codes()[0], digest, salt)
    assert not recovery_code_matches("short", digest, salt)


def test_hashes_are_salted() -> None:
    """The same code hashes differently under two salts.

    :return: None
    """
    code = new_recovery_codes()[0]
    assert hash_recovery_code(code)[0] != hash_recovery_code(code)[0]


@pytest.mark.parametrize("typed", ["", "ABCDE", "ABCDE-FGH0K", "ABCDE-FGHJKL"])
def test_implausible_codes_normalise_to_nothing(typed: str) -> None:
    """Wrong length or a character outside the alphabet.

    :param typed: What was typed
    :return: None
    """
    assert normalise_recovery_code(typed) == ""
