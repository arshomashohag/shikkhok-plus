"""The one place a request's per-IP bucket is decided [PA-SEC-2].

Every per-IP limit -- sign-in, signup, deletion -- counts against the
value :func:`client_prefix` returns, so the three cannot disagree about
who a caller is.

**Where the address comes from is a deployment fact, so it is a
setting.** Behind the production proxy chain the peer uvicorn sees is
nginx, and the only address worth counting is the viewer address
CloudFront verified. The proxy overwrites one named request header with
it, and :data:`TRUSTED_CLIENT_IP_HEADER_ENV` names that header. Reading
``X-Forwarded-For`` instead -- which uvicorn does when told to trust
every forwarder -- lets the caller choose their own bucket by sending a
different value per request, which turns the per-IP limit off.

**The header contract**: one bare IPv4 or IPv6 address, no port, no
brackets, no list. The proxy *overwrites* the header rather than
appending to it, so a caller-supplied value never survives. Anything
else is unparsable here and lands in the fallback bucket -- which is
loud in the right direction: everyone shares ten requests an hour, so a
broken proxy config is noticed on the first busy hour rather than
silently granting every caller a bucket of their own.

**With the setting unset**, the peer address is used. That is correct
for local work and the test client, and wrong behind a proxy -- which is
why a production process refuses to start without the setting (see
:mod:`app.config`).

**Prefixes, not addresses**: IPv4 to its /24 and IPv6 to its /64. A
prefix keeps one mobile NAT from becoming a per-user counter, and keeps
the counter from being a record of who called from where. The IPv6
width is the one that matters: a /64 is what a single subscriber is
handed, so counting whole IPv6 addresses gave each caller 2**64 buckets.
"""

from __future__ import annotations

import ipaddress
import os
from typing import Final

from starlette.requests import Request

__all__ = [
    "FALLBACK_BUCKET",
    "TRUSTED_CLIENT_IP_HEADER_ENV",
    "address_prefix",
    "client_address",
    "client_prefix",
]

#: Names the request header the proxy overwrites with the verified
#: client address. Unset by default; production requires it.
TRUSTED_CLIENT_IP_HEADER_ENV: Final = "SHIKKHOKPLUS_TRUSTED_CLIENT_IP_HEADER"

#: The single bucket every missing or unparsable address shares.
#:
#: **One bucket, never the raw string.** Counting an unparsable value as
#: its own scope gives a caller who can vary it a fresh bucket per
#: request. Not a network spelling either, so no real address can land
#: in it.
FALLBACK_BUCKET: Final = "unparsable"

_IPV4_PREFIX: Final = 24
_IPV6_PREFIX: Final = 64


def address_prefix(raw: str | None) -> str:
    """Reduce one address to the prefix its per-IP limits count against.

    :param raw: The address as received, or None if there was none
    :return: The network in CIDR form, or :data:`FALLBACK_BUCKET`
    """
    if not raw:
        return FALLBACK_BUCKET
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return FALLBACK_BUCKET

    # A dual-stack listener reports an IPv4 caller as ::ffff:a.b.c.d.
    # Prefixed as IPv6, all of IPv4 would share ::ffff:0:0/64 -- one
    # bucket for every IPv4 caller on the internet.
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped

    width = _IPV4_PREFIX if isinstance(address, ipaddress.IPv4Address) else _IPV6_PREFIX
    return str(ipaddress.ip_network(f"{address}/{width}", strict=False))


def client_prefix(request: Request) -> str:
    """Return the per-IP bucket for this request.

    With the trusted header configured, **only** that header is read: a
    missing value is the fallback bucket, never the peer address,
    because falling back to the peer hands the bucket back to whatever
    set the peer -- the spoofable forwarding header this setting exists
    to take out of the decision.

    :param request: The incoming request
    :return: The prefix to count against
    """
    header = os.environ.get(TRUSTED_CLIENT_IP_HEADER_ENV, "").strip()
    if header:
        return address_prefix(request.headers.get(header))
    return address_prefix(request.client.host if request.client else None)


def client_address(request: Request) -> str | None:
    """Return the verified client address itself, not its bucket.

    The same trust rule as :func:`client_prefix`: with the trusted header
    configured only that header is read, so a caller cannot choose the
    address an allowlist is checked against.

    :param request: The incoming request
    :return: The address, or None when none was supplied
    """
    header = os.environ.get(TRUSTED_CLIENT_IP_HEADER_ENV, "").strip()
    if header:
        value = request.headers.get(header)
        return value.strip() if value else None
    return request.client.host if request.client else None
