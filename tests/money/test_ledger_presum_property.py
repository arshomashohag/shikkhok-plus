"""
The fold is linear per (period, kind): pre-summed entries derive the same.

Owner-wide reads (dues, today, overview, the student list) used to load every
ledger row of every seat and fold them in Python. They now ask the database
for ``SUM(amount) GROUP BY enrollment_id, period, kind`` and fold those sums.
That is only a safe reduction if :func:`app.money.derive` cannot tell the two
inputs apart, and this suite is the proof the read path relies on.

**Why it should hold, stated so the test can refute it.** Every quantity the
fold produces is a sum over entries selected by kind, and the per-period
figures additionally by period; the only non-linear step, the per-period
floor, is applied to sums that are already grouped by period. Collapsing
same-(period, kind) entries into one entry carrying their sum therefore
changes no input to any step. The reduction here is hand-written, not imported
from the read path, so a wrong grouping in either place cannot agree with the
other by construction.

The histories are deliberately *arbitrary* rather than well-formed: the
equivalence is a property of the fold's arithmetic, so it must hold even over
histories no approval path produces, including over-relieved periods where the
floor bites.
"""

import random
from collections import defaultdict
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.money import LedgerEntry, LedgerEntryKind, Money, derive

PERIODS = ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]

amounts = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("50000.00"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


@st.composite
def entries(draw: st.DrawFn) -> LedgerEntry:
    """Draw one arbitrary, individually valid entry of any kind."""
    return LedgerEntry(
        kind=draw(st.sampled_from(list(LedgerEntryKind))),
        period=draw(st.sampled_from(PERIODS)),
        amount=Money(draw(amounts)),
    )


def presum(history: list[LedgerEntry]) -> list[LedgerEntry]:
    """Collapse entries sharing a (period, kind) into one carrying their sum.

    The same reduction ``GROUP BY period, kind`` with ``SUM(amount)``
    performs, written independently of the read path.

    :param history: Raw entries
    :return: One entry per (period, kind) present in the history
    """
    sums: defaultdict[tuple[str, LedgerEntryKind], Money] = defaultdict(
        lambda: Money.ZERO
    )
    for item in history:
        sums[(item.period, item.kind)] += item.amount
    return [
        LedgerEntry(kind=kind, period=period, amount=amount)
        for (period, kind), amount in sums.items()
    ]


@settings(max_examples=3000, deadline=None)
@given(st.lists(entries(), min_size=0, max_size=60), st.randoms())
def test_presummed_history_derives_identically(
    history: list[LedgerEntry], shuffle: random.Random
) -> None:
    """
    derive(raw) == derive(pre-summed), in every field, for any history.

    The pre-summed list is also shuffled, because SQL returns groups in no
    promised order and the read path must not depend on one.
    """
    reduced = presum(history)
    shuffle.shuffle(reduced)
    assert derive(reduced) == derive(history)


@settings(max_examples=500, deadline=None)
@given(st.lists(entries(), min_size=1, max_size=40))
def test_presummed_periods_keep_their_keys(history: list[LedgerEntry]) -> None:
    """
    A period settled to exactly zero is still a key of ``per_cycle``.

    ``per_cycle`` lists every period a cycle-moving entry touched, owing or
    not -- every kind but ``credit_grant``, which is held money and belongs
    to no cycle. A reduction that dropped zero-sum groups would remove
    settled months from it. Asserted separately from the equality above so
    the failure names the property.
    """
    touched = {e.period for e in history if e.kind is not LedgerEntryKind.CREDIT_GRANT}
    assert set(derive(presum(history)).per_cycle) == touched


def test_settled_and_overpaid_periods_example() -> None:
    """
    A worked case: two receipts in one month, one waived month, credit held.

    January is charged 1000 and paid in two 500 receipts; February is charged
    1000 and paid 1200 as 1000 receipt plus 200 credit grant; March is charged
    1000 and 300 is waived. Raw and pre-summed both owe 700, all of it March,
    with 200 credit available.
    """
    k = LedgerEntryKind
    raw = [
        LedgerEntry(kind=k.CHARGE, period="2026-01", amount=Money("1000")),
        LedgerEntry(kind=k.RECEIPT, period="2026-01", amount=Money("500")),
        LedgerEntry(kind=k.RECEIPT, period="2026-01", amount=Money("500")),
        LedgerEntry(kind=k.CHARGE, period="2026-02", amount=Money("1000")),
        LedgerEntry(kind=k.RECEIPT, period="2026-02", amount=Money("1000")),
        LedgerEntry(kind=k.CREDIT_GRANT, period="2026-02", amount=Money("200")),
        LedgerEntry(kind=k.CHARGE, period="2026-03", amount=Money("1000")),
        LedgerEntry(kind=k.FORGIVENESS, period="2026-03", amount=Money("300")),
    ]
    reduced = presum(raw)
    assert len(reduced) == 7
    assert derive(reduced) == derive(raw)
    assert derive(reduced).total_outstanding == Money("700")
    assert derive(reduced).per_cycle == {
        "2026-01": Money.ZERO,
        "2026-02": Money.ZERO,
        "2026-03": Money("700"),
    }
    assert derive(reduced).available_credit == Money("200")
