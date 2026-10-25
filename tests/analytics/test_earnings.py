"""Cash in is ``receipt + credit_grant`` and never ``credit_apply``.

Written before ``app/analytics/earnings.py`` existed. A wrong fold is a
**money** error and BR2.1 computes the expected total before any code,
so the team's test-first predicate holds on both clauses.

**§ 3.1 of the unit test instructions is why these assert the TOTAL.**
Month 1 reads 1500 under the correct fold **and** under the
double-count, because month 1 contains no ``credit_apply`` at all -- so
a per-month assertion on month 1 misses the defect this unit's central
rule exists to prevent. The total is where the two months differ, which
is the whole reason BR2.1's case spans two.

These are pure-fold tests: ``earnings.py`` holds no I/O and takes no
session, so no database is needed and the arithmetic is testable at unit
speed [logical-components § 1].
"""

from __future__ import annotations

from app.analytics.earnings import CASH_IN_KINDS, period_totals, trend
from app.money import LedgerEntry, LedgerEntryKind, Money

#: BR2.1's worked case, computed by running the fold rather than
#: asserted. Month 1: the seat owes 1000 and the student hands over
#: 1500, giving a receipt of 1000 and a credit grant of 500. Month 2:
#: the seat owes 1000, settled as a 500 credit apply plus a 500 receipt.
BR21_CASE: list[LedgerEntry] = [
    LedgerEntry(kind=LedgerEntryKind.CHARGE, period="2027-01", amount=Money("1000.00")),
    LedgerEntry(
        kind=LedgerEntryKind.RECEIPT, period="2027-01", amount=Money("1000.00")
    ),
    LedgerEntry(
        kind=LedgerEntryKind.CREDIT_GRANT, period="2027-01", amount=Money("500.00")
    ),
    LedgerEntry(kind=LedgerEntryKind.CHARGE, period="2027-02", amount=Money("1000.00")),
    LedgerEntry(
        kind=LedgerEntryKind.CREDIT_APPLY, period="2027-02", amount=Money("500.00")
    ),
    LedgerEntry(kind=LedgerEntryKind.RECEIPT, period="2027-02", amount=Money("500.00")),
]


def test_the_total_is_two_thousand_and_specifically_not_two_thousand_five_hundred() -> (
    None
):
    """BR2.1's case totals 2000; counting the apply would read 2500.

    **This is the unit's central assertion.** The overstatement is
    exactly the credit, counted once when it arrived as a grant and
    again when it was spent as an apply -- and every ledger row still
    balances while it does so, which is why nothing else can catch it.

    2000 is what the student actually handed over: 1500 in month one and
    500 in month two.

    :return: None
    """
    totals = period_totals(BR21_CASE)
    total = Money.sum(totals.values())

    assert total == Money("2000.00"), (
        f"cash in totalled {total}, not 2000.00. 2500.00 means "
        "credit_apply is being counted as money received, which "
        "double-counts the credit -- once on arrival and again on use "
        "[BR2.1]. 4500.00 means charges are being summed."
    )
    assert total != Money("2500.00")


def test_month_one_and_month_two_are_fifteen_hundred_and_five_hundred() -> None:
    """The split behind the total, so a wrong split is visible.

    Kept **in addition to** the total rather than instead of it: on its
    own, month one's 1500 is identical under the correct fold and under
    the double-count, so this assertion cannot carry the rule.

    :return: None
    """
    totals = period_totals(BR21_CASE)

    assert totals["2027-01"] == Money("1500.00")
    assert totals["2027-02"] == Money("500.00")


def test_a_month_whose_charge_and_receipt_differ_excludes_the_charge() -> None:
    """Charge-summing has its own failing assertion [reliability § 1.1].

    For coverage rather than coincidence. The 2000/2500 case does catch
    charge-summing on its total (4500 against 2000), but it catches it
    on the *same* assertion as the double-count -- so a month whose
    charge and receipt differ separates the two defects.

    :return: None
    """
    entries = [
        LedgerEntry(
            kind=LedgerEntryKind.CHARGE, period="2027-05", amount=Money("2000.00")
        ),
        LedgerEntry(
            kind=LedgerEntryKind.RECEIPT, period="2027-05", amount=Money("300.00")
        ),
    ]

    assert period_totals(entries)["2027-05"] == Money("300.00")


