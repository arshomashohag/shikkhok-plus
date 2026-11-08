"""The staging outbox: a way to read a code that was never texted.

**This exists so a person can sign in on a device before real SMS
credentials exist**, and it is the most dangerous thing in this Unit if
it ever reaches production — it hands an OTP to anyone who asks.

So production impossibility is enforced three ways, each of which alone
would be a convention someone could overlook:

1. :func:`outbox_enabled` is **false unless the environment is
   explicitly and exactly ``staging``, ``development`` or ``test``**,
   read fresh on every call rather than captured at import. A process
   promoted to production by its environment variable loses the route
   immediately, with no rebuild. An UNSET name permits nothing: unlike
   the startup checks, which read unset as development, the outbox
   requires the name to be stated [C-19].
2. The route is **not registered at all** when disabled, so there is no
   endpoint to reach — not a 404 handler, an absent route.
3. The startup check **refuses to start a production process** that has
   the outbox forced on, so a misconfiguration fails loudly at boot
   rather than quietly serving codes.

A test asserts each of the three independently, because this is the one
control where "it is obviously fine" is the most expensive possible
assumption.

**And on staging it serves only the operator's own numbers** [C-19].
Staging is reachable from the internet through CloudFront, so an outbox
that answered for ANY number let anyone who knew a real person's phone
number sign in as them there. On ``staging`` the outbox is therefore off
unless ``SHIKKHOKPLUS_STAGING_OUTBOX_NUMBERS`` names the numbers it may
record and read back, and every other number is neither recorded nor
readable -- the reader answers exactly as for a number with no message,
so the allowlist is not an oracle either. In ``development`` and
``test`` the list is optional and, when set, enforced the same way.

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
    "OUTBOX_NUMBERS_ENV",
    "OutboxEntry",
    "outbox_enabled",
    "outbox_number_permitted",
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

#: The numbers the outbox may record and read back: E.164, separated by
#: commas or whitespace. Required on staging; optional elsewhere.
OUTBOX_NUMBERS_ENV: Final = "SHIKKHOKPLUS_STAGING_OUTBOX_NUMBERS"

#: The one permitted environment that is reachable from the internet,
#: and so the one where the allowlist is mandatory.
ALLOWLIST_REQUIRED_ENVIRONMENTS: Final[frozenset[str]] = frozenset({"staging"})

#: How long an entry is readable. Shorter than the OTP's own five-minute
#: expiry, so the outbox never outlives the thing it exposes.
RETENTION = dt.timedelta(minutes=5)


class OutboxEntry:
    """One recorded message.

    :ivar destination: The number or address it was for
    :ivar message: The rendered body, carrying the code
    :ivar recorded_at: When it was recorded
    """

    __slots__ = ("destination", "message", "recorded_at")

    def __init__(
        self, destination: str, message: str, recorded_at: dt.datetime
    ) -> None:
        """Hold one entry.

        :param destination: The number or address it was for
        :param message: The rendered body
        :param recorded_at: When it was recorded
        """
        self.destination = destination
        self.message = message
        self.recorded_at = recorded_at


def _allowlist() -> frozenset[str]:
    """Read the operator numbers the outbox may serve.

    Operator email addresses may be listed too [0032], compared
    lowercased as the account stores them.

    :return: The numbers and addresses, empty when unset or blank
    """
    raw = os.environ.get(OUTBOX_NUMBERS_ENV, "")
    return frozenset(
        entry.lower() if "@" in entry else entry
        for entry in raw.replace(",", " ").split()
    )


def outbox_enabled(environment: str | None = None) -> bool:
    """Report whether the outbox may be used at all.

    **Read fresh on every call**, never captured at import: a process
    whose environment says production must lose this immediately, and a
    module-level constant would hold the value the process started with.

    :param environment: The environment name, or None to read it
    :return: True only in an explicitly named permitted environment with
        the flag set and, on staging, an allowlist of operator numbers
    """
    resolved = environment or os.environ.get(ENVIRONMENT_ENV, "")
    if resolved not in PERMITTED_ENVIRONMENTS:
        return False
    if os.environ.get(OUTBOX_FORCE_ENV, "") != "1":
        return False
    return resolved not in ALLOWLIST_REQUIRED_ENVIRONMENTS or bool(_allowlist())


def outbox_number_permitted(destination: str) -> bool:
    """Report whether the outbox may record or read back this destination.

    :param destination: The canonical number or address
    :return: True when no allowlist applies or it is on the list
    """
    allowed = _allowlist()
    return not allowed or destination in allowed


def record_outbox(
    session: Session,
    *,
    phone: str | None = None,
    email: str | None = None,
    message: str,
    correlation_id: str,
) -> None:
    """Record a message that was not sent, when the outbox is enabled.

    A no-op when disabled, so the gateway adapter calls it
    unconditionally and carries no environment branch of its own.

    :param session: The session to write through
    :param phone: The destination number, or None for an email
    :param email: The destination address [0032], or None for an SMS
    :param message: The rendered body
    :param correlation_id: Ties the entry to the issuing request
    :return: None
    """
    destination = phone or email or ""
    if not outbox_enabled() or not outbox_number_permitted(destination):
        return

    session.execute(
        sa.text(
            "INSERT INTO staging_sms_outbox "
            "(id, phone, email, message, correlation_id, recorded_at) "
            "VALUES (:id, :phone, :email, :message, :correlation_id, :now)"
        ),
        {
            "id": uuid.uuid4(),
            "phone": phone,
            "email": None if phone else email,
            "message": message,
            "correlation_id": correlation_id,
            "now": dt.datetime.now(tz=dt.UTC),
        },
    )


def read_outbox(
    session: Session, *, phone: str | None = None, email: str | None = None
) -> OutboxEntry | None:
    """Read the most recent unexpired message for a number or an address.

    :param session: The session to query through
    :param phone: The destination number, or None
    :param email: The destination address, or None
    :return: The entry, or None when there is none within the window
    :raises RuntimeError: The outbox is not enabled in this environment
    """
    if not outbox_enabled():
        # Defence in depth. The route is not registered when disabled,
        # so reaching this is already a programming error -- raising
        # makes it one that stops rather than one that serves a code.
        raise RuntimeError("the staging outbox is not enabled in this environment")
    destination = phone or email or ""
    if not destination or not outbox_number_permitted(destination):
        # The same answer as a number with no message, so the allowlist
        # does not say which numbers are on it.
        return None

    cutoff = dt.datetime.now(tz=dt.UTC) - RETENTION
    where = "phone = :value" if phone else "email = :value"
    row = session.execute(
        sa.text(
            "SELECT message, recorded_at FROM staging_sms_outbox "  # noqa: S608 -- fixed column
            f"WHERE {where} AND recorded_at >= :cutoff "
            "ORDER BY recorded_at DESC LIMIT 1"
        ),
        {"value": destination, "cutoff": cutoff},
    ).one_or_none()

    if row is None:
        return None
    return OutboxEntry(destination=destination, message=row[0], recorded_at=row[1])
