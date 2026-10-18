"""
The ledger fold and its derived quantities.

The eight worked scenarios below are transcribed from the functional design,
where each was computed term by term. They are not read back from the
implementation — they are the specification the implementation must satisfy.

Every scenario asserts the identity:

    total_charged - total_forgiven - (total_receipt + total_credit_grant)
        == total_outstanding - available_credit

together with available_credit >= 0, total_outstanding >= 0, and
sum(carry_forward) == sum(carried_out).
"""

import pytest

from app.money import (
    LedgerEntry,
    Money,
    MoneyValidationError,
    carry_forward,
    derive,
)
from app.money import (
    LedgerEntryKind as K,
)

MAR, APR, MAY = "2026-03", "2026-04", "2026-05"


def entry(kind: K, period: str, amount: str) -> LedgerEntry:
    """Build an entry for a scenario table."""
    return LedgerEntry(kind=kind, period=period, amount=Money(amount))


def assert_identity(entries: list[LedgerEntry]) -> None:
    """Assert the balance identity and its three side conditions."""
    d = derive(entries)
    left = d.total_charged - d.total_forgiven - (d.total_receipt + d.total_credit_grant)
    right = d.total_outstanding - d.available_credit
    assert left == right, f"identity failed: {left} != {right}"
    assert not d.available_credit.is_negative()
    assert not d.total_outstanding.is_negative()
    assert d.total_carry_forward == d.total_carried_out


class TestEntryValidation:
    """BR4.1 — the sign belongs to the kind."""

    def test_negative_amount_refused(self) -> None:
        with pytest.raises(MoneyValidationError):
            LedgerEntry(kind=K.CHARGE, period=MAR, amount=Money("-1.00"))

    def test_zero_amount_permitted(self) -> None:
        """A zero charge is representable and legal; it folds as zero."""
        e = LedgerEntry(kind=K.CHARGE, period=MAR, amount=Money.ZERO)
        assert derive([e]).total_outstanding == Money.ZERO


class TestWorkedScenarios:
    """The eight scenarios computed in the functional design."""

    def test_scenario_s1_paid_in_full(self) -> None:
        entries = [
            entry(K.CHARGE, MAR, "1000.00"),
            entry(K.RECEIPT, MAR, "1000.00"),
        ]
        d = derive(entries)
        assert d.total_outstanding == Money("0.00")
        assert d.available_credit == Money("0.00")
        assert_identity(entries)

    def test_scenario_s2_partial_payment(self) -> None:
        entries = [
            entry(K.CHARGE, MAR, "1000.00"),
            entry(K.RECEIPT, MAR, "600.00"),
        ]
        d = derive(entries)
        assert d.total_outstanding == Money("400.00")
        assert d.per_cycle[MAR] == Money("400.00")
        assert_identity(entries)

    def test_scenario_s3_shortfall_waived(self) -> None:
        entries = [
            entry(K.CHARGE, MAR, "1000.00"),
            entry(K.RECEIPT, MAR, "600.00"),
            entry(K.FORGIVENESS, MAR, "400.00"),
        ]
        d = derive(entries)
        assert d.total_outstanding == Money("0.00")
        assert d.total_forgiven == Money("400.00")
        assert_identity(entries)

    def test_scenario_s4_single_carry(self) -> None:
        """
        Two charges of 1000 with one carried: the total is 2000, the two
        charges — not 3000. A one-sided carry would read 3000, because
        March's 1000 would still stand while April's carried-in 1000 counted
        it again.
        """
        entries = [
            entry(K.CHARGE, MAR, "1000.00"),
            entry(K.CARRIED_OUT, MAR, "1000.00"),
            entry(K.CARRY_FORWARD, APR, "1000.00"),
            entry(K.CHARGE, APR, "1000.00"),
        ]
        d = derive(entries)
        assert d.total_outstanding == Money("2000.00")
        assert d.per_cycle[MAR] == Money("0.00")
        assert d.per_cycle[APR] == Money("2000.00")
        assert_identity(entries)

    def test_scenario_s5_multi_period_carry(self) -> None:
        """
        THE test that a single carry cannot replace.

        Three periods charging 1000 each, nothing paid, each balance carried
        on. The correct total is 3000. A one-sided model reads 4000 here —
        and only 3000 against a true 2000 at two periods, which is small
        enough to look plausible. The gap grows with every period.
        """
        entries = [
            entry(K.CHARGE, MAR, "1000.00"),
            entry(K.CARRIED_OUT, MAR, "1000.00"),
            entry(K.CARRY_FORWARD, APR, "1000.00"),
            entry(K.CHARGE, APR, "1000.00"),
            entry(K.CARRIED_OUT, APR, "2000.00"),
            entry(K.CARRY_FORWARD, MAY, "2000.00"),
            entry(K.CHARGE, MAY, "1000.00"),
        ]
        d = derive(entries)
        assert d.total_outstanding == Money("3000.00")
        assert d.per_cycle[MAR] == Money("0.00")
        assert d.per_cycle[APR] == Money("0.00")
        assert d.per_cycle[MAY] == Money("3000.00")
        assert d.total_carry_forward == Money("3000.00")
        assert_identity(entries)

    def test_scenario_s6_overpayment_makes_credit(self) -> None:
        """
        The scenario that killed the first correction attempt.

        An earlier identity read `charged + carried - received - forgiven ==
        outstanding - credit`, giving 0 on the left against -200 on the
        right. The cause: a receipt records only the APPLIED part, so the 200
        that physically arrived as a credit grant never reached the received
        side. Cash in is receipts PLUS credit grants.
        """
        entries = [
            entry(K.CHARGE, MAR, "1000.00"),
            entry(K.RECEIPT, MAR, "1000.00"),
            entry(K.CREDIT_GRANT, MAR, "200.00"),
        ]
        d = derive(entries)
        assert d.total_outstanding == Money("0.00")
        assert d.available_credit == Money("200.00")
        assert_identity(entries)

    def test_scenario_s7_credit_applied_later(self) -> None:
        """
        April's per-cycle figure needs its credit-applied term: 1000 - 800 -
        200 = 0. Without that term it computes 200 outstanding on a fully
        settled cycle, which was the second recorded error.

        The credit counts as received in April, the period whose charge it
        settles, not March where it arrived. [BR4.7]
        """
        entries = [
            entry(K.CHARGE, MAR, "1000.00"),
            entry(K.RECEIPT, MAR, "1000.00"),
            entry(K.CREDIT_GRANT, MAR, "200.00"),
            entry(K.CHARGE, APR, "1000.00"),
            entry(K.CREDIT_APPLY, APR, "200.00"),
            entry(K.RECEIPT, APR, "800.00"),
        ]
        d = derive(entries)
        assert d.total_outstanding == Money("0.00")
        assert d.available_credit == Money("0.00")
        assert d.per_cycle[APR] == Money("0.00")
        assert_identity(entries)

    def test_scenario_s8_credit_exceeds_charge(self) -> None:
        """
        1500 available against 1000 owed applies 1000 and retains 500.
        available_credit is non-negative BY CONSTRUCTION rather than by a
        floor — a floor would have discarded the 500 and broken the
        equality.
        """
        entries = [
            entry(K.CHARGE, MAR, "1000.00"),
            entry(K.RECEIPT, MAR, "1000.00"),
            entry(K.CREDIT_GRANT, MAR, "1500.00"),
            entry(K.CHARGE, APR, "1000.00"),
            entry(K.CREDIT_APPLY, APR, "1000.00"),
        ]
        d = derive(entries)
        assert d.total_outstanding == Money("0.00")
        assert d.available_credit == Money("500.00")
        assert_identity(entries)


