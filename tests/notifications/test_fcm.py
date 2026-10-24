"""The push adapter and the reminder event it backs [BR7.1, BR7.2].

Four properties, each with a plausible wrong version:

* **Delivery never fails the trigger.** A push failure rolling back a
  recorded payment verification is strictly worse than no push.
* **The failure is recorded, not swallowed.** The exception covers not
  SURFACING it; the ``outcome`` column exists precisely because a flag
  cannot express a failed send.
* **``UNREGISTERED`` is not an error** [NFR19.22]: it is the
  token-lifecycle signal, and treating it as a failure grows a
  dead-token table for ever.
* **The event is committed BEFORE the dispatch.** Writing it afterwards
  loses the record of a send that happened if the process dies between
  the two.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import ReminderEvent
from app.fees.reminders import latest_reminder, send_fee_reminder
from app.notifications.fcm import (
    ADAPTER_ENV,
    DeliveryOutcome,
    NullPushAdapter,
    PushMessage,
    PushResult,
    build_push_adapter,
)
from tests.batches.conftest import TeacherFixture


class _FailingAdapter:
    """An adapter whose every send raises.

    :ivar calls: How many sends were attempted
    """

    def __init__(self) -> None:
        """Start with no calls recorded."""
        self.calls = 0

    def send(self, token: str, message: PushMessage, correlation_id: str) -> PushResult:
        """Raise, as a real transport failure would.

        :param token: The device token
        :param message: What to send
        :param correlation_id: Ties the log line to a request
        :return: Never returns
        :raises RuntimeError: Always
        """
        self.calls += 1
        raise RuntimeError("transport is down")


class _UnregisteredAdapter:
    """An adapter reporting a dead token."""

    def send(self, token: str, message: PushMessage, correlation_id: str) -> PushResult:
        """Report the token as unregistered.

        :param token: The device token
        :param message: What to send
        :param correlation_id: Ties the log line to a request
        :return: The unregistered outcome
        """
        return PushResult(outcome=DeliveryOutcome.UNREGISTERED)


def test_the_default_adapter_makes_no_network_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The default must be the adapter that cannot reach a real person's
    # device, on the SMS gateway's reasoning.
    monkeypatch.delenv(ADAPTER_ENV, raising=False)

    assert isinstance(build_push_adapter(), NullPushAdapter)


def test_selecting_the_real_adapter_refuses_rather_than_falling_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Refusing beats falling back: a product that believes it is
    # sending reminders and is not is the failure the whole
    # absence-of-success design is arranged around.
    monkeypatch.setenv(ADAPTER_ENV, "fcm")

    with pytest.raises(RuntimeError):
        build_push_adapter()


def test_a_successful_send_records_a_sent_event(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    adapter = NullPushAdapter()

    event = send_fee_reminder(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        sent_by_account_id=teacher.account_id,
        device_token="token-1",
        adapter=adapter,
    )

    assert event.outcome == "sent"
    assert event.channel == "push"
    assert adapter.sent == [("token-1", adapter.sent[0][1])]


def test_a_failed_send_is_recorded_and_does_not_raise(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # Both halves at once: the caller gets no exception, AND the row
    # says the send failed. An implementation that swallowed the
    # failure without recording it passes the first and fails this.
    adapter = _FailingAdapter()

    event = send_fee_reminder(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        sent_by_account_id=teacher.account_id,
        device_token="token-1",
        adapter=adapter,
    )

    assert adapter.calls == 1
    assert event.outcome == "failed"


def test_an_unregistered_token_is_recorded_as_a_non_delivery(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # Nobody received it, so the teacher-facing outcome is honest;
    # the token-lifecycle response belongs to the adapter.
    event = send_fee_reminder(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        sent_by_account_id=teacher.account_id,
        device_token="dead-token",
        adapter=_UnregisteredAdapter(),
    )

    assert event.outcome == "failed"


def test_no_registered_device_still_records_an_event(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # "No device registered" is a real outcome the teacher should see.
    # A row left at `pending` would be indistinguishable from a crash.
    event = send_fee_reminder(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        sent_by_account_id=teacher.account_id,
        device_token=None,
    )

    assert event.outcome == "failed"


def test_the_event_survives_a_dispatch_that_never_returns(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # THE WRITE-ORDER ASSERTION. The row is committed BEFORE the
    # dispatch, so a process that died inside the adapter leaves a
    # record behind. An implementation writing the event afterwards
    # leaves nothing at all, and the whole reason a reminder is an
    # event is that a flag cannot express a send that may have happened.
    send_fee_reminder(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        sent_by_account_id=teacher.account_id,
        device_token="token-1",
        adapter=_FailingAdapter(),
    )

    rows = restricted_session.execute(
        sa.text("SELECT count(*) FROM reminder_event WHERE enrollment_id = :id"),
        {"id": seat},
    ).scalar_one()
    assert rows == 1


def test_two_reminders_leave_two_rows_and_the_later_one_wins(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # [BR7.1] A boolean cannot express a second reminder. The derived
    # state is the LATEST event, not the only one.
    send_fee_reminder(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        sent_by_account_id=teacher.account_id,
        device_token=None,
    )
    second = send_fee_reminder(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        sent_by_account_id=teacher.account_id,
        device_token="token-1",
        adapter=NullPushAdapter(),
    )

    rows = restricted_session.scalars(
        sa.select(ReminderEvent).where(ReminderEvent.enrollment_id == seat)
    ).all()
    assert len(rows) == 2

    newest = latest_reminder(restricted_session, enrollment_id=seat, period="2027-02")
    assert newest is not None
    assert newest.id == second.id
    assert newest.outcome == "sent"


def test_never_reminded_is_the_absence_of_a_row(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    assert (
        latest_reminder(restricted_session, enrollment_id=seat, period="2027-02")
        is None
    )


def test_a_reminder_for_one_period_is_not_a_reminder_for_another(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    send_fee_reminder(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        sent_by_account_id=teacher.account_id,
        device_token=None,
    )

    assert (
        latest_reminder(restricted_session, enrollment_id=seat, period="2027-03")
        is None
    )


def test_the_message_carries_keys_and_never_english(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # [TC-15, D-43] A server-authored English string cannot be
    # localized, and on a lock screen in a Bangla-first product it
    # guarantees untranslated English.
    adapter = NullPushAdapter()

    send_fee_reminder(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        sent_by_account_id=teacher.account_id,
        device_token="token-1",
        adapter=adapter,
    )

    _, message = adapter.sent[0]
    assert message.title_key == "fees.reminder.title"
    assert message.body_key == "fees.reminder.body"
    assert message.data == {"enrollment_id": str(seat), "period": "2027-02"}
