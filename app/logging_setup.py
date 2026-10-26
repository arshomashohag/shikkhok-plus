"""Log formatting that keeps the structured fields.

**The gap this closes.** Several call sites log with
``extra={"outcome": ..., "provider_code": ...}`` — the SMS gateway's
send outcome most importantly — and Python's default formatter prints
only the message. So a production log line read ``sms send`` with no
verdict attached, and establishing whether a message had actually been
delivered meant reading the source to discover the fields existed at
all.

That is worse than it sounds for this particular field. The gateway
offers no delivery report, so its ``outcome`` and ``provider_code``
are the ONLY record of whether an OTP reached a person. Dropping them
turns the one observable into nothing, and a code of 1032 — "IP not
whitelisted", which never succeeds on retry — looks identical to a
successful send.

The formatter is deliberately plain text rather than JSON. Nothing
ships these logs anywhere [team: Deployment], so the only reader is a
person running ``docker logs``, and JSON would make that worse for no
gain. When a log sink arrives this is the place to change.
"""

from __future__ import annotations

import logging
import sys
from typing import Final

__all__ = ["STRUCTURED_FIELDS", "StructuredFormatter", "configure_logging"]

#: The fields call sites attach through ``extra=``, in the order they
#: are printed. Listed explicitly rather than discovered by diffing
#: against ``logging.LogRecord``'s own attributes: that diff also
#: catches anything the logging machinery adds, so a library changing
#: its internals would silently change our log format.
STRUCTURED_FIELDS: Final[tuple[str, ...]] = (
    "purpose",
    "outcome",
    "provider_code",
    "correlation_id",
    "event",
)


class StructuredFormatter(logging.Formatter):
    """Print the message, then whichever structured fields are present.

    A record with no extras formats exactly as it did before, so this
    changes nothing for the FastAPI and uvicorn lines that make up most
    of the output.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Render one record.

        :param record: The record to render
        :return: The formatted line
        """
        base = super().format(record)
        pairs = [
            f"{name}={getattr(record, name)!r}"
            for name in STRUCTURED_FIELDS
            if hasattr(record, name)
        ]
        if not pairs:
            return base
        return f"{base} [{' '.join(pairs)}]"


def configure_logging(level: int = logging.INFO) -> None:
    """Install the formatter on the root handler.

    Called once at application start. Replaces the root handlers
    rather than adding one, because uvicorn installs its own and two
    handlers would print every line twice.

    :param level: The root level to set
    :return: None
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        StructuredFormatter(
            fmt="%(levelname)s:%(name)s:%(message)s",
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
