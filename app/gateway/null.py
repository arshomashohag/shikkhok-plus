"""The null adapter, and it is the DEFAULT.

**BulkSMSBD has no sandbox**, so the practice that non-production
environments hold test credentials cannot hold as written -- the
mechanism it names does not exist. The property it protects is preserved
by a different one: every non-production environment runs this adapter,
which records the intended send, returns ``SENT``, and makes no network
call. A staging run therefore still cannot spend money and cannot message
a real person [BR5.4].

**Selection is explicit, and the default is this adapter.** A missing or
misspelt setting therefore fails *toward not sending* rather than toward
spending real money and messaging a stranger.
"""

from __future__ import annotations

import logging
import os
from typing import Final

from app.gateway.sms import Outcome, SendResult, SmsGateway

__all__ = ["ADAPTER_ENV", "NullGateway", "build_gateway"]

_log = logging.getLogger(__name__)

#: Names the variable that selects the real adapter. Anything other than
#: the exact sentinel below yields the null adapter.
ADAPTER_ENV: Final = "SHIKKHOKPLUS_SMS_ADAPTER"

#: The one value that selects the real, money-spending adapter.
REAL_ADAPTER_SENTINEL: Final = "bulksmsbd"


class NullGateway:
    """Records the intended send and makes no network call.

    :ivar sent: Every send attempted, for a test or a staging check
    """

    def __init__(self) -> None:
        """Start with an empty record.

        :return: None
        """
        self.sent: list[tuple[str, str]] = []

    def send(self, number: str, message: str, correlation_id: str) -> SendResult:
        """Record an intended send without making one.

        The body is held in memory for a test to assert on but is never
        logged: it carries the number and the code together [BR6.2].

        :param number: The destination number
        :param message: The rendered body
        :param correlation_id: Ties the log line to a request
        :return: Always ``SENT``
        """
        self.sent.append((number, message))
        _log.info(
            "sms send (null adapter)",
            extra={
                "purpose": "otp",
                "outcome": Outcome.SENT.value,
                "correlation_id": correlation_id,
            },
        )
        return SendResult(outcome=Outcome.SENT)


def build_gateway() -> SmsGateway:
    """Select an adapter, defaulting to the one that cannot spend money.

    :return: The configured gateway
    :raises RuntimeError: The real adapter is selected but unconfigured
    """
    if os.environ.get(ADAPTER_ENV) != REAL_ADAPTER_SENTINEL:
        return NullGateway()

    from app.gateway.bulksmsbd import BulkSmsBdGateway

    base_url = os.environ.get("SHIKKHOKPLUS_SMS_BASE_URL")
    api_key = os.environ.get("SHIKKHOKPLUS_SMS_API_KEY")
    sender_id = os.environ.get("SHIKKHOKPLUS_SMS_SENDER_ID")

    if not (base_url and api_key and sender_id):
        raise RuntimeError(
            "the real SMS adapter was selected but is not fully "
            "configured. Refusing to start rather than falling back, "
            "because a silent fallback either spends money unexpectedly "
            "or stops sending without anyone noticing."
        )

    return BulkSmsBdGateway(base_url=base_url, api_key=api_key, sender_id=sender_id)
