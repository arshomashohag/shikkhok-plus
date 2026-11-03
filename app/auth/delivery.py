"""The one door an OTP SMS goes out through, with its budget at the door.

**The daily send budget is spent where the money is spent** [PA-SEC-2].
The sign-in and deletion routes answer a known and an unknown number
identically and text only the known one, so a budget consumed on the
request path is spent by requests that cost nothing -- and anyone can
then exhaust it with numbers nobody owns, locking every real user out.
Consumed here, immediately before ``gateway.send``, only a real send
spends it.

**Still before the gateway call, never after** [BR2.2]: a budget
checked after the send has already spent what it protects.

**A refusal here cannot be reported to the caller, and must not be.**
On the sign-in and deletion routes this runs after the response was
written (deferred so the known branch is not one gateway round trip
slower than the unknown one -- the timing oracle [BR2.7]), and the
response was already identical for both. So an exhausted budget skips
the send and says so at CRITICAL, carrying the scope and the
correlation id and never the number. The person sees "code sent" and
receives nothing, which is the price of the budget not being an
existence oracle; the operator sees why, from the alert.

**Its own session**, because a deferred task outlives the request's:
the request-scope middleware has already closed that one by the time
the response body is written.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import Connection, Engine
from sqlalchemy.orm import sessionmaker

from app.auth.ceilings import CeilingBreach, CeilingChecker, SendBudget
from app.gateway.sms import SendResult, SmsGateway

__all__ = ["send_within_budget"]

_log = logging.getLogger(__name__)


def send_within_budget(
    bind: Engine | Connection,
    gateway: SmsGateway,
    number: str,
    message: str,
    correlation_id: str,
    *,
    budget: SendBudget,
    now: dt.datetime | None = None,
) -> SendResult | None:
    """Spend one unit of a daily send budget, then send -- or skip.

    ``budget`` is keyword-only with no default, on ``otp.issue``'s
    reasoning: a new caller must choose which budget it spends rather
    than inherit sign-in's by saying nothing.

    :param bind: The engine to open this send's own session on
    :param gateway: The configured SMS gateway
    :param number: The destination number
    :param message: The rendered body
    :param correlation_id: Ties the log line to the request
    :param budget: Which daily budget this send spends
    :param now: The moment to count against, or None for the clock
    :return: The gateway's result, or None when the budget refused
    """
    factory = sessionmaker(bind=bind, expire_on_commit=False)
    with factory() as session:
        try:
            CeilingChecker(session).consume_send(budget, now)
        except CeilingBreach as breach:
            _log.critical(
                "sms send skipped: daily send budget exhausted",
                extra={
                    "scope": breach.scope.value,
                    "correlation_id": correlation_id,
                },
            )
            return None
    return gateway.send(number, message, correlation_id)
