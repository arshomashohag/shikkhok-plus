"""Reading a seat's ledger back, and handing it to the fold.

**The arithmetic is not here.** This module loads rows and converts them
into the value shapes ``app.money`` folds; every quantity it returns is
computed by ``app.money.derive``. The division is the one that module's
docstring states: it persists nothing, and this is the part that does.

A balance is **derived, never stored** [BR1.2]. ``fee_cycle`` carries no
money column, so there is nothing to read a total from and nothing to
drift.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import LedgerEntryRow
from app.money import DerivedQuantities, LedgerEntry, LedgerEntryKind, Money, derive

__all__ = ["derive_for_enrollment", "entries_for_enrollment", "oldest_unpaid_period"]


def entries_for_enrollment(
    session: Session, enrollment_id: uuid.UUID
) -> list[LedgerEntry]:
    """Load a seat's entries as the value shapes the fold takes.

    **Every row, including superseded ones** [BR3.3]. A correction
    appends a compensating entry and the pair sums to zero, so excluding
    the superseded row would count the compensation on its own and move
    the balance by the amount of the correction. ``superseded_by_id``
    drives what a teacher SEES, not what the balance IS.

    :param session: The session to read through
    :param enrollment_id: The seat whose ledger to load
    :return: The entries, as value shapes
    """
    rows = session.scalars(
        sa.select(LedgerEntryRow)
        .where(LedgerEntryRow.enrollment_id == enrollment_id)
        .order_by(LedgerEntryRow.period, LedgerEntryRow.created_at)
    )
    return [
        LedgerEntry(
            kind=LedgerEntryKind(row.kind),
            period=row.period,
            amount=row.amount,
        )
        for row in rows
    ]


def derive_for_enrollment(
    session: Session, enrollment_id: uuid.UUID
) -> DerivedQuantities:
    """Derive every balance quantity for one seat.

    One linear pass over one enrollment's rows, which is the hottest
    read in the fee system. The per-period floor and the credit cap are
    the fold's, not this module's.

    :param session: The session to read through
    :param enrollment_id: The seat
    :return: Every derived quantity, including the per-period breakdown
    """
    return derive(entries_for_enrollment(session, enrollment_id))


def oldest_unpaid_period(session: Session, enrollment_id: uuid.UUID) -> str | None:
    """Return the earliest period with an outstanding balance.

    **The resolution target for a payment claim** [BR5.1]. Period keys
    are fixed width precisely so this is a sort rather than a parse:
    lexical order is chronological order.

    :param session: The session to read through
    :param enrollment_id: The seat
    :return: The period key, or None where nothing is owed
    """
    per_cycle = derive_for_enrollment(session, enrollment_id).per_cycle
    owing = sorted(
        period for period, balance in per_cycle.items() if balance > Money.ZERO
    )
    return owing[0] if owing else None
