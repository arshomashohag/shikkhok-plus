"""The server-computed fee status [BR6.1].

**Four values rather than two, and the fourth is why this exists.** A
fully waived cycle has a zero balance and is **not** "Paid": nobody
paid, the teacher excused it. `if (balance > 0) "Due" else "Paid"` is a
business rule about what counts as due, written where it looks like
presentation, and it diverges from the server the first time a waiver or
a credit is involved.

The team practice names this as one of the two places the layer boundary
is tested hardest in this product. The client switches on the value this
module returns and performs no arithmetic of its own.
"""

from __future__ import annotations

import uuid
from typing import Final, Literal

from sqlalchemy.orm import Session

from app.fees.balances import entries_for_enrollment
from app.money import LedgerEntry, LedgerEntryKind, Money, derive

__all__ = [
    "CLAIM_STATUS_VALUES",
    "DISPOSITION_VALUES",
    "FEE_STATUS_VALUES",
    "ClaimStatus",
    "FeeStatus",
    "ShortfallDisposition",
    "fee_status",
    "status_from_entries",
]

#: The four statuses as a TYPE, not only as a tuple of strings.
#:
#: Declared here and imported by ``app.schemas.fees`` rather than
#: restated there, so the response schema and the function computing
#: the value are the same closed set by construction. Restating it
#: would need a ``type: ignore`` at every call site crossing the two --
#: and an ignore is how a widening in one place stops being checked
#: against the other.
FeeStatus = Literal["paid", "partly_paid", "unpaid", "waived"]

#: The four a claim may report [BR6.3].
ClaimStatus = Literal["pending", "approved_full", "approved_partial", "rejected"]

#: The teacher's choice on approving less than was charged [BR5.4].
ShortfallDisposition = Literal["carried", "waived"]

#: The same two as a TYPED tuple, so a membership test against it
#: narrows rather than merely checking. ``app.db.models`` carries the
#: untyped twin that the database enum is built from, and a test
#: asserts the two agree -- one declaration could not serve both,
#: because the model's list must stay importable without pulling the
#: fee package into the ORM.
DISPOSITION_VALUES: Final[tuple[ShortfallDisposition, ...]] = ("carried", "waived")

#: The four statuses a cycle may report [BR6.1]. Closed: a fifth is a
#: contract change the client must be released for, not a data change.
FEE_STATUS_VALUES: Final[tuple[FeeStatus, ...]] = (
    "paid",
    "partly_paid",
    "unpaid",
    "waived",
)

#: The four a claim may report [BR6.3], mirroring the database enum.
#: Restated here so the client contract has one import rather than
#: reaching into the ORM, and asserted equal to the column's values by
#: a test.
CLAIM_STATUS_VALUES: Final[tuple[ClaimStatus, ...]] = (
    "pending",
    "approved_full",
    "approved_partial",
    "rejected",
)

#: Kinds that relieve a period by moving money, as opposed to excusing
#: the obligation. ``carried_out`` counts: the balance really did leave
#: this period, and the obligation now lives in the receiving one.
_CASH_RELIEF: Final[frozenset[LedgerEntryKind]] = frozenset(
    {
        LedgerEntryKind.RECEIPT,
        LedgerEntryKind.CREDIT_APPLY,
        LedgerEntryKind.CARRIED_OUT,
    }
)


def status_from_entries(entries: list[LedgerEntry], period: str) -> FeeStatus:
    """Compute one cycle's status from entries already in hand.

    **The pure half, split out so a batch-wide view folds each
    enrollment's ledger ONCE** [NFR20.16, NFR20.17]. :func:`fee_status`
    reads the rows and calls this; a caller that already holds them --
    the teacher's batch overview, which fetches every seat's entries in
    one statement -- calls this directly rather than issuing a second
    read per seat.

    That split is not a refinement. Before it, building one roster row
    folded the same enrollment's ledger twice and read its cycles a
    third time, so the view cost three statements per seat: 77 for a
    25-seat batch against 8 for a two-seat one.

    :param entries: Every entry for ONE enrollment, in any order
    :param period: The period, as ``YYYY-MM``
    :return: One of :data:`FEE_STATUS_VALUES`
    :raises KeyError: The period has no entries at all. A period nobody
        charged is not "paid": there is nothing for a status to
        describe, and returning one would let a caller render a settled
        cycle for a month that never happened.
    """
    in_period = [entry for entry in entries if entry.period == period]
    if not in_period:
        raise KeyError(period)

    outstanding = derive(entries).per_cycle.get(period, Money.ZERO)
    kinds = {entry.kind for entry in in_period}

    if outstanding.is_positive():
        # Something is still owed. Partly paid only if some relief was
        # actually recorded -- otherwise nothing has happened to it.
        relieved = kinds & (_CASH_RELIEF | {LedgerEntryKind.FORGIVENESS})
        return "partly_paid" if relieved else "unpaid"

    # Settled. The distinction is HOW: a cycle relieved by forgiveness
    # alone is waived, and one where money or credit arrived is paid.
    return "paid" if kinds & _CASH_RELIEF else "waived"


def fee_status(
    session: Session,
    *,
    enrollment_id: uuid.UUID,
    period: str,
) -> FeeStatus:
    """Compute one cycle's status, reading that seat's ledger.

    The single-enrollment entry point. A caller looping over seats
    should fetch the ledger once and call :func:`status_from_entries`
    instead; doing otherwise is the N+1 that NFR20.17 names.

    :param session: The session to read through
    :param enrollment_id: The seat
    :param period: The period, as ``YYYY-MM``
    :return: One of :data:`FEE_STATUS_VALUES`
    :raises KeyError: The period has no entries at all
    """
    return status_from_entries(entries_for_enrollment(session, enrollment_id), period)
