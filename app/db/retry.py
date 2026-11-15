"""A bounded re-run of one unit of work on a serialization failure or deadlock.

**The lock order is the control; this is the backstop** [U2: NFR4.2,
NFR4.3]. U2's paths take advisory keys before row locks and row locks in
one table order, so two U2 paths cannot wait on each other in a cycle.
Account deletion still runs legacy statements whose order U2 does not
own, and PostgreSQL resolves a cycle there by aborting one side with
``40P01``. A ``40001`` serialization failure is the same kind of event.
Both roll the whole transaction back, so the unit of work left nothing
durable, and re-running it from its first statement is safe -- as long as
nothing left the process before its commit, which is why only units that
send nothing before committing are wrapped.

**At most two re-runs** (three attempts), with jittered backoff of 10 to
50 ms and then 50 to 150 ms; after that the request fails as a
:class:`~app.errors.TransientError`, ``retryable: true``, as any other
transient database failure does. ``55P03`` (``lock_timeout``) is **not**
retried: the engine already waited five seconds, and waiting again only
lengthens the request [NFR4.4].

Standard library only: a retry library would be a new dependency for a
dozen lines [tech-stack-decisions].
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import Final

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.errors import TransientError

__all__ = ["RETRIED_SQLSTATES", "run_with_retry", "sqlstate_of"]

_log = logging.getLogger(__name__)

#: Serialization failure and deadlock detected.
RETRIED_SQLSTATES: Final = frozenset({"40001", "40P01"})

#: The backoff before each re-run, in seconds: (low, high) per retry.
_BACKOFF: Final = ((0.010, 0.050), (0.050, 0.150))


def sqlstate_of(error: BaseException) -> str | None:
    """Return the SQLSTATE a driver error carries, if any.

    :param error: The wrapped driver error
    :return: The five-character state, or None
    """
    state = getattr(getattr(error, "orig", None), "sqlstate", None)
    return state if isinstance(state, str) else None


def run_with_retry[T](
    session: Session,
    unit: Callable[[], T],
    *,
    correlation_id: str | None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run a unit of work, re-running it on ``40001`` and ``40P01``.

    The unit must be the WHOLE transaction: it starts from its first
    statement and ends with its own commit, and it sends nothing outside
    the process before that commit. Each failed attempt is rolled back
    before the next starts, and each re-run is logged once with the
    SQLSTATE and the attempt number, never a statement or a value
    [NFR4.10].

    :param session: The request's session
    :param unit: The unit of work
    :param correlation_id: Ties the log lines to the request
    :param sleep: How to wait between attempts; injectable for tests
    :return: What the unit returned
    :raises TransientError: Every attempt failed with a retried state
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return unit()
        except OperationalError as error:
            state = sqlstate_of(error)
            if state not in RETRIED_SQLSTATES:
                raise
            session.rollback()
            exhausted = attempt > len(_BACKOFF)
            _log.warning(
                "database retry",
                extra={
                    "event": "db_retry",
                    "outcome": "exhausted" if exhausted else "retrying",
                    "sqlstate": state,
                    "purpose": f"attempt_{attempt}",
                    "correlation_id": correlation_id,
                },
            )
            if exhausted:
                raise TransientError(
                    code="SERVICE_UNAVAILABLE",
                    message_key="error.temporarily_unavailable",
                ) from error
            low, high = _BACKOFF[attempt - 1]
            sleep(random.uniform(low, high))  # noqa: S311 -- jitter, not a secret
