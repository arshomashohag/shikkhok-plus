"""
One child's approved amount settling their months oldest first.

The figures were computed by hand from the fill order: each month takes
what is left, up to what it owes, starting with the oldest.
"""

import pytest

from app.money import Money, MoneyValidationError, settle_oldest_first

M = Money


def test_two_months_paid_in_full_leave_no_excess() -> None:
    result = settle_oldest_first(M("2000"), [M("1000"), M("1000")])
    assert result.receipts == (M("1000"), M("1000"))
    assert result.shortfalls == (Money.ZERO, Money.ZERO)
    assert result.excess == Money.ZERO


def test_a_short_amount_fills_the_oldest_month_first() -> None:
    result = settle_oldest_first(M("1500"), [M("1000"), M("1000")])
    assert result.receipts == (M("1000"), M("500"))
    assert result.shortfalls == (Money.ZERO, M("500"))
    assert result.excess == Money.ZERO


def test_less_than_one_month_leaves_every_later_month_short() -> None:
    result = settle_oldest_first(M("400"), [M("1000"), M("1000")])
    assert result.receipts == (M("400"), Money.ZERO)
    assert result.shortfalls == (M("600"), M("1000"))
    assert result.excess == Money.ZERO


def test_more_than_is_owed_returns_the_excess() -> None:
    result = settle_oldest_first(M("2500"), [M("1000"), M("1000")])
    assert result.receipts == (M("1000"), M("1000"))
    assert result.excess == M("500")


def test_nothing_owed_is_all_excess() -> None:
    result = settle_oldest_first(M("1000"), [])
    assert result.receipts == ()
    assert result.shortfalls == ()
    assert result.excess == M("1000")


def test_receipts_plus_excess_equal_the_amount() -> None:
    result = settle_oldest_first(M("1234.56"), [M("300"), M("0"), M("900.10")])
    assert Money.sum([*result.receipts, result.excess]) == M("1234.56")


def test_a_negative_amount_is_refused() -> None:
    with pytest.raises(MoneyValidationError, match="SETTLEMENT_AMOUNT_NEGATIVE"):
        settle_oldest_first(M("-1"), [M("1000")])


def test_a_negative_outstanding_is_refused() -> None:
    with pytest.raises(MoneyValidationError, match="SETTLEMENT_OWED_NEGATIVE"):
        settle_oldest_first(M("1"), [M("-1")])
