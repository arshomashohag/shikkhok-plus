"""What a teacher leaves behind when they delete their account.

The O5 board's teacher variant tells them before they confirm: how many
batches, how many students, and how much is still recorded as owed --
which stays on those records and which they will no longer be able to
collect. All three are counted here so the phone counts nothing.

**Read by the authenticated account's own id**, never a lens: the
question is about the caller themselves, and an account owning nothing
is answered with zeros rather than refused.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.analytics.seats import ledger_for_seats
from app.db.models import Batch, Enrollment, Owner
from app.money import Money, derive

__all__ = ["Footprint", "teacher_footprint"]


@dataclass(frozen=True, slots=True)
class Footprint:
    """The records that outlive a teacher's account.

    :ivar batch_count: Batches the account owns
    :ivar student_count: Seats in them that nobody declined
    :ivar outstanding: What those seats still owe, from the ledger fold
    """

    batch_count: int
    student_count: int
    outstanding: Money


def teacher_footprint(session: Session, account_id: uuid.UUID) -> Footprint:
    """Count what stays when this account is deleted.

    Three statements whatever the teacher's size: the batches, the seats,
    and one ledger read folded in memory.

    :param session: The session to read through
    :param account_id: The authenticated account
    :return: Batches, students and money still owed
    """
    batch_ids = list(
        session.scalars(
            sa.select(Batch.id)
            .join(Owner, Owner.id == Batch.owner_id)
            .where(Owner.account_id == account_id)
        )
    )
    seat_ids = (
        list(
            session.scalars(
                sa.select(Enrollment.id).where(
                    Enrollment.batch_id.in_(batch_ids),
                    Enrollment.student_decision != "declined",
                )
            )
        )
        if batch_ids
        else []
    )
    ledger = ledger_for_seats(session, seat_ids)
    return Footprint(
        batch_count=len(batch_ids),
        student_count=len(seat_ids),
        outstanding=Money.sum(
            derive(entries).total_outstanding for entries in ledger.values()
        ),
    )
