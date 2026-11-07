"""Engine and session construction.

**One transaction per request, committed by the endpoint and never by a
repository method**, or a partial money write becomes possible. This
module supplies the session; the endpoint owns its boundary.

The database URL is read from the environment and never hardcoded
[project.md Forbidden]. Connection errors redact it, because a URL carries
the password.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

__all__ = [
    "DATABASE_URL_ENV",
    "MIGRATION_DATABASE_URL_ENV",
    "build_engine",
    "redact_url",
    "session_scope",
]

#: The environment variable naming the database. Never a literal in code.
#: In a deployed environment it connects as the restricted application
#: role, never as the owner [OPS-5].
DATABASE_URL_ENV = "SHIKKHOKPLUS_DATABASE_URL"

#: The OWNER's URL, for the two things the application role must not be
#: able to do: migrate the schema and set its own role's password. Read
#: by ``migrations/env.py`` and ``app.db.commands`` only, never by the
#: request path.
MIGRATION_DATABASE_URL_ENV = "SHIKKHOKPLUS_MIGRATION_DATABASE_URL"


def redact_url(url: str) -> str:
    """Strip the password from a database URL for safe logging.

    A connection failure logs the URL by default in most stacks, and that
    URL carries the password. Redaction here means no caller has to
    remember to do it at the log site.

    :param url: The URL to redact
    :return: The same URL with any password replaced
    """
    parts = urlsplit(url)
    if parts.password is None:
        return url
    host = parts.hostname or ""
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    user = parts.username or ""
    return urlunsplit(
        (parts.scheme, f"{user}:***@{host}", parts.path, parts.query, parts.fragment)
    )


def build_engine(url: str | None = None) -> Engine:
    """Build the engine from the environment.

    ``pool_pre_ping`` is on because a 2 GB single instance drops idle
    connections, and a stale one surfaces as a confusing mid-request
    failure rather than a reconnect.

    :param url: An explicit URL, or None to read the environment
    :return: The configured engine
    :raises RuntimeError: Neither an argument nor the environment names one
    """
    resolved = url or os.environ.get(DATABASE_URL_ENV)
    if not resolved:
        raise RuntimeError(
            f"no database URL: pass one or set {DATABASE_URL_ENV}. "
            "It is never hardcoded."
        )
    return create_engine(
        resolved,
        pool_pre_ping=True,
        future=True,
        # Sized, not defaulted [audit C-18]. Each uvicorn worker owns one
        # pool; a request waiting longer than ``pool_timeout`` for a
        # connection fails fast as a retryable 503 rather than hanging.
        pool_size=_int_env(POOL_SIZE_ENV, 8),
        max_overflow=_int_env(POOL_OVERFLOW_ENV, 4),
        pool_timeout=_int_env(POOL_TIMEOUT_ENV, 10),
        pool_recycle=1800,
        connect_args={
            "connect_timeout": 10,
            # Server-side bounds, so a runaway statement, a queued lock or
            # an abandoned transaction ends in the database rather than
            # outliving the proxy's timeout while holding a connection.
            "options": (
                f"-c statement_timeout={_int_env(STATEMENT_TIMEOUT_ENV, 15000)} "
                f"-c lock_timeout={_int_env(LOCK_TIMEOUT_ENV, 5000)} "
                "-c idle_in_transaction_session_timeout="
                f"{_int_env(IDLE_TIMEOUT_ENV, 60000)} "
                "-c TimeZone=UTC"
            ),
        },
    )


#: Pool and timeout settings, each overridable for one deployment.
POOL_SIZE_ENV: Final = "SHIKKHOKPLUS_DB_POOL_SIZE"
POOL_OVERFLOW_ENV: Final = "SHIKKHOKPLUS_DB_POOL_OVERFLOW"
POOL_TIMEOUT_ENV: Final = "SHIKKHOKPLUS_DB_POOL_TIMEOUT_S"
STATEMENT_TIMEOUT_ENV: Final = "SHIKKHOKPLUS_DB_STATEMENT_TIMEOUT_MS"
LOCK_TIMEOUT_ENV: Final = "SHIKKHOKPLUS_DB_LOCK_TIMEOUT_MS"
IDLE_TIMEOUT_ENV: Final = "SHIKKHOKPLUS_DB_IDLE_IN_TRANSACTION_TIMEOUT_MS"


def _int_env(name: str, default: int) -> int:
    """Read a positive integer setting, or use the default.

    :param name: The environment variable
    :param default: The value when it is unset or empty
    :return: The setting
    :raises RuntimeError: It is set but not a positive integer
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    if not raw.isdigit() or int(raw) <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return int(raw)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Yield a session inside one transaction, committing on clean exit.

    :param engine: The engine to bind the session to
    :return: A context manager yielding the session
    """
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