class TestCarryForwardPairing:
    """BR4.6 — two-sided by construction, with no one-sided path."""

    def test_produces_both_sides(self) -> None:
        out_entry, in_entry = carry_forward(
            amount=Money("1000.00"), origin=MAR, receiver=APR
        )
        assert out_entry.kind is K.CARRIED_OUT
        assert out_entry.period == MAR
        assert in_entry.kind is K.CARRY_FORWARD
        assert in_entry.period == APR
        assert out_entry.amount == in_entry.amount

    def test_pair_cancels_against_the_charge_it_relieves(self) -> None:
        """
        The two sides cancel at enrollment level *when the origin period has
        the obligation they relieve* — which is the only way a carry is ever
        produced.

        A pair in isolation does NOT total zero, and that is correct rather
        than a defect: the origin period goes to -500 and floors at zero,
        while the receiver is charged 500. The floor is per-cycle and
        deliberate [BR4.4]. Asserting zero on a bare pair would be asserting
        that a floor does not exist.
        """
        entries = [
            entry(K.CHARGE, MAR, "500.00"),
            *carry_forward(Money("500.00"), origin=MAR, receiver=APR),
        ]
        d = derive(entries)
        assert d.per_cycle[MAR] == Money("0.00")
        assert d.per_cycle[APR] == Money("500.00")
        assert d.total_outstanding == Money("500.00")
        assert d.total_carry_forward == d.total_carried_out
        assert_identity(entries)

    def test_bare_pair_does_not_cancel_without_its_charge(self) -> None:
        """
        Stated explicitly so the asymmetry above is not read as a bug: the
        per-cycle floor means an unmatched relief is discarded, not carried
        as a negative.
        """
        pair = list(carry_forward(Money("500.00"), origin=MAR, receiver=APR))
        d = derive(pair)
        assert d.per_cycle[MAR] == Money("0.00")
        assert d.total_outstanding == Money("500.00")
        assert d.total_carry_forward == d.total_carried_out

    def test_negative_carry_refused(self) -> None:
        with pytest.raises(MoneyValidationError):
            carry_forward(Money("-1.00"), origin=MAR, receiver=APR)


class TestPerCycleAndFloors:
    """BR4.4 — outstanding floors at zero per cycle and in total."""

    def test_overpaid_cycle_floors_at_zero(self) -> None:
        """
        A cycle paid beyond its charge contributes zero outstanding, not a
        negative. The excess is a credit grant, not a negative balance.
        """
        entries = [
            entry(K.CHARGE, MAR, "500.00"),
            entry(K.RECEIPT, MAR, "500.00"),
            entry(K.CREDIT_GRANT, MAR, "100.00"),
            entry(K.CHARGE, APR, "300.00"),
        ]
        d = derive(entries)
        assert d.per_cycle[MAR] == Money("0.00")
        assert d.total_outstanding == Money("300.00")
        assert_identity(entries)

    def test_empty_ledger(self) -> None:
        d = derive([])
        assert d.total_outstanding == Money.ZERO
        assert d.available_credit == Money.ZERO
        assert d.per_cycle == {}
        assert_identity([])
