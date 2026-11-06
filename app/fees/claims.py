"""Submitting a payment claim [BR5.1, BR5.2].

**A claim is an assertion, not a payment.** There is no gateway: the
system records what the claimant says and what the teacher decides
[FR6.10]. The distinction matters downstream, because a shortfall is
measured against what the cycle CHARGED and never against what was
claimed -- otherwise a payer could change what they owe by changing what
they assert.

**The resolution is stored, not recomputed** [BR5.1]. The claim's period
is settled once at submission so the claimant and the teacher are
looking at the same cycle; recomputing it later would silently move the
claim as other payments landed.

The two validation rules have deliberately opposite shapes. Zero and
negative are refused **before the claim is recorded**; an amount
**exceeding** the balance is **accepted**, because money may genuinely
have been overpaid out of band and blocking it at submission makes a
real overpayment unreportable -- leaving a phone call as the only
route, which is the thing this feature exists to remove.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.orm import Session

from app.db.models import Batch, Enrollment, PaymentClaim
from app.errors import ValidationError
from app.fees.purposes import MONTHLY, Target, point_claim
from app.money import Money
from app.notifications.inbox import CLAIM_TO_VERIFY, deliver
from app.notifications.recipients import teacher_recipient

__all__ = ["CASH", "MOBILE_SERVICES", "record_claim", "submit_claim"]

#: The mobile services the form suggests [BR6.5, FR6.11]. **Server-supplied
#: data, not a client-side list**: adding one is a data change rather
#: than an app release. A teacher may still name any other service.
MOBILE_SERVICES: tuple[str, ...] = ("bKash", "Nagad", "Rocket")

#: The built-in channel for money handed over in person.
CASH: str = "cash"


def record_claim(
    session: Session,
    *,
    enrollment_id: uuid.UUID,
    submitted_by_account_id: uuid.UUID,
    claimed_amount: Money,
    channel: str,
    target: Target,
    transaction_id: str | None = None,
    submission_id: uuid.UUID | None = None,
    today: dt.date | None = None,
) -> PaymentClaim:
    """Add one pending claim against the oldest unpaid cycle, or a fee.

    **Paying when nothing is owed is accepted**: a seat with no unpaid
    cycle resolves to Bangladesh's current period, and on approval the
    receipt is capped at that period's charge with the rest held as
    credit. No cycle is created to receive the payment.

    Flushes and does not commit; the caller owns the transaction and
    the notification.

    :param session: The session to write through
    :param enrollment_id: The seat the claim is against
    :param submitted_by_account_id: Who is claiming
    :param claimed_amount: What they say they paid, or this child's share
    :param channel: Which service the money moved through
    :param target: What it is for: the months, or one extra fee. Stated
        by every caller, never defaulted [0020]
    :param transaction_id: The reference they quote, if any
    :param submission_id: The submission this claim is a share of, if any
    :param today: Bangladesh's date; the real clock by default
    :return: The pending claim
    :raises ValidationError: The seat was not charged the named fee
    """
    claim = PaymentClaim(
        enrollment_id=enrollment_id,
        claimed_amount=claimed_amount,
        channel=channel,
        transaction_id=transaction_id,
        submitted_by_account_id=submitted_by_account_id,
        submitted_at=dt.datetime.now(tz=dt.UTC),
        status="pending",
        payment_submission_id=submission_id,
    )
    point_claim(session, claim, target=target, today=today)
    session.add(claim)
    session.flush()
    return claim


def submit_claim(
    session: Session,
    *,
    enrollment_id: uuid.UUID,
    submitted_by_account_id: uuid.UUID,
    claimed_amount: Money,
    channel: str,
    transaction_id: str | None = None,
    submission_id: uuid.UUID | None = None,
    today: dt.date | None = None,
) -> PaymentClaim:
    """Record a standalone claim and tell the teacher.

    Commits, because a submission is a complete operation.

    :param session: The session to write through
    :param enrollment_id: The seat the claim is against
    :param submitted_by_account_id: Who is claiming
    :param claimed_amount: What they say they paid
    :param channel: Which service the money moved through
    :param transaction_id: The reference they quote, if any
    :param submission_id: The submission this claim belongs to, if any
    :param today: Bangladesh's date; the real clock by default
    :return: The pending claim
    :raises ValidationError: The amount is not strictly positive, or the
        channel is not one the server offers
    """
    if not claimed_amount.is_positive():
        raise ValidationError(
            code="CLAIM_AMOUNT_NOT_POSITIVE",
            message_key="fees.claim.amount_not_positive",
        )
    if channel not in (*MOBILE_SERVICES, CASH):
        raise ValidationError(
            code="CLAIM_CHANNEL_UNKNOWN",
            message_key="fees.claim.channel_unknown",
        )
    claim = record_claim(
        session,
        enrollment_id=enrollment_id,
        submitted_by_account_id=submitted_by_account_id,
        claimed_amount=claimed_amount,
        channel=channel,
        target=MONTHLY,
        transaction_id=transaction_id,
        submission_id=submission_id,
        today=today,
    )
    _tell_the_teacher(session, claim)
    session.commit()
    return claim


def _tell_the_teacher(session: Session, claim: PaymentClaim) -> None:
    """Tell the batch's teacher a claim awaits verification.

    Adds to the submission's transaction and does not commit.

    :param session: The session the claim is written through
    :param claim: The new pending claim
    :return: None
    """
    seat = session.get(Enrollment, claim.enrollment_id)
    if seat is None:
        return
    teacher = teacher_recipient(session, batch_id=seat.batch_id)
    if teacher is None:
        return
    batch = session.get(Batch, seat.batch_id)
    deliver(
        session,
        account_ids=[teacher],
        kind=CLAIM_TO_VERIFY,
        batch_name=batch.name if batch is not None else "",
        now=dt.datetime.now(tz=dt.UTC),
        enrollment_id=seat.id,
        period=claim.period,
        amount=claim.claimed_amount,
        source_id=claim.id,
        child_names={teacher: seat.display_name},
    )
