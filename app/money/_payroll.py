"""Payroll arithmetic [P1, D12]: a salary's base, and what is owed and paid.

**Here, inside the money module, and nowhere else.** A per-class salary is
a rate times a count, which is a multiplication; the module's rule is that
every multiplication is a named operation with one declared rounding, so
the count becomes a rate through :meth:`Money.apply_rate` here rather than
an arithmetic expression at a call site.

**No negative money leaves this module.** Deductions larger than the base
and the additions together are refused, as is a payment past what is
owed: both would mean a negative amount the wire and the ledger cannot
carry. A salary that should go negative is a correction somewhere else.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from ._errors import MoneyValidationError
from ._money import Money

__all__ = ["SalaryTotals", "salary_base", "salary_totals"]

#: The two bases that pay [D12]; ``none`` pays nothing and draws no line.
PAID_BASES = ("monthly", "per_class")


@dataclass(frozen=True, slots=True)
class SalaryTotals:
    """One salary line's figures, all derived.

    :ivar owed: The base, plus additions, less deductions
    :ivar paid: Everything paid against it
    :ivar remaining: What is still owed
    """

    owed: Money
    paid: Money
    remaining: Money


def salary_base(basis: str, rate: Money, *, classes_held: int) -> Money:
    """Compute a salary's base for one month.

    :param basis: ``monthly`` or ``per_class``
    :param rate: The salary, or the rate for each class
    :param classes_held: The classes this person held in the month; read
        only for ``per_class``
    :return: The base
    :raises MoneyValidationError: An unpaid or unknown basis, or a
        negative class count
    """
    if basis not in PAID_BASES:
        raise MoneyValidationError(
            f"{basis!r} pays no salary; no line is drawn for it."
        )
    if classes_held < 0:
        raise MoneyValidationError("A count of classes held cannot be negative.")
    if basis == "monthly":
        return rate
    return rate.apply_rate(Decimal(classes_held))


def salary_totals(
    base: Money,
    *,
    additions: Sequence[Money],
    deductions: Sequence[Money],
    payments: Sequence[Money],
) -> SalaryTotals:
    """Fold a salary line into what is owed, paid and remaining.

    :param base: The line's base
    :param additions: Every addition, each non-negative
    :param deductions: Every deduction, each non-negative
    :param payments: Every payment made against it
    :return: The three figures
    :raises MoneyValidationError: Deductions exceed the base and the
        additions, or the payments exceed what is owed
    """
    gross = base + Money.sum(additions)
    taken = Money.sum(deductions)
    if taken > gross:
        raise MoneyValidationError(
            "Deductions larger than the salary would leave it below zero."
        )
    owed = gross - taken
    paid = Money.sum(payments)
    if paid > owed:
        raise MoneyValidationError("Payments larger than the salary owed.")
    return SalaryTotals(owed=owed, paid=paid, remaining=owed - paid)
