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

**A code whose send was skipped is killed** [C-20]. It used to stay
live, so whoever had drained the budget still had five guesses at a code
nobody could receive. Given the code's row, the skip marks it spent in
the same session; verify then refuses it as a used code, which is what
it answers for any spent code, so this changes no response either.

**Its own session**, because a deferred task outlives the request's:
the request-scope middleware has already closed that one by the time
the response body is written.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import uuid

import sqlalchemy as sa
from fastapi import BackgroundTasks
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session, sessionmaker

from app.accounts.identifier import Identifier
from app.auth.ceilings import CeilingBreach, CeilingChecker, SendBudget
from app.gateway.email import EmailGateway, EmailMessage
from app.gateway.outbox import record_outbox
from app.gateway.sms import Outcome, SendResult, SmsGateway
from app.gateway.template import (
    render_contact_notice_email,
    render_contact_notice_sms,
    render_email_code,
    render_otp_message,
)

__all__ = [
    "deliver_code",
    "send_contact_notice",
    "send_email_within_budget",
    "send_within_budget",
]

#: The SMS Retriever app hash, from configuration.
_APP_HASH_ENV = "SHIKKHOKPLUS_SMS_APP_HASH"

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
    otp_request_id: uuid.UUID | None = None,
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
    :param otp_request_id: The code this message carries, killed if the
        send is skipped; None for a caller that has not adopted it yet
    :return: The gateway's result, or None when the budget refused
    """
    if not _spend(bind, budget, correlation_id, now, otp_request_id):
        return None
    return gateway.send(number, message, correlation_id)


def send_email_within_budget(
    bind: Engine | Connection,
    gateway: EmailGateway,
    address: str,
    message: EmailMessage,
    correlation_id: str,
    *,
    now: dt.datetime | None = None,
    otp_request_id: uuid.UUID | None = None,
) -> SendResult | None:
    """Spend one unit of the daily email budget, then send -- or skip.

    One budget for every emailed code [0032]; see
    :data:`~app.auth.ceilings.EMAIL_GLOBAL_DAILY` for why it is not an
    SMS budget.

    :param bind: The engine to open this send's own session on
    :param gateway: The configured email gateway
    :param address: The destination address
    :param message: The rendered email
    :param correlation_id: Ties the log line to the request
    :param now: The moment to count against, or None for the clock
    :param otp_request_id: The code this email carries, killed if skipped
    :return: The gateway's result, or None when the budget refused
    """
    if not _spend(bind, SendBudget.EMAIL, correlation_id, now, otp_request_id):
        return None
    return gateway.send(address, message, correlation_id)


def deliver_code(
    background: BackgroundTasks,
    session: Session,
    identifier: Identifier,
    code: str,
    correlation_id: str,
    *,
    sms_budget: SendBudget,
    sms_gateway: SmsGateway,
    email_gateway: EmailGateway,
    otp_request_id: uuid.UUID,
) -> None:
    """Send one code by SMS or by email, after the response.

    The one place a route hands a code to a channel [0032], so no route
    branches on the channel itself. **Deferred, never inline**, for the
    reason the sign-in route records: a send made before the response
    would make a known destination measurably slower than an unknown
    one [BR2.7]. Also records the staging outbox entry, which is a no-op
    anywhere it is not permitted.

    The caller decides WHETHER to send -- an unknown destination is never
    sent to -- and this decides only HOW.

    :param background: Runs the send after the response is written
    :param session: The request's session, for the outbox entry
    :param identifier: Where the code goes
    :param code: The code
    :param correlation_id: Ties the log lines to the request
    :param sms_budget: Which SMS budget a text spends; an email always
        spends the email budget
    :param sms_gateway: The configured SMS gateway
    :param email_gateway: The configured email gateway
    :param otp_request_id: The code's row, killed if the send is skipped
    :return: None
    """
    bind = session.get_bind()
    if identifier.is_phone:
        text = render_otp_message(code, os.environ.get(_APP_HASH_ENV, ""))
        background.add_task(
            send_within_budget,
            bind,
            sms_gateway,
            identifier.value,
            text,
            correlation_id,
            budget=sms_budget,
            otp_request_id=otp_request_id,
        )
        record_outbox(
            session, phone=identifier.value, message=text, correlation_id=correlation_id
        )
        return

    message = render_email_code(code)
    background.add_task(
        send_email_within_budget,
        bind,
        email_gateway,
        identifier.value,
        message,
        correlation_id,
        otp_request_id=otp_request_id,
    )
    record_outbox(
        session,
        email=identifier.value,
        message=message.text,
        correlation_id=correlation_id,
    )


def send_contact_notice(
    bind: Engine | Connection,
    contact: Identifier,
    correlation_id: str,
    *,
    sms_gateway: SmsGateway,
    email_gateway: EmailGateway,
) -> None:
    """Tell a contact that just left an account, once, best-effort [BR5.9].

    Run after the change has committed, from the response's background
    tasks, so no transaction is open while the gateway is called and a
    server-side retry of the change can never send it twice [NFR4.7].
    It spends the budget its channel's codes spend (the sign-in SMS
    budget, or the email budget), and a refused budget means it is not
    sent.

    **Never raised to anybody** -- the stated exception to "silent
    failures are not acceptable", as an FCM push is. The outcome is
    logged once by channel and correlation id [NFR4.9]; the contact, the
    account and the text never are [NFR3.4].

    :param bind: The engine to open the budget's own session on
    :param contact: The contact that left the account
    :param correlation_id: Ties the log line to the request
    :param sms_gateway: The configured SMS gateway
    :param email_gateway: The configured email gateway
    :return: None
    """
    purpose = "contact_notice_sms" if contact.is_phone else "contact_notice_email"
    try:
        if contact.is_phone:
            result = send_within_budget(
                bind,
                sms_gateway,
                contact.value,
                render_contact_notice_sms(),
                correlation_id,
                budget=SendBudget.SIGN_IN,
            )
        else:
            result = send_email_within_budget(
                bind,
                email_gateway,
                contact.value,
                render_contact_notice_email(),
                correlation_id,
            )
        outcome = Outcome.BUDGET_REFUSED if result is None else result.outcome
    except Exception:  # noqa: BLE001  best-effort by rule [BR5.9, NFR4.7]
        outcome = Outcome.FAILED
    _log.info(
        "contact notice",
        extra={
            "purpose": purpose,
            "outcome": outcome.value.lower(),
            "correlation_id": correlation_id,
        },
    )


def _spend(
    bind: Engine | Connection,
    budget: SendBudget,
    correlation_id: str,
    now: dt.datetime | None,
    otp_request_id: uuid.UUID | None,
) -> bool:
    """Spend one unit of a budget, killing the code when it is exhausted.

    :param bind: The engine to open this send's own session on
    :param budget: Which daily budget this send spends
    :param correlation_id: Ties the log line to the request
    :param now: The moment to count against, or None for the clock
    :param otp_request_id: The code to kill on a skip, or None
    :return: True when the send may go ahead
    """
    factory = sessionmaker(bind=bind, expire_on_commit=False)
    with factory() as session:
        try:
            CeilingChecker(session).consume_send(budget, now)
        except CeilingBreach as breach:
            _log.critical(
                "code send skipped: daily send budget exhausted",
                extra={
                    "scope": breach.scope.value,
                    "correlation_id": correlation_id,
                },
            )
            if otp_request_id is not None:
                session.execute(
                    sa.text(
                        "UPDATE otp_request "
                        "SET consumed_at = coalesce(consumed_at, :now) "
                        "WHERE id = :id"
                    ),
                    {"now": now or dt.datetime.now(tz=dt.UTC), "id": otp_request_id},
                )
                session.commit()
            return False
    return True
