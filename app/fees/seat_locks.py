"""One lock per seat, taken before any ledger write derives a balance.

**Every ledger writer derives, then appends** [audit C-03]. Approving a
payment reads what each child owes, applying credit reads what is
available, a correction reads what it is reversing, and the daily job
reads what credit a new charge can absorb. Under READ COMMITTED two such
writers on one seat each derive from the same snapshot and each append
against it: a month receipted twice, its surplus lost to the per-cycle
zero floor rather than becoming credit, or one credit spent twice.

``app.fees.received`` already locked the seat and said why. This module
is that lock made shared, so every writer takes the same one:

* **One row, the enrollment's.** The ledger has no per-seat row of its
  own to lock, and the enrollment row is the natural owner of every
  ledger entry hanging off it.
* **Sorted, always.** A writer touching several seats -- one family
  payment split across siblings -- locks them in id order, so two such
  writers never wait on each other in opposite orders.
* **Re-entrant within a transaction.** PostgreSQL grants a row lock the
  transaction already holds immediately, so an outer operation can lock
  all its seats up front and the per-claim helpers it calls can lock
  their one seat again at no cost. That is what lets the helpers lock
  defensively without each caller having to remember to.

The lock lives until the transaction ends; every caller commits or rolls
back at the end of its operation.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import Enrollment

__all__ = ["lock_seats"]


def lock_seats(session: Session, enrollment_ids: Iterable[uuid.UUID | None]) -> None:
    """Lock each named seat, in id order, until the transaction ends.

    ``None`` entries are skipped, so a caller can pass an optional seat
    without a branch. An empty set takes no lock and issues no query.

    :param session: The session whose transaction holds the locks
    :param enrollment_ids: The seats about to have balances derived
    :return: None
    """
    wanted = sorted({seat for seat in enrollment_ids if seat is not None})
    if not wanted:
        return
    session.execute(
        sa.select(Enrollment.id)
        .where(Enrollment.id.in_(wanted))
        .order_by(Enrollment.id)
        .with_for_update()
    ).all()
