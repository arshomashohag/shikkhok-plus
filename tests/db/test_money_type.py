"""The storage chokepoint refuses what the wire chokepoint refuses.

A money column that accepted a bare ``Decimal`` would be a convention
rather than a chokepoint: the value would have skipped the rounding mode
and the float prohibition, and nothing would say so. These tests pin the
refusal and the exact round trip.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.db.money_type import MONEY_PRECISION, MONEY_SCALE, MoneyColumn
from app.money import Money


def test_a_money_value_binds_as_an_exact_decimal() -> None:
    """Storage receives the exact amount, never a float.

    :return: None
    """
    bound = MoneyColumn.process_bind_param(Money("1234.56"), None)

    assert bound == Decimal("1234.56")
    assert isinstance(bound, Decimal)


def test_a_stored_decimal_reads_back_as_money() -> None:
    """The round trip reconstructs the type, not just the number.

    :return: None
    """
    result = MoneyColumn.process_result_value(Decimal("1234.56"), None)

    assert result == Money("1234.56")
    assert isinstance(result, Money)


def test_none_round_trips_as_none() -> None:
    """A nullable money column stays nullable.

    ``fee_amount`` is nullable by design: null means inherit the batch
    default, and zero is a real fee of zero [AC2.2.5].

    :return: None
    """
    assert MoneyColumn.process_bind_param(None, None) is None
    assert MoneyColumn.process_result_value(None, None) is None


def test_zero_is_stored_and_is_not_null() -> None:
    """Zero is a waiver, not an absence, and must survive the round trip.

    A type that conflated them would silently turn a waiver into "charge
    the batch default", which is a money error that looks like nothing.

    :return: None
    """
    bound = MoneyColumn.process_bind_param(Money("0.00"), None)

    assert bound == Decimal("0.00")
    assert bound is not None
    assert MoneyColumn.process_result_value(bound, None) == Money("0.00")


@pytest.mark.parametrize("value", [Decimal("10.00"), 10, "10.00", 10.0])
def test_anything_that_is_not_money_is_refused(value: object) -> None:
    """A bare number reaching a money column raises.

    **Including a ``Decimal``**, which is the one that would otherwise
    slip through: it is exact, so it looks harmless, and it has skipped
    the construction that applies the rounding mode and rejects a float.

    :param value: A non-Money value offered to the column
    :return: None
    """
    with pytest.raises(TypeError, match="takes Money"):
        MoneyColumn.process_bind_param(value, None)


def test_the_precision_is_declared_once() -> None:
    """No model restates the precision, so none can disagree.

    :return: None
    """
    assert (MONEY_PRECISION, MONEY_SCALE) == (12, 2)
    assert MoneyColumn.impl.precision == 12
    assert MoneyColumn.impl.scale == 2
    # asdecimal is what keeps the driver from handing back a float on
    # read, which would reintroduce the error silently.
    assert MoneyColumn.impl.asdecimal is True
