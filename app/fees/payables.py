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
from app.fees.overdue import days_overdue
from app.local_time import bangladesh_today
from app.money import Money, derive

__all__ = [
    "Payable",
    "Payables",
    "WaitingPayment",
    "payables",
    "payables_for_seats",
]


@dataclass(frozen=True, slots=True)
class Payable:
    """One month a student can pay for.

    :ivar enrollment_id: Their seat
    :ivar batch_name: The batch
    :ivar period: The month a claim would be recorded against
    :ivar amount_due: What is still owed on that month
    :ivar due_date: When it was due, if a cycle records one
    :ivar total_due: Everything the seat owes, that month included
    :ivar later_periods: How many later months also owe
    :ivar days_late: Days past the oldest late due date, or None
    """

    enrollment_id: uuid.UUID
    batch_name: str
    period: str
    amount_due: Money
    due_date: dt.date | None
    total_due: Money = Money.ZERO
    later_periods: int = 0
    days_late: int | None = None


@dataclass(frozen=True, slots=True)
class WaitingPayment:
    """A seat not offered because its payment is being checked.

    :ivar batch_name: The batch
    :ivar period: The month the waiting payment is for
    :ivar amount: What was claimed
    :ivar channel: Which app it moved through
    :ivar submitted_at: When it was sent
    """

    batch_name: str
    period: str
    amount: Money = Money.ZERO
    channel: str = ""
    submitted_at: dt.datetime | None = None


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
    return payables_for_seats(session, [(seat_id, name) for seat_id, name in seats])


def payables_for_seats(
    session: Session, seats: list[tuple[uuid.UUID, str]], today: dt.date | None = None
) -> Payables:
    """List what can be paid on these seats, and what is already waiting.

    The caller has established that its lens reaches every seat.

    :param session: The session to read through
    :param seats: Each seat with its batch name
    :param today: Bangladesh's date, which lateness is measured on
    :return: The payable months and the waiting seats
    """
    on = today or bangladesh_today()
    seat_ids = [seat_id for seat_id, _ in seats]
    ledger = ledger_for_seats(session, seat_ids)
    due = due_dates_for_seats(session, seat_ids)
    pending: dict[uuid.UUID, PaymentClaim] = {}
    for waiting_claim in session.scalars(
        sa.select(PaymentClaim)
        .where(
            PaymentClaim.enrollment_id.in_(seat_ids),
            PaymentClaim.status == "pending",
        )
        .order_by(PaymentClaim.submitted_at)
    ):
        pending.setdefault(waiting_claim.enrollment_id, waiting_claim)

    payable: list[Payable] = []
    waiting: list[WaitingPayment] = []
    for seat_id, batch_name in seats:
        claim = pending.get(seat_id)
        if claim is not None:
            waiting.append(
                WaitingPayment(
                    batch_name=batch_name,
                    period=claim.period,
                    amount=claim.claimed_amount,
                    channel=claim.channel,
                    submitted_at=claim.submitted_at,
                )
            )
            continue
        derived = derive(ledger[seat_id])
        per_cycle = derived.per_cycle
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
                total_due=derived.total_outstanding,
                later_periods=len(owing) - 1,
                days_late=days_overdue(per_cycle, due[seat_id], on),
            )
        )

    payable.sort(key=lambda row: (row.due_date or dt.date.max, row.batch_name))
    return Payables(payable=payable, waiting=waiting)
