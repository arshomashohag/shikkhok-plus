"""Collections over months: what was charged, what came in, what is owed.

**The ledger is append-only, so a correction adds rows rather than
removing them**, and a naive sum over a month double-counts every
corrected decision. Two rules keep the figures honest:

* **Charged** is the ``charge`` rows a month was really billed. A
  ``charge`` that compensates a reversed receipt, forgiveness or credit
  grant is not a bill: it is recognised as the target of another row's
  ``superseded_by_id`` or by carrying the verification that wrote it,
  and it is left out, as is a ``charge`` that was itself superseded.
  ``carry_forward`` is never charged: it moves an obligation between
  months and the original charge is already counted.
* **Collected** is ``receipt`` plus ``credit_grant`` and never
  ``credit_apply``, taken from :func:`app.analytics.earnings.period_totals`
  after the rows a correction superseded have been dropped.

The bars are percentages of the largest charged month, computed with
``Money.percent_of`` so the client draws without doing money arithmetic.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session, aliased

from app.analytics.earnings import period_totals
from app.analytics.seats import (
    OwnedSeat,
    any_of,
    owing_ledger_for_seats,
    owned_seats,
)
from app.authz.lenses import TeacherLens
from app.db.models import Batch, LedgerEntryRow
from app.errors import AuthorizationError
from app.errors.codes import NOT_AVAILABLE
from app.local_time import bangladesh_today
from app.money import LedgerEntry, LedgerEntryKind, Money, derive

__all__ = [
    "DEFAULT_MONTHS",
    "MAX_MONTHS",
    "CollectionsReport",
    "LedgerFact",
    "MonthCollection",
    "carried_in_by_period",
    "charged_by_period",
    "clamp_months",
    "collected_by_period",
    "collections",
    "facts_for_seats",
    "months_ending",
]

DEFAULT_MONTHS: Final[int] = 6
MAX_MONTHS: Final[int] = 24


@dataclass(frozen=True, slots=True)
class LedgerFact:
    """Stored ledger rows with what a correction did to them.

    One fact stands for every row of one seat sharing a period, a kind
    and all three flags, its amount their sum (:func:`facts_for_seats`).

    :ivar enrollment_id: The seat; None when summed across seats
    :ivar entry: The rows as the money module's value shape, summed
    :ivar superseded: A later entry compensates this one
    :ivar compensation: This row is a compensation or was written to
        undo a prior decision, not a bill or a receipt
    :ivar reverses: Another row's ``superseded_by_id`` points here, so
        this row is the compensation that cancels it
    """

    enrollment_id: uuid.UUID | None
    entry: LedgerEntry
    superseded: bool
    compensation: bool
    reverses: bool = False


@dataclass(frozen=True, slots=True)
class MonthCollection:
    """One month of the collections report.

    :ivar period: The month, as ``YYYY-MM``
    :ivar charged: What the month was billed
    :ivar collected: What came in for it
    :ivar in_progress: The month contains today
    :ivar charged_bar: Charged as a percent of the largest charged month
    :ivar collected_bar: Collected on the same scale
    """

    period: str
    charged: Money
    collected: Money
    in_progress: bool
    charged_bar: int
    collected_bar: int


@dataclass(frozen=True, slots=True)
class CollectionsReport:
    """The collections report for a set of batches.

    :ivar months: Oldest first, ending at the current month
    :ivar outstanding: What the selected seats owe now
    :ivar owing_students: How many selected seats owe anything
    """

    months: list[MonthCollection]
    outstanding: Money
    owing_students: int


def clamp_months(months: int) -> int:
    """Pull a requested window into 1 to 24 months.

    :param months: The requested number of months
    :return: The window actually used
    """
    return max(1, min(MAX_MONTHS, months))


def months_ending(today: dt.date, count: int) -> list[str]:
    """List the last ``count`` period keys ending with today's month.

    :param today: A date in the final month
    :param count: How many months
    :return: Period keys, oldest first
    """
    last = today.year * 12 + today.month - 1
    return [
        f"{index // 12:04d}-{index % 12 + 1:02d}"
        for index in range(last - count + 1, last + 1)
    ]


def facts_for_seats(
    session: Session, seat_ids: Sequence[uuid.UUID], *, across_seats: bool = False
) -> list[LedgerFact]:
    """Read these seats' rows, summed per correction flags, in one statement.

    Rows are flagged first and then summed per (seat, period, kind,
    flags), so one fact stands for every row sharing all of those
    [C-14]. Every consumer here sums facts selected by kind, period and
    flags, or folds a seat's facts through :func:`app.money.derive`,
    which is linear per (period, kind)
    (``tests/money/test_ledger_presum_property.py``) -- so the summed
    facts answer exactly what the rows did, with one value built per
    group instead of per row. A fact must therefore never be counted.

    With ``across_seats`` the seat is dropped from the grouping too, for
    figures summed per period over many seats -- a month's charged and
    collected -- so a centre's month costs one fact per kind and flags
    rather than one per seat. Such facts carry no seat and must never be
    folded as one seat's ledger, whose floor is per seat.

    :param session: The session to read through
    :param seat_ids: The seats
    :param across_seats: Sum over the seats as well; facts then carry
        ``enrollment_id=None``
    :return: The summed facts, in no particular order
    """
    if not seat_ids:
        return []
    compensating = aliased(LedgerEntryRow)
    targeted = sa.exists().where(compensating.superseded_by_id == LedgerEntryRow.id)
    flagged = (
        sa.select(
            LedgerEntryRow.enrollment_id,
            LedgerEntryRow.kind,
            LedgerEntryRow.period,
            LedgerEntryRow.amount,
            LedgerEntryRow.superseded_by_id.is_not(None).label("superseded"),
            sa.or_(targeted, LedgerEntryRow.payment_claim_id.is_not(None)).label(
                "compensation"
            ),
            targeted.label("reverses"),
        )
        .where(LedgerEntryRow.enrollment_id == any_of(seat_ids))
        .subquery()
    )
    seat = sa.null() if across_seats else flagged.c.enrollment_id
    keys = (
        flagged.c.kind,
        flagged.c.period,
        flagged.c.superseded,
        flagged.c.compensation,
        flagged.c.reverses,
    )
    grouping = keys if across_seats else (flagged.c.enrollment_id, *keys)
    rows = session.execute(
        sa.select(seat, *keys, sa.func.sum(flagged.c.amount)).group_by(*grouping)
    ).all()
    return [
        LedgerFact(
            enrollment_id=row[0],
            entry=LedgerEntry(
                kind=LedgerEntryKind(row[1]), period=row[2], amount=row[6]
            ),
            superseded=bool(row[3]),
            compensation=bool(row[4]),
            reverses=bool(row[5]),
        )
        for row in rows
    ]


def charged_by_period(facts: Sequence[LedgerFact]) -> dict[str, Money]:
    """Total what each month was billed.

    :param facts: Rows with their correction flags
    :return: Charged per period; months billed nothing are absent
    """
    totals: defaultdict[str, Money] = defaultdict(lambda: Money.ZERO)
    for fact in facts:
        if (
            fact.entry.kind is LedgerEntryKind.CHARGE
            and not fact.superseded
            and not fact.compensation
        ):
            totals[fact.entry.period] += fact.entry.amount
    return dict(totals)


def carried_in_by_period(facts: Sequence[LedgerFact]) -> dict[str, Money]:
    """Total the balances carried into each month by decisions still in force.

    A ``carry_forward`` a correction superseded, and the one a
    correction wrote to cancel a ``carried_out``, move nothing that
    stands, so both are left out.

    :param facts: Rows with their correction flags
    :return: Carried in per period; months with none are absent
    """
    totals: defaultdict[str, Money] = defaultdict(lambda: Money.ZERO)
    for fact in facts:
        if (
            fact.entry.kind is LedgerEntryKind.CARRY_FORWARD
            and not fact.superseded
            and not fact.reverses
        ):
            totals[fact.entry.period] += fact.entry.amount
    return dict(totals)


def collected_by_period(facts: Sequence[LedgerFact]) -> dict[str, Money]:
    """Total the cash that stands for each month after corrections.

    :param facts: Rows with their correction flags
    :return: Collected per period; months with none are absent
    """
    return period_totals([fact.entry for fact in facts if not fact.superseded])


def _refusal() -> AuthorizationError:
    """Build the shared refusal for a batch that is not the lens's.

    :return: The refusal
    """
    return AuthorizationError(code=NOT_AVAILABLE, message_key="fees.not_available")


def _selected_seats(
    session: Session, lens: TeacherLens, batch_ids: Sequence[uuid.UUID] | None
) -> list[OwnedSeat]:
    """Pick the seats a report covers, refusing any batch not the lens's.

    :param session: The session to read through
    :param lens: The teacher lens
    :param batch_ids: The batches asked for, or None for all
    :return: The seats in those batches
    :raises AuthorizationError: A named batch is not this lens's
    """
    seats = owned_seats(session, lens)
    if batch_ids is None:
        return seats
    wanted = set(batch_ids)
    owned = set(
        session.scalars(
            sa.select(Batch.id).where(
                Batch.id.in_(wanted), Batch.owner_id == lens.owner_id
            )
        )
    )
    if owned != wanted:
        raise _refusal()
    return [seat for seat in seats if seat.batch_id in wanted]


def collections(
    session: Session,
    *,
    lens: TeacherLens,
    batch_ids: Sequence[uuid.UUID] | None,
    months: int,
    today: dt.date | None = None,
) -> CollectionsReport:
    """Build the collections report over the last months.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param batch_ids: The batches to cover, or None for every owned batch
    :param months: How many months, clamped to 1 to 24
    :param today: The server's date; Bangladesh's by default
    :return: One row per month, the amount owed now and how many owe
    :raises AuthorizationError: A named batch is not this lens's
    """
    on = today or bangladesh_today()
    seats = _selected_seats(session, lens, batch_ids)
    seat_ids = [seat.enrollment_id for seat in seats]
    facts = facts_for_seats(session, seat_ids, across_seats=True)

    charged = charged_by_period(facts)
    collected = collected_by_period(facts)
    periods = months_ending(on, clamp_months(months))
    largest = max(
        (charged.get(period, Money.ZERO) for period in periods), default=Money.ZERO
    )

    # What each seat owes needs only its months still owing [C-14].
    ledger = owing_ledger_for_seats(session, seat_ids)
    owed = [derive(ledger[seat]).total_outstanding for seat in seat_ids]

    current = months_ending(on, 1)[0]
    rows: list[MonthCollection] = []
    for period in periods:
        billed = charged.get(period, Money.ZERO)
        received = collected.get(period, Money.ZERO)
        rows.append(
            MonthCollection(
                period=period,
                charged=billed,
                collected=received,
                in_progress=period == current,
                charged_bar=billed.percent_of(largest),
                collected_bar=min(100, received.percent_of(largest)),
            )
        )
    return CollectionsReport(
        months=rows,
        outstanding=Money.sum(owed),
        owing_students=sum(1 for amount in owed if amount.is_positive()),
    )
