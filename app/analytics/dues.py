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

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from app.analytics.seats import OwnedSeat
from app.money import LedgerEntry, Money, derive

__all__ = ["DuesRow", "dues_rows"]


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
    """

    enrollment_id: uuid.UUID
    batch_id: uuid.UUID
    batch_name: str
    display_name: str
    outstanding: Money
    oldest_unpaid_period: str | None


def dues_rows(
    seats: Iterable[OwnedSeat],
    ledger: dict[uuid.UUID, list[LedgerEntry]],
) -> list[DuesRow]:
    """Build one row per seat that owes money, largest debt first.

    **Both arguments are already in hand**, which is what makes the
    constant statement count structural: the fold runs over a dict
    populated by one read, so there is no seat loop a query could be put
    inside.

    **Ordered here rather than in the client** [functional-spec § 7a]:
    the largest debt is first, and a client sorting a domain list is one
    of the five erosion paths ``team.md`` names. The secondary key is
    the seat id, so two equal debts return in a stable order across
    repeated reads rather than in whatever order the dict happened to
    yield.

    :param seats: The owned seats, from :func:`~app.analytics.seats.owned_seats`
    :param ledger: Their entries, from
        :func:`~app.analytics.seats.ledger_for_seats`
    :return: One row per owing seat, outstanding descending, possibly
        empty [BR1.5]
    """
    rows: list[DuesRow] = []

    for seat in seats:
        derived = derive(ledger.get(seat.enrollment_id, []))
        if not derived.total_outstanding.is_positive():
            # Owing nothing means absent, active or not [BR1.3]. A dues
            # view listing everyone is not a dues view.
            continue

        rows.append(
            DuesRow(
                enrollment_id=seat.enrollment_id,
                batch_id=seat.batch_id,
                batch_name=seat.batch_name,
                display_name=seat.display_name,
                outstanding=derived.total_outstanding,
                oldest_unpaid_period=_oldest_unpaid(derived.per_cycle),
            )
        )

    rows.sort(key=lambda row: (row.outstanding, row.enrollment_id), reverse=True)
    return rows


def _oldest_unpaid(per_cycle: dict[str, Money]) -> str | None:
    """Return the earliest period still owing, from a fold in hand.

    **The same definition as the built ``oldest_unpaid_period``**, over
    the same ``per_cycle`` map, without the second read that function
    performs for one enrollment. Period keys are fixed width precisely
    so this is a sort rather than a parse.

    The balance test is not optional: ``min(per_cycle)`` alone would
    return a settled period whenever an earlier one has been paid off.

    :param per_cycle: Outstanding per period, each floored at zero
    :return: The earliest period owing, or None where nothing is owed
    """
    owing = sorted(
        period for period, balance in per_cycle.items() if balance.is_positive()
    )
    return owing[0] if owing else None
