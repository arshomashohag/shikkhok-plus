"""Fixtures for the moderation suite.

Administration fixtures are re-exported rather than rebuilt: the admin routes
here sit behind the same edge secret, allowlist and admin token as the rest.
"""

from __future__ import annotations

from tests.admin.conftest import (
    ADMIN_NETWORK_ADDRESS,
    EDGE,
    EDGE_SECRET,
    account_factory,
    admin_edge,
    admin_headers,
    people,
)

__all__ = [
    "ADMIN_NETWORK_ADDRESS",
    "EDGE",
    "EDGE_SECRET",
    "account_factory",
    "admin_edge",
    "admin_headers",
    "people",
]
