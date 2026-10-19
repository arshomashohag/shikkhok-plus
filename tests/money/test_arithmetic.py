"""
Arithmetic on the Money value type.

Covers BR2.1-BR2.10 and BR3.1-BR3.2. Every expected value is computed in the
functional design, not read back from an implementation.
"""

from decimal import Decimal

import pytest

from app.money import Money, MoneyValidationError


class TestAddSubtract:
    """BR2.1, BR2.7 — Money-only operands; negatives permitted internally."""

    def test_add(self) -> None:
        assert Money("10.50") + Money("4.50") == Money("15.00")

    def test_subtract(self) -> None:
        assert Money("10.50") - Money("4.50") == Money("6.00")

    def test_add_bare_number_is_type_error(self) -> None:
        """BR2.1 — mypy catches this statically; this proves it at runtime."""
        with pytest.raises(TypeError):
            Money("10.00") + 5  # type: ignore[operator]

    def test_subtract_bare_number_is_type_error(self) -> None:
        with pytest.raises(TypeError):
            Money("10.00") - 5  # type: ignore[operator]

    def test_subtract_can_go_negative(self) -> None:
        """
        BR2.7 — permitted inside the module. A blanket non-negative type
        would make the per-cycle outstanding formula inexpressible, because
        that expression is genuinely negative before its floor is applied.
        """
        assert (Money("5.00") - Money("8.00")).amount == Decimal("-3.00")


class TestApplyRate:
    """BR2.2, BR2.10, BR3.1 — the named multiplication, and its domain."""

    def test_rounds_half_up_not_banker(self) -> None:
        """
        333.33 x 0.5 = 166.665 exactly, which quantizes half-up to 166.67.
        Under banker's rounding it would be 166.66. On a single value the
        one-paisa difference is invisible; across a ledger it is a
        reconciliation discrepancy nobody can explain.
        """
        assert Money("333.33").apply_rate(Decimal("0.5")) == Money("166.67")

    def test_float_rate_refused(self) -> None:
        """BR2.10 — a float rate is wrong before it is multiplied."""
        with pytest.raises(MoneyValidationError):
            Money("100.00").apply_rate(0.5)  # type: ignore[arg-type]

    def test_negative_rate_refused(self) -> None:
        """
        BR2.10 — would silently manufacture a negative Money that BR2.7 then
        permits to propagate. A reduction is a compensating entry [BR4.1],
        never a negative rate.
        """
        with pytest.raises(MoneyValidationError):
            Money("100.00").apply_rate(Decimal("-0.5"))

    def test_zero_rate_permitted(self) -> None:
        assert Money("100.00").apply_rate(Decimal("0")) == Money("0.00")

    def test_rate_above_one_permitted(self) -> None:
        """A late fee or multi-month catch-up charge is a rate above one."""
        assert Money("100.00").apply_rate(Decimal("1.5")) == Money("150.00")

    def test_rate_on_zero_is_zero(self) -> None:
        assert Money("0.00").apply_rate(Decimal("0.37")) == Money("0.00")


