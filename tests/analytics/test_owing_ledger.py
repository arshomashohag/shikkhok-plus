"""The owing-only ledger read folds to what the whole ledger folds to [C-14].

``owing_ledger_for_seats`` sends the fold only the months that can still
owe or hold credit: a (seat, period) whose net is zero or less and which
holds no credit row is left out in SQL. That is a semantic reduction, not
a mere regrouping, so it carries two proofs:

1. **The SQL's sign table agrees with the fold**, probed through
   :func:`app.money.derive` itself for every kind -- the table is
   hand-written beside the SQL, and an independent source is what makes
   a mis-signed kind fail instead of agreeing with itself.
2. **The three promised quantities agree with the whole ledger** --
   ``total_outstanding``, every positive ``per_cycle`` period, and
   ``available_credit`` -- over seeded random histories including settled,
   over-relieved, credited and carried months.
"""

from __future__ import annotations

import random

from sqlalchemy.orm import Session

from app.analytics.earnings import period_totals
from app.analytics.seats import (
    CREDIT_KINDS,
    CYCLE_SIGN,
    due_dates_for_seats,
    ledger_by_period,
    ledger_for_seats,
    owing_ledger_for_seats,
)
from app.fees.balances import entries_for_enrollment
from app.money import DerivedQuantities, LedgerEntry, LedgerEntryKind, Money, derive
from tests.analytics.conftest import seat_with_ledger
from tests.batches.conftest import TeacherFixture

KINDS = [kind.value for kind in LedgerEntryKind]


def _owing(derived: DerivedQuantities) -> dict[str, Money]:
    """Keep the positive periods of a fold, which is all the reduction keeps.

    :param derived: A fold
    :return: Period to a positive balance
    """
    return {p: v for p, v in derived.per_cycle.items() if v.is_positive()}


def test_the_sign_table_is_the_fold_s() -> None:
    """Every kind moves a cycle the way CYCLE_SIGN says, probed via derive.

    A period charged 5 then given 2 of the kind under test owes 7, 5 or 3
    as the kind adds to it, leaves it alone, or relieves it.

    :return: None
    """
    assert set(CYCLE_SIGN) == set(LedgerEntryKind)
    for kind in LedgerEntryKind:
        probe = derive(
            [
                LedgerEntry(kind=LedgerEntryKind.CHARGE, period="p", amount=Money(5)),
                LedgerEntry(kind=kind, period="p", amount=Money(2)),
            ]
        )
        assert probe.per_cycle["p"] == Money(5 + 2 * CYCLE_SIGN[kind]), kind


def test_the_credit_kinds_are_the_fold_s() -> None:
    """Exactly the CREDIT_KINDS move available credit, probed via derive.

    :return: None
    """
    for kind in LedgerEntryKind:
        probe = derive(
            [
                LedgerEntry(
                    kind=LedgerEntryKind.CREDIT_GRANT, period="p", amount=Money(5)
                ),
                LedgerEntry(kind=kind, period="q", amount=Money(2)),
            ]
        )
        assert (probe.available_credit != Money(5)) == (kind in CREDIT_KINDS), kind


def test_the_owing_read_folds_to_the_whole_ledger_s_owed_figures(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """Outstanding, positive months and credit agree, seat by seat.

    Histories mix fully settled months (charge then an equal receipt),
    which the read must drop, with random entries of every kind, which
    it must keep wherever they owe or credit. The seat's due dates,
    restricted to the kept months, still date every owing month.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    rng = random.Random(7)  # noqa: S311  test data, not security
    periods = [f"2026-{month:02d}" for month in range(1, 9)]
    seats = []
    for index in range(14):
        entries: list[tuple[str, str, str]] = []
        for period in rng.sample(periods, rng.randint(0, 5)):
            entries += [("charge", period, "1000.00"), ("receipt", period, "1000.00")]
        entries += [
            (rng.choice(KINDS), rng.choice(periods), f"{rng.randint(0, 2000)}.00")
            for _ in range(rng.randint(0, 12))
        ]
        rng.shuffle(entries)
        seats.append(
            seat_with_ledger(
                owner_session,
                restricted_session,
                batch_id=teacher.batch_id,
                display_name=f"Seat {index}",
                entries=entries,
            )
        )

    owing = owing_ledger_for_seats(restricted_session, seats)
    whole = ledger_for_seats(restricted_session, seats)
    dropped = 0
    for seat in seats:
        raw = derive(entries_for_enrollment(restricted_session, seat))
        reduced = derive(owing[seat])
        assert reduced.total_outstanding == raw.total_outstanding
        assert reduced.available_credit == raw.available_credit
        assert _owing(reduced) == _owing(raw)
        dropped += len(whole[seat]) - len(owing[seat])
    assert dropped > 0, "no settled month was left out: the reduction did nothing"

    due = due_dates_for_seats(restricted_session, seats, periods=owing)
    assert set(due) == set(seats)


def test_the_by_period_read_totals_what_every_seat_received(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """Money received per month is the same summed across seats in SQL.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    rng = random.Random(11)  # noqa: S311  test data, not security
    seats = [
        seat_with_ledger(
            owner_session,
            restricted_session,
            batch_id=teacher.batch_id,
            display_name=f"Payer {index}",
            entries=[
                (
                    rng.choice(KINDS),
                    f"2026-0{rng.randint(1, 4)}",
                    f"{rng.randint(1, 900)}.50",
                )
                for _ in range(rng.randint(1, 8))
            ],
        )
        for index in range(6)
    ]
    rows = [
        entry
        for seat in seats
        for entry in entries_for_enrollment(restricted_session, seat)
    ]
    assert period_totals(ledger_by_period(restricted_session, seats)) == period_totals(
        rows
    )
    assert ledger_by_period(restricted_session, []) == []
