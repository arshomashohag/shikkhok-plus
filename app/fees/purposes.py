"""What a payment is for, and what that makes each child owe [0020].

**One place decides which ledger a claim settles.** A ``monthly`` claim
settles a seat's months, oldest first, exactly as before this revision.
An ``extra`` claim settles that seat's charge under one extra fee and
nothing else. Every path that needs "what does this child owe for this
payment" -- the payer's form, the teacher's review, the approval and the
hand-recorded payment -- asks :func:`owed_for_claim` or
:func:`owed_for_target`, so the four cannot disagree.

**A missing purpose is ``monthly``**, because that is what every payment
was before the field existed, and an older app build sends none. The
conversion happens here, in one visible line, never as a database
default.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.analytics.seats import any_of
from app.db.models import ExtraFee, ExtraFeeCharge, PaymentClaim
from app.errors import ValidationError
from app.fees.balances import derive_for_enrollment, oldest_unpaid_period
from app.fees.extra_ledger import owed_on_charge
from app.fees.periods import Period
from app.local_time import bangladesh_today
from app.money import Money

__all__ = [
    "MONTHLY",
    "FeeRef",
    "Purpose",
    "Target",
    "charge_for",
    "fee_refs",
    "fees_charging_all",
    "fees_charging_each",
    "owed_for_claim",
    "owed_for_target",
    "point_claim",
    "resolve_target",
]

#: The two things a payment can be for.
Purpose = Literal["monthly", "extra"]


@dataclass(frozen=True, slots=True)
class Target:
    """What a payment is for: the months, or one extra fee.

    :ivar purpose: ``monthly`` or ``extra``
    :ivar extra_fee_id: The fee, exactly when the purpose is ``extra``
    """

    purpose: Purpose
    extra_fee_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class FeeRef:
    """An extra fee as a payment names it: enough to label it.

    :ivar extra_fee_id: The fee
    :ivar purpose: ``exam`` or ``other``
    :ivar label: The name families see
    :ivar due_on: When it is due
    """

    extra_fee_id: uuid.UUID
    purpose: str
    label: str
    due_on: dt.date


def fee_refs(
    session: Session, fee_ids: list[uuid.UUID | None]
) -> dict[uuid.UUID, FeeRef]:
    """Label several fees in one statement.

    :param session: The session to read through
    :param fee_ids: The fees; Nones are ignored
    :return: Fee id to its label
    """
    wanted = {fee_id for fee_id in fee_ids if fee_id is not None}
    if not wanted:
        return {}
    return {
        fee.id: FeeRef(
            extra_fee_id=fee.id, purpose=fee.purpose, label=fee.label, due_on=fee.due_on
        )
        for fee in session.scalars(
            sa.select(ExtraFee).where(ExtraFee.id == any_of(wanted))
        )
    }


def fees_charging_all(
    session: Session, *, batch_id: uuid.UUID, enrollment_ids: list[uuid.UUID]
) -> list[FeeRef]:
    """List the batch's fees every one of these seats was charged, soonest first.

    What a payment covering these seats can be applied to besides the
    monthly fee: a fee one of them was never charged cannot settle that
    child's share.

    :param session: The session to read through
    :param batch_id: The batch
    :param enrollment_ids: The seats a payment covers
    :return: The fees
    """
    return fees_charging_each(session, {None: (batch_id, enrollment_ids)})[None]


def fees_charging_each[K](
    session: Session, wanted: Mapping[K, tuple[uuid.UUID, Sequence[uuid.UUID]]]
) -> dict[K, list[FeeRef]]:
    """Answer :func:`fees_charging_all` for several payments in ONE statement.

    The verification queue asks this once per waiting payment; asked
    one payment at a time it was a statement each [C-13]. Each key's
    answer is exactly :func:`fees_charging_all`'s for its batch and
    seats: the fees of that batch, soonest first, that every one of its
    seats was charged.

    :param session: The session to read through
    :param wanted: Key to the batch and the seats one payment covers
    :return: Key to its fees; every key is present
    """
    found: dict[K, list[FeeRef]] = {key: [] for key in wanted}
    seats_wanted = {seat for _batch, seats in wanted.values() for seat in seats}
    if not seats_wanted:
        return found
    rows = session.execute(
        sa.select(ExtraFee, ExtraFeeCharge.enrollment_id)
        .join(ExtraFeeCharge, ExtraFeeCharge.extra_fee_id == ExtraFee.id)
        .where(
            ExtraFee.batch_id == any_of({batch for batch, _seats in wanted.values()}),
            ExtraFeeCharge.enrollment_id == any_of(seats_wanted),
        )
        .order_by(ExtraFee.due_on, ExtraFee.created_at, ExtraFee.id)
    ).all()
    for key, (batch_id, enrollment_ids) in wanted.items():
        mine = set(enrollment_ids)
        if not mine:
            continue
        seats: dict[uuid.UUID, set[uuid.UUID]] = {}
        fees: dict[uuid.UUID, ExtraFee] = {}
        for fee, seat in rows:
            if fee.batch_id == batch_id and seat in mine:
                fees[fee.id] = fee
                seats.setdefault(fee.id, set()).add(seat)
        found[key] = [
            FeeRef(
                extra_fee_id=fee.id,
                purpose=fee.purpose,
                label=fee.label,
                due_on=fee.due_on,
            )
            for fee_id, fee in fees.items()
            if seats[fee_id] == mine
        ]
    return found


#: The months, which is what a payment naming nothing is for.
MONTHLY: Final = Target(purpose="monthly")


def resolve_target(
    session: Session,
    *,
    purpose: str | None,
    extra_fee_id: uuid.UUID | None,
    batch_id: uuid.UUID,
) -> Target:
    """Check a requested purpose against the batch, or refuse.

    :param session: The session to read through
    :param purpose: ``monthly``, ``extra``, or None from an older build
    :param extra_fee_id: The fee named, if any
    :param batch_id: The batch every covered seat sits in
    :return: The checked target
    :raises ValidationError: ``extra`` naming no fee, a fee on a monthly
        payment, or a fee that is not this batch's
    """
    if purpose is None or purpose == "monthly":
        if extra_fee_id is not None:
            raise ValidationError(
                code="EXTRA_FEE_NOT_APPLICABLE",
                message_key="fees.extra.not_applicable",
            )
        return MONTHLY
    if purpose != "extra":
        raise ValidationError(
            code="PAYMENT_PURPOSE_UNKNOWN", message_key="fees.extra.purpose_unknown"
        )
    if extra_fee_id is None:
        raise ValidationError(
            code="EXTRA_FEE_REQUIRED", message_key="fees.extra.required"
        )
    found = session.scalars(
        sa.select(ExtraFee.id).where(
            ExtraFee.id == extra_fee_id, ExtraFee.batch_id == batch_id
        )
    ).one_or_none()
    if found is None:
        raise ValidationError(
            code="EXTRA_FEE_NOT_FOUND", message_key="fees.extra.not_found"
        )
    return Target(purpose="extra", extra_fee_id=extra_fee_id)


def charge_for(
    session: Session, *, extra_fee_id: uuid.UUID, enrollment_id: uuid.UUID
) -> ExtraFeeCharge:
    """One seat's charge under a fee, or refuse.

    :param session: The session to read through
    :param extra_fee_id: The fee
    :param enrollment_id: The seat
    :return: The charge
    :raises ValidationError: The seat was not charged this fee
    """
    charge = session.scalars(
        sa.select(ExtraFeeCharge).where(
            ExtraFeeCharge.extra_fee_id == extra_fee_id,
            ExtraFeeCharge.enrollment_id == enrollment_id,
        )
    ).one_or_none()
    if charge is None:
        raise ValidationError(
            code="EXTRA_FEE_NOT_CHARGED", message_key="fees.extra.not_charged"
        )
    return charge


def owed_for_target(
    session: Session, *, target: Target, enrollment_id: uuid.UUID
) -> Money:
    """Say what one seat owes for what a payment is for.

    :param session: The session to read through
    :param target: The months, or one fee
    :param enrollment_id: The seat
    :return: The outstanding, never negative
    :raises ValidationError: The seat was not charged the named fee
    """
    if target.extra_fee_id is None:
        return derive_for_enrollment(session, enrollment_id).total_outstanding
    charge = charge_for(
        session, extra_fee_id=target.extra_fee_id, enrollment_id=enrollment_id
    )
    return owed_on_charge(session, charge.id)


def owed_for_claim(session: Session, claim: PaymentClaim) -> Money:
    """Say what a claim's child owes for what the claim points at now.

    :param session: The session to read through
    :param claim: The claim
    :return: The outstanding, never negative
    """
    if claim.extra_fee_charge_id is not None:
        return owed_on_charge(session, claim.extra_fee_charge_id)
    return derive_for_enrollment(session, claim.enrollment_id).total_outstanding


def point_claim(
    session: Session,
    claim: PaymentClaim,
    *,
    target: Target,
    today: dt.date | None = None,
) -> None:
    """Point a claim at the months or at its seat's charge under a fee.

    The claim's ``period`` is the one shown beside it: the oldest unpaid
    month for a monthly claim, as :func:`app.fees.claims.record_claim`
    always resolved it, and the fee's due month for an extra one. Call
    only while the claim holds no decision -- a decided claim is
    withdrawn first, against the ledger it was settled in.

    :param session: The session to write through
    :param claim: The claim, undecided
    :param target: What it is for
    :param today: Bangladesh's date; the real clock by default
    :return: None
    :raises ValidationError: The seat was not charged the named fee
    """
    if target.extra_fee_id is None:
        claim.purpose = "monthly"
        claim.extra_fee_charge_id = None
        claim.period = oldest_unpaid_period(session, claim.enrollment_id) or str(
            Period.containing(today or bangladesh_today())
        )
        return
    charge = charge_for(
        session, extra_fee_id=target.extra_fee_id, enrollment_id=claim.enrollment_id
    )
    fee = session.get_one(ExtraFee, target.extra_fee_id)
    claim.purpose = "extra"
    claim.extra_fee_charge_id = charge.id
    claim.period = str(Period.containing(fee.due_on))
