"""A child's fee history for their guardian (G3).

One line per batch per month, newest month first: what the month charged
and where its payment stands -- due, sent and being checked, or approved
on a date through an app. "Paid in 2026" is the sum of payments approved
this year, so the guardian has the total without adding anything up.

Read through each seat's own fee history with the guardian's lens, so
the per-seat acceptance check is the fee module's, not this module's.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens
from app.db.models import PaymentClaim
from app.fees.views import enrollment_fee_history
from app.guardians.children import Child
from app.local_time import DHAKA, bangladesh_today
from app.money import Money

__all__ = ["ChildPayments", "LineState", "PaymentLine", "child_payments"]

#: Where one month's payment stands.
LineState = Literal["paid", "partly_paid", "waived", "verifying", "due"]


@dataclass(frozen=True, slots=True)
class PaymentLine:
    """One batch's fee in one month.

    :ivar enrollment_id: The seat
    :ivar batch_name: The batch
    :ivar period: ``YYYY-MM``
    :ivar amount: What the month charged
    :ivar state: Where its payment stands
    :ivar due_date: When it was due
    :ivar sent_on: When the latest payment was sent, if any
    :ivar decided_on: When that payment was approved, if it was
    :ivar channel: Which app it moved through, if any
    """

    enrollment_id: uuid.UUID
    batch_name: str
    period: str
    amount: Money
    state: LineState
    due_date: dt.date
    sent_on: dt.date | None
    decided_on: dt.date | None
    channel: str | None


@dataclass(frozen=True, slots=True)
class ChildPayments:
    """A child's fee history.

    :ivar year: The year the total covers
    :ivar paid_this_year: Payments approved this year, summed
    :ivar lines: Every line, newest month first, then by batch
    """

    year: int
    paid_this_year: Money
    lines: list[PaymentLine]


def child_payments(
    session: Session, *, lens: GuardianLens, child: Child, today: dt.date | None = None
) -> ChildPayments:
    """Build one child's fee history.

    :param session: The session to read through
    :param lens: The guardian lens, re-checked per seat by the fee read
    :param child: The child, from :func:`~app.guardians.children.child_of`
    :param today: Bangladesh's date, which picks the year
    :return: The history and this year's total
    """
    year = (today or bangladesh_today()).year
    seat_ids = [seat.enrollment_id for seat in child.seats]
    latest: dict[tuple[uuid.UUID, str], PaymentClaim] = {}
    paid = Money.ZERO
    for row in session.scalars(
        sa.select(PaymentClaim)
        .where(PaymentClaim.enrollment_id.in_(seat_ids))
        .order_by(PaymentClaim.submitted_at)
    ):
        if row.status != "rejected":
            latest[(row.enrollment_id, row.period)] = row
        approved = row.approved_amount
        if (
            approved is not None
            and row.verified_at is not None
            and row.verified_at.astimezone(DHAKA).year == year
        ):
            paid = paid + approved

    lines: list[PaymentLine] = []
    for seat in child.seats:
        history = enrollment_fee_history(
            session, lens=lens, enrollment_id=seat.enrollment_id
        )
        for cycle in history.cycles:
            claim = latest.get((seat.enrollment_id, cycle.period))
            pending = claim is not None and claim.status == "pending"
            lines.append(
                PaymentLine(
                    enrollment_id=seat.enrollment_id,
                    batch_name=seat.batch_name,
                    period=cycle.period,
                    amount=cycle.charged,
                    state=_state_of(cycle.status, pending=pending),
                    due_date=cycle.due_date,
                    sent_on=claim.submitted_at.astimezone(DHAKA).date()
                    if claim
                    else None,
                    decided_on=(
                        claim.verified_at.astimezone(DHAKA).date()
                        if claim and claim.verified_at and not pending
                        else None
                    ),
                    channel=claim.channel if claim else None,
                )
            )
    lines.sort(key=lambda line: (_newest_first(line.period), line.batch_name))
    return ChildPayments(year=year, paid_this_year=paid, lines=lines)


def _state_of(status: str, *, pending: bool) -> LineState:
    """Name where a month's payment stands.

    :param status: The cycle's server status
    :param pending: Whether a payment for it is waiting to be checked
    :return: The line's state
    """
    if pending:
        return "verifying"
    if status == "paid":
        return "paid"
    if status == "partly_paid":
        return "partly_paid"
    if status == "waived":
        return "waived"
    return "due"


def _newest_first(period: str) -> int:
    """Order periods newest first.

    :param period: ``YYYY-MM``
    :return: A key that sorts later months earlier
    """
    year, month = period.split("-")
    return -(int(year) * 12 + int(month))
