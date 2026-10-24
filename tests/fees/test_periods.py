"""The calendar: periods, the anchor, and the non-degrading clamp.

**Written before `app/fees/periods.py` existed**, which the predicate in
the affirmed testing posture requires: every value here is knowable from
BR2.2's table without having written the code, and a wrong due date is a
money error -- it is the date a teacher chases a payment on.

**The third row of the anchor-31 table is the one that separates the two
designs.** A degrading clamp -- one that rewrites the stored anchor to 28
after February -- gives 2027-03-28 and every month after, for ever. The
non-degrading answer is 2027-03-31. A test covering only January and
February cannot tell them apart.

These are pure calendar tests and take no database fixture: the clamp is
arithmetic over a stored anchor and a period, with no row involved.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.fees.periods import (
    Period,
    days_in_period,
    due_date_for,
    periods_from_through,
)

#: The anchor that exposes a degrading clamp. 31 is the only value that
#: must be reduced in every short month and restored in every long one.
EXPOSING_ANCHOR = 31


def test_a_period_round_trips_through_its_key() -> None:
    period = Period.parse("2027-02")

    assert period.year == 2027
    assert period.month == 2
    assert str(period) == "2027-02"


def test_a_period_key_is_fixed_width_and_sorts_chronologically() -> None:
    # Lexical order must BE chronological order, because the oldest
    # unpaid cycle is resolved by sorting these keys [BR5.1]. A
    # single-digit month would sort "2027-9" after "2027-10".
    keys = [str(Period(2027, month)) for month in range(1, 13)]

    assert all(len(key) == 7 for key in keys)
    assert keys == sorted(keys)
    assert keys[8] == "2027-09"


@pytest.mark.parametrize(
    ("period", "expected"),
    [
        ("2027-01", dt.date(2027, 1, 31)),
        ("2027-02", dt.date(2027, 2, 28)),
        # THE SEPARATING CASE. A degrading clamp gives 2027-03-28 here,
        # having rewritten the anchor to 28 in February, and keeps
        # giving the 28th for ever after.
        ("2027-03", dt.date(2027, 3, 31)),
        ("2028-02", dt.date(2028, 2, 29)),
    ],
)
def test_the_clamp_does_not_degrade_the_anchor(period: str, expected: dt.date) -> None:
    assert due_date_for(Period.parse(period), anchor_day=EXPOSING_ANCHOR) == expected


def test_a_null_anchor_means_the_last_day_of_the_period() -> None:
    # [BR2.3] The column is nullable and nothing upstream says what a
    # null means. Last-day is the only default that cannot make a fee
    # due before the month it pays for has been taught, and it degrades
    # to the same behaviour as an anchor of 31.
    assert due_date_for(Period.parse("2027-02"), anchor_day=None) == dt.date(
        2027, 2, 28
    )
    assert due_date_for(Period.parse("2027-03"), anchor_day=None) == dt.date(
        2027, 3, 31
    )


def test_an_anchor_inside_every_month_is_used_unchanged() -> None:
    assert due_date_for(Period.parse("2027-02"), anchor_day=5) == dt.date(2027, 2, 5)
    assert due_date_for(Period.parse("2027-03"), anchor_day=5) == dt.date(2027, 3, 5)


def test_days_in_period_knows_the_leap_year() -> None:
    assert days_in_period(Period.parse("2027-02")) == 28
    assert days_in_period(Period.parse("2028-02")) == 29
    assert days_in_period(Period.parse("2027-04")) == 30


def test_the_period_range_is_inclusive_at_both_ends() -> None:
    # This is what makes a missed day self-heal [BR1.4]: generation
    # considers every period from the first generating one THROUGH the
    # current one, so a hole left by a missed run is filled rather than
    # permanent.
    span = periods_from_through(Period.parse("2026-11"), Period.parse("2027-02"))

    assert [str(period) for period in span] == [
        "2026-11",
        "2026-12",
        "2027-01",
        "2027-02",
    ]


def test_the_period_range_spanning_one_month_yields_that_month() -> None:
    span = periods_from_through(Period.parse("2027-02"), Period.parse("2027-02"))

    assert [str(period) for period in span] == ["2027-02"]


def test_the_period_range_ending_before_it_starts_is_empty() -> None:
    # Reachable in real operation: an enrollment whose first generating
    # period is next month, considered by a run today.
    span = periods_from_through(Period.parse("2027-03"), Period.parse("2027-02"))

    assert list(span) == []


def test_a_malformed_period_key_is_refused() -> None:
    for malformed in ("2027-2", "2027/02", "27-02", "2027-13", "2027-00", ""):
        with pytest.raises(ValueError):
            Period.parse(malformed)


def test_the_period_containing_a_date_is_that_dates_month() -> None:
    assert str(Period.containing(dt.date(2027, 2, 15))) == "2027-02"
    assert str(Period.containing(dt.date(2027, 12, 31))) == "2027-12"


def test_the_first_day_of_a_period_is_the_inactive_from_comparand() -> None:
    # [BR1.5] The test is `inactive_from >= the period's first day`, so
    # the first day is what the rule compares against.
    assert Period.parse("2027-02").first_day() == dt.date(2027, 2, 1)
    assert Period.parse("2027-02").last_day() == dt.date(2027, 2, 28)
