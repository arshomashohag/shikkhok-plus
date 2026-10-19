"""
The ledger vocabulary: seven kinds, closed.

The balance identity is true *only because* each kind sits on a known side of
it. Closure is therefore not a tidiness preference — an eighth kind folded
into neither side would balance perfectly across the seven it knows about,
while every enrollment carrying the new kind would be wrong.

Closure is enforced two ways, and both are needed:

- **Statically**, by an exhaustive match in the fold. Adding a member here
  without extending the fold fails the type check.
- **In the property test**, whose generators derive their kind set from this
  enumeration, so a new kind appears in randomized histories automatically
  and fails the identity on the commit that adds it.

The property test additionally carries a *hand-written* expected effect per
kind, independent of :data:`IDENTITY_SIDE` below. That independence is the
point: if the test read its expectation from the same place the fold reads
it, the two would agree by construction and a mis-sided kind would pass.
"""

from enum import StrEnum, unique


@unique
class LedgerEntryKind(StrEnum):
    """
    What a ledger entry means.

    Seven values, and never an eighth without deciding which side of the
    identity it falls on.

    Every kind classifies a **non-negative** amount: the sign is carried by
    the kind, never by the amount. [BR4.1]
    """

    #: An obligation placed on an enrollment for a period.
    CHARGE = "charge"

    #: Money received and applied to an obligation.
    RECEIPT = "receipt"

    #: An obligation carried *into* this period from an earlier one.
    #: Always paired with a :attr:`CARRIED_OUT` of equal amount. [BR4.6]
    CARRY_FORWARD = "carry_forward"

    #: An obligation carried *out of* this period, relieving it.
    #: Always paired with a :attr:`CARRY_FORWARD` of equal amount. [BR4.6]
    CARRIED_OUT = "carried_out"

    #: An obligation waived by the teacher. Leaves the identity on the
    #: forgiven term, separately from cash in, which is what lets analytics
    #: exclude waivers from a collection-rate denominator while balancing.
    FORGIVENESS = "forgiveness"

    #: Money received in excess of what was owed, held against the
    #: enrollment. Cash in is receipts **plus** credit grants: money received
    #: as credit is money received.
    CREDIT_GRANT = "credit_grant"

    #: Held credit spent against a later obligation. Never exceeds the
    #: available credit, because the applied amount is computed as
    #: ``min(available, owed)`` rather than supplied by a caller. [BR4.5]
    CREDIT_APPLY = "credit_apply"


#: Which side of the balance identity each kind contributes to.
#:
#: **This mapping is for readers, not for the fold and not for the test.**
#: The fold matches exhaustively on the kind itself so the type checker can
#: prove totality; the property test carries its own hand-written
#: expectations. A single source of truth is correct for the implementation
#: and fatal for the test that checks it.
IDENTITY_SIDE: dict[LedgerEntryKind, str] = {
    LedgerEntryKind.CHARGE: "obligation",
    LedgerEntryKind.RECEIPT: "cash_in",
    LedgerEntryKind.CREDIT_GRANT: "cash_in",
    LedgerEntryKind.FORGIVENESS: "forgiven",
    LedgerEntryKind.CREDIT_APPLY: "credit_spent",
    LedgerEntryKind.CARRY_FORWARD: "internal_transfer",
    LedgerEntryKind.CARRIED_OUT: "internal_transfer",
}
