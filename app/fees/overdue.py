"""Overdue: money still owing on a period whose due date has passed.

**One definition, used everywhere it is shown** -- Today's overdue total,
the roster's "৳3,600 · 68 days" chip -- so the two cannot disagree about
whether a student is late. The client is sent the figures and never
compares a due date with its clock [TC-9].

A period due today is due, not late: overdue starts the day after.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping

from app.money import Money

__all__ = ["days_overdue", "overdue_balance"]


def _late_periods(
    per_cycle: Mapping[str, Money],
    due_by_period: Mapping[str, dt.date],
    today: dt.date,
) -> list[tuple[str, Money, dt.date]]:
    """List the periods still owing whose due date has passed.

    :param per_cycle: Outstanding per period, from the ledger fold
    :param due_by_period: Each period's due date
    :param today: Bangladesh's date
    :return: Period, balance and due date for each late period
    """
    late: list[tuple[str, Money, dt.date]] = []
    for period, balance in per_cycle.items():
        due = due_by_period.get(period)
        if balance.is_positive() and due is not None and due < today:
            late.append((period, balance, due))
    return late


def overdue_balance(
    per_cycle: Mapping[str, Money],
    due_by_period: Mapping[str, dt.date],
    today: dt.date,
) -> Money:
    """Total what is owed on periods past their due date.

    :param per_cycle: Outstanding per period, from the ledger fold
    :param due_by_period: Each period's due date
    :param today: Bangladesh's date
    :return: The overdue amount, zero when nothing is late
    """
    return Money.sum(
        balance for _, balance, _ in _late_periods(per_cycle, due_by_period, today)
    )


def days_overdue(
    per_cycle: Mapping[str, Money],
    due_by_period: Mapping[str, dt.date],
    today: dt.date,
) -> int | None:
    """Count how many days late the oldest unpaid period is.

    :param per_cycle: Outstanding per period, from the ledger fold
    :param due_by_period: Each period's due date
    :param today: Bangladesh's date
    :return: Days since the oldest late due date, or None when none is late
    """
    late = _late_periods(per_cycle, due_by_period, today)
    if not late:
        return None
    return (today - min(due for _, _, due in late)).days
