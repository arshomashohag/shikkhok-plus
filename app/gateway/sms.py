"""The gateway contract: one protocol, four outcomes, no retry.

**A send is attempted exactly once, at any layer** [BR5.3]. Automatic
retry is a bug here rather than resilience: it double-charges and
double-messages, and there is no idempotency key and no message id to
deduplicate against — the gateway offers no delivery report at all,
verified against nine probed endpoint names. So ``202`` means "submitted"
and nothing more, permanently, which is what makes :attr:`Outcome.UNKNOWN`
mandatory rather than cautious.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Protocol

__all__ = ["Outcome", "SendResult", "SmsGateway"]


class Outcome(enum.Enum):
    """What happened to one send attempt.

    ``UNKNOWN`` is a first-class outcome, not an error case. A timeout
    may have been delivered, so recording it as ``FAILED`` would be a
    claim the gateway does not support — and would invite exactly the
    retry that double-charges.
    """

    SENT = "SENT"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    BUDGET_REFUSED = "BUDGET_REFUSED"


@dataclass(frozen=True, slots=True)
class SendResult:
    """The outcome of one attempt.

    Carries no provider payload: ``error_message`` **echoes the API key
    back in plaintext**, so it is never stored and never logged [BR6.2].

    :ivar outcome: What happened
    :ivar provider_code: The provider's numeric code, for the operator
    """

    outcome: Outcome
    provider_code: int | None = None


class SmsGateway(Protocol):
    """What every adapter must provide.

    A protocol rather than a base class, so the null adapter is not a
    subclass of the real one -- which would make "accidentally using the
    real adapter" a one-word change.
    """

    def send(self, number: str, message: str, correlation_id: str) -> SendResult:
        """Attempt one send.

        :param number: The destination number
        :param message: The rendered body
        :param correlation_id: Ties the log line to a request
        :return: The outcome
        """
        ...
