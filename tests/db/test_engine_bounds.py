"""Every engine is sized and carries server-side timeouts [audit C-18].

Defaults were 5+10 connections per worker with a 30-second checkout wait
and no statement, lock or idle-transaction bound: a burst hung for 30
seconds and then failed, and a runaway query outlived the proxy's own
timeout while holding a connection.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.db.session import STATEMENT_TIMEOUT_ENV, build_engine


def test_the_engine_bounds_statements_locks_and_idle_transactions(
    migrated_url: str,
) -> None:
    """The settings are in force on a fresh connection.

    :param migrated_url: A URL for the test database
    :return: None
    """
    engine = build_engine(migrated_url)
    try:
        with engine.connect() as connection:
            settings = {
                name: connection.scalar(sa.text(f"SHOW {name}"))
                for name in (
                    "statement_timeout",
                    "lock_timeout",
                    "idle_in_transaction_session_timeout",
                    "TimeZone",
                )
            }
    finally:
        engine.dispose()

    assert settings == {
        "statement_timeout": "15s",
        "lock_timeout": "5s",
        "idle_in_transaction_session_timeout": "1min",
        "TimeZone": "UTC",
    }
    assert engine.pool.size() == 8  # type: ignore[attr-defined]


def test_a_malformed_setting_is_refused(
    migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A typo fails at startup rather than silently using a default.

    :param migrated_url: A URL for the test database
    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(STATEMENT_TIMEOUT_ENV, "15s")
    with pytest.raises(RuntimeError, match=STATEMENT_TIMEOUT_ENV):
        build_engine(migrated_url)
