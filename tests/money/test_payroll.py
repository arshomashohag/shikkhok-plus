"""Payroll arithmetic [P1, D12]: a named test per basis and per adjustment kind.

Written before the code. Every expected figure is computed here from the
inputs, so a wrong answer is visible as arithmetic rather than trusted as
output:

* ``monthly``: the base is the rate.
* ``per_class``: the base is the rate times the classes HELD; none held is
  zero, never the rate.
* ``none``: no base, and no line is ever drawn for it.
* An addition raises what is owed; a deduction lowers it; a deduction that
  would take it below zero is refused, because the wire and the ledger
  carry no negative money.
* Paid is the sum of payments; remaining is owed less paid, and paying
  past it is refused.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.money import Money, MoneyValidationError, salary_base, salary_totals


def test_a_monthly_base_is_the_rate() -> None:
    """8000.00 a month is 8000.00, whatever the classes."""
    assert salary_base("monthly", Money("8000.00"), classes_held=0) == Money("8000.00")
    assert salary_base("monthly", Money("8000.00"), classes_held=12) == Money("8000.00")


def test_a_per_class_base_is_the_rate_times_classes_held() -> None:
    """500.00 a class for 13 held classes is 6500.00."""
    assert salary_base("per_class", Money("500.00"), classes_held=13) == Money(
        "6500.00"
    )


def test_a_per_class_base_with_none_held_is_zero() -> None:
    """No classes held earns nothing, not one class's rate."""
    assert salary_base("per_class", Money("500.00"), classes_held=0) == Money.ZERO


def test_a_per_class_rate_with_paisa_multiplies_exactly() -> None:
    """333.33 for 3 classes is 999.99, with no rounding to hide."""
    assert salary_base("per_class", Money("333.33"), classes_held=3) == Money("999.99")


def test_an_unpaid_basis_has_no_base() -> None:
    """``none`` is refused: no line is drawn for an unpaid staff member."""
    with pytest.raises(MoneyValidationError):
        salary_base("none", Money("1.00"), classes_held=1)


def test_a_negative_class_count_is_refused() -> None:
    """A count below zero is a bug upstream, not a refund."""
    with pytest.raises(MoneyValidationError):
        salary_base("per_class", Money("500.00"), classes_held=-1)


def test_an_unknown_basis_is_refused() -> None:
    """Only the two paid bases have a base."""
    with pytest.raises(MoneyValidationError):
        salary_base("share", Money("500.00"), classes_held=1)


def test_an_addition_raises_what_is_owed() -> None:
    """8000.00 with a 500.00 bonus owes 8500.00."""
    totals = salary_totals(
        Money("8000.00"), additions=[Money("500.00")], deductions=[], payments=[]
    )
    assert (totals.owed, totals.paid, totals.remaining) == (
        Money("8500.00"),
        Money.ZERO,
        Money("8500.00"),
    )


def test_a_deduction_lowers_what_is_owed() -> None:
    """8000.00 less a 1000.00 advance recovered owes 7000.00."""
    totals = salary_totals(
        Money("8000.00"), additions=[], deductions=[Money("1000.00")], payments=[]
    )
    assert totals.owed == Money("7000.00")


def test_additions_and_deductions_together() -> None:
    """6500.00 + 500.00 + 250.00 - 1000.00 - 300.00 = 5950.00."""
    totals = salary_totals(
        Money("6500.00"),
        additions=[Money("500.00"), Money("250.00")],
        deductions=[Money("1000.00"), Money("300.00")],
        payments=[],
    )
    assert totals.owed == Money("5950.00")


def test_deductions_may_bring_it_to_zero_and_no_further() -> None:
    """Exactly the base is allowed; one paisa more is refused."""
    zero = salary_totals(
        Money("1000.00"), additions=[], deductions=[Money("1000.00")], payments=[]
    )
    assert zero.owed == Money.ZERO
    with pytest.raises(MoneyValidationError):
        salary_totals(
            Money("1000.00"), additions=[], deductions=[Money("1000.01")], payments=[]
        )


def test_payments_count_against_what_is_owed() -> None:
    """7000.00 owed, 3000.00 then 2500.00 paid, leaves 1500.00."""
    totals = salary_totals(
        Money("7000.00"),
        additions=[],
        deductions=[],
        payments=[Money("3000.00"), Money("2500.00")],
    )
    assert (totals.paid, totals.remaining) == (Money("5500.00"), Money("1500.00"))


def test_paying_past_what_is_owed_is_refused() -> None:
    """A payment that would make remaining negative is refused."""
    with pytest.raises(MoneyValidationError):
        salary_totals(
            Money("1000.00"), additions=[], deductions=[], payments=[Money("1000.01")]
        )


amounts = st.integers(min_value=0, max_value=10_000_00).map(
    lambda paisa: Money(f"{paisa // 100}.{paisa % 100:02d}")
)


@given(
    base=amounts,
    additions=st.lists(amounts, max_size=4),
    deductions=st.lists(amounts, max_size=4),
)
def test_owed_is_base_plus_additions_less_deductions_or_refused(
    base: Money, additions: list[Money], deductions: list[Money]
) -> None:
    """The invariant: owed + deductions == base + additions, owed >= 0."""
    gross = base + Money.sum(additions)
    taken = Money.sum(deductions)
    if taken > gross:
        with pytest.raises(MoneyValidationError):
            salary_totals(base, additions=additions, deductions=deductions, payments=[])
        return
    totals = salary_totals(
        base, additions=additions, deductions=deductions, payments=[]
    )
    assert totals.owed + taken == gross
    assert totals.remaining == totals.owed
