"""Business dates are Bangladesh dates, never UTC dates [audit C-23].

Dhaka is UTC+6, so from 00:00 to 05:59 local time the UTC date is still
yesterday. A seat created in that window on the 1st of a month, with no
``joined_on``, was billed for the PREVIOUS month: generation took its
start from ``created_at.date()``, a UTC date. These pin every helper that
turns a moment into a business date to the Bangladesh calendar.
"""

from __future__ import annotations

import datetime as dt

from app.fees.generation import seat_start

#: 01:00 in Dhaka on 1 December is 19:00 UTC on 30 November.
JUST_AFTER_DHAKA_MIDNIGHT = dt.datetime(2026, 11, 30, 19, 0, tzinfo=dt.UTC)


def test_a_seat_created_after_dhaka_midnight_starts_that_day() -> None:
    """The seat's first day is 1 December, not 30 November.

    :return: None
    """
    assert seat_start(None, JUST_AFTER_DHAKA_MIDNIGHT) == dt.date(2026, 12, 1)


def test_joined_on_still_wins_over_creation() -> None:
    """A recorded start date is used as written.

    :return: None
    """
    joined = dt.date(2026, 11, 15)
    assert seat_start(joined, JUST_AFTER_DHAKA_MIDNIGHT) == joined


def test_a_seat_created_in_dhaka_daytime_keeps_its_date() -> None:
    """The ordinary case is unchanged.

    :return: None
    """
    noon_dhaka = dt.datetime(2026, 12, 1, 6, 0, tzinfo=dt.UTC)
    assert seat_start(None, noon_dhaka) == dt.date(2026, 12, 1)
