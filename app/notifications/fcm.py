"""The push adapter: best-effort, post-commit, and never silent.

**Delivery never fails the operation that triggered it** [BR7.2,
FR10.2]. A push failure rolling back a recorded payment verification
would be strictly worse than no push at all, so dispatch happens
**after** the transaction commits, outside it -- a push for a write that
then rolled back is worse than none.

**The exception covers not SURFACING the failure; it does not cover
failing to record it.** Best-effort FCM is this project's one stated
exception to "silent failures are not acceptable", and the exception is
narrow: the caller writes a ``ReminderEvent`` row carrying the outcome
whatever happens, which is the whole reason a reminder is an event
rather than a boolean.

**``UNREGISTERED`` is not an error** [NFR19.22]. It is the
token-lifecycle signal: the app was uninstalled or the token rotated,
and the right response is to delete the stored token. Treating it as a
failure is how a dead-token table grows for ever, and it is the specific
divergence OQ-4 names as the cost of two adapters.

**No device or advertising identifier, ever** [NFR11.2, TC-3, D-37]. An
FCM registration token is not one: it is a per-install credential for a
delivery channel, rotated by the system and revocable, and it names no
hardware. The distinction is the reason this adapter is permitted at all
on a Families-track app.

**No retry queue in V1** [NFR19.23]. A reminder is re-sendable by a
person; a queue would be a durability mechanism for the least durable
thing in the product.
"""

from __future__ import annotations

import enum
import logging
import os
from dataclasses import dataclass
from typing import Final, Protocol

__all__ = [
    "DeliveryOutcome",
    "NullPushAdapter",
    "PushAdapter",
    "PushMessage",
    "PushResult",
    "build_push_adapter",
]

_log = logging.getLogger(__name__)

#: Selects the real adapter. Anything else gets the one that makes no
#: network call, on the SMS gateway's reasoning: the default must be the
#: adapter that cannot reach a real person's device.
ADAPTER_ENV: Final = "SHIKKHOKPLUS_PUSH_ADAPTER"

#: The one value that selects the real adapter.
REAL_ADAPTER_SENTINEL: Final = "fcm"


class DeliveryOutcome(enum.Enum):
    """What happened to one push attempt.

    ``UNREGISTERED`` is a first-class outcome rather than a failure
    [NFR19.22]. The send did not succeed, but the reason is that the
    token is dead -- which calls for deleting it, not for retrying or
    alerting.
    """

    SENT = "SENT"
    FAILED = "FAILED"
    UNREGISTERED = "UNREGISTERED"


@dataclass(frozen=True, slots=True)
class PushMessage:
    """What to send.

    **Carries message KEYS and data, never rendered English** [TC-15,
    D-43]. A server-authored English string cannot be localized, and in
    a Bangla-first product it guarantees untranslated English on a
    teacher's lock screen. The client renders the key.

    :ivar title_key: Names a client string resource for the title
    :ivar body_key: Names a client string resource for the body
    :ivar data: Values the client substitutes, rendered not interpreted
    """

    title_key: str
    body_key: str
    data: dict[str, str]


@dataclass(frozen=True, slots=True)
class PushResult:
    """The outcome of one attempt.

    Carries no provider payload. The SMS gateway's ``error_message``
    echoes its API key back in plaintext and is therefore never stored;
    the same discipline applies here by default rather than after
    somebody checks.

    :ivar outcome: What happened
    """

    outcome: DeliveryOutcome


class PushAdapter(Protocol):
    """What every push adapter must provide.

    A protocol rather than a base class, so the null adapter is not a
    subclass of the real one -- which would make "accidentally using the
    real adapter" a one-word change.
    """

    def send(self, token: str, message: PushMessage, correlation_id: str) -> PushResult:
        """Attempt one push.

        :param token: The device registration token
        :param message: What to send
        :param correlation_id: Ties the log line to a request
        :return: The outcome
        """
        ...


class NullPushAdapter:
    """Records the intended push and makes no network call.

    :ivar sent: Every push attempted, for a test or a staging check
    """

    def __init__(self) -> None:
        """Start with an empty record."""
        self.sent: list[tuple[str, PushMessage]] = []

    def send(self, token: str, message: PushMessage, correlation_id: str) -> PushResult:
        """Record an intended push without making one.

        The token is held in memory for a test to assert on and is
        never logged: it is a per-install credential, and a log store
        is a wider audience than a delivery channel needs.

        :param token: The device registration token
        :param message: What to send
        :param correlation_id: Ties the log line to a request
        :return: Always ``SENT``
        """
        self.sent.append((token, message))
        _log.info(
            "push send (null adapter)",
            extra={
                "outcome": DeliveryOutcome.SENT.value,
                "correlation_id": correlation_id,
            },
        )
        return PushResult(outcome=DeliveryOutcome.SENT)


def build_push_adapter() -> PushAdapter:
    """Select an adapter, defaulting to the one that reaches nobody.

    The real adapter is not implemented in V1: no Firebase project is
    provisioned and no credential exists, so selecting it refuses at
    startup rather than silently falling back. **Refusing beats falling
    back**: a product that believes it is sending reminders and is not
    is the failure this whole design is arranged around, and it is
    exactly the shape the SMS gateway already refuses.

    :return: The configured adapter
    :raises RuntimeError: The real adapter was selected and none exists
    """
    if os.environ.get(ADAPTER_ENV) != REAL_ADAPTER_SENTINEL:
        return NullPushAdapter()

    raise RuntimeError(
        "the real push adapter was selected and none is built. V1 ships "
        "the null adapter; a Firebase project, a service-account "
        "credential and a token table arrive with the Unit that needs "
        "real delivery. Refusing to start rather than falling back, "
        "because a product that believes it is sending reminders and is "
        "not is the failure this design exists to prevent."
    )
