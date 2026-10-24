"""Sending a fee reminder, recorded as an event [BR7.1, BR7.2].

**A reminder is an event, not a flag.** A boolean or a
``last_reminded_at`` column cannot express the channel, a failed send,
or a second reminder, and would force a migration the moment a second
channel arrives. The teacher-facing "reminded 3 days ago" / "Never
reminded" state is **derived** as the latest event per
``(enrollment, period)``.

**The write order is the opposite of the intuitive one, deliberately**
[reliability-design § 5]::

    COMMIT the reminder event (outcome = 'pending')
    dispatch the push                       <- outside the transaction
    UPDATE the event's outcome to 'sent' or 'failed'

Writing the event *after* a successful dispatch loses the record of a
send that happened if the process dies in between -- and the whole
reason a reminder is an event rather than a boolean is that a flag
cannot express a failed send.

**The adapter is imported, never defined here** [NFR19.24, OQ-4]. It
lives in ``app.notifications`` beside the SMS gateway, and a test
asserts that no module under a feature package defines one: an adapter
in the fee feature is one D4 copies rather than imports.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import ReminderEvent
from app.notifications.fcm import (
    DeliveryOutcome,
    PushAdapter,
    PushMessage,
    build_push_adapter,
)

__all__ = ["PUSH_CHANNEL", "latest_reminder", "send_fee_reminder"]

_log = logging.getLogger(__name__)

#: V1 ships one channel. The column exists so a second is data rather
#: than a migration.
PUSH_CHANNEL = "push"

#: How an outcome maps onto the stored value. A dictionary rather than
#: a name comparison, so an outcome added to the adapter without a
#: decision here raises at the lookup instead of being stored as
#: something plausible.
_STORED_OUTCOME: dict[DeliveryOutcome, str] = {
    DeliveryOutcome.SENT: "sent",
    DeliveryOutcome.FAILED: "failed",
    # A dead token is not a delivery: nobody received it. Recorded as
    # failed so the teacher sees an honest state, while the TOKEN
    # handling (deleting it) is the adapter's concern and not this row's.
    DeliveryOutcome.UNREGISTERED: "failed",
}


def send_fee_reminder(
    session: Session,
    *,
    enrollment_id: uuid.UUID,
    period: str,
    sent_by_account_id: uuid.UUID,
    device_token: str | None,
    correlation_id: str = "",
    adapter: PushAdapter | None = None,
) -> ReminderEvent:
    """Record a reminder and dispatch it, in that order.

    **Never raises on a delivery failure** [BR7.2]. The row is written
    and committed first, the dispatch happens outside that transaction,
    and the outcome is written back. A caller gets a row describing what
    happened and no exception to handle, because a push failure must not
    fail the operation that triggered it.

    :param session: The session to write through
    :param enrollment_id: The seat being chased
    :param period: The period being chased, as ``YYYY-MM``
    :param sent_by_account_id: The teacher sending it
    :param device_token: The recipient's registration token, or None
        where no device is registered
    :param correlation_id: Ties the log line to a request
    :param adapter: The push adapter; the configured one by default
    :return: The event row, carrying its final outcome
    """
    event = ReminderEvent(
        enrollment_id=enrollment_id,
        period=period,
        channel=PUSH_CHANNEL,
        sent_at=dt.datetime.now(tz=dt.UTC),
        sent_by_account_id=sent_by_account_id,
        outcome="pending",
    )
    session.add(event)
    # COMMITTED BEFORE THE DISPATCH. A crash between the two then loses
    # a push, which is recoverable; the other order loses the RECORD of
    # a push that happened, which is not.
    session.commit()

    if device_token is None:
        # Nothing to send to. Recorded as failed rather than left
        # pending: "no device registered" is a real outcome the teacher
        # should see, and a row stuck at pending is indistinguishable
        # from a crash.
        event.outcome = "failed"
        session.commit()
        return event

    push = adapter or build_push_adapter()
    message = PushMessage(
        title_key="fees.reminder.title",
        body_key="fees.reminder.body",
        data={"enrollment_id": str(enrollment_id), "period": period},
    )

    try:
        result = push.send(device_token, message, correlation_id)
        outcome = _STORED_OUTCOME[result.outcome]
    except Exception:  # noqa: BLE001  best-effort by rule [BR7.2]
        # The project's stated exception to "silent failures are not
        # acceptable", and it is narrow: the failure is LOGGED and
        # RECORDED, and only the SURFACING is suppressed. Nothing
        # identifying reaches the log line [NFR24.6].
        _log.exception(
            "push dispatch failed",
            extra={"correlation_id": correlation_id, "period": period},
        )
        outcome = "failed"

    event.outcome = outcome
    session.commit()
    return event


def latest_reminder(
    session: Session,
    *,
    enrollment_id: uuid.UUID,
    period: str,
) -> ReminderEvent | None:
    """Return the most recent reminder for one seat and period.

    **The derived state, from the event log.** "Reminded 3 days ago" is
    computed from this row's ``sent_at``; "Never reminded" is this
    returning None. Neither is a stored field.

    :param session: The session to read through
    :param enrollment_id: The seat
    :param period: The period
    :return: The latest event, or None where none was ever sent
    """
    return session.scalars(
        sa.select(ReminderEvent)
        .where(
            ReminderEvent.enrollment_id == enrollment_id,
            ReminderEvent.period == period,
        )
        .order_by(ReminderEvent.sent_at.desc())
        .limit(1)
    ).one_or_none()
