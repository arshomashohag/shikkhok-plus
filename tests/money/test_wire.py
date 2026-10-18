"""
The API chokepoint, asserted in both directions.

Covers BR5.1, BR5.2, BR5.7 and NFR9.8/9.9/9.11.
"""

import pytest

from app.money import Money, MoneyValidationError
from app.money.wire import WIRE_PATTERN, parse, to_wire


class TestEmit:
    """BR5.1 — the canonical form, and only it."""

    @pytest.mark.parametrize(
        ("amount", "expected"),
        [
            ("0.00", "0.00"),
            ("1500", "1500.00"),
            ("1234.56", "1234.56"),
            ("9999999999.99", "9999999999.99"),
        ],
    )
    def test_canonical_string(self, amount: str, expected: str) -> None:
        assert to_wire(Money(amount)) == expected

    def test_emitted_form_matches_the_contract_pattern(self) -> None:
        """What is emitted must satisfy the pattern the schema publishes."""
        for raw in ["0.00", "7.05", "1500", "9999999999.99"]:
            assert WIRE_PATTERN.match(to_wire(Money(raw)))

    def test_no_thousands_separator(self) -> None:
        assert to_wire(Money("1234567.89")) == "1234567.89"

    def test_negative_refused(self) -> None:
        """
        BR5.7 — a consistency check on the sign rules, not a limitation.

        Every quantity that legitimately crosses the API is one the sign
        rules already forbid to be negative, so a negative reaching here
        means a floor was missed upstream. Failing at emission beats a
        silently dropped sign that shows a debt as a credit.
        """
        with pytest.raises(MoneyValidationError):
            to_wire(Money("5.00") - Money("8.00"))


class TestParse:
    """BR5.2 — reject a number loudly; never coerce."""

    def test_string_round_trips(self) -> None:
        assert parse("1234.56") == Money("1234.56")

    @pytest.mark.parametrize("number", [1234.56, 1234, 0, 0.0])
    def test_json_number_rejected(self, number: float | int) -> None:
        """
        The lenient-decoder case. A decoder that quietly accepts a number
        and converts it passes a happy-path test on both sides while the
        value is already wrong.
        """
        with pytest.raises(MoneyValidationError):
            parse(number)

    def test_bool_rejected(self) -> None:
        with pytest.raises(MoneyValidationError):
            parse(True)

    def test_none_rejected(self) -> None:
        with pytest.raises(MoneyValidationError):
            parse(None)

    @pytest.mark.parametrize(
        "bad",
        [
            "1234.5",  # one decimal
            "1234.567",  # three decimals
            "1234",  # no decimals
            "-1.00",  # signed
            "+1.00",  # signed
            "1,234.00",  # separator
            "১২৩৪.৫৬",  # non-Latin digits
            " 1234.56",  # whitespace
            "1234.56 ",
            "",
        ],
    )
    def test_non_canonical_string_rejected(self, bad: str) -> None:
        with pytest.raises(MoneyValidationError):
            parse(bad)


class TestRoundTrip:
    """Both directions compose."""

    @pytest.mark.parametrize("amount", ["0.00", "0.01", "1500.00", "9999999999.99"])
    def test_emit_then_parse(self, amount: str) -> None:
        original = Money(amount)
        assert parse(to_wire(original)) == original
