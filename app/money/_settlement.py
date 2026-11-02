"""
One child's approved amount settling their months, oldest first.

A child may owe more than one month when a payment is approved. What the
teacher approved for that child pays the oldest month first, each month up
to what it owes, and whatever is left after every month is paid is the
excess. What each month is still short of is returned too, so the caller
can carry or waive exactly that.

A pure function of its arguments: it knows nothing of periods, only of
amounts in the order the caller lists them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ._errors import MoneyValidationError
from ._money import Money


@dataclass(frozen=True, slots=True)
class Settlement:
    """
    How one amount settles a list of months.

    :ivar receipts: What each month receives, in the caller's order.
    :ivar shortfalls: What each month is still short of, in the same order.
    :ivar excess: What is left once every month is paid.
    """

    receipts: tuple[Money, ...]
    shortfalls: tuple[Money, ...]
    excess: Money


def settle_oldest_first(amount: Money, outstanding: Sequence[Money]) -> Settlement:
    """
    Pay each month in order, up to what it owes, with one amount.

    :param amount: What was approved for the child.
    :param outstanding: What each month owes, oldest first.
    :return: Each month's receipt and shortfall, and the excess.
    :raises MoneyValidationError: If the amount or a month's figure is
        negative.
    """
    if amount.is_negative():
        raise MoneyValidationError(
            f"SETTLEMENT_AMOUNT_NEGATIVE: amount {amount} is negative."
        )
    if any(owed.is_negative() for owed in outstanding):
        raise MoneyValidationError(
            "SETTLEMENT_OWED_NEGATIVE: a month's outstanding is negative."
        )
    receipts: list[Money] = []
    shortfalls: list[Money] = []
    remaining = amount
    for owed in outstanding:
        paid = min(owed, remaining)
        receipts.append(paid)
        shortfalls.append(owed - paid)
        remaining = remaining - paid
    return Settlement(
        receipts=tuple(receipts), shortfalls=tuple(shortfalls), excess=remaining
    )
