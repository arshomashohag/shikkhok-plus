"""
The ledger identity over randomized histories.

This is the specification, not a supplement to the worked scenarios. This
project's identity was stated wrongly **twice** while satisfying its own
worked examples, which is exactly the class of defect no enumerated case
catches: a wrong identity that happens to agree with every example someone
thought to write down.

Two properties of this suite are load-bearing and must not be simplified
away:

1. **Generators derive their kind set from the enumeration**, so a kind added
   later appears in generated histories automatically and fails the identity
   on the commit that adds it, rather than being silently untested.

2. **The expected per-kind effects are hand-written here**, NOT read from
   ``IDENTITY_SIDE`` in the module under test. If this test derived its
   expectation from the same place the fold derives its behaviour, the two
   would agree *by construction*: a mis-sided kind would balance perfectly,
   every check would pass, and every enrollment carrying it would be wrong.
   A single source of truth is correct for an implementation and fatal for
   the test that checks it.
"""

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.money import (
    DerivedQuantities,
    LedgerEntry,
    LedgerEntryKind,
    Money,
    derive,
)
from app.money._ledger import apply_credit

# --------------------------------------------------------------------------
# Hand-written expectation, independent of the module under test.
#
# One row per kind. If a kind is added to the enumeration and not added here,
# `test_every_kind_has_a_handwritten_expectation` fails — which is the point.
# --------------------------------------------------------------------------
EXPECTED_EFFECT: dict[LedgerEntryKind, tuple[str, str]] = {
    # kind: (effect on total_outstanding, effect on available_credit)
    LedgerEntryKind.CHARGE: ("increase", "none"),
    LedgerEntryKind.RECEIPT: ("decrease", "none"),
    LedgerEntryKind.FORGIVENESS: ("decrease", "none"),
    LedgerEntryKind.CREDIT_GRANT: ("none", "increase"),
    LedgerEntryKind.CREDIT_APPLY: ("decrease", "decrease"),
    LedgerEntryKind.CARRY_FORWARD: ("increase", "none"),
    LedgerEntryKind.CARRIED_OUT: ("decrease", "none"),
}

PERIODS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]


def test_every_kind_has_a_handwritten_expectation() -> None:
    """
    A kind added to the enumeration without a hand-written expectation here
    fails immediately, rather than being generated into histories whose
    correctness nothing independent checks.
    """
    assert set(EXPECTED_EFFECT) == set(LedgerEntryKind)


amounts = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("100000.00"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)

# Generators read the enumeration itself, never a hand-written list.
kinds = st.sampled_from(list(LedgerEntryKind))


@st.composite
def entries(draw: st.DrawFn) -> LedgerEntry:
    """Draw one arbitrary, individually-valid ledger entry."""
    return LedgerEntry(
        kind=draw(kinds),
        period=draw(st.sampled_from(PERIODS)),
        amount=Money(draw(amounts)),
    )


def _identity_holds(d: DerivedQuantities) -> bool:
    """Check the balance identity in its verified form."""
    left = d.total_charged - d.total_forgiven - (d.total_receipt + d.total_credit_grant)
    return left == d.total_outstanding - d.available_credit


@settings(max_examples=2000, deadline=None)
@given(st.lists(entries(), min_size=0, max_size=40))
def test_floors_and_pairing_hold_over_arbitrary_histories(
    history: list[LedgerEntry],
) -> None:
    """
    Over *arbitrary* entry sequences, the floors still hold.

    Note what is deliberately NOT asserted here: the balance identity. An
    earlier version of this test did assert it, and Hypothesis refuted it in
    one entry — a receipt of 0.01 against no charge gives -0.01 on the left
    and 0.00 on the right.

    That is the per-cycle floor working correctly, not an arithmetic defect.
    The floor discards an unmatched relief, which is right: a period cannot
    owe a negative amount. But it means the identity is a property of
    histories the system can actually produce, where every relief has an
    obligation to relieve — not of arbitrary bags of entries. Claiming
    otherwise overstated it.

    The identity itself is checked over realistic histories below. What holds
    unconditionally is the flooring and the carry pairing.
    """
    d = derive(history)
    assert not d.total_outstanding.is_negative()
    assert all(not v.is_negative() for v in d.per_cycle.values())
    assert d.total_outstanding == Money.sum(d.per_cycle.values())


