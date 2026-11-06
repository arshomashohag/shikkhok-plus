"""Fixtures for the expense tests, shared with the fee suite.

Imported rather than copied, for the fee suite's own reason: a second
copy of a fixture drifts the moment either suite changes it.
"""

from __future__ import annotations

from tests.fees.conftest import account_factory, teacher

__all__ = ["account_factory", "teacher"]
