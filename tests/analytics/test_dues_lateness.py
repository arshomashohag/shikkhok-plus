"""How late each debt is, and what the Dues screen groups and totals.

**Written before the fields existed.** T5 groups people by how late they
are -- "30+ days late", "1-30 days late", "Due, not late yet" -- totals
each group, and offers to remind the late ones. Every one of those is a
decision about money and dates, so the server makes it and the client
renders it [TC-9]. The expected values follow from the charges and due
dates below.

These are pure: ``dues_rows`` takes no session, so the fold is tested
on values in hand.
"""

from __future__ import annotations

import datetime as dt
import uuid

from app.analytics.dues import dues_rows, dues_summary
from app.analytics.seats import OwnedSeat
from app.money import LedgerEntry, LedgerEntryKind, Money

TODAY = dt.date(2026, 10, 17)
NOW = dt.datetime(2026, 10, 17, 6, 0, tzinfo=dt.UTC)


def _seat(name: str, *, reachable: bool = True) -> OwnedSeat:
    """Build one owned seat.

    :param name: The teacher-typed name
    :param reachable: Whether anyone on it has accepted
    :return: The seat
    """
    return OwnedSeat(
        enrollment_id=uuid.uuid4(),
        batch_id=uuid.uuid4(),
        batch_name="Physics",
        display_name=name,
        reachable=reachable,
    )


def _charges(*periods: tuple[str, str]) -> list[LedgerEntry]:
    """Charge each ``(period, amount)``.

    :param periods: Period and amount pairs
    :return: The ledger entries
    """
    return [
        LedgerEntry(kind=LedgerEntryKind.CHARGE, period=period, amount=Money(amount))
        for period, amount in periods
    ]


#: Due on the 10th of each month.
DUE = {
    "2026-08": dt.date(2026, 8, 10),
    "2026-09": dt.date(2026, 9, 10),
    "2026-10": dt.date(2026, 10, 10),
    "2026-11": dt.date(2026, 11, 10),
}


def test_rows_carry_days_late_bucket_and_period_range() -> None:
    """Aug-Oct unpaid is 68 days late; Oct alone is 7; Nov is not late.

    :return: None
    """
    long_late, just_late, not_late = _seat("A"), _seat("B"), _seat("C")
    seats = [long_late, just_late, not_late]
    ledger = {
        long_late.enrollment_id: _charges(
            ("2026-08", "1200.00"), ("2026-09", "1200.00"), ("2026-10", "1200.00")
        ),
        just_late.enrollment_id: _charges(("2026-10", "1500.00")),
        not_late.enrollment_id: _charges(("2026-11", "900.00")),
    }
    due = {seat.enrollment_id: DUE for seat in seats}

    rows = dues_rows(seats, ledger, due_by_seat=due, today=TODAY, now=NOW)
    by_name = {row.display_name: row for row in rows}

    assert (by_name["A"].days_late, by_name["A"].bucket) == (68, "over_30")
    assert (by_name["A"].oldest_unpaid_period, by_name["A"].latest_unpaid_period) == (
        "2026-08",
        "2026-10",
    )
    assert (by_name["B"].days_late, by_name["B"].bucket) == (7, "late")
    assert (by_name["C"].days_late, by_name["C"].bucket) == (None, "not_late")


def test_rows_are_ordered_by_how_late_then_by_amount() -> None:
    """The latest debt first; equal lateness puts the larger debt first.

    :return: None
    """
    small_old, large_old, large_new = _seat("S"), _seat("L"), _seat("N")
    seats = [large_new, small_old, large_old]
    ledger = {
        small_old.enrollment_id: _charges(("2026-08", "500.00")),
        large_old.enrollment_id: _charges(("2026-08", "3000.00")),
        large_new.enrollment_id: _charges(("2026-11", "9000.00")),
    }
    due = {seat.enrollment_id: DUE for seat in seats}

    rows = dues_rows(seats, ledger, due_by_seat=due, today=TODAY, now=NOW)

    assert [row.display_name for row in rows] == ["L", "S", "N"]


def test_a_late_reachable_seat_not_reminded_today_can_be_reminded() -> None:
    """Late, someone accepted, and not reminded in the last day.

    :return: None
    """
    fresh, reminded, recent, nobody, not_late = (
        _seat("fresh"),
        _seat("reminded"),
        _seat("recent"),
        _seat("nobody", reachable=False),
        _seat("not_late"),
    )
    seats = [fresh, reminded, recent, nobody, not_late]
    ledger = {seat.enrollment_id: _charges(("2026-10", "1000.00")) for seat in seats}
    ledger[not_late.enrollment_id] = _charges(("2026-11", "1000.00"))
    due = {seat.enrollment_id: DUE for seat in seats}
    last = {
        reminded.enrollment_id: NOW - dt.timedelta(days=3),
        recent.enrollment_id: NOW - dt.timedelta(hours=2),
    }

    rows = dues_rows(
        seats, ledger, due_by_seat=due, last_reminded=last, today=TODAY, now=NOW
    )
    remindable = {row.display_name: row.remindable for row in rows}

    assert remindable == {
        "fresh": True,
        "reminded": True,
        "recent": False,
        "nobody": False,
        "not_late": False,
    }
    assert {row.display_name: row.last_reminded_at for row in rows}["reminded"] == (
        NOW - dt.timedelta(days=3)
    )


def test_the_summary_totals_each_group_and_the_whole() -> None:
    """৳3,600 + ৳1,500 + ৳900 is ৳6,000 across three groups of one.

    :return: None
    """
    a, b, c = _seat("A"), _seat("B"), _seat("C")
    seats = [a, b, c]
    ledger = {
        a.enrollment_id: _charges(
            ("2026-08", "1200.00"), ("2026-09", "1200.00"), ("2026-10", "1200.00")
        ),
        b.enrollment_id: _charges(("2026-10", "1500.00")),
        c.enrollment_id: _charges(("2026-11", "900.00")),
    }
    due = {seat.enrollment_id: DUE for seat in seats}

    summary = dues_summary(
        dues_rows(seats, ledger, due_by_seat=due, today=TODAY, now=NOW)
    )

    assert (summary.total, summary.count) == (Money("6000.00"), 3)
    assert (summary.late_total, summary.remindable) == (Money("5100.00"), 2)
    assert {g.bucket: (g.total, g.count, g.share) for g in summary.groups} == {
        "over_30": (Money("3600.00"), 1, 60),
        "late": (Money("1500.00"), 1, 25),
        "not_late": (Money("900.00"), 1, 15),
    }


def test_an_empty_dues_list_totals_zero() -> None:
    """Everyone paid is a zero, never an absence [BR1.5].

    :return: None
    """
    summary = dues_summary([])

    assert (summary.total, summary.count, summary.remindable) == (Money.ZERO, 0, 0)
    assert [(g.count, g.share) for g in summary.groups] == [(0, 0), (0, 0), (0, 0)]
