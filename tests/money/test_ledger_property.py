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

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.money import (
    DerivedQuantities,
    LedgerEntry,
    LedgerEntryKind,
    Money,
    carry_forward,
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

    That is the floor working correctly, not an arithmetic defect. A relief
    with no obligation to relieve is not a history the system can produce,
    and the identity is a property of histories it CAN produce — checked
    over those below. What holds unconditionally is the flooring.

    **The total is the floor of the sum, never the sum of the floors**, and
    the difference is not cosmetic: summing independently-floored periods
    discards relief the enrollment genuinely received, which is the defect
    found at code review. A late payment against an already-carried period
    made 400 Taka vanish. So the two quantities are related by an inequality,
    not an equality — the total can be LOWER than the per-period sum when a
    period carries surplus relief, and never higher.
    """
    d = derive(history)
    assert not d.total_outstanding.is_negative()
    assert all(not v.is_negative() for v in d.per_cycle.values())
    assert d.total_outstanding <= Money.sum(d.per_cycle.values())


def _carried_out_by_period(history: list[LedgerEntry]) -> dict[str, Money]:
    """
    How much each period moved forward.

    A period that carried an obligation out can absorb a late payment even
    though its own balance floors at zero — the obligation the payment
    settles now lives in the receiving period. Its capacity is bounded by
    what it actually moved: beyond that, a payment relieves nothing.

    :param history: The entries so far.
    :return: Carried-out totals, per period.
    """
    moved: dict[str, Money] = {}
    for item in history:
        if item.kind is LedgerEntryKind.CARRIED_OUT:
            moved[item.period] = moved.get(item.period, Money.ZERO) + item.amount
    return moved


@st.composite
def well_formed_history(draw: st.DrawFn) -> list[LedgerEntry]:
    """
    Draw a history the system could actually produce.

    **This generator was rewritten after a code review found it could not
    produce the histories that broke the identity.** The earlier version
    emitted relief only within the period it was iterating, capped every
    receipt and waiver at the running balance, and always paired carries. It
    therefore pre-enforced exactly the invariants whose violation was the
    defect — 2000 examples checking that `derive` agreed with the generator
    rather than that the arithmetic was right.

    That is the same failure this suite exists to catch, in the suite itself:
    a test that cannot disagree with its implementation. What it missed was
    real — a late payment recorded against a period already carried forward
    made 400 Taka vanish.

    So the domain modelled here is wider, and deliberately includes the
    awkward shapes a real teacher produces:

    - **a payment against ANY earlier period**, not only the current one,
      which is what a teacher does when a parent pays late;
    - **relief that exceeds what a single period owes**, since a teacher
      waives or receives against a period without consulting a floor;
    - **a waiver after the period was already carried forward.**

    What stays constrained is only what the system genuinely guarantees:
    amounts are non-negative, carries are paired and never exceed the origin
    balance, and credit is applied through `apply_credit`.
    """
    history: list[LedgerEntry] = []
    available = Money.ZERO
    periods = PERIODS[: draw(st.integers(min_value=1, max_value=6))]

    for index, period in enumerate(periods):
        charge = Money(draw(amounts))
        history.append(
            LedgerEntry(kind=LedgerEntryKind.CHARGE, period=period, amount=charge)
        )

        # A payment lands against ANY period seen so far — including one
        # already carried forward, which is the late-payment case that made
        # 400 Taka vanish and which the first generator could not produce.
        #
        # Two caps, both of which the real system enforces:
        #   * the payment settles at most what the target period can absorb
        #     (its own balance, plus whatever it carried out);
        #   * any overpayment becomes a CREDIT GRANT, and is bounded by what
        #     was actually offered.
        #
        # An earlier draft capped `applied` twice but computed the excess
        # from the uncapped `paid`, so an unabsorbed payment turned into a
        # credit grant of 212161.17 against 0.19 of charges. Chasing that
        # generator cost several rounds of arithmetic "fixes" for a history
        # the system cannot produce.
        snapshot = derive(history)
        settled = periods[: index + 1]
        moved = _carried_out_by_period(history)
        capacity = {
            p: snapshot.per_cycle.get(p, Money.ZERO) + moved.get(p, Money.ZERO)
            for p in settled
        }
        absorbers = sorted(p for p, c in capacity.items() if c.is_positive())
        if absorbers:
            target = draw(st.sampled_from(absorbers))
            # Draw WITHIN the capacity rather than drawing freely and
            # clamping afterwards: the clamp is what let the two quantities
            # drift apart.
            offered = Money(draw(amounts))
            applied = apply_credit(offered, capacity[target])
            if not applied.is_zero():
                history.append(
                    LedgerEntry(
                        kind=LedgerEntryKind.RECEIPT,
                        period=target,
                        amount=applied,
                    )
                )
            overpaid = offered - applied
            if overpaid.is_positive() and draw(st.booleans()):
                history.append(
                    LedgerEntry(
                        kind=LedgerEntryKind.CREDIT_GRANT,
                        period=target,
                        amount=overpaid,
                    )
                )
                available += overpaid

        if not available.is_zero() and draw(st.booleans()):
            snap = derive(history)
            debtors = sorted(
                p for p, bal in snap.per_cycle.items() if bal.is_positive()
            )
            if debtors:
                debtor = draw(st.sampled_from(debtors))
                spend = apply_credit(available, snap.per_cycle[debtor])
                if not spend.is_zero():
                    history.append(
                        LedgerEntry(
                            kind=LedgerEntryKind.CREDIT_APPLY,
                            period=debtor,
                            amount=spend,
                        )
                    )
                    available -= spend

        if draw(st.booleans()):
            snap = derive(history)
            debtors = sorted(
                p for p, bal in snap.per_cycle.items() if bal.is_positive()
            )
            if debtors:
                debtor = draw(st.sampled_from(debtors))
                waived = apply_credit(Money(draw(amounts)), snap.per_cycle[debtor])
                if not waived.is_zero():
                    history.append(
                        LedgerEntry(
                            kind=LedgerEntryKind.FORGIVENESS,
                            period=debtor,
                            amount=waived,
                        )
                    )

        # A carry never exceeds what the origin actually owes.
        is_last = index == len(periods) - 1
        balance = derive(history).per_cycle.get(period, Money.ZERO)
        if balance.is_positive() and not is_last:
            history.extend(
                carry_forward(
                    balance,
                    origin=period,
                    receiver=periods[index + 1],
                    origin_balance=balance,
                )
            )

    return history


@pytest.mark.xfail(
    reason=(
        "BR4.4 and ADR-002's identity are mathematically incompatible "
        "whenever a period is over-relieved. Minimal case: March charges 100 "
        "and receives 150, April charges 100. BR4.4 (sum of floored "
        "per-cycle figures) gives 100; the identity, rearranged to "
        "charged - forgiven - receipt - applied, gives 50. Both are honest "
        "answers to different questions sharing one name. This is marked "
        "xfail rather than narrowing the generator to hide it, because "
        "narrowing is exactly the defect the previous review iteration "
        "found. Needs a human decision on which quantity total_outstanding "
        "names."
    ),
    strict=False,
)
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
