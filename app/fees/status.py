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
from collections.abc import Mapping
from typing import Final, Literal

from sqlalchemy.orm import Session

from app.fees.balances import entries_for_enrollment
from app.money import LedgerEntry, LedgerEntryKind, Money, derive

__all__ = [
    "CLAIM_STATUS_VALUES",
    "DISPOSITION_VALUES",
    "FEE_STATUS_VALUES",
    "MONTH_STATE_VALUES",
    "SUBMISSION_STATUS_VALUES",
    "ClaimStatus",
    "FeeStatus",
    "MonthState",
    "ShortfallDisposition",
    "SubmissionStatus",
    "fee_status",
    "month_state",
    "status_from_entries",
    "statuses_from_entries",
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

#: The five states a month reports on a teacher's strip: the four fee
#: statuses plus ``checking``, a payment waiting for the teacher.
MonthState = Literal["paid", "partly_paid", "unpaid", "waived", "checking"]

#: The same five as a typed tuple.
MONTH_STATE_VALUES: Final[tuple[MonthState, ...]] = (
    "paid",
    "partly_paid",
    "unpaid",
    "waived",
    "checking",
)

#: The four a claim may report [BR6.3].
ClaimStatus = Literal["pending", "approved_full", "approved_partial", "rejected"]

#: The teacher's choice on approving less than was charged [BR5.4].
ShortfallDisposition = Literal["carried", "waived"]

#: The three a payment submission may report.
SubmissionStatus = Literal["pending", "approved", "rejected"]

#: The same three as a typed tuple, so a membership test narrows.
SUBMISSION_STATUS_VALUES: Final[tuple[SubmissionStatus, ...]] = (
    "pending",
    "approved",
    "rejected",
)

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
    return _status(outstanding, {entry.kind for entry in in_period})


def statuses_from_entries(entries: list[LedgerEntry]) -> dict[str, FeeStatus]:
    """Compute every period's status from ONE fold of one seat's entries.

    :func:`status_from_entries` folds the whole ledger to answer one
    period, so asking it once per cycle is quadratic in the seat's age
    [C-14]. This folds once and answers every period an entry touches,
    by the same rule: a period absent from the result is one
    :func:`status_from_entries` refuses with ``KeyError``.

    Entries summed per (period, kind) give the same answer, because the
    rule reads only the fold's per-period outstanding and which kinds
    are present -- ``tests/fees/test_status_single_fold.py``.

    :param entries: Every entry for ONE enrollment, in any order
    :return: Period to its status, for every period with entries
    """
    per_cycle = derive(entries).per_cycle
    kinds: dict[str, set[LedgerEntryKind]] = {}
    for entry in entries:
        kinds.setdefault(entry.period, set()).add(entry.kind)
    return {
        period: _status(per_cycle.get(period, Money.ZERO), present)
        for period, present in kinds.items()
    }


def _status(outstanding: Money, kinds: set[LedgerEntryKind]) -> FeeStatus:
    """Name a period's status from its balance and the kinds it holds.

    :param outstanding: What the period still owes, floored at zero
    :param kinds: The kinds of the period's entries; never empty
    :return: One of :data:`FEE_STATUS_VALUES`
    """
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


def month_state(
    entries: list[LedgerEntry],
    period: str,
    *,
    checking: bool,
    statuses: Mapping[str, FeeStatus] | None = None,
) -> MonthState | None:
    """Compute one month's state, with a waiting payment taking precedence.

    A payment waiting for the teacher is what the family and the
    teacher are both looking at, so it outranks the ledger's own
    status until the teacher decides it.

    :param entries: Every entry for ONE enrollment, in any order
    :param period: The period, as ``YYYY-MM``
    :param checking: Whether a claim for this period awaits the teacher
    :param statuses: Every period's status from
        :func:`statuses_from_entries`, when the caller asks for several
        months of one seat; ``entries`` is then not folded again
    :return: The state, or None when the month has neither entries nor a
        waiting payment
    """
    if checking:
        return "checking"
    if statuses is not None:
        return statuses.get(period)
    try:
        return status_from_entries(entries, period)
    except KeyError:
        return None
