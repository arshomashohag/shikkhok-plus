"""
The paths the main suites leave untested.

These are not filler for a coverage number. Each one is a refusal or an
operation a caller can actually reach, and each was found by the 100% branch
gate refusing the build — which is the gate doing its job.
"""

from decimal import Decimal

import pytest

from app.money import Money, MoneyValidationError


class TestNonFiniteAmounts:
    """
    Infinity and NaN are valid Decimals and must not become amounts.

    ``Decimal("Infinity")`` constructs happily and would then quantize to
    something meaningless. A money value is finite by definition.
    """

    @pytest.mark.parametrize("raw", ["Infinity", "-Infinity", "NaN", "sNaN"])
    def test_non_finite_refused(self, raw: str) -> None:
        with pytest.raises(MoneyValidationError):
            Money(raw)

    def test_non_finite_decimal_refused(self) -> None:
        with pytest.raises(MoneyValidationError):
            Money(Decimal("Infinity"))


class TestNegation:
    """Unary minus, used wherever a signed difference is built."""

    def test_negate_positive(self) -> None:
        assert (-Money("10.50")).amount == Decimal("-10.50")

    def test_negate_negative(self) -> None:
        assert (-(Money("0.00") - Money("3.00"))).amount == Decimal("3.00")

    def test_negate_zero_is_zero(self) -> None:
        assert (-Money.ZERO).is_zero()


class TestRateTypeRefusal:
    """
    A rate that is neither a float nor a Decimal.

    The float branch is tested in test_arithmetic; this covers the second
    refusal, which catches a string or an int being passed where an exact
    proportion was meant.
    """

    @pytest.mark.parametrize("rate", ["0.5", 1, None, [1]])
    def test_non_decimal_rate_refused(self, rate: object) -> None:
        with pytest.raises(MoneyValidationError):
            Money("100.00").apply_rate(rate)  # type: ignore[arg-type]


class TestComparisonWithNonMoney:
    """
    Every ordering operator refuses a non-Money operand.

    Each returns NotImplemented, which Python turns into a TypeError. All
    four are tested because each is a separate branch, and an operator that
    silently compared against a bare number would be exactly the bug
    Money.ZERO exists to prevent.
    """

    @pytest.mark.parametrize("other", [5, "5.00", None, 5.0])
    def test_lt(self, other: object) -> None:
        with pytest.raises(TypeError):
            Money("1.00") < other  # type: ignore[operator]

    @pytest.mark.parametrize("other", [5, "5.00", None, 5.0])
    def test_le(self, other: object) -> None:
        with pytest.raises(TypeError):
            Money("1.00") <= other  # type: ignore[operator]

    @pytest.mark.parametrize("other", [5, "5.00", None, 5.0])
    def test_gt(self, other: object) -> None:
        with pytest.raises(TypeError):
            Money("1.00") > other  # type: ignore[operator]

    @pytest.mark.parametrize("other", [5, "5.00", None, 5.0])
    def test_ge(self, other: object) -> None:
        with pytest.raises(TypeError):
            Money("1.00") >= other  # type: ignore[operator]


class TestNegativeZeroIsNormalised:
    """
    Zero has one representation.

    Decimal distinguishes -0.00 from 0.00, and the difference leaked: a rate
    of Decimal('-0') passed the sign guard (it is not strictly negative),
    produced Money('-0.00'), and `str()` rendered "-0.00" — a string the wire
    chokepoint would emit and its own parser would then reject.
    """

    def test_negative_zero_rate(self) -> None:
        result = Money("100.00").apply_rate(Decimal("-0"))
        assert str(result) == "0.00"
        assert result.is_zero()

    def test_negative_zero_construction(self) -> None:
        assert str(Money("-0.00")) == "0.00"
        assert str(Money(Decimal("-0.00"))) == "0.00"

    def test_negative_zero_from_subtraction(self) -> None:
        assert str(Money("5.00") - Money("5.00")) == "0.00"

    def test_normalised_zero_survives_the_wire(self) -> None:
        from app.money.wire import parse, to_wire

        emitted = to_wire(Money("100.00").apply_rate(Decimal("-0")))
        assert emitted == "0.00"
        assert parse(emitted) == Money.ZERO
