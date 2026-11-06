"""A centre's payroll: drawing a month, adjusting, approving, paying [P1].

**Every figure is folded by :mod:`app.money`.** This module reads rows and
hands amounts to :func:`app.money.salary_base` and
:func:`app.money.salary_totals`; it adds, multiplies and compares no money
itself.

**A draft is live, an approved line is frozen.** While a line is a draft
its class count and base are computed on every read from the classes that
person held that month, so a class marked held this afternoon is in
tonight's figure. Approving stores the count and the base, and nothing
read afterwards changes them [P1 design: "a class edited next month never
silently changes a salary already approved"].

**Paying records an expense** against the line, with the expense's own
replay key, so the month's summary counts salary as money out and a lost
response resent pays once. Paid and remaining are derived from the line's
standing expenses; voiding one restores what remains.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.centres.service import centre_of
from app.db.models import (
    Batch,
    Expense,
    Owner,
    OwnerMember,
    SalaryAdjustment,
    SalaryLine,
    Staff,
)
from app.db.models import Session as ClassSession
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.expenses.service import ExpenseDraft, month_of, record_expense
from app.fees.periods import Period
from app.local_time import bangladesh_today
from app.money import Money, MoneyValidationError, salary_base, salary_totals

__all__ = [
    "AdjustmentView",
    "LineView",
    "PaymentView",
    "add_adjustment",
    "approve",
    "draw_month",
    "my_pay",
    "pay",
    "remove_adjustment",
]


@dataclass(frozen=True, slots=True)
class AdjustmentView:
    """One adjustment on a line.

    :ivar adjustment_id: The adjustment
    :ivar kind: ``addition`` or ``deduction``
    :ivar label: What it is for
    :ivar amount: How much
    """

    adjustment_id: uuid.UUID
    kind: str
    label: str
    amount: Money


@dataclass(frozen=True, slots=True)
class PaymentView:
    """One standing payment against a line.

    :ivar expense_id: The expense that records it
    :ivar amount: How much
    :ivar paid_on: When
    """

    expense_id: uuid.UUID
    amount: Money
    paid_on: dt.date


@dataclass(frozen=True, slots=True)
class LineView:
    """One salary line with every figure folded.

    :ivar line_id: The line
    :ivar staff_id: The person
    :ivar staff_name: The name the centre typed
    :ivar centre_name: The centre
    :ivar period: ``YYYY-MM``
    :ivar basis: ``monthly`` or ``per_class``
    :ivar rate: The salary or the rate per class
    :ivar classes_held: Classes held, frozen once approved
    :ivar base: The base, frozen once approved
    :ivar owed: Base plus additions less deductions
    :ivar paid: Everything paid against it
    :ivar remaining: What is still owed
    :ivar status: ``draft`` or ``approved``
    :ivar adjustments: Its adjustments, oldest first
    :ivar payments: Its standing payments, oldest first
    """

    line_id: uuid.UUID
    staff_id: uuid.UUID
    staff_name: str
    centre_name: str
    period: str
    basis: str
    rate: Money
    classes_held: int
    base: Money
    owed: Money
    paid: Money
    remaining: Money
    status: str
    adjustments: list[AdjustmentView] = field(default_factory=list)
    payments: list[PaymentView] = field(default_factory=list)


def _period(key: str) -> Period:
    """Read a ``YYYY-MM`` month.

    :param key: The month
    :return: The period
    :raises ValidationError: Not a real month
    """
    return month_of(key)


def _classes_held(
    session: DbSession, *, staff: Staff, owner_id: uuid.UUID, period: Period
) -> int:
    """Count the classes this person held at this centre in the month.

    :param session: The session to read through
    :param staff: The staff record
    :param owner_id: The centre
    :param period: The month
    :return: The count; zero for someone with no app membership
    """
    if staff.member_id is None:
        return 0
    return int(
        session.scalar(
            sa.select(sa.func.count())
            .select_from(ClassSession)
            .join(Batch, Batch.id == ClassSession.batch_id)
            .where(
                Batch.owner_id == owner_id,
                ClassSession.teacher_member_id == staff.member_id,
                ClassSession.status == "held",
                ClassSession.date >= period.first_day(),
                ClassSession.date <= period.last_day(),
            )
        )
        or 0
    )


def _view(session: DbSession, line: SalaryLine) -> LineView:
    """Fold one line's figures, live for a draft and frozen once approved.

    :param session: The session to read through
    :param line: The line
    :return: Its view
    """
    staff = session.get_one(Staff, line.staff_id)  # the line cascades with it
    centre = session.get(Owner, line.owner_id)
    if line.status == "approved":
        classes = line.classes_held or 0
        base = line.base_amount or Money.ZERO
    else:
        classes = _classes_held(
            session,
            staff=staff,
            owner_id=line.owner_id,
            period=Period.parse(line.period),
        )
        base = salary_base(line.basis, line.rate, classes_held=classes)
    adjustments = [
        AdjustmentView(row.id, row.kind, row.label, row.amount)
        for row in session.scalars(
            sa.select(SalaryAdjustment)
            .where(SalaryAdjustment.salary_line_id == line.id)
            .order_by(SalaryAdjustment.created_at, SalaryAdjustment.id)
        )
    ]
    payments = [
        PaymentView(row.id, row.amount, row.spent_on)
        for row in session.scalars(
            sa.select(Expense)
            .where(Expense.salary_line_id == line.id, Expense.voided_at.is_(None))
            .order_by(Expense.spent_on, Expense.created_at, Expense.id)
        )
    ]
    totals = salary_totals(
        base,
        additions=[a.amount for a in adjustments if a.kind == "addition"],
        deductions=[a.amount for a in adjustments if a.kind == "deduction"],
        payments=[p.amount for p in payments],
    )
    return LineView(
        line_id=line.id,
        staff_id=line.staff_id,
        staff_name=staff.display_name,
        centre_name=(centre.name if centre is not None else None) or "",
        period=line.period,
        basis=line.basis,
        rate=line.rate,
        classes_held=classes,
        base=base,
        owed=totals.owed,
        paid=totals.paid,
        remaining=totals.remaining,
        status=line.status,
        adjustments=adjustments,
        payments=payments,
    )


def draw_month(
    session: DbSession, *, lens: TeacherLens, period_key: str
) -> list[LineView]:
    """Draw a line for every paid staff member working the month, once.

    Idempotent on ``(staff_id, period)`` through the database constraint,
    as fee cycles are: drawing the month again draws nothing new and
    leaves every existing line, draft or approved, as it is. Commits.

    :param session: The session to write through
    :param lens: The manager's lens on the centre
    :param period_key: ``YYYY-MM``
    :return: Every line the month has, by name
    :raises ConflictError: Not a centre
    :raises ValidationError: Not a real month
    """
    centre = centre_of(session, lens)
    period = _period(period_key)
    working = session.scalars(
        sa.select(Staff).where(
            Staff.owner_id == centre.id,
            Staff.pay_basis != "none",
            Staff.joined_on <= period.last_day(),
            sa.or_(Staff.left_on.is_(None), Staff.left_on >= period.first_day()),
        )
    ).all()
    now = dt.datetime.now(tz=dt.UTC)
    for staff in working:
        if staff.pay_rate is None:  # pragma: no cover - the staff CHECK forbids it
            continue
        session.execute(
            pg_insert(SalaryLine)
            .values(
                id=uuid.uuid4(),
                owner_id=centre.id,
                staff_id=staff.id,
                period=str(period),
                basis=staff.pay_basis,
                rate=staff.pay_rate,
                status="draft",
                created_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_salary_line_staff_period")
        )
    session.commit()
    return month_lines(session, lens=lens, period_key=str(period))


def month_lines(
    session: DbSession, *, lens: TeacherLens, period_key: str
) -> list[LineView]:
    """List the month's lines, by the staff member's name.

    :param session: The session to read through
    :param lens: The manager's lens on the centre
    :param period_key: ``YYYY-MM``
    :return: The lines
    :raises ConflictError: Not a centre
    :raises ValidationError: Not a real month
    """
    centre = centre_of(session, lens)
    period = _period(period_key)
    lines = session.scalars(
        sa.select(SalaryLine)
        .join(Staff, Staff.id == SalaryLine.staff_id)
        .where(SalaryLine.owner_id == centre.id, SalaryLine.period == str(period))
        .order_by(sa.func.lower(Staff.display_name), SalaryLine.id)
    ).all()
    return [_view(session, line) for line in lines]


def _owned_line(
    session: DbSession, lens: TeacherLens, line_id: uuid.UUID, *, lock: bool = True
) -> SalaryLine:
    """Return this centre's line, refusing any other id alike.

    :param session: The session to read through
    :param lens: The manager's lens on the centre
    :param line_id: The line
    :param lock: Whether to lock it for a write
    :return: The line
    :raises ConflictError: Not a centre
    :raises AuthorizationError: No such line in this centre
    """
    centre = centre_of(session, lens)
    query = sa.select(SalaryLine).where(
        SalaryLine.id == line_id, SalaryLine.owner_id == centre.id
    )
    line = session.scalar(query.with_for_update() if lock else query)
    if line is None:
        raise AuthorizationError(
            code="NO_TEACHER_LENS", message_key="authz.lens.not_available"
        )
    return line


def _refuse_approved(line: SalaryLine) -> None:
    """Refuse a change to an approved line.

    :param line: The line
    :raises ConflictError: It is approved
    """
    if line.status == "approved":
        raise ConflictError(code="SALARY_APPROVED", message_key="payroll.approved")


def _check_not_below_zero(session: DbSession, line: SalaryLine) -> LineView:
    """Fold the line, turning a below-zero salary into a refusal.

    :param session: The session to read through
    :param line: The line, with its pending changes flushed
    :return: Its view
    :raises ValidationError: Deductions exceed the salary
    """
    try:
        return _view(session, line)
    except MoneyValidationError as error:
        session.rollback()
        raise ValidationError(
            code="SALARY_BELOW_ZERO", message_key="payroll.below_zero"
        ) from error


def add_adjustment(
    session: DbSession,
    *,
    lens: TeacherLens,
    line_id: uuid.UUID,
    kind: str,
    label: str,
    amount: Money,
) -> LineView:
    """Add a named addition or deduction to a draft line. Commits.

    :param session: The session to write through
    :param lens: The manager's lens on the centre
    :param line_id: The line
    :param kind: ``addition`` or ``deduction``
    :param label: What it is for
    :param amount: How much, above zero
    :return: The line, refolded
    :raises ConflictError: The line is approved
    :raises ValidationError: The amount is not above zero, the label is
        blank, or a deduction would take the salary below zero
    """
    line = _owned_line(session, lens, line_id)
    _refuse_approved(line)
    if not amount.is_positive():
        raise ValidationError(
            code="SALARY_ADJUSTMENT_NOT_POSITIVE",
            message_key="payroll.amount_not_positive",
        )
    if not label.strip():
        raise ValidationError(code="NAME_REQUIRED", message_key="centre.name.required")
    session.add(
        SalaryAdjustment(
            salary_line_id=line.id,
            kind=kind,
            label=label.strip(),
            amount=amount,
            created_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    session.flush()
    view = _check_not_below_zero(session, line)
    session.commit()
    return view


def remove_adjustment(
    session: DbSession,
    *,
    lens: TeacherLens,
    line_id: uuid.UUID,
    adjustment_id: uuid.UUID,
) -> LineView:
    """Remove an adjustment from a draft line. Commits.

    :param session: The session to write through
    :param lens: The manager's lens on the centre
    :param line_id: The line
    :param adjustment_id: The adjustment
    :return: The line, refolded
    :raises AuthorizationError: No such adjustment on this line
    :raises ConflictError: The line is approved
    :raises ValidationError: Removing an addition would take it below zero
    """
    line = _owned_line(session, lens, line_id)
    _refuse_approved(line)
    deleted = session.execute(
        sa.delete(SalaryAdjustment).where(
            SalaryAdjustment.id == adjustment_id,
            SalaryAdjustment.salary_line_id == line.id,
        )
    )
    if getattr(deleted, "rowcount", 0) == 0:
        raise AuthorizationError(
            code="NO_TEACHER_LENS", message_key="authz.lens.not_available"
        )
    view = _check_not_below_zero(session, line)
    session.commit()
    return view


def approve(session: DbSession, *, lens: TeacherLens, line_id: uuid.UUID) -> LineView:
    """Approve a draft line, freezing its class count and base. Commits.

    Approving twice returns the line unchanged.

    :param session: The session to write through
    :param lens: The manager's lens on the centre
    :param line_id: The line
    :return: The line, frozen
    """
    line = _owned_line(session, lens, line_id)
    if line.status == "draft":
        live = _view(session, line)
        line.classes_held = live.classes_held
        line.base_amount = live.base
        line.status = "approved"
        line.approved_by_account_id = lens.account_id
        line.approved_at = dt.datetime.now(tz=dt.UTC)
        session.commit()
    return _view(session, line)


def pay(
    session: DbSession,
    *,
    lens: TeacherLens,
    line_id: uuid.UUID,
    amount: Money,
    paid_on: dt.date | None,
    client_mutation_id: uuid.UUID,
    note: str | None,
) -> LineView:
    """Record a payment against an approved line, as an expense.

    A resend under the same key is the expense module's replay and pays
    nothing twice. Commits through the expense writer.

    :param session: The session to write through
    :param lens: The manager's lens on the centre
    :param line_id: The line
    :param amount: How much, above zero
    :param paid_on: When, or None for today
    :param client_mutation_id: The retry key
    :param note: A note, such as a receipt number
    :return: The line, with the payment counted
    :raises ConflictError: The line is a draft, or the payment exceeds
        what remains
    """
    line = _owned_line(session, lens, line_id)
    if line.status != "approved":
        raise ConflictError(
            code="SALARY_NOT_APPROVED", message_key="payroll.not_approved"
        )
    replay = session.scalar(
        sa.select(Expense.id).where(
            Expense.recorded_by_account_id == lens.account_id,
            Expense.client_mutation_id == client_mutation_id,
        )
    )
    if replay is None:
        before = _view(session, line)
        if amount > before.remaining:
            raise ConflictError(code="SALARY_OVERPAID", message_key="payroll.overpaid")
        staff = session.get(Staff, line.staff_id)
        name = staff.display_name if staff is not None else ""
        # The line stays locked until the expense writer commits, in the
        # same transaction, so two payments at once cannot both pass the
        # remaining check.
        record_expense(
            session,
            lens=lens,
            draft=ExpenseDraft(
                category="salary",
                what=f"Salary {line.period}",
                amount=amount,
                spent_on=paid_on or bangladesh_today(),
                payee=name[:80] or None,
                note=note,
                client_mutation_id=client_mutation_id,
                salary_line_id=line.id,
            ),
        )
    return _view(session, session.get(SalaryLine, line.id) or line)


def my_pay(session: DbSession, *, account_id: uuid.UUID) -> list[LineView]:
    """List the caller's approved salary lines, newest month first [D15].

    Through ``staff.member_id`` and the caller's own live memberships, so
    a line reaches only the person it pays; drafts are the manager's
    working state and are not shown.

    :param session: The session to read through
    :param account_id: The authenticated account
    :return: Their lines, with adjustments and payments
    """
    lines = session.scalars(
        sa.select(SalaryLine)
        .join(Staff, Staff.id == SalaryLine.staff_id)
        .join(
            OwnerMember,
            sa.and_(
                OwnerMember.id == Staff.member_id,
                OwnerMember.account_id == account_id,
                OwnerMember.decision == "accepted",
                OwnerMember.revoked_at.is_(None),
            ),
        )
        .where(SalaryLine.status == "approved")
        .order_by(SalaryLine.period.desc(), SalaryLine.id)
    ).all()
    return [_view(session, line) for line in lines]
