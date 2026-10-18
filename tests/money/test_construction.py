"""
Construction and representation of the Money value type.

Covers BR1.1-BR1.7. Every expected value here comes from the design, not from
an implementation: these tests were written before the type existed.
"""

from decimal import Decimal

import pytest

from app.money import Money, MoneyValidationError


class TestFloatRefusal:
    """BR1.1, BR1.2 — the float barrier, layer one."""

    def test_float_construction_refused(self) -> None:
        with pytest.raises(MoneyValidationError):
            Money(0.1)  # type: ignore[arg-type]

    def test_integral_float_also_refused(self) -> None:
        """
        The check is on the TYPE, not the value.

        A float that happens to be integral is refused identically to one that
        is not. Accepting the integral case would make the rule
        value-dependent and therefore unpredictable to a caller.
        """
        with pytest.raises(MoneyValidationError):
            Money(1000.0)  # type: ignore[arg-type]

    def test_zero_float_also_refused(self) -> None:
        with pytest.raises(MoneyValidationError):
            Money(0.0)  # type: ignore[arg-type]

    def test_bool_refused(self) -> None:
        """A bool is an int subclass; money is not a flag."""
        with pytest.raises(MoneyValidationError):
            Money(True)  # type: ignore[arg-type]


class TestAcceptedInputs:
    """BR1.2 — a string parses exactly; an integer is whole Taka."""

    def test_string_parsed_exactly(self) -> None:
        assert Money("1234.56").amount == Decimal("1234.56")

    def test_int_is_whole_taka(self) -> None:
        assert Money(1500).amount == Decimal("1500.00")

    def test_decimal_accepted(self) -> None:
        assert Money(Decimal("12.30")).amount == Decimal("12.30")

    def test_malformed_string_refused(self) -> None:
        with pytest.raises(MoneyValidationError):
            Money("not a number")

    def test_empty_string_refused(self) -> None:
        with pytest.raises(MoneyValidationError):
            Money("")


class TestQuantization:
    """BR1.3 — quantized to exactly 2dp at construction, half-up."""

    def test_three_decimals_quantized(self) -> None:
        assert Money("1.005").amount == Decimal("1.01")

    def test_one_decimal_padded(self) -> None:
        assert Money("1.5").amount == Decimal("1.50")

    def test_equal_values_hash_equally(self) -> None:
        """
        Quantizing at construction is what makes equality, hashing and
        serialization mutually consistent. An unquantized value makes two
        'equal' amounts hash differently, which bites in sets and dict keys.
        """
        a, b = Money("1.5"), Money("1.50")
        assert a == b
        assert hash(a) == hash(b)
        assert len({a, b}) == 1


class TestOverflow:
    """BR1.7 — ten integer digits, refused rather than truncated."""

    def test_ten_integer_digits_accepted(self) -> None:
        assert Money("9999999999.99").amount == Decimal("9999999999.99")

    def test_eleven_integer_digits_refused(self) -> None:
        with pytest.raises(MoneyValidationError):
            Money("10000000000.00")

    def test_negative_overflow_refused(self) -> None:
        """The bound is on magnitude, so the sign does not excuse it."""
        with pytest.raises(MoneyValidationError):
            Money("-10000000000.00")


class TestImmutabilityAndSurface:
    """BR1.5, BR1.6 — immutable, and no escape back to a primitive."""

    def test_immutable(self) -> None:
        m = Money("10.00")
        with pytest.raises(Exception):  # noqa: B017 - frozen dataclass raises
            m.amount = Decimal("20.00")  # type: ignore[misc]

    def test_no_float_conversion(self) -> None:
        """
        BR1.6 — would reintroduce BR1.1's defect by the back door.
        """
        with pytest.raises(TypeError):
            float(Money("10.00"))  # type: ignore[arg-type]

    def test_no_int_conversion(self) -> None:
        """BR1.6 — silently discards paisa."""
        with pytest.raises(TypeError):
            int(Money("10.99"))  # type: ignore[arg-type]

    def test_repr_round_trips(self) -> None:
        assert repr(Money("10.50")) == "Money('10.50')"
