"""What a student can pay right now (S3).

"Which fee are you paying?" lists one line per seat: the month a claim
would be recorded against -- the oldest unpaid period, which is the
period :func:`~app.fees.claims.submit_claim` itself chooses -- with what
is still owed on it and when it was due.

**Only seats the student ACCEPTED** [BR1.1]: a pending invitation is not
yet their fee. **A seat whose payment is already waiting** for the
teacher is listed apart, so the screen can say why it is not offered
rather than letting a second claim race the first.

Four statements whatever the student's size: seats, ledger, due dates
and waiting claims, then a fold in memory.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.analytics.seats import due_dates_for_seats, ledger_for_seats
from app.authz.lenses import StudentLens
from app.db.models import Batch, Enrollment, PaymentClaim
from app.money import Money, derive

__all__ = ["Payable", "Payables", "WaitingPayment", "payables"]


@dataclass(frozen=True, slots=True)
class Payable:
    """One month a student can pay for.

    :ivar enrollment_id: Their seat
    :ivar batch_name: The batch
    :ivar period: The month a claim would be recorded against
    :ivar amount_due: What is still owed on that month
    :ivar due_date: When it was due, if a cycle records one
    """

    enrollment_id: uuid.UUID
    batch_name: str
    period: str
    amount_due: Money
    due_date: dt.date | None


@dataclass(frozen=True, slots=True)
class WaitingPayment:
    """A seat not offered because its payment is being checked.

    :ivar batch_name: The batch
    :ivar period: The month the waiting payment is for
    """

    batch_name: str
    period: str


@dataclass(frozen=True, slots=True)
class Payables:
    """Everything the "Pay a fee" screen offers or explains.

    :ivar payable: Months to pay for, earliest due first
    :ivar waiting: Seats whose payment is already being checked
    """

    payable: list[Payable]
    waiting: list[WaitingPayment]


def payables(session: Session, *, lens: StudentLens) -> Payables:
    """List what this student can pay for, and what is already waiting.

    :param session: The session to read through
    :param lens: The student lens
    :return: The payable months and the waiting seats
    """
    seats = session.execute(
        sa.select(Enrollment.id, Batch.name)
        .join(Batch, Batch.id == Enrollment.batch_id)
        .where(
            Enrollment.student_account_id == lens.account_id,
            Enrollment.student_decision == "accepted",
        )
        .order_by(Batch.name, Enrollment.id)
    ).all()
    seat_ids = [seat_id for seat_id, _ in seats]
    ledger = ledger_for_seats(session, seat_ids)
    due = due_dates_for_seats(session, seat_ids)
    pending = dict(
        session.execute(
            sa.select(PaymentClaim.enrollment_id, sa.func.min(PaymentClaim.period))
            .where(
                PaymentClaim.enrollment_id.in_(seat_ids),
                PaymentClaim.status == "pending",
            )
            .group_by(PaymentClaim.enrollment_id)
        ).all()
    )

    payable: list[Payable] = []
    waiting: list[WaitingPayment] = []
    for seat_id, batch_name in seats:
        if seat_id in pending:
            waiting.append(
                WaitingPayment(batch_name=batch_name, period=pending[seat_id])
            )
            continue
        per_cycle = derive(ledger[seat_id]).per_cycle
        owing = sorted(p for p, balance in per_cycle.items() if balance.is_positive())
        if not owing:
            continue
        period = owing[0]
        payable.append(
            Payable(
                enrollment_id=seat_id,
                batch_name=batch_name,
                period=period,
                amount_due=per_cycle[period],
                due_date=due[seat_id].get(period),
            )
        )

    payable.sort(key=lambda row: (row.due_date or dt.date.max, row.batch_name))
    return Payables(payable=payable, waiting=waiting)
