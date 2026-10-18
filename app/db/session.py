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
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

__all__ = ["DATABASE_URL_ENV", "build_engine", "redact_url", "session_scope"]

#: The environment variable naming the database. Never a literal in code.
DATABASE_URL_ENV = "SHIKKHOKPLUS_DATABASE_URL"


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
    return create_engine(resolved, pool_pre_ping=True, future=True)


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
