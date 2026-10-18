"""The chokepoint, and the assertion that a bare digest would fail.

**"The stored value differs from the transmitted one" is satisfied by
SHA-256.** It is also satisfied by ROT13. So the test that carries BR2.4
is the second half: the digest must **not be reproducible without the
key**, which is the property that stops an attacker holding only the
database.

Asserting that a correct code verifies is satisfied by storing it in
plaintext, so that test certifies nothing on its own and is here only as
a sanity check beneath the two that matter.
"""

from __future__ import annotations

import hashlib

import pytest

from app.auth.hashing import (
    CODE_DIGITS,
    OTP_HMAC_KEY_ENV,
    generate_code,
    generate_refresh_token,
    hash_otp,
    hash_refresh_token,
    verify_otp,
)

PHONE = "+8801711111111"
CODE = "123456"


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a test HMAC key.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")


def test_the_stored_value_is_not_the_transmitted_code() -> None:
    assert hash_otp(CODE, PHONE) != CODE


def test_the_digest_is_not_reproducible_without_the_key() -> None:
    # THE HALF THAT MATTERS. A bare SHA-256 of the same message passes
    # the test above and fails this one -- which is the whole distinction
    # between a digest and a keyed MAC [BR2.4, NFR9.5].
    stored = hash_otp(CODE, PHONE)

    unkeyed = hashlib.sha256(f"{PHONE}:{CODE}".encode()).hexdigest()
    assert stored != unkeyed

    also_unkeyed = hashlib.sha256(CODE.encode()).hexdigest()
    assert stored != also_unkeyed


def test_a_different_key_produces_a_different_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = hash_otp(CODE, PHONE)
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "a-different-key")
    assert hash_otp(CODE, PHONE) != first


def test_the_digest_is_bound_to_the_number() -> None:
    # A digest captured for one number must not be replayable against
    # another, even by someone holding the key.
    assert hash_otp(CODE, PHONE) != hash_otp(CODE, "+8801799999999")


def test_a_correct_code_verifies() -> None:
    assert verify_otp(CODE, PHONE, hash_otp(CODE, PHONE))


def test_a_wrong_code_does_not_verify() -> None:
    assert not verify_otp("999999", PHONE, hash_otp(CODE, PHONE))


def test_a_correct_code_for_another_number_does_not_verify() -> None:
    assert not verify_otp(CODE, "+8801799999999", hash_otp(CODE, PHONE))


def test_a_missing_key_raises_rather_than_defaulting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Defaulting to a constant would make every digest reproducible by
    # anyone reading the source, which is the failure this raise exists
    # to prevent.
    monkeypatch.delenv(OTP_HMAC_KEY_ENV, raising=False)
    with pytest.raises(RuntimeError):
        hash_otp(CODE, PHONE)


def test_the_key_is_not_hardcoded_anywhere() -> None:
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[2] / "app" / "auth" / "hashing.py"
    ).read_text()
    # The module names the ENVIRONMENT VARIABLE; it must not carry a
    # fallback value for it.
    assert "os.environ.get(OTP_HMAC_KEY_ENV)" in source
    assert "os.environ.get(OTP_HMAC_KEY_ENV," not in source


def test_generated_codes_are_six_digits() -> None:
    for _ in range(50):
        code = generate_code()
        assert len(code) == CODE_DIGITS
        assert code.isdigit()


def test_generated_codes_are_not_predictable() -> None:
    # A `random`-seeded generator would collide far more often than this
    # over 200 draws, and a predicted code defeats every control
    # downstream of it.
    assert len({generate_code() for _ in range(200)}) > 150


def test_refresh_tokens_are_stored_hashed() -> None:
    token = generate_refresh_token()
    assert hash_refresh_token(token) != token


def test_refresh_token_digests_are_also_keyed() -> None:
    token = generate_refresh_token()
    unkeyed = hashlib.sha256(token.encode()).hexdigest()
    assert hash_refresh_token(token) != unkeyed


def test_generated_refresh_tokens_are_unique() -> None:
    assert len({generate_refresh_token() for _ in range(100)}) == 100
