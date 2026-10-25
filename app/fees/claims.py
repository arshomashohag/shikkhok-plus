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

from app.db.models import PaymentClaim
from app.errors import ValidationError
from app.fees.balances import oldest_unpaid_period
from app.money import Money

__all__ = ["CHANNELS", "NoOpenCycle", "submit_claim"]

#: The payment channels V1 accepts [BR6.5, FR6.11]. **Server-supplied
#: data, not a client-side list**: adding one is a data change rather
#: than an app release, and an installed Android app cannot be forced to
#: update. The client reads this set from the payment-destination
#: response and ships no enumeration of its own.
CHANNELS: tuple[str, ...] = ("bKash", "Nagad", "Rocket", "cash")


class NoOpenCycle(ValidationError):
    """Nothing is owed, so there is no cycle for a claim to land on.

    **Refused with a stated reason, and no cycle is created to receive
    the payment** [BR5.1]. Generating one would bill the student for a
    period that had not begun.
    """

    def __init__(self) -> None:
        """Initialize the refusal with its registered code."""
        super().__init__(
            code="NO_OPEN_FEE_CYCLE",
            message_key="fees.claim.no_open_cycle",
        )


def submit_claim(
    session: Session,
    *,
    enrollment_id: uuid.UUID,
    submitted_by_account_id: uuid.UUID,
    claimed_amount: Money,
    channel: str,
    transaction_id: str | None = None,
) -> PaymentClaim:
    """Record a claim against the oldest unpaid cycle.

    Commits, because a submission is a complete operation.

    :param session: The session to write through
    :param enrollment_id: The seat the claim is against
    :param submitted_by_account_id: Who is claiming
    :param claimed_amount: What they say they paid
    :param channel: Which service the money moved through
    :param transaction_id: The reference they quote, if any
    :return: The pending claim
    :raises ValidationError: The amount is not strictly positive, the
        channel is not one the server offers, or nothing is owed
    """
    if not claimed_amount.is_positive():
        raise ValidationError(
            code="CLAIM_AMOUNT_NOT_POSITIVE",
            message_key="fees.claim.amount_not_positive",
        )
    if channel not in CHANNELS:
        raise ValidationError(
            code="CLAIM_CHANNEL_UNKNOWN",
            message_key="fees.claim.channel_unknown",
        )

    period = oldest_unpaid_period(session, enrollment_id)
    if period is None:
        raise NoOpenCycle

    claim = PaymentClaim(
        enrollment_id=enrollment_id,
        period=period,
        claimed_amount=claimed_amount,
        channel=channel,
        transaction_id=transaction_id,
        submitted_by_account_id=submitted_by_account_id,
        submitted_at=dt.datetime.now(tz=dt.UTC),
        # STATED, because the column carries no default. A claim is
        # pending from creation and every insert path says so.
        status="pending",
    )
    session.add(claim)
    session.commit()
    return claim
