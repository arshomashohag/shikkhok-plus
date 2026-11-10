"""Sending a code by email: the protocol, the null adapter and the selector.

The email twin of :mod:`app.gateway.sms` and :mod:`app.gateway.null`,
on their terms [0032]:

* **A protocol, not a base class**, so the null adapter is not a
  subclass of the real one.
* **The null adapter is the default.** Anything other than the exact
  sentinel ``ses`` selects it, so a local run or a test never mails
  anyone; the production startup check refuses a process without the
  real one (:mod:`app.config`).
* **One attempt, no retry.** A timeout may have been delivered, so it is
  ``UNKNOWN`` and the person asks for a new code, exactly as for SMS.
* **The body is never logged**: it carries the address and the code
  together.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Final, Protocol

from app.gateway.sms import Outcome, SendResult

__all__ = [
    "EMAIL_ADAPTER_ENV",
    "REAL_EMAIL_ADAPTER_SENTINEL",
    "EmailGateway",
    "EmailMessage",
    "NullEmailGateway",
    "build_email_gateway",
    "email_gateway_configured",
]

_log = logging.getLogger(__name__)

#: Selects the adapter.
EMAIL_ADAPTER_ENV: Final = "SHIKKHOKPLUS_EMAIL_ADAPTER"

#: The one value that selects the real adapter.
REAL_EMAIL_ADAPTER_SENTINEL: Final = "ses"

#: The settings the real adapter cannot run without.
_REQUIRED: Final = (
    "SHIKKHOKPLUS_SES_SMTP_HOST",
    "SHIKKHOKPLUS_SES_SMTP_USERNAME",
    "SHIKKHOKPLUS_SES_SMTP_PASSWORD",
    "SHIKKHOKPLUS_EMAIL_FROM",
)


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """One rendered email.

    :ivar subject: The subject line
    :ivar text: The plain-text body, always sent, and what a client that
        does not render HTML shows
    :ivar html: The HTML alternative, or None for a text-only email
    """

    subject: str
    text: str
    html: str | None = None


class EmailGateway(Protocol):
    """What every email adapter must provide."""

    def send(
        self, address: str, message: EmailMessage, correlation_id: str
    ) -> SendResult:
        """Attempt one send.

        :param address: The destination address
        :param message: The rendered email
        :param correlation_id: Ties the log line to a request
        :return: The outcome
        """
        ...


class NullEmailGateway:
    """Records the intended send and makes no network call.

    :ivar sent: Every send attempted, for a test to assert on
    """

    def __init__(self) -> None:
        """Start with an empty record.

        :return: None
        """
        self.sent: list[tuple[str, EmailMessage]] = []

    def send(
        self, address: str, message: EmailMessage, correlation_id: str
    ) -> SendResult:
        """Record an intended send without making one.

        :param address: The destination address
        :param message: The rendered email
        :param correlation_id: Ties the log line to a request
        :return: Always ``SENT``
        """
        self.sent.append((address, message))
        _log.info(
            "email send (null adapter)",
            extra={"outcome": Outcome.SENT.value, "correlation_id": correlation_id},
        )
        return SendResult(outcome=Outcome.SENT)


def email_gateway_configured() -> bool:
    """Report whether the real adapter is selected and fully configured.

    :return: True when ``ses`` is selected and every setting is present
    """
    if os.environ.get(EMAIL_ADAPTER_ENV) != REAL_EMAIL_ADAPTER_SENTINEL:
        return False
    return all(os.environ.get(name, "").strip() for name in _REQUIRED)


def build_email_gateway() -> EmailGateway:
    """Select an adapter, defaulting to the one that mails nobody.

    :return: The configured gateway
    :raises RuntimeError: The real adapter is selected but unconfigured
    """
    if os.environ.get(EMAIL_ADAPTER_ENV) != REAL_EMAIL_ADAPTER_SENTINEL:
        return NullEmailGateway()
    if not email_gateway_configured():
        raise RuntimeError(
            "the SES email adapter was selected but is not fully configured "
            f"({', '.join(_REQUIRED)}). Refusing rather than falling back, "
            "because a silent fallback stops sending without anyone noticing."
        )

    from app.gateway.ses_smtp import SesSmtpGateway

    return SesSmtpGateway(
        host=os.environ["SHIKKHOKPLUS_SES_SMTP_HOST"],
        port=int(os.environ.get("SHIKKHOKPLUS_SES_SMTP_PORT", "587")),
        username=os.environ["SHIKKHOKPLUS_SES_SMTP_USERNAME"],
        password=os.environ["SHIKKHOKPLUS_SES_SMTP_PASSWORD"],
        sender=os.environ["SHIKKHOKPLUS_EMAIL_FROM"],
        configuration_set=os.environ.get("SHIKKHOKPLUS_SES_CONFIGURATION_SET") or None,
    )
