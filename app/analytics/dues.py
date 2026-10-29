"""Assembling dues rows: the per-seat loop, with no session to reach.

**This module takes no session, and that is the unit's one structural
control** [logical-components § 1, NFR20.32]. The per-seat loop lives
here, so this is the one place a query could be added per row -- and a
module that cannot reach a session cannot make that mistake. The N+1
obligation becomes a property of the module graph rather than a rule
someone has to remember.

**The specific trap is a correct function called at the wrong
granularity.** ``app/fees/balances.py:72``'s ``oldest_unpaid_period``
takes one ``enrollment_id`` and folds that seat's ledger, so one call
per dues row is one query per seat: at the scale ceiling -- five batches
of up to twenty seats -- up to a hundred statements for one screen. The
function is correct; reusing it here is what would be wrong.

So the oldest unpaid period is computed from the **same** ``per_cycle``
map the outstanding balance comes from: the minimum period whose balance
is above zero. Same definition, same fold, no second query -- and
``test_dues.py`` pins the two answers to each other so the copy is
tracked rather than merely cheap [NFR20.33].
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final, Literal

from app.analytics.seats import OwnedSeat
from app.fees.overdue import days_overdue
from app.fees.reminders import REMIND_AGAIN_AFTER
from app.money import LedgerEntry, Money, derive

__all__ = [
    "BUCKETS",
    "DuesBucket",
    "DuesGroup",
    "DuesRow",
    "DuesSummary",
    "dues_rows",
    "dues_summary",
]

#: How late a debt is, as the Dues screen groups it.
DuesBucket = Literal["over_30", "late", "not_late"]

#: The groups in the order the screen shows them, latest first.
BUCKETS: Final[tuple[DuesBucket, ...]] = ("over_30", "late", "not_late")

#: Beyond this many days a debt is in the "30+ days late" group.
_LONG_LATE_DAYS: Final[int] = 30


@dataclass(frozen=True, slots=True)
class DuesRow:
    """One person who owes money, in one batch, right now [FR7.1].

    **Membership is driven by outstanding balance and NOT by active
    status** [FR7.2, BR1.2]: a student who left owing money still
    appears, which is the single most load-bearing sentence in this
    unit.

    :ivar enrollment_id: The seat, never a global account id [ADR-001]
    :ivar batch_id: The batch the debt sits in
    :ivar batch_name: That batch's name, because the same person may
        owe in two
    :ivar display_name: What the TEACHER recorded, never a
        student-authored profile field [TC-13]
    :ivar outstanding: What this seat still owes, from the built fold
    :ivar oldest_unpaid_period: Which period the debt starts in
    :ivar latest_unpaid_period: Which period it runs to
    :ivar days_late: Days since the oldest late due date, or None when
        nothing is past due
    :ivar bucket: Which group the screen shows it in
    :ivar last_reminded_at: When a reminder last went out, if ever
    :ivar remindable: Late, someone has accepted the seat, and not
        reminded within the last day
    """

    enrollment_id: uuid.UUID
    batch_id: uuid.UUID
    batch_name: str
    display_name: str
    outstanding: Money
    oldest_unpaid_period: str | None
    latest_unpaid_period: str | None = None
    days_late: int | None = None
    bucket: DuesBucket = "not_late"
    last_reminded_at: dt.datetime | None = None
    remindable: bool = False


@dataclass(frozen=True, slots=True)
class DuesGroup:
    """One group's total.

    :ivar bucket: Which group
    :ivar total: What its rows owe together
    :ivar count: How many rows
    :ivar share: Its total as a whole percent of everything owed, for
        the screen's bar
    """

    bucket: DuesBucket
    total: Money
    count: int
    share: int


@dataclass(frozen=True, slots=True)
class DuesSummary:
    """The Dues screen's headline figures.

    :ivar total: Everything owed
    :ivar count: How many seats owe it
    :ivar late_total: What is owed past its due date
    :ivar remindable: How many seats "Remind" would reach
    :ivar groups: One per bucket, in :data:`BUCKETS` order, empty ones
        included so the screen never infers a zero
    """

    total: Money
    count: int
    late_total: Money
    remindable: int
    groups: list[DuesGroup]


def _bucket(days_late: int | None) -> DuesBucket:
    """Name the group a debt this late belongs in.

    :param days_late: Days past due, or None
    :return: Its bucket
    """
    if days_late is None:
        return "not_late"
    return "over_30" if days_late > _LONG_LATE_DAYS else "late"


def dues_rows(
    seats: Iterable[OwnedSeat],
    ledger: dict[uuid.UUID, list[LedgerEntry]],
    *,
    due_by_seat: Mapping[uuid.UUID, Mapping[str, dt.date]] | None = None,
    last_reminded: Mapping[uuid.UUID, dt.datetime] | None = None,
    today: dt.date | None = None,
    now: dt.datetime | None = None,
) -> list[DuesRow]:
    """Build one row per seat that owes money, latest debt first.

    **Every argument is already in hand**, which is what makes the
    constant statement count structural: the fold runs over maps
    populated by one read each, so there is no seat loop a query could
    be put inside.

    **Ordered here rather than in the client** [functional-spec § 7a]:
    the latest debt first, then the larger, then the seat id so equal
    rows return in a stable order. A client sorting a domain list is one
    of the five erosion paths ``team.md`` names.

    :param seats: The owned seats, from :func:`~app.analytics.seats.owned_seats`
    :param ledger: Their entries, from
        :func:`~app.analytics.seats.ledger_for_seats`
    :param due_by_seat: Due date per period per seat; none means nothing
        is late
    :param last_reminded: The latest reminder per seat
    :param today: Bangladesh's date, which lateness is measured on
    :param now: The current time, which "reminded today" is measured on
    :return: One row per owing seat, possibly empty [BR1.5]
    """
    on = today or dt.datetime.now(tz=dt.UTC).date()
    at = now or dt.datetime.now(tz=dt.UTC)
    due = due_by_seat or {}
    reminded = last_reminded or {}
    rows: list[DuesRow] = []

    for seat in seats:
        derived = derive(ledger.get(seat.enrollment_id, []))
        if not derived.total_outstanding.is_positive():
            # Owing nothing means absent, active or not [BR1.3]. A dues
            # view listing everyone is not a dues view.
            continue

        owing = _owing_periods(derived.per_cycle)
        days_late = days_overdue(derived.per_cycle, due.get(seat.enrollment_id, {}), on)
        last = reminded.get(seat.enrollment_id)
        rows.append(
            DuesRow(
                enrollment_id=seat.enrollment_id,
                batch_id=seat.batch_id,
                batch_name=seat.batch_name,
                display_name=seat.display_name,
                outstanding=derived.total_outstanding,
                oldest_unpaid_period=owing[0] if owing else None,
                latest_unpaid_period=owing[-1] if owing else None,
                days_late=days_late,
                bucket=_bucket(days_late),
                last_reminded_at=last,
                remindable=(
                    days_late is not None
                    and seat.reachable
                    and (last is None or at - last >= REMIND_AGAIN_AFTER)
                ),
            )
        )

    rows.sort(
        key=lambda row: (
            -1 if row.days_late is None else row.days_late,
            row.outstanding,
            row.enrollment_id,
        ),
        reverse=True,
    )
    return rows


def dues_summary(rows: list[DuesRow]) -> DuesSummary:
    """Total the rows, overall and per group.

    :param rows: The dues rows
    :return: The headline figures
    """
    total = Money.sum(row.outstanding for row in rows)
    totals = {
        bucket: Money.sum(row.outstanding for row in rows if row.bucket == bucket)
        for bucket in BUCKETS
    }
    return DuesSummary(
        total=total,
        count=len(rows),
        late_total=Money.sum(
            row.outstanding for row in rows if row.days_late is not None
        ),
        remindable=sum(1 for row in rows if row.remindable),
        groups=[
            DuesGroup(
                bucket=bucket,
                total=totals[bucket],
                count=sum(1 for row in rows if row.bucket == bucket),
                share=totals[bucket].percent_of(total),
            )
            for bucket in BUCKETS
        ],
    )


def _owing_periods(per_cycle: dict[str, Money]) -> list[str]:
    """List the periods still owing, earliest first, from a fold in hand.

    **The same definition as the built ``oldest_unpaid_period``**, over
    the same ``per_cycle`` map, without the second read that function
    performs for one enrollment. Period keys are fixed width precisely
    so this is a sort rather than a parse.

    The balance test is not optional: ``min(per_cycle)`` alone would
    return a settled period whenever an earlier one has been paid off.

    :param per_cycle: Outstanding per period, each floored at zero
    :return: The periods owing, earliest first; empty where nothing is
    """
    return sorted(
        period for period, balance in per_cycle.items() if balance.is_positive()
    )
