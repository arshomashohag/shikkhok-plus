"""Fixtures for the administration suite.

Re-exported from the help suite rather than rebuilt: the administrator
reads the same people and tickets the help centre creates, and a second
copy of the arrangement would drift the moment either changed.
"""

from __future__ import annotations

from tests.help.conftest import account_factory, people

__all__ = ["account_factory", "people"]
