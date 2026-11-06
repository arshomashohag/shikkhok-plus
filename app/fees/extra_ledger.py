"""The extra-fee ledger: append, fold, compensate [0020].

**A second ledger, deliberately apart from ``ledger_entry``.** Every
reader of the monthly ledger treats a period as a calendar month, so an
exam fee written there would be settled by monthly payments, counted in
lateness and listed among months owed. Kept in ``extra_fee_entry``, none
of them can reach it, and nothing here needs a filter to stay correct.

**The arithmetic is the money module's.** Each charge's rows are folded
by :func:`app.money.derive` with the charge id as the opaque period key,
so the per-key floor and the relief rules are the ones the monthly
ledger uses, not a second implementation of them. Three kinds only --
``charge``, ``receipt``, ``forgiveness`` -- and the table refuses any
other, so no carry and no credit can appear in a fold.

**Append-only, like the monthly ledger** [BR3.3]. A correction appends
the compensating kind and points the original at it; the fold reads
both and the pair sums to zero.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.orm import Session, aliased

from app.db.models import EXTRA_FEE_ENTRY_KIND_VALUES, ExtraFeeEntry, PaymentClaim
from app.money import (
    DerivedQuantities,
    LedgerEntry,
    LedgerEntryKind,
    Money,
    derive,
    relief_of,
)

__all__ = [
    "append_extra_entry",
    "charge_entries",
    "derive_for_charge",
    "extra_decision_relief",
    "live_charge_entries",
    "owed_on_charge",
    "reverse_extra_entries",
]

#: The kind that cancels each relieving kind: both are put back owed.
_OPPOSITE: dict[str, str] = {"receipt": "charge", "forgiveness": "charge"}


def _value(row: ExtraFeeEntry) -> LedgerEntry:
    """Turn a row into the value shape the fold takes.

    :param row: The stored entry
    :return: The value, keyed by its charge
    """
    return LedgerEntry(
        kind=LedgerEntryKind(row.kind),
        period=str(row.extra_fee_charge_id),
        amount=row.amount,
    )


def charge_entries(
    session: Session, charge_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[LedgerEntry]]:
    """Load every entry of several charges in one statement.

    Every row, superseded ones included, for the monthly ledger's
    reason: a compensation counted without its original would move the
    balance by the size of the correction.

    :param session: The session to read through
    :param charge_ids: The charges
    :return: Charge id to its entries, as values; absent charges map to []
    """
    wanted = list(charge_ids)
    found: dict[uuid.UUID, list[LedgerEntry]] = {charge: [] for charge in wanted}
    if not wanted:
        return found
    rows = session.scalars(
        sa.select(ExtraFeeEntry)
        .where(ExtraFeeEntry.extra_fee_charge_id.in_(wanted))
        .order_by(ExtraFeeEntry.created_at, ExtraFeeEntry.id)
    )
    for row in rows:
        found[row.extra_fee_charge_id].append(_value(row))
    return found


def live_charge_entries(
    session: Session, charge_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[LedgerEntry]]:
    """Load the entries still in force: what a person should be SHOWN.

    A corrected entry and the entry compensating it are left out
    together. The pair sums to zero, so the balance this folds to is the
    balance :func:`charge_entries` folds to -- but "paid" and the status
    read what is really paid, rather than a reversed payment's receipt
    beside the charge that cancelled it.

    :param session: The session to read through
    :param charge_ids: The charges
    :return: Charge id to its live entries; absent charges map to []
    """
    wanted = list(charge_ids)
    found: dict[uuid.UUID, list[LedgerEntry]] = {charge: [] for charge in wanted}
    if not wanted:
        return found
    compensating = aliased(ExtraFeeEntry)
    rows = session.scalars(
        sa.select(ExtraFeeEntry)
        .where(
            ExtraFeeEntry.extra_fee_charge_id.in_(wanted),
            ExtraFeeEntry.superseded_by_id.is_(None),
            ~sa.exists().where(compensating.superseded_by_id == ExtraFeeEntry.id),
        )
        .order_by(ExtraFeeEntry.created_at, ExtraFeeEntry.id)
    )
    for row in rows:
        found[row.extra_fee_charge_id].append(_value(row))
    return found


def derive_for_charge(session: Session, charge_id: uuid.UUID) -> DerivedQuantities:
    """Fold one charge's entries.

    :param session: The session to read through
    :param charge_id: The charge
    :return: Every derived quantity for it
    """
    return derive(charge_entries(session, [charge_id])[charge_id])


def owed_on_charge(session: Session, charge_id: uuid.UUID) -> Money:
    """Say what one student still owes on one extra fee, never negative.

    :param session: The session to read through
    :param charge_id: The charge
    :return: The outstanding
    """
    return derive_for_charge(session, charge_id).total_outstanding


def append_extra_entry(
    session: Session,
    *,
    charge_id: uuid.UUID,
    kind: str,
    amount: Money,
    payment_claim_id: uuid.UUID | None = None,
    created_by_account_id: uuid.UUID | None = None,
) -> ExtraFeeEntry:
    """Append one entry. Does **not** commit.

    :param session: The session to write through
    :param charge_id: The student's charge
    :param kind: ``charge``, ``receipt`` or ``forgiveness``
    :param amount: A non-negative amount
    :param payment_claim_id: The decision that wrote it, if any
    :param created_by_account_id: Who caused it
    :return: The flushed row
    :raises ValueError: The kind is not one an extra fee takes. The table
        refuses it too; failing here names the defect at its source.
    """
    if kind not in EXTRA_FEE_ENTRY_KIND_VALUES:
        raise ValueError(f"an extra fee takes no {kind!r} entry")
    row = ExtraFeeEntry(
        extra_fee_charge_id=charge_id,
        kind=kind,
        amount=amount,
        payment_claim_id=payment_claim_id,
        created_by_account_id=created_by_account_id,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(row)
    session.flush()
    return row


def _live_rows(session: Session, claim_ids: list[uuid.UUID]) -> list[ExtraFeeEntry]:
    """Load the entries a claim's CURRENT decision wrote.

    Not superseded, and not themselves a compensation: a second
    correction must not reverse the first correction's reversals.

    :param session: The session to read through
    :param claim_ids: The claims
    :return: Their live entries, oldest first
    """
    if not claim_ids:
        return []
    compensating = aliased(ExtraFeeEntry)
    return list(
        session.scalars(
            sa.select(ExtraFeeEntry)
            .where(
                ExtraFeeEntry.payment_claim_id.in_(claim_ids),
                ExtraFeeEntry.superseded_by_id.is_(None),
                ~sa.exists().where(compensating.superseded_by_id == ExtraFeeEntry.id),
            )
            .order_by(ExtraFeeEntry.created_at, ExtraFeeEntry.id)
        )
    )


def reverse_extra_entries(
    session: Session,
    claim: PaymentClaim,
    *,
    verified_by_account_id: uuid.UUID,
) -> None:
    """Compensate every entry a claim's prior decision wrote [BR3.3].

    A ``receipt`` or ``forgiveness`` relieved the charge, so each is
    cancelled by a ``charge`` of the same amount and points at it. Adds
    to the transaction and does not commit.

    :param session: The session to write through
    :param claim: The claim whose decision is being undone
    :param verified_by_account_id: Who is correcting
    :return: None
    """
    for entry in _live_rows(session, [claim.id]):
        mirror = _OPPOSITE.get(entry.kind)
        if mirror is None:
            continue
        compensation = append_extra_entry(
            session,
            charge_id=entry.extra_fee_charge_id,
            kind=mirror,
            amount=entry.amount,
            payment_claim_id=claim.id,
            created_by_account_id=verified_by_account_id,
        )
        entry.superseded_by_id = compensation.id
        session.flush()


def extra_decision_relief(
    session: Session, claim_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Money]:
    """Measure what each claim's current decision took off its charge.

    The extra-fee twin of the review's monthly measure: a decided
    payment is shown against what was owed before it.

    :param session: The session to read through
    :param claim_ids: The claims
    :return: Claim id to the relief its live entries give
    """
    live: defaultdict[uuid.UUID, list[LedgerEntry]] = defaultdict(list)
    for row in _live_rows(session, claim_ids):
        if row.payment_claim_id is not None and row.kind != "charge":
            live[row.payment_claim_id].append(_value(row))
    return {claim_id: relief_of(live[claim_id]) for claim_id in claim_ids}
