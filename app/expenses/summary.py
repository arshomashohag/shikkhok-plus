"""One month's money, in and out, for one owner [0021].

**Cash basis, both sides.** Collected is what was approved for payments
the family says they paid during the month; spent is what was spent
during the month. Measuring one side by billing month and the other by
cash date would set two different months against each other.

**Every figure is folded here, never in a client.** The difference is
sent as an amount and a verdict -- ``surplus``, ``deficit`` or ``even``
-- because the wire carries no negative money and the client compares
nothing.

**What is still owed is today's figure**, not the month's: the monthly
fees from the same fold the Dues screen uses, and the extra fees from
their own ledger.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.analytics.seats import owing_ledger_for_seats, owned_seats
from app.authz.lenses import TeacherLens
from app.db.models import (
    Batch,
    Expense,
    ExtraFee,
    ExtraFeeCharge,
    PaymentClaim,
    PaymentSubmission,
)
from app.expenses.service import expenses_in_month
from app.fees.extra_ledger import live_charge_entries
from app.fees.periods import Period
from app.money import Money, derive

__all__ = ["FeeLine", "MonthSummary", "NetKind", "month_summary"]

NetKind = Literal["surplus", "deficit", "even"]


@dataclass(frozen=True, slots=True)
class FeeLine:
    """One extra fee's takings set against what was spent for it.

    :ivar extra_fee_id: The fee
    :ivar label: Its name
    :ivar collected: Everything paid against it, all time
    :ivar spent: Every standing expense tagged to it, all time
    """

    extra_fee_id: uuid.UUID
    label: str
    collected: Money
    spent: Money


@dataclass(frozen=True, slots=True)
class MonthSummary:
    """The month's figures.

    :ivar month: ``YYYY-MM``
    :ivar collected_monthly: Approved for the monthly fee
    :ivar collected_exam: Approved for exam fees
    :ivar collected_other: Approved for other fees
    :ivar collected_total: The three together
    :ivar spent_total: Standing expenses
    :ivar spent_by_category: Category to total, largest first
    :ivar net: The difference, never negative
    :ivar net_kind: Which way it goes
    :ivar owed_monthly: Monthly fees still owed today
    :ivar owed_extra: Exam and other fees still owed today
    :ivar extra_fees: Fees due this month or spent for this month
    """

    month: str
    collected_monthly: Money
    collected_exam: Money
    collected_other: Money
    collected_total: Money
    spent_total: Money
    spent_by_category: list[tuple[str, Money]]
    net: Money
    net_kind: NetKind
    owed_monthly: Money
    owed_extra: Money
    extra_fees: list[FeeLine]


def _collected(
    session: Session, *, lens: TeacherLens, month: Period
) -> dict[str, Money]:
    """Total what was approved for payments paid in the month, by purpose.

    :param session: The session to read through
    :param lens: The teacher lens
    :param month: The month
    :return: ``monthly``, ``exam`` and ``other`` to their totals
    """
    rows = session.execute(
        sa.select(PaymentClaim.approved_amount, PaymentClaim.purpose, ExtraFee.purpose)
        .join(
            PaymentSubmission,
            PaymentSubmission.id == PaymentClaim.payment_submission_id,
        )
        .join(Batch, Batch.id == PaymentSubmission.batch_id)
        .outerjoin(
            ExtraFeeCharge, ExtraFeeCharge.id == PaymentClaim.extra_fee_charge_id
        )
        .outerjoin(ExtraFee, ExtraFee.id == ExtraFeeCharge.extra_fee_id)
        .where(
            Batch.owner_id == lens.owner_id,
            PaymentSubmission.status == "approved",
            PaymentClaim.approved_amount.is_not(None),
            PaymentSubmission.paid_on >= month.first_day(),
            PaymentSubmission.paid_on <= month.last_day(),
        )
    ).all()
    found: dict[str, list[Money]] = {"monthly": [], "exam": [], "other": []}
    for amount, purpose, fee_kind in rows:
        key = (
            "monthly"
            if purpose == "monthly"
            else ("exam" if fee_kind == "exam" else "other")
        )
        if amount is not None:
            found[key].append(amount)
    return {key: Money.sum(amounts) for key, amounts in found.items()}


def _owed_monthly(session: Session, lens: TeacherLens) -> Money:
    """Monthly fees still owed today across every seat, as Dues folds them.

    :param session: The session to read through
    :param lens: The teacher lens
    :return: The total
    """
    seats = [seat.enrollment_id for seat in owned_seats(session, lens)]
    ledger = owing_ledger_for_seats(session, seats)
    return Money.sum([derive(ledger.get(seat, [])).total_outstanding for seat in seats])


def _owner_charges(
    session: Session, lens: TeacherLens
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Every charge under every fee this owner raised.

    :param session: The session to read through
    :param lens: The teacher lens
    :return: Charge id and fee id pairs
    """
    return [
        (row[0], row[1])
        for row in session.execute(
            sa.select(ExtraFeeCharge.id, ExtraFeeCharge.extra_fee_id)
            .join(ExtraFee, ExtraFee.id == ExtraFeeCharge.extra_fee_id)
            .join(Batch, Batch.id == ExtraFee.batch_id)
            .where(Batch.owner_id == lens.owner_id)
        ).all()
    ]


