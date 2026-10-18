"""
Ledger entries as values, and the fold that derives a balance from them.

**This module persists nothing.** It owns no table, no row, no identifier and
no supersession. A :class:`LedgerEntry` here is a *value shape*: what an entry
means arithmetically, and what a sequence of them implies about a balance. The
unit that owns the table implements against these semantics and must not
restate or reimplement them.

The balance is **derived, never stored** [BR4.2]. The ledger is append-only,
so a stored total would be a second source of truth that drifts from the
entries that produce it. Every quantity in :class:`DerivedQuantities` is a
fold over entries; none is a field anybody writes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import assert_never

from ._errors import MoneyValidationError
from ._kinds import LedgerEntryKind
from ._money import Money


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """
    One entry in an enrollment's ledger.

    :ivar kind: What the entry means. The sign of its contribution is carried
        here, never by the amount.
    :ivar period: The fee cycle the entry belongs to, as an opaque key. This
        module holds no calendar knowledge: period arithmetic belongs to the
        unit that owns fee cycles.
    :ivar amount: A non-negative amount.
    """

    kind: LedgerEntryKind
    period: str
    amount: Money

    def __post_init__(self) -> None:
        """
        Refuse a negative amount.

        A negative amount reaching the fold would invert a term's
        contribution silently. A correction is a compensating entry of the
        appropriate kind, never a negative amount on the original kind.

        :raises MoneyValidationError: If the amount is negative.
        """
        if self.amount.is_negative():
            raise MoneyValidationError(
                f"A {self.kind.value} entry cannot carry a negative amount "
                f"({self.amount}). The sign belongs to the kind; a "
                "correction is a compensating entry."
            )


@dataclass(frozen=True, slots=True)
class DerivedQuantities:
    """
    Everything a balance is, computed from a sequence of entries.

    :ivar total_charged: Every obligation placed.
    :ivar total_receipt: Cash applied to obligations.
    :ivar total_forgiven: Obligations waived.
    :ivar total_credit_grant: Money received in excess of what was owed.
    :ivar total_credit_apply: Held credit spent against later obligations.
    :ivar total_carry_forward: Obligations carried into periods.
    :ivar total_carried_out: Obligations carried out of periods. Equals
        :attr:`total_carry_forward` whenever carries are correctly paired.
    :ivar total_outstanding: What is still owed, floored at zero.
    :ivar per_cycle: Outstanding per period, each floored at zero.
    :ivar available_credit: Credit held and not yet spent, non-negative by
        construction rather than by a floor.
    """

    total_charged: Money
    total_receipt: Money
    total_forgiven: Money
    total_credit_grant: Money
    total_credit_apply: Money
    total_carry_forward: Money
    total_carried_out: Money
    total_outstanding: Money
    per_cycle: dict[str, Money]
    available_credit: Money


def derive(entries: list[LedgerEntry]) -> DerivedQuantities:
    """
    Fold a sequence of entries into every derived quantity.

    A single linear pass, with no nested iteration: this runs inside the
    hottest query in the system, on one small instance.

    The ``match`` below is **total over the kind enumeration**, with
    :func:`typing.assert_never` in the position an unrecognised kind would
    reach. The type checker proves the mapping exhaustive, so adding a kind
    without extending this fold fails the type check rather than silently
    excluding the new kind from the sums — which is the specific failure that
    produces a balance that looks right and is not.

    :param entries: The entries to fold, in any order.
    :return: Every derived quantity, including the per-period breakdown.
    """
    zero = Money.ZERO
    charged = receipt = forgiven = zero
    grant = applied = carried_in = carried_out = zero

    cycle_charged: defaultdict[str, Money] = defaultdict(lambda: zero)
    cycle_relieved: defaultdict[str, Money] = defaultdict(lambda: zero)
    #: What each period waived, tracked separately because a waiver cannot
    #: relieve more than its own period owed.
    cycle_forgiven: defaultdict[str, Money] = defaultdict(lambda: zero)

    for item in entries:
        kind = item.kind
        amount = item.amount
        match kind:
            case LedgerEntryKind.CHARGE:
                charged += amount
                cycle_charged[item.period] += amount
            case LedgerEntryKind.RECEIPT:
                receipt += amount
                cycle_relieved[item.period] += amount
            case LedgerEntryKind.FORGIVENESS:
                forgiven += amount
                cycle_relieved[item.period] += amount
                cycle_forgiven[item.period] += amount
            case LedgerEntryKind.CREDIT_GRANT:
                grant += amount
            case LedgerEntryKind.CREDIT_APPLY:
                applied += amount
                cycle_relieved[item.period] += amount
            case LedgerEntryKind.CARRY_FORWARD:
                carried_in += amount
                cycle_charged[item.period] += amount
            case LedgerEntryKind.CARRIED_OUT:
                carried_out += amount
                cycle_relieved[item.period] += amount
            case _ as unreachable:
                assert_never(unreachable)

    # BR4.4 and ADR-002's identity are **mathematically incompatible**
    # whenever a period is over-relieved, and no implementation satisfies
    # both. The conflict was found at code review after two wrong answers in
    # a row, and is recorded in full in code-summary.md; it needs a human
    # decision, not another arithmetic patch.
    #
    # The identity, rearranged, defines
    #     outstanding = charged - forgiven - receipt - applied
    # which is a pure enrollment-level quantity with no per-period structure.
    # BR4.4 defines it as the sum of floored per-cycle figures. Minimal
    # divergence: March charges 100 and receives 150, April charges 100.
    # BR4.4 gives 100 ("April still owes 100" — true). The identity gives 50
    # ("the family is 50 ahead overall" — also true). Two honest answers to
    # two different questions, sharing one name.
    #
    # **This implementation follows BR4.4's RATIONALE rather than its
    # literal formula**, pending a human decision on the conflict. Taking the
    # formula literally reintroduces the money loss it was written before
    # anyone knew about: a 400 payment recorded against an already-carried
    # March floors away entirely.
    #
    # So: cash surplus (a receipt or an applied credit) is real money and
    # settles the enrollment's debt wherever it was recorded. Waiver surplus
    # is an accounting act that can only relieve what its own period owed, so
    # it is discarded — which is exactly the phantom offset BR4.4's rationale
    # forbids. Both named failures are then correct, and the eight worked
    # scenarios are unaffected because none of them over-relieves a period.
    #
    # What is NOT in dispute, and what the floors still guarantee: per-cycle
    # figures never go negative, and one over-settled cycle never silently
    # cancels another cycle's genuine debt — the offset BR4.4's rationale
    # exists to forbid.
    per_cycle: dict[str, Money] = {}
    #: Surplus relief that is real money rather than an accounting act, so it
    #: settles the enrollment's debt instead of evaporating with the period
    #: it was recorded against.
    surplus_cash = zero

    for period in {*cycle_charged, *cycle_relieved}:
        signed = cycle_charged[period] - cycle_relieved[period]
        per_cycle[period] = _floor(signed)
        if signed.is_negative():
            surplus = -signed
            waived = cycle_forgiven[period]
            phantom = waived if waived < surplus else surplus
            surplus_cash += surplus - phantom

    outstanding = _floor(Money.sum(per_cycle.values()) - surplus_cash)

    return DerivedQuantities(
        total_charged=charged,
        total_receipt=receipt,
        total_forgiven=forgiven,
        total_credit_grant=grant,
        total_credit_apply=applied,
        total_carry_forward=carried_in,
        total_carried_out=carried_out,
        total_outstanding=outstanding,
        per_cycle=per_cycle,
        available_credit=_floor(grant - applied),
    )


def carry_forward(
    amount: Money,
    origin: str,
    receiver: str,
    origin_balance: Money | None = None,
) -> tuple[LedgerEntry, LedgerEntry]:
    """
    Carry an unpaid balance forward, as the pair it must always be.

    One operation producing two entries, never two independently callable
    operations. That makes ``sum(carry_forward) == sum(carried_out)``
    structurally true rather than something a caller must remember, and means
    a one-sided carry cannot be written.

    A one-sided carry counts the same debt in both periods: carrying 1000 into
    a second 1000 charge reads 3000 owed against a true 2000, and the gap
    grows with every period.

    :param amount: The balance to carry. Must be non-negative, and must not
        exceed `origin_balance` when that is supplied.
    :param origin: The period being relieved.
    :param receiver: The period being charged.
    :param origin_balance: What the origin period actually owes. Supply it
        wherever it is known — which is every path the system has, since a
        carry is only ever produced from a computed balance.
    :return: The ``carried_out`` entry against the origin, then the
        ``carry_forward`` entry against the receiver.
    :raises MoneyValidationError: If the amount is negative, or exceeds the
        origin period's balance.
    """
    if origin_balance is not None and amount > origin_balance:
        # Carrying more than the origin owes manufactures debt: the receiver
        # is charged the full amount while the origin is relieved only down
        # to its floor, and the surplus appears from nowhere.
        #
        # This mirrors `apply_credit`, which computes min(available, owed)
        # precisely so over-application is unrepresentable rather than
        # refused. The same argument applies verbatim to a carry, and an
        # earlier version of this function made the opposite choice by
        # accepting whatever it was handed.
        raise MoneyValidationError(
            f"Cannot carry {amount} out of {origin}, which owes "
            f"{origin_balance}. Carrying more than is owed manufactures "
            "debt."
        )
    return (
        LedgerEntry(kind=LedgerEntryKind.CARRIED_OUT, period=origin, amount=amount),
        LedgerEntry(
            kind=LedgerEntryKind.CARRY_FORWARD,
            period=receiver,
            amount=amount,
        ),
    )


def apply_credit(available: Money, owed: Money) -> Money:
    """
    Decide how much held credit to spend against an obligation.

    The applied amount is the smaller of the two, which is why applying more
    credit than is available is *unrepresentable* rather than refused: the
    amount is computed here rather than supplied by a caller. Flooring the
    derived credit instead would discard value and break the identity.

    :param available: Credit currently held.
    :param owed: The obligation to settle.
    :return: The amount to apply, never exceeding either input.
    """
    return available if available < owed else owed


def _floor(value: Money) -> Money:
    """
    Clamp a signed balance to zero.

    :param value: The possibly-negative balance.
    :return: The value, or zero if it is negative.
    """
    return Money.ZERO if value.is_negative() else value
