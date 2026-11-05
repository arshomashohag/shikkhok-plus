"""A mark as a number with at most two decimal places.

Decided by the owner on 2026-11-05: a mark may be any number, whole or
decimal, such as ``19.5``. A mark is a count, never money, so it is a
``float`` here as the marksheet's average already is -- but **every
comparison and every sum works in whole hundredths**, so ``0.1 + 0.2``
never decides a rank, a direction or a percent. The column is
``NUMERIC(6,2)``, so what is stored is exact.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "MAX_PLACES",
    "centi",
    "has_at_most_two_places",
    "mean",
    "percent",
]

#: Decimal places a mark may carry, as the column stores it.
MAX_PLACES: Final[int] = 2

#: Hundredths in one mark.
_CENTI: Final[int] = 100

#: How far a float may sit from a whole hundredth and still be one.
_TOLERANCE: Final[float] = 1e-6


def centi(marks: float) -> int:
    """Give a mark in whole hundredths.

    :param marks: The mark, at most two decimal places
    :return: The mark times 100, exactly
    """
    return round(marks * _CENTI)


def has_at_most_two_places(marks: float) -> bool:
    """Say whether a mark is a whole number of hundredths.

    :param marks: The mark as it arrived
    :return: True for ``19``, ``19.5`` and ``19.25``; False for ``19.125``
    """
    return abs(marks * _CENTI - centi(marks)) < _TOLERANCE


def percent(marks: float, total: int) -> int | None:
    """Give a mark as a whole percent of its total, rounded half up.

    :param marks: The mark
    :param total: The exam's total
    :return: The percent, or None where the total is zero
    """
    if total <= 0:
        return None
    return (2 * centi(marks) + total) // (2 * total)


def mean(marks: list[float]) -> float | None:
    """Give the mean of some marks to two places, rounded half up.

    :param marks: The marks
    :return: The mean, or None for no marks
    """
    if not marks:
        return None
    hundredths = [centi(mark) for mark in marks]
    count = len(hundredths)
    return ((2 * sum(hundredths) + count) // (2 * count)) / _CENTI
