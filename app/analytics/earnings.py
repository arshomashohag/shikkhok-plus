"""Money received per period: a pure fold over entries already in hand.

**This module holds no I/O, no session and no HTTP**, which is the same
property the money module and ``app/marks/marksheet.py`` have and is why
the double-count test needs no database [logical-components § 1].

**Cash in is ``receipt`` plus ``credit_grant``, and never
``credit_apply``** [BR2.1]. The built money module already states it:
*"Cash in is receipts plus credit grants: money received as credit is
money received"* [``app/money/_kinds.py:58-60``]. D5 is the first
consumer of that sentence.

Counting the apply **double-counts the credit** -- once when it arrived
as a grant and again when it was spent -- and every ledger row still
balances while it does so, because the apply is a real entry for a real
amount. Computed rather than reasoned about:

====== ========== ================ ============== =========
        ``receipt``  ``credit_grant`` ``credit_apply`` cash in
====== ========== ================ ============== =========
M1      1000       500              --             **1500**
M2      500        --               500            **500**
                                                   **2000**
====== ========== ================ ============== =========

2000 is exactly what the student handed over. Counting the apply makes
M2 read 1000 and the total **2500**, overstated by exactly the credit.
**M1 reads 1500 under both**, which is why the test asserts the total.

**This module adds no money arithmetic** [BR4.3]: every amount comes
from summing ``Money`` values, and the rounding mode is declared once,
in ``app/money``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Final

from app.money import LedgerEntry, LedgerEntryKind, Money

__all__ = ["CASH_IN_KINDS", "MonthlyEarnings", "period_totals", "trend"]

#: The kinds that mean money arrived.
#:
#: **Hand-written here rather than derived from ``IDENTITY_SIDE``**, and
#: the money module's own docstring says why: *"A single source of truth
#: is correct for the implementation and fatal for the test that checks
#: it."* ``test_earnings.py`` asserts this set against that mapping
#: independently, so a mis-sided kind fails rather than agreeing with
#: itself by construction.
#:
#: Excluded deliberately, each for its own reason: ``charge`` is an
#: obligation created rather than money arrived; ``credit_apply`` is
#: held credit spent, received in an earlier month; ``forgiveness`` is a
#: waiver and not cash; ``carry_forward`` and ``carried_out`` are the
#: two halves of one accounting move between periods.
CASH_IN_KINDS: Final[frozenset[LedgerEntryKind]] = frozenset(
    {
        LedgerEntryKind.RECEIPT,
        LedgerEntryKind.CREDIT_GRANT,
    }
)


@dataclass(frozen=True, slots=True)
class MonthlyEarnings:
    """Money received in one calendar month, across every owned batch.

    :ivar period: The fixed-width period key, so lexical order IS
        chronological order
    :ivar received: ``receipt`` plus ``credit_grant`` for that period
    """

    period: str
    received: Money


def period_totals(entries: list[LedgerEntry]) -> dict[str, Money]:
    """Fold entries into money received per period.

    **The grouping key is the entry's ``period`` and never its
    ``created_at``** [BR2.6]. The two disagree whenever a payment is
    recorded late, which is the normal case rather than an edge: a
    teacher verifying October's cash on 2 November produces an entry
    whose period is October and whose creation stamp is November.
    Grouping by the stamp understates October, overstates November, and
    produces a trend with a dip and a spike that never happened.

    This signature is what makes that mistake unreachable rather than
    merely discouraged: :class:`~app.money.LedgerEntry` carries no
    creation stamp at all, so there is nothing here to group by
    wrongly.

    **A period with no money received is ABSENT from the result**, not
    zero [reliability § 1.3]. Absence inside the fold is honest -- that
    period had no cash in -- and turning it into a zero is the response
    boundary's job. Doing it here would make a read that returned
    nothing indistinguishable from a month that genuinely earned
    nothing.

    :param entries: The entries to fold, in any order
    :return: Money received per period, periods with none omitted
    """
    totals: defaultdict[str, Money] = defaultdict(lambda: Money.ZERO)

    for entry in entries:
        if entry.kind in CASH_IN_KINDS:
            totals[entry.period] += entry.amount

    return dict(totals)


def trend(totals: dict[str, Money]) -> list[MonthlyEarnings] | None:
    """Build the monthly series, ascending, or nothing at all.

    **Fewer than two months of history returns no trend** [BR2.3]. A
    single point is not a trend, and a one-point chart implies a
    direction it cannot know -- so this returns ``None`` rather than a
    one-element list, and the absence reaches the wire as an absent
    block rather than an empty one.

    **Ordered here and never in the client** [BR2.4]. A client sorting a
    domain list is the second of the five erosion paths ``team.md``
    names and the one most easily reached on a chart screen. Period keys
    are fixed width, so this is a sort rather than a parse.

    :param totals: Money received per period, from :func:`period_totals`
    :return: The series in ascending period order, or None under two
        months
    """
    if len(totals) < 2:
        return None

    return [
        MonthlyEarnings(period=period, received=totals[period])
        for period in sorted(totals)
    ]