def _fee_lines(
    session: Session,
    *,
    lens: TeacherLens,
    month: Period,
    received: dict[uuid.UUID, Money],
) -> list[FeeLine]:
    """Fees due this month or with spending recorded this month.

    :param session: The session to read through
    :param lens: The teacher lens
    :param month: The month
    :param received: Fee id to everything paid against it
    :return: One line per such fee, soonest due first
    """
    tagged_this_month = (
        sa.select(Expense.extra_fee_id)
        .where(
            Expense.owner_id == lens.owner_id,
            Expense.extra_fee_id.is_not(None),
            Expense.spent_on >= month.first_day(),
            Expense.spent_on <= month.last_day(),
        )
        .scalar_subquery()
    )
    fees = list(
        session.scalars(
            sa.select(ExtraFee)
            .join(Batch, Batch.id == ExtraFee.batch_id)
            .where(
                Batch.owner_id == lens.owner_id,
                sa.or_(
                    sa.and_(
                        ExtraFee.due_on >= month.first_day(),
                        ExtraFee.due_on <= month.last_day(),
                    ),
                    ExtraFee.id.in_(tagged_this_month),
                ),
            )
            .order_by(ExtraFee.due_on, ExtraFee.id)
        )
    )
    if not fees:
        return []
    spent_rows = session.execute(
        sa.select(Expense.extra_fee_id, Expense.amount).where(
            Expense.extra_fee_id.in_([fee.id for fee in fees]),
            Expense.voided_at.is_(None),
        )
    ).all()
    spent: dict[uuid.UUID, list[Money]] = {}
    for fee_id, amount in spent_rows:
        if fee_id is not None:
            spent.setdefault(fee_id, []).append(amount)
    return [
        FeeLine(
            extra_fee_id=fee.id,
            label=fee.label,
            collected=received.get(fee.id, Money.ZERO),
            spent=Money.sum(spent.get(fee.id, [])),
        )
        for fee in fees
    ]


def month_summary(
    session: Session, *, lens: TeacherLens, month: Period
) -> MonthSummary:
    """Fold one month's money for this owner.

    :param session: The session to read through
    :param lens: The teacher lens
    :param month: The month
    :return: The summary
    """
    collected = _collected(session, lens=lens, month=month)
    collected_total = Money.sum(collected.values())
    kind: NetKind
    spending = expenses_in_month(session, lens=lens, month=month)
    if collected_total > spending.total:
        net, kind = collected_total - spending.total, "surplus"
    elif spending.total > collected_total:
        net, kind = spending.total - collected_total, "deficit"
    else:
        net, kind = Money.ZERO, "even"

    charges = _owner_charges(session, lens)
    entries = live_charge_entries(session, [charge for charge, _fee in charges])
    owed_extra: list[Money] = []
    received: dict[uuid.UUID, list[Money]] = {}
    for charge, fee in charges:
        totals = derive(entries[charge])
        owed_extra.append(totals.total_outstanding)
        received.setdefault(fee, []).append(totals.total_receipt)

    return MonthSummary(
        month=str(month),
        collected_monthly=collected["monthly"],
        collected_exam=collected["exam"],
        collected_other=collected["other"],
        collected_total=collected_total,
        spent_total=spending.total,
        spent_by_category=spending.by_category,
        net=net,
        net_kind=kind,
        owed_monthly=_owed_monthly(session, lens),
        owed_extra=Money.sum(owed_extra),
        extra_fees=_fee_lines(
            session,
            lens=lens,
            month=month,
            received={fee: Money.sum(amounts) for fee, amounts in received.items()},
        ),
    )
