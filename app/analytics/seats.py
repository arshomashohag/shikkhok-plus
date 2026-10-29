"""The owned-seat set and its ledger: this package's only two reads.

**No read here accepts a resource id** [security-design § 1]. Not a
batch id, not an enrollment id. D1 through D4 each validate an id a
caller supplies -- a batch, a session, an enrollment, an exam -- and
each therefore has a check that can be omitted. The lens's ``owner_id``
is the only scoping value these reads have, so there is nothing to
validate and nothing to forget.

That removes the IDOR class from this unit's reads entirely. What it
does not remove is the **aggregate** problem: a wrong scope on a row
query returns a row somebody can point at, while a wrong scope on a sum
returns a number that looks right [security-design § 2]. Which is why
the probes assert each figure's VALUE against seeded data.

**The predicate departs from D4's roster predicate in two of its four
clauses, deliberately** [entities.md § 4]:

======================= ========================= =======================
Clause                  D4's roster [BR1.5]       D5's dues [BR1.2]
======================= ========================= =======================
batch ownership         the lens's ``owner_id``   the lens's ``owner_id``
``student_decision``    excludes ``declined``     excludes ``declined``
``inactive_from``       **excludes**              **no predicate at all**
``joined_on``           **excludes**              **no predicate at all**
======================= ========================= =======================

Two of four carry over, not three of three. Stated precisely because an
approximate comparison is how the wrong predicate gets reused by someone
checking a table rather than the code.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.db.models import Batch, Enrollment, FeeCycle, LedgerEntryRow, ReminderEvent
from app.money import LedgerEntry, LedgerEntryKind

__all__ = [
    "OwnedSeat",
    "due_dates_for_seats",
    "last_reminders_for_seats",
    "ledger_for_seats",
    "owned_seats",
]


@dataclass(frozen=True, slots=True)
class OwnedSeat:
    """One seat in one of this teacher's batches.

    Carries the teacher-facing key and the teacher-recorded name, never
    a global account id and never an owner-private profile field
    [ADR-001, TC-13].

    :ivar enrollment_id: The seat, which is the teacher-facing key
    :ivar batch_id: The batch it sits in
    :ivar batch_name: That batch's name, because the same person may
        owe in two
    :ivar display_name: What the TEACHER recorded
    :ivar reachable: Whether a student or guardian has ACCEPTED the
        seat, so an in-app reminder has somewhere to go. A yes or no,
        never which account [ADR-001]
    """

    enrollment_id: uuid.UUID
    batch_id: uuid.UUID
    batch_name: str
    display_name: str
    reachable: bool = False


def owned_seats(session: Session, lens: TeacherLens) -> list[OwnedSeat]:
    """Every seat across every batch this teacher owns.

    **ONE statement, joined rather than looped**, so there is no
    per-batch query and no batch id from the request to validate
    [NFR20.31]. D5 is the first unit reading across every batch a
    teacher owns, which makes the join the thing that keeps the
    statement count flat in the number of batches as well as seats.

    The ``declined`` exclusion is the one clause this shares with D4's
    roster predicate beyond ownership [BR1.7]: a seat someone declined
    because it was never theirs must not keep appearing on a list of
    people to chase for money.

    **There is deliberately no predicate on ``inactive_from`` or
    ``joined_on``** [BR1.2]. A student who left owing money is exactly
    who the dues view exists for, and a seat that joined recently can
    still owe -- a dues view has no session date to compare a joining
    date against.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :return: One entry per seat, ordered so repeated reads agree
    """
    rows = session.execute(
        sa.select(
            Enrollment.id,
            Enrollment.batch_id,
            Batch.name,
            Enrollment.display_name,
            sa.or_(
                sa.and_(
                    Enrollment.student_account_id.is_not(None),
                    Enrollment.student_decision == "accepted",
                ),
                sa.and_(
                    Enrollment.guardian_account_id.is_not(None),
                    Enrollment.guardian_decision == "accepted",
                ),
            ),
        )
        .join(Batch, Batch.id == Enrollment.batch_id)
        .where(
            Batch.owner_id == lens.owner_id,
            Enrollment.student_decision != "declined",
        )
        .order_by(Batch.name, Enrollment.created_at, Enrollment.id)
    ).all()

    return [
        OwnedSeat(
            enrollment_id=row[0],
            batch_id=row[1],
            batch_name=row[2],
            display_name=row[3],
            reachable=bool(row[4]),
        )
        for row in rows
    ]


def ledger_for_seats(
    session: Session, seat_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[LedgerEntry]]:
    """Read every entry for these seats in ONE statement.

    The shape D3 arrived at after its N+1 defect
    [``app/fees/views.py:330-345``]: one ``IN (:seat_ids)`` select, then
    a fold in memory, never a query per seat. D5 widens the seat set
    from one batch to all of them, which makes the property **more**
    load-bearing rather than less -- at the scale ceiling a per-seat
    query is up to a hundred statements for one screen.

    Every seat is present in the returned map, including seats with no
    entries at all, so a caller never distinguishes "no ledger" from "no
    such seat" by a missing key.

    :param session: The session to read through
    :param seat_ids: The seats whose entries to load
    :return: Entries per seat, as the value shapes the fold takes
    """
    ledger: dict[uuid.UUID, list[LedgerEntry]] = {key: [] for key in seat_ids}
    if not seat_ids:
        return ledger

    for row in session.execute(
        sa.select(
            LedgerEntryRow.enrollment_id,
            LedgerEntryRow.kind,
            LedgerEntryRow.period,
            LedgerEntryRow.amount,
        )
        .where(LedgerEntryRow.enrollment_id.in_(seat_ids))
        .order_by(LedgerEntryRow.period, LedgerEntryRow.created_at)
    ).all():
        ledger[row[0]].append(
            LedgerEntry(kind=LedgerEntryKind(row[1]), period=row[2], amount=row[3])
        )
    return ledger


def due_dates_for_seats(
    session: Session, seat_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, dt.date]]:
    """Read every cycle's due date for these seats in ONE statement.

    :param session: The session to read through
    :param seat_ids: The seats
    :return: Due date per period, per seat; every seat is present
    """
    due: dict[uuid.UUID, dict[str, dt.date]] = {key: {} for key in seat_ids}
    if not seat_ids:
        return due
    for enrollment_id, period, due_date in session.execute(
        sa.select(FeeCycle.enrollment_id, FeeCycle.period, FeeCycle.due_date).where(
            FeeCycle.enrollment_id.in_(seat_ids)
        )
    ):
        due[enrollment_id][period] = due_date
    return due


def last_reminders_for_seats(
    session: Session, seat_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dt.datetime]:
    """Read when each seat was last reminded, in ONE statement.

    Only reminders that went out count: a failed push reminded nobody.

    :param session: The session to read through
    :param seat_ids: The seats
    :return: The latest sent reminder per seat; absent where none was
    """
    if not seat_ids:
        return {}
    return {
        enrollment_id: sent_at
        for enrollment_id, sent_at in session.execute(
            sa.select(ReminderEvent.enrollment_id, sa.func.max(ReminderEvent.sent_at))
            .where(
                ReminderEvent.enrollment_id.in_(seat_ids),
                ReminderEvent.outcome == "sent",
            )
            .group_by(ReminderEvent.enrollment_id)
        )
    }
