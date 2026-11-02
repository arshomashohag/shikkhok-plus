"""Which per-IP bucket a request counts against [PA-SEC-2].

Test-first under the ordering predicate: the bucket for a given address
is knowable from the requirement, and a wrong one is an abuse-control
error -- either a caller who can mint a fresh bucket per request, or a
whole population folded into one bucket that ten requests lock out.

**Three defects these pin, each of which the old helper had**:

* An IPv6 address was its own whole-address bucket, so a caller holding
  a /64 -- which every IPv6 subscriber does -- had 2**64 buckets.
* The address came from uvicorn's proxy headers with every forwarder
  trusted, so ``X-Forwarded-For`` chose the bucket. Behind the trusted
  header that spoof must change nothing.
* An address the helper could not parse fell through to the raw string,
  which is a bucket per spelling. It now falls into ONE shared bucket.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.auth.client_address import (
    FALLBACK_BUCKET,
    TRUSTED_CLIENT_IP_HEADER_ENV,
    address_prefix,
    client_prefix,
)

TRUSTED: str = "X-Client-Address"


def _request(
    client_host: str | None,
    headers: dict[str, str] | None = None,
) -> Request:
    """Build a bare ASGI request with a peer address and headers.

    :param client_host: What uvicorn reports as the peer, or None
    :param headers: Request headers
    :return: The request
    """
    raw = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/auth/otp",
        "headers": raw,
        "client": (client_host, 51234) if client_host is not None else None,
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _no_trusted_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test with the setting unset, as it is by default.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.delenv(TRUSTED_CLIENT_IP_HEADER_ENV, raising=False)


# ---------------------------------------------------------------------------
# Prefixing.
# ---------------------------------------------------------------------------


def test_two_ipv4_addresses_in_one_slash_24_share_a_bucket() -> None:
    assert address_prefix("203.0.113.7") == address_prefix("203.0.113.250")
    assert address_prefix("203.0.113.7") == "203.0.113.0/24"


def test_ipv4_addresses_in_neighbouring_slash_24s_do_not_share() -> None:
    assert address_prefix("203.0.113.7") != address_prefix("203.0.114.7")


def test_two_ipv6_addresses_in_one_slash_64_share_a_bucket() -> None:
    # The whole of the old defect: these were two buckets, and a
    # subscriber's /64 holds 2**64 of them.
    first = address_prefix("2001:db8:1:2::1")
    second = address_prefix("2001:db8:1:2:ffff:ffff:ffff:ffff")
    assert first == second == "2001:db8:1:2::/64"


def test_ipv6_addresses_in_neighbouring_slash_64s_do_not_share() -> None:
    assert address_prefix("2001:db8:1:2::1") != address_prefix("2001:db8:1:3::1")


def test_an_ipv4_mapped_ipv6_address_counts_as_its_ipv4_slash_24() -> None:
    # A dual-stack listener reports an IPv4 caller as ::ffff:a.b.c.d.
    # Treated as IPv6, every IPv4 internet address would share the
    # one /64 ::ffff:0:0/64 -- a single bucket for all of IPv4.
    assert address_prefix("::ffff:203.0.113.7") == "203.0.113.0/24"
    assert address_prefix("::ffff:203.0.113.7") == address_prefix("203.0.113.9")


@pytest.mark.parametrize(
    "raw",
    [None, "", "testclient", "203.0.113", "203.0.113.7:443", "[2001:db8::1]", "a, b"],
)
def test_an_unparsable_address_falls_into_the_one_shared_bucket(
    raw: str | None,
) -> None:
    # One bucket, not one per spelling: if each unparsable value were
    # its own scope, a caller able to vary it would bypass the limit.
    assert address_prefix(raw) == FALLBACK_BUCKET


def test_the_fallback_bucket_cannot_be_reached_by_a_real_address() -> None:
    # Otherwise a genuine /24 would silently share the junk bucket.
    for raw in ("192.0.2.1", "255.255.255.255", "::1", "fe80::1"):
        assert address_prefix(raw) != FALLBACK_BUCKET


# ---------------------------------------------------------------------------
# Which address is read.
# ---------------------------------------------------------------------------


def test_with_the_setting_unset_the_peer_address_is_used() -> None:
    request = _request("198.51.100.20", {TRUSTED: "203.0.113.7"})
    assert client_prefix(request) == "198.51.100.0/24"


def test_with_the_setting_unset_a_missing_peer_is_the_fallback() -> None:
    assert client_prefix(_request(None)) == FALLBACK_BUCKET


def test_with_the_setting_on_the_trusted_header_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TRUSTED_CLIENT_IP_HEADER_ENV, TRUSTED)
    request = _request("10.0.0.5", {TRUSTED: "203.0.113.7"})
    assert client_prefix(request) == "203.0.113.0/24"


def test_with_the_setting_on_a_spoofed_forwarded_for_changes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # uvicorn's proxy-header middleware rewrites the PEER from
    # X-Forwarded-For, so a spoof shows up as a different client host.
    # Behind the trusted header neither may move the bucket.
    monkeypatch.setenv(TRUSTED_CLIENT_IP_HEADER_ENV, TRUSTED)
    honest = _request("10.0.0.5", {TRUSTED: "203.0.113.7"})
    spoofed = _request(
        "192.0.2.99",
        {TRUSTED: "203.0.113.7", "X-Forwarded-For": "192.0.2.99"},
    )
    assert client_prefix(honest) == client_prefix(spoofed)


def test_with_the_setting_on_a_missing_header_is_the_fallback_not_the_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Falling back to the peer would hand the bucket back to whatever
    # set the peer -- the spoofable header this setting exists to stop.
    monkeypatch.setenv(TRUSTED_CLIENT_IP_HEADER_ENV, TRUSTED)
    assert client_prefix(_request("203.0.113.7")) == FALLBACK_BUCKET


def test_with_the_setting_on_a_garbage_header_is_the_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TRUSTED_CLIENT_IP_HEADER_ENV, TRUSTED)
    request = _request("203.0.113.7", {TRUSTED: "not-an-address"})
    assert client_prefix(request) == FALLBACK_BUCKET


def test_the_header_name_is_matched_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TRUSTED_CLIENT_IP_HEADER_ENV, "x-client-address")
    request = _request("10.0.0.5", {"X-CLIENT-ADDRESS": "2001:db8:1:2::9"})
    assert client_prefix(request) == "2001:db8:1:2::/64"