def test_forgiveness_and_carries_are_not_money_received() -> None:
    """A waiver is not cash and a carry is an accounting move [BR2.1].

    :return: None
    """
    entries = [
        LedgerEntry(
            kind=LedgerEntryKind.FORGIVENESS, period="2027-06", amount=Money("400.00")
        ),
        LedgerEntry(
            kind=LedgerEntryKind.CARRY_FORWARD, period="2027-06", amount=Money("700.00")
        ),
        LedgerEntry(
            kind=LedgerEntryKind.CARRIED_OUT, period="2027-05", amount=Money("700.00")
        ),
    ]

    totals = period_totals(entries)

    assert totals.get("2027-06", Money.ZERO) == Money.ZERO
    assert totals.get("2027-05", Money.ZERO) == Money.ZERO


def test_the_cash_in_kinds_are_exactly_receipt_and_credit_grant() -> None:
    """The kind set, asserted against the money module's own mapping.

    **Hand-written in ``earnings.py`` and checked here rather than
    derived from ``IDENTITY_SIDE``.** ``app/money/_kinds.py`` states why:
    a test reading its expectation from the same place the
    implementation reads it would agree by construction, and a mis-sided
    kind would pass. So the implementation names its two kinds itself,
    and this test independently asserts they are the two the money
    module calls ``cash_in``.

    :return: None
    """
    from app.money._kinds import IDENTITY_SIDE

    cash_in = {kind for kind, side in IDENTITY_SIDE.items() if side == "cash_in"}

    assert CASH_IN_KINDS == frozenset(cash_in)
    assert CASH_IN_KINDS == frozenset(
        {LedgerEntryKind.RECEIPT, LedgerEntryKind.CREDIT_GRANT}
    )


def test_a_period_with_no_money_received_is_absent_from_the_fold() -> None:
    """Absence inside the fold, zero at the boundary [reliability § 1.3].

    The fold reports the periods that had cash in. Turning an absent
    period into a zero is the **response boundary's** job and is correct
    there; doing it inside the fold would hide a read that returned
    nothing.

    :return: None
    """
    entries = [
        LedgerEntry(
            kind=LedgerEntryKind.CHARGE, period="2027-07", amount=Money("900.00")
        ),
    ]

    assert "2027-07" not in period_totals(entries)


def test_under_two_months_of_history_returns_no_trend() -> None:
    """One point is not a trend [BR2.3].

    :return: None
    """
    one_month = [
        LedgerEntry(
            kind=LedgerEntryKind.RECEIPT, period="2027-01", amount=Money("1000.00")
        ),
    ]

    assert trend(period_totals(one_month)) is None


def test_two_months_returns_both_points_in_ascending_period_order() -> None:
    """Ordered in the fold, never sorted in the client [BR2.4].

    Asserted as a list rather than a set: the order **is** the contract,
    and a set assertion would pass against a client-sorted response.

    :return: None
    """
    series = trend(period_totals(BR21_CASE))

    assert series is not None
    assert [point.period for point in series] == ["2027-01", "2027-02"]
    assert [point.received for point in series] == [
        Money("1500.00"),
        Money("500.00"),
    ]


def test_the_trend_is_ascending_even_when_entries_arrive_reversed() -> None:
    """Order comes from the period key, not from insertion order.

    Period keys are fixed width, so lexical order IS chronological order
    and this is a sort rather than a parse.

    :return: None
    """
    series = trend(period_totals(list(reversed(BR21_CASE))))

    assert series is not None
    assert [point.period for point in series] == ["2027-01", "2027-02"]
