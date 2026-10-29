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
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.analytics.seats import ledger_for_seats
from app.authz.lenses import TeacherLens
from app.db.models import Batch, Enrollment, ReminderEvent
from app.errors import AuthorizationError
from app.errors.codes import NOT_AVAILABLE
from app.money import derive
from app.notifications.fcm import (
    DeliveryOutcome,
    PushAdapter,
    PushMessage,
    build_push_adapter,
)
from app.notifications.inbox import FEE_REMINDER, deliver

__all__ = [
    "IN_APP_CHANNEL",
    "PUSH_CHANNEL",
    "REMIND_AGAIN_AFTER",
    "ReminderBatch",
    "latest_reminder",
    "remind",
    "send_fee_reminder",
]

_log = logging.getLogger(__name__)

#: V1 ships one channel. The column exists so a second is data rather
#: than a migration.
PUSH_CHANNEL = "push"

#: The inbox channel: the message is a row the recipient reads in the
#: app, so delivery cannot fail the way a push can and the event is
#: recorded as ``sent`` in the same transaction as the message.
IN_APP_CHANNEL = "in_app"

#: How soon one seat may be reminded again. A teacher tapping "Remind"
#: twice should not send the same nudge twice.
REMIND_AGAIN_AFTER = dt.timedelta(hours=24)

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


@dataclass(frozen=True, slots=True)
class ReminderBatch:
    """What one "Remind" tap did.

    :ivar sent: Seats whose student or guardian was reminded
    :ivar skipped: Seats left alone: owing nothing, reminded within
        :data:`REMIND_AGAIN_AFTER`, or with nobody who has accepted
    """

    sent: int
    skipped: int


def remind(
    session: Session,
    *,
    lens: TeacherLens,
    enrollment_ids: list[uuid.UUID],
    now: dt.datetime | None = None,
) -> ReminderBatch:
    """Remind the people on these seats what they owe, in the app.

    **Every seat must be this teacher's, or nothing is sent.** One
    stranger's seat in the list refuses the whole request, the same
    refusal as a missing seat, so a probe learns nothing and no partial
    send needs explaining.

    **Only accounts that ACCEPTED the seat receive it** [BR1.1, BR5.2].
    A number a teacher typed is not that person's agreement, and a
    reminder names a batch and an amount.

    **The amount is the server's fold** over the seat's ledger, read in
    one statement for every seat; a seat owing nothing is skipped.

    :param session: The session to write through
    :param lens: The teacher sending it
    :param enrollment_ids: The seats to remind
    :param now: When it is sent; the current time by default
    :return: How many seats were reminded and how many skipped
    :raises AuthorizationError: A seat is not this teacher's, or does
        not exist
    """
    sent_at = now or dt.datetime.now(tz=dt.UTC)
    wanted = list(dict.fromkeys(enrollment_ids))
    seats = session.execute(
        sa.select(Enrollment, Batch.name)
        .join(Batch, Batch.id == Enrollment.batch_id)
        .where(Enrollment.id.in_(wanted), Batch.owner_id == lens.owner_id)
    ).all()
    if len(seats) != len(wanted):
        raise AuthorizationError(code=NOT_AVAILABLE, message_key="fees.not_available")

    recent = set(
        session.scalars(
            sa.select(ReminderEvent.enrollment_id).where(
                ReminderEvent.enrollment_id.in_(wanted),
                ReminderEvent.channel == IN_APP_CHANNEL,
                ReminderEvent.sent_at > sent_at - REMIND_AGAIN_AFTER,
            )
        )
    )
    ledger = ledger_for_seats(session, wanted)

    sent = 0
    for seat, batch_name in seats:
        derived = derive(ledger[seat.id])
        recipients = _accepted_accounts(seat)
        owing = sorted(
            period
            for period, balance in derived.per_cycle.items()
            if balance.is_positive()
        )
        if seat.id in recent or not recipients or not owing:
            continue

        session.add(
            ReminderEvent(
                enrollment_id=seat.id,
                period=owing[0],
                channel=IN_APP_CHANNEL,
                sent_at=sent_at,
                sent_by_account_id=lens.account_id,
                outcome="sent",
            )
        )
        deliver(
            session,
            account_ids=recipients,
            kind=FEE_REMINDER,
            batch_name=batch_name,
            now=sent_at,
            enrollment_id=seat.id,
            period=owing[0],
            amount=derived.total_outstanding,
        )
        sent += 1

    session.commit()
    return ReminderBatch(sent=sent, skipped=len(wanted) - sent)


def _accepted_accounts(seat: Enrollment) -> list[uuid.UUID]:
    """List the accounts on a seat that have accepted it.

    :param seat: The seat
    :return: The student and guardian accounts that accepted, if any
    """
    links = (
        (seat.student_account_id, seat.student_decision),
        (seat.guardian_account_id, seat.guardian_decision),
    )
    return [
        account
        for account, decision in links
        if account is not None and decision == "accepted"
    ]
