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
from app.local_time import bangladesh_today
from app.notifications.inbox import deliver

__all__ = [
    "Recipient",
    "child_names",
    "deliver_to_families",
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


def child_names(recipients: list[Recipient]) -> dict[uuid.UUID, str]:
    """Map each guardian recipient to the child the message is about.

    :param recipients: Who receives the message
    :return: The child's name keyed by guardian account; students omitted
    """
    return {r.account_id: r.child_name for r in recipients if r.child_name is not None}


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
            sa.or_(Enrollment.inactive_from.is_(None), Enrollment.inactive_from > on),
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


def deliver_to_families(
    session: Session,
    *,
    batch: Batch,
    kind: str,
    source_id: uuid.UUID,
    preview: str,
    now: dt.datetime,
) -> None:
    """Put one message in every accepted family member's inbox.

    One call per seat, so a guardian of two children gets two rows,
    each naming its child. Membership is as of today in Bangladesh.
    Adds to the caller's transaction and does not commit.

    :param session: The caller's session
    :param batch: The batch the message is for
    :param kind: What produced it
    :param source_id: The record it came from, already flushed
    :param preview: A short line of its content
    :param now: When it is sent
    :return: None
    """
    by_seat: dict[uuid.UUID, list[uuid.UUID]] = {}
    names: dict[uuid.UUID, dict[uuid.UUID, str]] = {}
    for recipient in family_recipients(
        session, batch_id=batch.id, on=bangladesh_today()
    ):
        by_seat.setdefault(recipient.enrollment_id, []).append(recipient.account_id)
        if recipient.child_name is not None:
            names.setdefault(recipient.enrollment_id, {})[recipient.account_id] = (
                recipient.child_name
            )
    for enrollment_id, accounts in by_seat.items():
        deliver(
            session,
            account_ids=accounts,
            kind=kind,
            batch_name=batch.name,
            now=now,
            enrollment_id=enrollment_id,
            source_id=source_id,
            preview=preview,
            child_names=names.get(enrollment_id),
        )

