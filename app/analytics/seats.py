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
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.db.models import Batch, Enrollment, FeeCycle, LedgerEntryRow, ReminderEvent
from app.money import LedgerEntry, LedgerEntryKind

__all__ = [
    "CREDIT_KINDS",
    "CYCLE_SIGN",
    "OwnedSeat",
    "any_of",
    "due_dates_for_seats",
    "last_reminders_for_seats",
    "ledger_by_period",
    "ledger_for_seats",
    "owing_ledger_for_seats",
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
    """Read these seats' ledgers, summed per (seat, period, kind), in ONE statement.

    The shape D3 arrived at after its N+1 defect
    [``app/fees/views.py:330-345``]: one statement over every seat, then
    a fold in memory, never a query per seat. D5 widens the seat set
    from one batch to all of them, which makes the property **more**
    load-bearing rather than less.

    **The database sums; the fold still decides** [C-14]. Each returned
    entry carries ``SUM(amount)`` over one seat's rows of one kind in
    one period, so the Python side builds one value per group rather
    than one per row. That is an exact reduction because
    :func:`app.money.derive` is linear per (period, kind): every figure
    it produces is a sum over entries selected by kind and period, and
    its one non-linear step, the per-period floor, runs on sums already
    grouped by period. ``tests/money/test_ledger_presum_property.py``
    proves the equivalence over arbitrary histories, and
    ``tests/analytics/test_seats.py`` proves this read against the
    row-by-row one. Callers must therefore only fold or sum what this
    returns -- never count its entries.

    **Every row is summed, superseded ones included** [BR3.3], exactly
    as :func:`app.fees.balances.entries_for_enrollment` reads them: a
    correction's pair sums to zero only when both halves are counted.

    The seat ids travel as one array parameter (``= ANY(:ids)``) rather
    than an ``IN`` list, so the statement's bind-parameter count does
    not grow with the number of seats.

    Every seat is present in the returned map, including seats with no
    entries at all, so a caller never distinguishes "no ledger" from "no
    such seat" by a missing key.

    :param session: The session to read through
    :param seat_ids: The seats whose entries to load
    :return: Summed entries per seat, as the value shapes the fold takes
    """
    ledger: dict[uuid.UUID, list[LedgerEntry]] = {key: [] for key in seat_ids}
    if not seat_ids:
        return ledger

    for enrollment_id, kind, period, amount in session.execute(
        sa.select(
            LedgerEntryRow.enrollment_id,
            LedgerEntryRow.kind,
            LedgerEntryRow.period,
            sa.func.sum(LedgerEntryRow.amount),
        )
        .where(LedgerEntryRow.enrollment_id == any_of(seat_ids))
        .group_by(
            LedgerEntryRow.enrollment_id, LedgerEntryRow.period, LedgerEntryRow.kind
        )
    ).all():
        ledger[enrollment_id].append(
            LedgerEntry(kind=LedgerEntryKind(kind), period=period, amount=amount)
        )
    return ledger


#: How each kind moves ONE cycle's balance in :func:`app.money.derive`:
#: ``1`` adds to what the period owes, ``-1`` relieves it, ``0`` leaves
#: it alone. **Hand-written, as** ``CASH_IN_KINDS`` **is**: the fold
#: matches on kinds exhaustively and exports no table, and
#: ``tests/analytics/test_owing_ledger.py`` probes the fold for every
#: kind and fails if this disagrees, or if a kind is added without a row.
CYCLE_SIGN: Final[Mapping[LedgerEntryKind, int]] = {
    LedgerEntryKind.CHARGE: 1,
    LedgerEntryKind.CARRY_FORWARD: 1,
    LedgerEntryKind.RECEIPT: -1,
    LedgerEntryKind.FORGIVENESS: -1,
    LedgerEntryKind.CREDIT_APPLY: -1,
    LedgerEntryKind.CARRIED_OUT: -1,
    LedgerEntryKind.CREDIT_GRANT: 0,
}

#: The kinds :attr:`~app.money.DerivedQuantities.available_credit` is
#: folded from. Probed against the fold by the same test.
CREDIT_KINDS: Final[frozenset[LedgerEntryKind]] = frozenset(
    {LedgerEntryKind.CREDIT_GRANT, LedgerEntryKind.CREDIT_APPLY}
)


def owing_ledger_for_seats(
    session: Session, seat_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[LedgerEntry]]:
    """Read only the part of these seats' ledgers that can still owe or credit.

    **For callers that read what is OWED, never what was charged or
    paid** [C-14]: the dues list, Today's money, the student list, the
    monthly summary's owed figure and the payment review. Folding what
    this returns through :func:`app.money.derive` gives exactly what
    folding the whole ledger gives for

    * ``total_outstanding``,
    * every ``per_cycle`` period that is **positive**, with its value,
    * ``available_credit``,

    and NOTHING else is promised: the ``total_*`` sums and the
    ``per_cycle`` keys of settled periods differ. A caller that needs
    those reads :func:`ledger_for_seats`.

    **What is left out, and why it cannot matter.** A (seat, period)
    group is omitted when its net -- the period's rows weighted by
    :data:`CYCLE_SIGN` -- is zero or less, so the fold floors it to
    zero and it adds nothing to the total and is not a positive period;
    and when it holds no :data:`CREDIT_KINDS` row, so no held credit is
    folded from it. That is every settled month of a seat's history,
    which at a centre's scale is nearly all of it: the fold builds a
    value per month still owing rather than per month ever billed.

    The kept groups are summed per (seat, period, kind), as
    :func:`ledger_for_seats` sums them. The floor and the totals are
    still the fold's: SQL only decides which months to send it, and
    ``tests/analytics/test_owing_ledger.py`` proves the three
    quantities over random histories against the whole ledger.

    :param session: The session to read through
    :param seat_ids: The seats
    :return: Their owing and credit entries; every seat is present
    """
    ledger: dict[uuid.UUID, list[LedgerEntry]] = {key: [] for key in seat_ids}
    if not seat_ids:
        return ledger

    # One aggregate pass per (seat, period): a sum per kind, and the two
    # tests that decide whether the fold needs the period at all. The
    # weighted sum is compared, never returned, so it is typed as a plain
    # numeric rather than asking the money column type to bind a bare 0.
    plain = sa.type_coerce(LedgerEntryRow.amount, sa.Numeric(asdecimal=True))
    signed = sa.case(
        *[
            (LedgerEntryRow.kind == kind.value, plain * sign)
            for kind, sign in CYCLE_SIGN.items()
            if sign
        ],
        else_=0,
    )
    kinds = list(LedgerEntryKind)
    rows = session.execute(
        sa.select(
            LedgerEntryRow.enrollment_id,
            LedgerEntryRow.period,
            *[
                sa.func.sum(LedgerEntryRow.amount).filter(
                    LedgerEntryRow.kind == kind.value
                )
                for kind in kinds
            ],
        )
        .where(LedgerEntryRow.enrollment_id == any_of(seat_ids))
        .group_by(LedgerEntryRow.enrollment_id, LedgerEntryRow.period)
        .having(
            sa.or_(
                sa.func.sum(signed) > 0,
                sa.func.bool_or(
                    LedgerEntryRow.kind.in_([kind.value for kind in CREDIT_KINDS])
                ),
            )
        )
    ).all()
    for enrollment_id, period, *sums in rows:
        # A kind with no row in the period sums to NULL and contributes no
        # entry; a kind whose rows sum to zero still does, as its rows did.
        ledger[enrollment_id].extend(
            LedgerEntry(kind=kind, period=period, amount=amount)
            for kind, amount in zip(kinds, sums, strict=True)
            if amount is not None
        )
    return ledger


def ledger_by_period(session: Session, seat_ids: list[uuid.UUID]) -> list[LedgerEntry]:
    """Read these seats' ledgers summed per (period, kind) across every seat.

    For figures that are sums per period over the whole owner, such as
    the overview's money received per month: one value per period and
    kind instead of one per row. Exact for any fold that is linear per
    (period, kind) across seats, which :func:`~app.analytics.earnings.period_totals`
    is; never fold it as one seat's ledger, since the per-period floor
    is per seat.

    :param session: The session to read through
    :param seat_ids: The seats
    :return: One entry per (period, kind) present
    """
    if not seat_ids:
        return []
    return [
        LedgerEntry(kind=LedgerEntryKind(kind), period=period, amount=amount)
        for kind, period, amount in session.execute(
            sa.select(
                LedgerEntryRow.kind,
                LedgerEntryRow.period,
                sa.func.sum(LedgerEntryRow.amount),
            )
            .where(LedgerEntryRow.enrollment_id == any_of(seat_ids))
            .group_by(LedgerEntryRow.period, LedgerEntryRow.kind)
        ).all()
    ]


def any_of(ids: Collection[uuid.UUID]) -> sa.ColumnElement[Any]:
    """Bind a set of ids as ONE array parameter, for ``column = ANY(:ids)``.

    An ``IN (:a, :b, ...)`` list binds one parameter per id, and
    PostgreSQL's wire protocol refuses a statement with more than 65,535
    of them -- a ceiling an owner-wide read reaches as history grows
    [C-13]. One ``uuid[]`` parameter has no such ceiling.

    :param ids: The ids
    :return: ``ANY(:ids)``, to compare a uuid column against
    """
    return sa.any_(sa.bindparam(None, list(ids), type_=ARRAY(PgUUID(as_uuid=True))))


def due_dates_for_seats(
    session: Session,
    seat_ids: list[uuid.UUID],
    *,
    periods: Mapping[uuid.UUID, Iterable[LedgerEntry]] | None = None,
) -> dict[uuid.UUID, dict[str, dt.date]]:
    """Read cycles' due dates for these seats in ONE statement.

    :param session: The session to read through
    :param seat_ids: The seats
    :param periods: Only the periods these entries name, per seat -- an
        :func:`owing_ledger_for_seats` result, so a dues read fetches the
        due dates of months still owing rather than of every month ever
        billed; None for every cycle
    :return: Due date per period, per seat; every seat is present
    """
    due: dict[uuid.UUID, dict[str, dt.date]] = {key: {} for key in seat_ids}
    if not seat_ids:
        return due
    statement = sa.select(FeeCycle.enrollment_id, FeeCycle.period, FeeCycle.due_date)
    if periods is None:
        statement = statement.where(FeeCycle.enrollment_id == any_of(seat_ids))
    else:
        pairs = sorted(
            {
                (seat, entry.period)
                for seat, entries in periods.items()
                for entry in entries
            }
        )
        if not pairs:
            return due
        wanted = (
            sa.func.unnest(
                sa.bindparam(
                    None, [p[0] for p in pairs], type_=ARRAY(PgUUID(as_uuid=True))
                ),
                sa.bindparam(None, [p[1] for p in pairs], type_=ARRAY(sa.Text())),
            )
            .table_valued("enrollment_id", "period")
            .render_derived()
        )
        statement = statement.join(
            wanted,
            sa.and_(
                FeeCycle.enrollment_id == wanted.c.enrollment_id,
                FeeCycle.period == wanted.c.period,
            ),
        ).where(FeeCycle.enrollment_id == any_of({seat for seat, _ in pairs}))
    for enrollment_id, period, due_date in session.execute(statement):
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
                ReminderEvent.enrollment_id == any_of(seat_ids),
                ReminderEvent.outcome == "sent",
            )
            .group_by(ReminderEvent.enrollment_id)
        )
    }