class TestRoundingAtTheHalf:
    """
    BR3.1 — half-up against banker's rounding, at five sampled halves.

    Three of the five genuinely diverge, which is why the mode is declared
    rather than inherited.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0.005", "0.01"),  # diverges: half-even gives 0.00
            ("0.015", "0.02"),  # agrees
            ("0.025", "0.03"),  # diverges: half-even gives 0.02
            ("1.005", "1.01"),  # diverges: half-even gives 1.00
            ("2.675", "2.68"),  # agrees - exact decimal is above the half
        ],
    )
    def test_half_up(self, raw: str, expected: str) -> None:
        assert Money(raw).amount == Decimal(expected)


class TestAllocate:
    """BR2.3, BR2.8, BR2.9 — exact-sum split, its domain, and its sign."""

    @pytest.mark.parametrize(
        ("amount", "parts", "expected"),
        [
            ("1000.00", 3, ["333.34", "333.33", "333.33"]),
            ("100.00", 7, ["14.29"] * 4 + ["14.28"] * 3),
            ("0.05", 3, ["0.02", "0.02", "0.01"]),
            ("0.01", 2, ["0.01", "0.00"]),
        ],
    )
    def test_exact_sum_positive(
        self, amount: str, parts: int, expected: list[str]
    ) -> None:
        result = Money(amount).allocate(parts)
        assert [str(m.amount) for m in result] == expected
        assert Money.sum(result) == Money(amount)

    def test_negative_magnitude_then_sign(self) -> None:
        """
        BR2.9 — THE test that distinguishes two implementations.

        Floor division gives -0.02, -0.02, -0.01 for -0.05 into three;
        truncating division gives -0.01, -0.02, -0.02. BOTH sum to exactly
        -0.05, so BR2.3's exact-sum property passes against either and cannot
        settle this. Allocating on the magnitude fixes the answer: the
        largest part comes first in absolute terms, mirroring the positive
        case.

        This asserts the SPECIFIC PARTS, in order. An exact-sum assertion
        alone would certify nothing.
        """
        result = Money("-0.05").allocate(3)
        assert [str(m.amount) for m in result] == ["-0.02", "-0.02", "-0.01"]
        assert Money.sum(result) == Money("-0.05")

    def test_negative_mirrors_positive(self) -> None:
        pos = [str(m.amount) for m in Money("1000.00").allocate(3)]
        neg = [str(m.amount) for m in Money("-1000.00").allocate(3)]
        assert neg == [f"-{p}" for p in pos]

    def test_zero_allocates_to_zeros(self) -> None:
        result = Money("0.00").allocate(4)
        assert len(result) == 4
        assert all(m.is_zero() for m in result)

    def test_single_part_returns_whole(self) -> None:
        assert Money("10.00").allocate(1) == [Money("10.00")]

    @pytest.mark.parametrize("n", [0, -1, -5])
    def test_below_one_part_refused(self, n: int) -> None:
        """
        BR2.8 — never an empty list. Returning one for n=0 would satisfy the
        exact-sum property vacuously for zero and violate it for anything
        else, turning a caller's error into a silent no-op or a lost amount.
        """
        with pytest.raises(MoneyValidationError):
            Money("10.00").allocate(n)

    def test_more_parts_than_paisa(self) -> None:
        """Five paisa into ten parts: five get one, five get nothing."""
        result = Money("0.05").allocate(10)
        assert [str(m.amount) for m in result] == ["0.01"] * 5 + ["0.00"] * 5
        assert Money.sum(result) == Money("0.05")


class TestSumAndConstants:
    """BR2.4, BR2.5, BR2.6."""

    def test_sum_empty_is_zero(self) -> None:
        """BR2.5 — a zero identity, not a failure."""
        assert Money.sum([]) == Money.ZERO

    def test_sum_values(self) -> None:
        assert Money.sum([Money("1.10"), Money("2.20")]) == Money("3.30")

    def test_zero_constant(self) -> None:
        assert Money.ZERO.amount == Decimal("0.00")

    def test_is_zero(self) -> None:
        assert Money("0.00").is_zero()
        assert not Money("0.01").is_zero()

    def test_is_positive(self) -> None:
        assert Money("0.01").is_positive()
        assert not Money("0.00").is_positive()
        assert not Money("-0.01").is_positive()


class TestComparison:
    """BR2.6 — type-safe ordering."""

    def test_ordering(self) -> None:
        assert Money("1.00") < Money("2.00")
        assert Money("2.00") > Money("1.00")
        assert Money("1.00") <= Money("1.00")
        assert Money("1.00") >= Money("1.00")

    def test_compare_to_int_is_type_error(self) -> None:
        """Comparing to a bare number is an error, not a surprise."""
        with pytest.raises(TypeError):
            Money("1.00") < 2  # type: ignore[operator]

    def test_equality_with_non_money_is_false(self) -> None:
        assert Money("1.00") != "1.00"
