"""The real email adapter: Amazon SES through its SMTP interface.

**SMTP rather than the SES API, because of where the API runs.** The
container cannot reach the instance role -- the metadata hop limit is 1,
deliberately (``infra/modules/app/main.tf``) -- so it holds the SMTP
credentials of an IAM user that may only send, only from one address
(``infra/modules/email``). SMTP needs no SDK: :mod:`smtplib` is in the
standard library, so this adds no dependency to lock and scan.

**STARTTLS is required, and the certificate is verified** against the
system trust store. A server that does not offer STARTTLS fails the send
rather than receiving the code in clear.

**The envelope sender is the bare From address.** The IAM policy matches
``ses:FromAddress`` against it, so a display name in the envelope would
make every send an AccessDenied.
"""

from __future__ import annotations

import email.message
import email.utils
import logging
import smtplib
import ssl
from typing import Final

from app.gateway.email import EmailMessage
from app.gateway.sms import Outcome, SendResult

__all__ = ["SesSmtpGateway"]

_log = logging.getLogger(__name__)

#: Long enough for SES from the same region; short enough that a stalled
#: connection does not hold a worker thread.
_TIMEOUT_SECONDS: Final = 10.0


class SesSmtpGateway:
    """Send one email per call through SES SMTP.

    :ivar host: ``email-smtp.<region>.amazonaws.com``
    :ivar port: 587, for STARTTLS
    :ivar sender: The From header, e.g. ``ShikkhokPlus <no-reply@...>``
    :ivar configuration_set: Sent as ``X-SES-CONFIGURATION-SET``, or None
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        configuration_set: str | None,
    ) -> None:
        """Hold the connection settings; connect per send.

        :param host: The SMTP endpoint
        :param port: The STARTTLS port
        :param username: The SMTP username (the IAM access key id)
        :param password: The SMTP password; never logged
        :param sender: The From header
        :param configuration_set: The SES configuration set, or None
        """
        self.host = host
        self.port = port
        self._username = username
        self._password = password
        self.sender = sender
        self.configuration_set = configuration_set

    def send(
        self, address: str, message: EmailMessage, correlation_id: str
    ) -> SendResult:
        """Send one email, once.

        :param address: The destination address
        :param message: The rendered email
        :param correlation_id: Ties the log line to a request
        :return: ``SENT``, ``FAILED`` for a refusal, ``UNKNOWN`` for a
            timeout or a dropped connection
        """
        mail = email.message.EmailMessage()
        mail["From"] = self.sender
        mail["To"] = address
        mail["Subject"] = message.subject
        mail["Date"] = email.utils.formatdate(localtime=False)
        mail["Message-ID"] = email.utils.make_msgid(
            domain=_domain_of(self.sender) or None
        )
        if self.configuration_set:
            mail["X-SES-CONFIGURATION-SET"] = self.configuration_set
        # Text first, HTML last: a client shows the last alternative it
        # can render, so the plain text is the fallback, not the default.
        mail.set_content(message.text, charset="utf-8")
        if message.html is not None:
            mail.add_alternative(message.html, subtype="html", charset="utf-8")

        envelope_from = email.utils.parseaddr(self.sender)[1]
        try:
            with smtplib.SMTP(self.host, self.port, timeout=_TIMEOUT_SECONDS) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(self._username, self._password)
                smtp.send_message(mail, from_addr=envelope_from, to_addrs=[address])
        except (TimeoutError, smtplib.SMTPServerDisconnected):
            outcome = Outcome.UNKNOWN
        except (smtplib.SMTPException, OSError):
            outcome = Outcome.FAILED
        else:
            outcome = Outcome.SENT

        # The outcome and the request, never the address or the body.
        _log.info(
            "email send",
            extra={"outcome": outcome.value, "correlation_id": correlation_id},
        )
        return SendResult(outcome=outcome)


def _domain_of(sender: str) -> str:
    """Read the domain of a From header, for the Message-ID.

    :param sender: ``Name <local@domain>`` or ``local@domain``
    :return: The domain, or an empty string
    """
    return email.utils.parseaddr(sender)[1].rpartition("@")[2]
