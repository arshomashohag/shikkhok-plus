"""Authenticator codes against RFC 6238's own published test vectors.

The vectors are the specification's, for HMAC-SHA1 with the ASCII key
``12345678901234567890``; the eight-digit values in Appendix B truncate
to these six digits. Written before trusting the implementation with an
administrator's sign-in: a wrong answer here is an authentication error.
"""

from __future__ import annotations

import base64
from urllib.parse import parse_qs, urlparse

import pytest

from app.auth import totp

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode().rstrip("=")


@pytest.mark.parametrize(
    ("unix_time", "expected"),
    [
        (59, "287082"),
        (1111111109, "081804"),
        (1111111111, "050471"),
        (1234567890, "005924"),
        (2000000000, "279037"),
        (20000000000, "353130"),
    ],
)
def test_codes_match_the_rfc_vectors(unix_time: int, expected: str) -> None:
    """Each published time yields the published code.

    :param unix_time: The RFC's time value
    :param expected: Its six-digit code
    :return: None
    """
    assert totp.code_at(RFC_SECRET, unix_time // totp.STEP_SECONDS) == expected


def test_a_code_is_accepted_one_step_either_side() -> None:
    """A phone clock thirty seconds out still signs in; ninety does not.

    :return: None
    """
    now = 1234567890.0
    step = int(now // 30)
    for drift in (-1, 0, 1):
        code = totp.code_at(RFC_SECRET, step + drift)
        assert totp.matching_step(RFC_SECRET, code, None, now=now) == step + drift
    far = totp.code_at(RFC_SECRET, step + 3)
    assert totp.matching_step(RFC_SECRET, far, None, now=now) is None


def test_a_used_step_and_older_ones_are_refused() -> None:
    """The same code twice, or the previous step's code, is a replay.

    :return: None
    """
    now = 1234567890.0
    step = int(now // 30)
    current = totp.code_at(RFC_SECRET, step)
    previous = totp.code_at(RFC_SECRET, step - 1)
    assert totp.matching_step(RFC_SECRET, current, step, now=now) is None
    assert totp.matching_step(RFC_SECRET, previous, step, now=now) is None
    assert totp.matching_step(RFC_SECRET, previous, step - 2, now=now) == step - 1


@pytest.mark.parametrize("typed", ["", "12345", "1234567", "abcdef", "12 34 5x"])
def test_malformed_codes_never_match(typed: str) -> None:
    """Anything but six digits is refused before any comparison.

    :param typed: What was typed
    :return: None
    """
    assert totp.matching_step(RFC_SECRET, typed, None, now=59.0) is None


def test_spaces_inside_a_code_are_tolerated() -> None:
    """``287 082`` is how some apps display the code.

    :return: None
    """
    assert totp.matching_step(RFC_SECRET, "287 082", None, now=59.0) == 1


def test_new_secrets_are_160_bit_and_distinct() -> None:
    """Twenty random bytes, base32 without padding, never repeated.

    :return: None
    """
    secrets = {totp.new_secret() for _ in range(50)}
    assert len(secrets) == 50
    for secret in secrets:
        assert len(secret) == 32
        assert "=" not in secret
        assert len(base64.b32decode(secret)) == 20


def test_the_uri_carries_the_standard_parameters() -> None:
    """What every authenticator app expects, and the issuer twice.

    :return: None
    """
    uri = totp.otpauth_uri(RFC_SECRET, "admin-4567", "ShikkhokPlus Admin")
    parsed = urlparse(uri)
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert parsed.scheme == "otpauth"
    assert parsed.netloc == "totp"
    assert parsed.path == "/ShikkhokPlus%20Admin%3Aadmin-4567"
    assert query == {
        "secret": RFC_SECRET,
        "issuer": "ShikkhokPlus Admin",
        "algorithm": "SHA1",
        "digits": "6",
        "period": "30",
    }