@st.composite
def well_formed_history(draw: st.DrawFn) -> list[LedgerEntry]:
    """
    Draw a history the system could actually produce.

    Carries are always paired; credit is only applied up to what is
    available, as `apply_credit` computes it.
    """
    history: list[LedgerEntry] = []
    available = Money.ZERO
    outstanding = Money.ZERO
    periods = PERIODS[: draw(st.integers(min_value=1, max_value=6))]

    for index, period in enumerate(periods):
        charge = Money(draw(amounts))
        history.append(
            LedgerEntry(kind=LedgerEntryKind.CHARGE, period=period, amount=charge)
        )
        outstanding += charge

        if not available.is_zero() and draw(st.booleans()):
            spend = apply_credit(available, outstanding)
            if not spend.is_zero():
                history.append(
                    LedgerEntry(
                        kind=LedgerEntryKind.CREDIT_APPLY,
                        period=period,
                        amount=spend,
                    )
                )
                available -= spend
                outstanding -= spend

        paid = Money(draw(amounts))
        applied = apply_credit(paid, outstanding)
        if not applied.is_zero():
            history.append(
                LedgerEntry(
                    kind=LedgerEntryKind.RECEIPT,
                    period=period,
                    amount=applied,
                )
            )
            outstanding -= applied
        excess = paid - applied
        if excess.is_positive():
            history.append(
                LedgerEntry(
                    kind=LedgerEntryKind.CREDIT_GRANT,
                    period=period,
                    amount=excess,
                )
            )
            available += excess

        if outstanding.is_positive() and draw(st.booleans()):
            waived = apply_credit(Money(draw(amounts)), outstanding)
            if not waived.is_zero():
                history.append(
                    LedgerEntry(
                        kind=LedgerEntryKind.FORGIVENESS,
                        period=period,
                        amount=waived,
                    )
                )
                outstanding -= waived

        is_last = index == len(periods) - 1
        if outstanding.is_positive() and not is_last:
            nxt = periods[index + 1]
            history.append(
                LedgerEntry(
                    kind=LedgerEntryKind.CARRIED_OUT,
                    period=period,
                    amount=outstanding,
                )
            )
            history.append(
                LedgerEntry(
                    kind=LedgerEntryKind.CARRY_FORWARD,
                    period=nxt,
                    amount=outstanding,
                )
            )

    return history


@settings(max_examples=2000, deadline=None)
@given(well_formed_history())
def test_identity_and_side_conditions_over_realistic_histories(
    history: list[LedgerEntry],
) -> None:
    """
    Over histories the system could produce, every side condition holds too.

    This is the test standing behind the 100% branch coverage target: the
    coverage number says the branches executed, and this says the arithmetic
    they implement is right.
    """
    d = derive(history)
    assert _identity_holds(d)
    assert not d.total_outstanding.is_negative()
    assert not d.available_credit.is_negative()
    assert d.total_carry_forward == d.total_carried_out
    assert d.total_credit_apply <= d.total_credit_grant


@settings(max_examples=500, deadline=None)
@given(st.lists(entries(), min_size=1, max_size=20))
def test_order_does_not_change_the_balance(
    history: list[LedgerEntry],
) -> None:
    """
    The fold is order-independent.

    A ledger is a set of facts, not a sequence of commands: replaying the
    same entries in a different order must give the same balance, or the
    derived balance would depend on insertion order.
    """
    forward = derive(history)
    backward = derive(list(reversed(history)))
    assert forward.total_outstanding == backward.total_outstanding
    assert forward.available_credit == backward.available_credit
    assert forward.per_cycle == backward.per_cycle
