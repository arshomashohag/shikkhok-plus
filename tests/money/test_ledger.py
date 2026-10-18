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

    def test_bare_pair_nets_to_zero_at_enrollment_level(self) -> None:
        """
        A carry pair in isolation nets to zero for the enrollment.

        **This test asserted 500.00 before the code review**, matching the
        old arithmetic where the total was the sum of independently-floored
        periods: March floored to zero while April was charged 500, so the
        relief vanished. That was the defect, not the specification.

        Now the total is the floor of the sum, so the two sides of a carry
        cancel as BR4.6 says they do — the per-period figures still show
        March 0.00 and April 500.00, because a period cannot display a
        negative balance.
        """
        pair = list(carry_forward(Money("500.00"), origin=MAR, receiver=APR))
        d = derive(pair)
        assert d.per_cycle[MAR] == Money("0.00")
        assert d.per_cycle[APR] == Money("500.00")
        assert d.total_outstanding == Money("0.00")
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


class TestSurplusReliefIsNotDiscarded:
    """
    Regressions for the defect found at code review.

    `total_outstanding` was the SUM OF THE PER-PERIOD FLOORS, so relief that
    exceeded one period's charges was silently discarded and the enrollment
    showed more debt than it had. The 198-test suite passed throughout,
    because the property test's generator could not produce these shapes.

    The total is now the FLOOR OF THE SUM. Per-period figures keep their own
    floors, since a period showing a negative balance means nothing to a
    teacher — but the surplus those floors discard is recovered at the
    enrollment level.
    """

    def test_late_payment_against_a_carried_period(self) -> None:
        """
        The one that would have been noticed in the field, eventually.

        A parent pays 400 for March in April, after March's balance was
        already carried forward. March is relieved by its `carried_out`, so
        under the old arithmetic the 400 floored away and the student still
        showed the full 2000 owed.
        """
        entries = [
            entry(K.CHARGE, MAR, "1000.00"),
            *carry_forward(Money("1000.00"), origin=MAR, receiver=APR),
            entry(K.CHARGE, APR, "1000.00"),
            entry(K.RECEIPT, MAR, "400.00"),
        ]
        d = derive(entries)
        assert d.total_outstanding == Money("1600.00")
        assert_identity(entries)

    def test_waiver_exceeding_a_period_does_not_offset_another(self) -> None:
        """
        A waiver can only relieve what its own period owed.

        **This test asserted the opposite through two review iterations**, and
        both answers were wrong in different directions. March is paid in
        full AND waived in full against a single 1000 charge, leaving 1000 of
        phantom relief. An intermediate fix let that phantom cancel April's
        genuine unpaid charge, so the books read zero owed while April owed a
        thousand — precisely the offset BR4.4's rationale warned about.

        A waiver is an accounting act, not money: waiving more than a period
        owes creates nothing, so the surplus is discarded. Cash behaves
        differently, which is what the late-payment test covers.
        """
        entries = [
            entry(K.CHARGE, MAR, "1000.00"),
            entry(K.RECEIPT, MAR, "1000.00"),
            entry(K.FORGIVENESS, MAR, "1000.00"),
            entry(K.CHARGE, APR, "1000.00"),
        ]
        d = derive(entries)
        assert d.total_outstanding == Money("1000.00")
        assert d.per_cycle[APR] == Money("1000.00")

    def test_overpaid_cash_reduces_the_enrollment(self) -> None:
        """
        Cash is real wherever it lands. Overpaying March by 500 reduces what
        the enrollment owes, rather than evaporating with the period.
        """
        entries = [
            entry(K.CHARGE, MAR, "1000.00"),
            entry(K.RECEIPT, MAR, "1500.00"),
            entry(K.CHARGE, APR, "1000.00"),
        ]
        d = derive(entries)
        assert d.per_cycle[MAR] == Money("0.00")
        assert d.total_outstanding == Money("500.00")

    def test_total_never_exceeds_the_sum_of_per_cycle_floors(self) -> None:
        """
        The relationship is an inequality, and this is its direction.

        The total sums the floored per-cycle figures [BR4.4] and then returns
        the CASH portion of any surplus, so it can be lower than that sum but
        never higher.
        """
        entries = [
            entry(K.CHARGE, MAR, "1000.00"),
            entry(K.RECEIPT, MAR, "1500.00"),
            entry(K.CHARGE, APR, "1000.00"),
        ]
        d = derive(entries)
        assert d.total_outstanding <= Money.sum(d.per_cycle.values())


class TestCarryCannotManufactureDebt:
    """
    `carry_forward` accepted any amount, unrelated to what the origin owed.

    The module argues the opposite way for credit: `apply_credit` computes
    min(available, owed) so over-application is unrepresentable. The same
    argument applies verbatim to a carry.
    """

    def test_over_carry_refused(self) -> None:
        with pytest.raises(MoneyValidationError):
            carry_forward(
                Money("1000.00"),
                origin=MAR,
                receiver=APR,
                origin_balance=Money("600.00"),
            )

    def test_carry_within_balance_allowed(self) -> None:
        out_entry, in_entry = carry_forward(
            Money("600.00"),
            origin=MAR,
            receiver=APR,
            origin_balance=Money("600.00"),
        )
        assert out_entry.amount == in_entry.amount == Money("600.00")
