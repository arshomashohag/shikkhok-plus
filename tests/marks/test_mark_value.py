"""Decimal marks compared in hundredths (decided 2026-11-05).

Pure arithmetic, no database: the helpers every rank, direction,
percent and average goes through.
"""

from __future__ import annotations

import pytest

from app.marks.value import centi, has_at_most_two_places, mean, percent


@pytest.mark.parametrize(
    ("marks", "expected"), [(19, 1900), (19.5, 1950), (19.25, 1925), (0.1, 10)]
)
def test_a_mark_is_exact_in_hundredths(marks: float, expected: int) -> None:
    """``0.1`` is ten hundredths, not 10.000000000000002.

    :param marks: The mark
    :param expected: Its hundredths
    :return: None
    """
    assert centi(marks) == expected


@pytest.mark.parametrize(
    ("marks", "allowed"), [(19, True), (19.5, True), (0.29, True), (19.125, False)]
)
def test_two_places_at_most(marks: float, allowed: bool) -> None:
    """A third place is not a mark the column can hold.

    :param marks: The mark
    :param allowed: Whether it fits
    :return: None
    """
    assert has_at_most_two_places(marks) is allowed


def test_percent_rounds_half_up() -> None:
    """12.5 of 25 is 50 percent; 0.125 of a whole percent rounds up.

    :return: None
    """
    assert percent(12.5, 25) == 50
    assert percent(10.5, 21) == 50
    assert percent(1, 8) == 13
    assert percent(5, 0) is None


def test_the_mean_is_two_places_rounded_half_up() -> None:
    """The batch average of decimal marks, without float drift.

    :return: None
    """
    assert mean([0.1, 0.2]) == 0.15
    assert mean([19.5, 20, 20.25]) == 19.92
    assert mean([]) is None
