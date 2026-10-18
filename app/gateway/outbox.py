"""The staging outbox: a way to read a code that was never texted.

**This exists so a person can sign in on a device before real SMS
credentials exist**, and it is the most dangerous thing in this Unit if
it ever reaches production — it hands an OTP to anyone who asks.

So production impossibility is enforced three ways, each of which alone
would be a convention someone could overlook:

1. :func:`outbox_enabled` is **false unless the environment is exactly
   ``staging`` or ``development``**, read fresh on every call rather
   than captured at import. A process promoted to production by its
   environment variable loses the route immediately, with no rebuild.
2. The route is **not registered at all** when disabled, so there is no
   endpoint to reach — not a 404 handler, an absent route.
3. The startup check **refuses to start a production process** that has
   the outbox forced on, so a misconfiguration fails loudly at boot
   rather than quietly serving codes.

A test asserts each of the three independently, because this is the one
control where "it is obviously fine" is the most expensive possible
assumption.

**Why a table rather than the null gateway's in-memory list.** The
container runs two Uvicorn workers [team.md], so a code recorded by
worker A is invisible to worker B — the same reason the rate-limit
counters are datastore-backed. An in-memory outbox would work in a
single-worker test and fail about half the time on a real host, which
is the failure shape this project has a standing rule about.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.config import ENVIRONMENT_ENV

__all__ = [
    "OUTBOX_FORCE_ENV",
    "OutboxEntry",
    "outbox_enabled",
    "read_outbox",
    "record_outbox",
]

#: Environments where reading a code back is permissible. Production is
#: deliberately absent and no value can add it.
PERMITTED_ENVIRONMENTS: Final[frozenset[str]] = frozenset(
    {"staging", "development", "test"}
)

#: Set to "1" to enable the outbox in a permitted environment. Having to
#: opt in means a staging host that does not need it does not carry it.
OUTBOX_FORCE_ENV: Final = "SHIKKHOKPLUS_STAGING_OUTBOX"

#: How long an entry is readable. Shorter than the OTP's own five-minute
#: expiry, so the outbox never outlives the thing it exposes.
RETENTION = dt.timedelta(minutes=5)


class OutboxEntry:
    """One recorded message.

    :ivar phone: The destination number
    :ivar message: The rendered body, carrying the code
    :ivar recorded_at: When it was recorded
    """

    __slots__ = ("message", "phone", "recorded_at")

    def __init__(self, phone: str, message: str, recorded_at: dt.datetime) -> None:
        """Hold one entry.

        :param phone: The destination number
        :param message: The rendered body
        :param recorded_at: When it was recorded
        """
        self.phone = phone
        self.message = message
        self.recorded_at = recorded_at


def outbox_enabled(environment: str | None = None) -> bool:
    """Report whether the outbox may be used at all.

    **Read fresh on every call**, never captured at import: a process
    whose environment says production must lose this immediately, and a
    module-level constant would hold the value the process started with.

    :param environment: The environment name, or None to read it
    :return: True only in a permitted environment with the flag set
    """
    resolved = environment or os.environ.get(ENVIRONMENT_ENV, "development")
    if resolved not in PERMITTED_ENVIRONMENTS:
        return False
    return os.environ.get(OUTBOX_FORCE_ENV, "") == "1"


def record_outbox(
    session: Session,
    *,
    phone: str,
    message: str,
    correlation_id: str,
) -> None:
    """Record a message that was not sent, when the outbox is enabled.

    A no-op when disabled, so the gateway adapter calls it
    unconditionally and carries no environment branch of its own.

    :param session: The session to write through
    :param phone: The destination number
    :param message: The rendered body
    :param correlation_id: Ties the entry to the issuing request
    :return: None
    """
    if not outbox_enabled():
        return

    session.execute(
        sa.text(
            "INSERT INTO staging_sms_outbox "
            "(id, phone, message, correlation_id, recorded_at) "
            "VALUES (:id, :phone, :message, :correlation_id, :now)"
        ),
        {
            "id": uuid.uuid4(),
            "phone": phone,
            "message": message,
            "correlation_id": correlation_id,
            "now": dt.datetime.now(tz=dt.UTC),
        },
    )


def read_outbox(session: Session, *, phone: str) -> OutboxEntry | None:
    """Read the most recent unexpired message for a number.

    :param session: The session to query through
    :param phone: The destination number
    :return: The entry, or None when there is none within the window
    :raises RuntimeError: The outbox is not enabled in this environment
    """
    if not outbox_enabled():
        # Defence in depth. The route is not registered when disabled,
        # so reaching this is already a programming error -- raising
        # makes it one that stops rather than one that serves a code.
        raise RuntimeError("the staging outbox is not enabled in this environment")

    cutoff = dt.datetime.now(tz=dt.UTC) - RETENTION
    row = session.execute(
        sa.text(
            "SELECT phone, message, recorded_at FROM staging_sms_outbox "
            "WHERE phone = :phone AND recorded_at >= :cutoff "
            "ORDER BY recorded_at DESC LIMIT 1"
        ),
        {"phone": phone, "cutoff": cutoff},
    ).one_or_none()

    if row is None:
        return None
    return OutboxEntry(phone=row[0], message=row[1], recorded_at=row[2])
