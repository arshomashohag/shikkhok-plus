"""Every period's status from ONE fold equals the per-period computation [C-14].

A seat's fee history used to call :func:`app.fees.status.fee_status` once
per generated cycle, and each call read and folded the seat's whole ledger:
quadratic in the seat's age. :func:`statuses_from_entries` folds once and
answers every period. It must agree with :func:`status_from_entries` -- the
per-period definition -- for every period of every history, including the
awkward ones: a period touched only by a credit grant, a period whose relief
is a zero-amount entry, an over-relieved period. It must also agree when fed
the database's per-(period, kind) sums, because the fee history now reads
those.

No database: the property is about the arithmetic and the kind sets.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.fees.status import month_state, status_from_entries, statuses_from_entries
from app.money import LedgerEntry, LedgerEntryKind, Money

PERIODS = ["2026-07", "2026-08", "2026-09", "2026-10"]

amounts = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("3000.00"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


@st.composite
def entries(draw: st.DrawFn) -> LedgerEntry:
    """Draw one arbitrary entry of any kind."""
    return LedgerEntry(
        kind=draw(st.sampled_from(list(LedgerEntryKind))),
        period=draw(st.sampled_from(PERIODS)),
        amount=Money(draw(amounts)),
    )


def _presum(history: list[LedgerEntry]) -> list[LedgerEntry]:
    """Collapse same-(period, kind) entries into their sum, as SQL does.

    :param history: Raw entries
    :return: One entry per (period, kind)
    """
    sums: defaultdict[tuple[str, LedgerEntryKind], Money] = defaultdict(
        lambda: Money.ZERO
    )
    for item in history:
        sums[(item.period, item.kind)] += item.amount
    return [LedgerEntry(kind=k, period=p, amount=a) for (p, k), a in sums.items()]


@settings(max_examples=2000, deadline=None)
@given(st.lists(entries(), min_size=0, max_size=30))
def test_one_fold_agrees_with_the_per_period_status(
    history: list[LedgerEntry],
) -> None:
    """Same status for every period; the same periods missing.

    :param history: A random history
    :return: None
    """
    single = statuses_from_entries(history)
    summed = statuses_from_entries(_presum(history))
    for period in PERIODS:
        if any(entry.period == period for entry in history):
            expected = status_from_entries(history, period)
            assert single[period] == expected
            assert summed[period] == expected
            assert month_state(history, period, checking=False, statuses=single) == (
                expected
            )
        else:
            assert period not in single
            assert period not in summed
            with pytest.raises(KeyError):
                status_from_entries(history, period)
            assert month_state(history, period, checking=False, statuses=single) is None


def test_a_month_waiting_for_the_teacher_is_checking_whatever_the_fold() -> None:
    """A waiting payment outranks the precomputed statuses too.

    :return: None
    """
    history = [
        LedgerEntry(kind=LedgerEntryKind.CHARGE, period="2026-07", amount=Money("500"))
    ]
    statuses = statuses_from_entries(history)
    assert statuses == {"2026-07": "unpaid"}
    assert month_state(history, "2026-07", checking=True, statuses=statuses) == (
        "checking"
    )
