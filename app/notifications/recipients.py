"""Who an inbox message goes to.

**Only an ACCEPTED link receives.** A seat a teacher created but nobody
has accepted reaches no one, and a guardian who declined is not told a
child's fees or exams [BR5.2]. One rule decides it here, so every
producer -- notices, payments, exams, marks -- agrees on it.

A guardian of two children is two recipients, one per seat, each
carrying that child's name, so the inbox can say whose item it is.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import Batch, Enrollment, Owner

__all__ = [
    "Recipient",
    "accepted_accounts",
    "family_recipients",
    "seat_recipients",
    "teacher_recipient",
]


@dataclass(frozen=True, slots=True)
class Recipient:
    """One account receiving a message about one seat.

    :ivar account_id: Who receives it
    :ivar enrollment_id: The seat it is about
    :ivar child_name: The child's name for a guardian; None for a student
    """

    account_id: uuid.UUID
    enrollment_id: uuid.UUID
    child_name: str | None


def accepted_accounts(seat: Enrollment) -> list[uuid.UUID]:
    """List the accounts on a seat that have accepted it.

    :param seat: The seat
    :return: The student and guardian accounts that accepted, if any
    """
    links = (
        (seat.student_account_id, seat.student_decision),
        (seat.guardian_account_id, seat.guardian_decision),
    )
    return [
        account
        for account, decision in links
        if account is not None and decision == "accepted"
    ]


def _recipients(seat: Enrollment) -> list[Recipient]:
    """Turn a seat's accepted links into recipients.

    :param seat: The seat
    :return: The student (unnamed) and guardian (named for the child)
    """
    found: list[Recipient] = []
    if seat.student_account_id is not None and seat.student_decision == "accepted":
        found.append(Recipient(seat.student_account_id, seat.id, None))
    if seat.guardian_account_id is not None and seat.guardian_decision == "accepted":
        found.append(Recipient(seat.guardian_account_id, seat.id, seat.display_name))
    return found


def family_recipients(
    session: Session, *, batch_id: uuid.UUID, on: dt.date
) -> list[Recipient]:
    """List who in a batch's families receives a message on a day.

    :param session: The session to read through
    :param batch_id: The batch
    :param on: The day; a seat that left before it is excluded
    :return: Accepted students and guardians of every seat still active
    """
    seats = session.scalars(
        sa.select(Enrollment)
        .where(
            Enrollment.batch_id == batch_id,
            sa.or_(Enrollment.inactive_from.is_(None), Enrollment.inactive_from >= on),
        )
        .order_by(Enrollment.id)
    ).all()
    return [recipient for seat in seats for recipient in _recipients(seat)]


def seat_recipients(session: Session, *, enrollment_id: uuid.UUID) -> list[Recipient]:
    """List who receives a message about one seat.

    Ignores ``inactive_from``: a payment still reaches a seat that has
    left.

    :param session: The session to read through
    :param enrollment_id: The seat
    :return: Its accepted student and guardian, if any
    """
    seat = session.get(Enrollment, enrollment_id)
    return [] if seat is None else _recipients(seat)


def teacher_recipient(session: Session, *, batch_id: uuid.UUID) -> uuid.UUID | None:
    """Find the account that owns a batch.

    :param session: The session to read through
    :param batch_id: The batch
    :return: The owner's account, or None if there is none
    """
    return session.scalar(
        sa.select(Owner.account_id)
        .join(Batch, Batch.owner_id == Owner.id)
        .where(Batch.id == batch_id)
    )
