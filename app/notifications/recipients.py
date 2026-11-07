"""Who an inbox message goes to.

**Only an ACCEPTED link receives.** A seat a teacher created but nobody
has accepted reaches no one, and a guardian who declined is not told a
child's fees or exams [BR5.2]. One rule decides it here, so every
producer -- notices, payments, exams, marks -- agrees on it.

A guardian of two children is two recipients, one per seat, each
carrying that child's name, so the inbox can say whose item it is.

**The rule is one SQL query, :func:`_recipient_rows`**, and every path
uses it: reading recipients for a single seat, re-flagging an edit, and
the batch fan-out, which turns it into one ``INSERT ... SELECT`` so a
notice to a thousand seats is a single statement rather than two
thousand ORM objects and their parameters shipped back to the database.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Session

from app.db.models import Batch, Enrollment, Notification, Owner, OwnerMember
from app.local_time import bangladesh_today
from app.notifications.inbox import mark_unread_for_source

__all__ = [
    "Recipient",
    "child_names",
    "deliver_to_families",
    "family_recipients",
    "mark_unread_for_families",
    "seat_recipients",
    "teacher_recipients",
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


def _recipient_rows(
    *seat_filter: sa.ColumnElement[bool],
) -> sa.Select[tuple[uuid.UUID, uuid.UUID, str | None]]:
    """Select the accepted links of the seats a filter picks, one row each.

    The student comes back unnamed and the guardian named for the child.
    A seat with both yields two rows; a seat with neither accepted yields
    none.

    :param seat_filter: Conditions on :class:`Enrollment` picking the seats
    :return: ``(account_id, enrollment_id, child_name)`` rows
    """
    student = sa.select(
        Enrollment.student_account_id.label("account_id"),
        Enrollment.id.label("enrollment_id"),
        sa.null().cast(sa.Text).label("child_name"),
    ).where(
        *seat_filter,
        Enrollment.student_account_id.is_not(None),
        Enrollment.student_decision == "accepted",
    )
    guardian = sa.select(
        Enrollment.guardian_account_id.label("account_id"),
        Enrollment.id.label("enrollment_id"),
        Enrollment.display_name.label("child_name"),
    ).where(
        *seat_filter,
        Enrollment.guardian_account_id.is_not(None),
        Enrollment.guardian_decision == "accepted",
    )
    union = sa.union_all(student, guardian).subquery()
    return sa.select(union.c.account_id, union.c.enrollment_id, union.c.child_name)


def _active_in_batch(batch_id: uuid.UUID, on: dt.date) -> list[sa.ColumnElement[bool]]:
    """Pick a batch's seats that have not left by a day.

    :param batch_id: The batch
    :param on: The day; a seat that left on or before it is excluded
    :return: The conditions
    """
    return [
        Enrollment.batch_id == batch_id,
        sa.or_(Enrollment.inactive_from.is_(None), Enrollment.inactive_from > on),
    ]


def _read(
    session: Session, rows: sa.Select[tuple[uuid.UUID, uuid.UUID, str | None]]
) -> list[Recipient]:
    """Run a recipient query, seat by seat with the student first.

    :param session: The session to read through
    :param rows: A query from :func:`_recipient_rows`
    :return: The recipients
    """
    found = rows.subquery()
    ordered = sa.select(found).order_by(
        found.c.enrollment_id, found.c.child_name.is_not(None)
    )
    return [
        Recipient(account_id, enrollment_id, child_name)
        for account_id, enrollment_id, child_name in session.execute(ordered)
    ]


def family_recipients(
    session: Session, *, batch_id: uuid.UUID, on: dt.date
) -> list[Recipient]:
    """List who in a batch's families receives a message on a day.

    :param session: The session to read through
    :param batch_id: The batch
    :param on: The day; a seat that left before it is excluded
    :return: Accepted students and guardians of every seat still active
    """
    return _read(session, _recipient_rows(*_active_in_batch(batch_id, on)))


def seat_recipients(session: Session, *, enrollment_id: uuid.UUID) -> list[Recipient]:
    """List who receives a message about one seat.

    Ignores ``inactive_from``: a payment still reaches a seat that has
    left.

    :param session: The session to read through
    :param enrollment_id: The seat
    :return: Its accepted student and guardian, if any
    """
    return _read(session, _recipient_rows(Enrollment.id == enrollment_id))


def teacher_recipients(session: Session, *, batch_id: uuid.UUID) -> list[uuid.UUID]:
    """Find who acts for the owner of a batch.

    A solo tutor's own account; for a coaching centre [0022], every
    manager whose membership is accepted and unrevoked, oldest first. The
    same predicates the lens query grants by, so a notification never
    reaches someone who could not open it.

    :param session: The session to read through
    :param batch_id: The batch
    :return: The accounts, possibly none
    """
    solo = (
        sa.select(Owner.account_id.label("account_id"), Owner.created_at)
        .join(Batch, Batch.owner_id == Owner.id)
        .where(Batch.id == batch_id, Owner.account_id.is_not(None))
    )
    managers = (
        sa.select(OwnerMember.account_id.label("account_id"), OwnerMember.created_at)
        .join(Batch, Batch.owner_id == OwnerMember.owner_id)
        .where(
            Batch.id == batch_id,
            OwnerMember.account_id.is_not(None),
            OwnerMember.role == "manager",
            OwnerMember.decision == "accepted",
            OwnerMember.revoked_at.is_(None),
        )
    )
    union = sa.union_all(solo, managers).subquery()
    found = session.scalars(
        sa.select(union.c.account_id).order_by(union.c.created_at)
    ).all()
    return [account for account in dict.fromkeys(found) if account is not None]


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

    One row per ``(account, seat)``, so a guardian of two children gets
    two rows, each naming its child. Membership is as of today in
    Bangladesh.

    **One statement whatever the batch size**: an ``INSERT ... SELECT``
    over :func:`_recipient_rows`, so the rows are built inside the
    database. Adds to the caller's transaction and does not commit.

    :param session: The caller's session
    :param batch: The batch the message is for
    :param kind: What produced it
    :param source_id: The record it came from, already flushed
    :param preview: A short line of its content
    :param now: When it is sent
    :return: None
    """
    found = _recipient_rows(*_active_in_batch(batch.id, bangladesh_today())).subquery()
    session.execute(
        sa.insert(Notification).from_select(
            [
                "id",
                "account_id",
                "enrollment_id",
                "kind",
                "batch_name",
                "created_at",
                "source_id",
                "preview",
                "child_name",
            ],
            sa.select(
                sa.func.gen_random_uuid(),
                found.c.account_id,
                found.c.enrollment_id,
                sa.literal(kind, sa.String),
                sa.literal(batch.name, sa.Text),
                sa.literal(now, sa.DateTime(timezone=True)),
                sa.literal(source_id, PgUUID(as_uuid=True)),
                sa.literal(preview, sa.Text),
                found.c.child_name,
            ),
        )
    )


def mark_unread_for_families(
    session: Session,
    *,
    batch_id: uuid.UUID,
    kind: str,
    source_id: uuid.UUID,
    preview: str,
) -> None:
    """Re-flag an edited batch record for the families it reaches today.

    Membership is as of today in Bangladesh, the same rule
    :func:`deliver_to_families` sends by, so an edit reaches exactly the
    people a new record would. Adds to the caller's transaction and does
    not commit.

    :param session: The caller's session
    :param batch_id: The batch the record belongs to
    :param kind: What produced the messages
    :param source_id: The edited record
    :param preview: Its new preview line
    :return: None
    """
    reaches = [
        (recipient.account_id, recipient.enrollment_id)
        for recipient in family_recipients(
            session, batch_id=batch_id, on=bangladesh_today()
        )
    ]
    mark_unread_for_source(
        session, kind=kind, source_id=source_id, reaches=reaches, preview=preview
    )
