"""Fixtures for the notification suite.

Re-exported from the fee suite rather than rebuilt. A reminder is about
a seat and a period, so the arrangement is the same one D3's fee tests
need, and a second copy would drift the moment either changed.
"""

from __future__ import annotations

from tests.fees.conftest import account_factory, seat, teacher

__all__ = ["account_factory", "seat", "teacher"]
