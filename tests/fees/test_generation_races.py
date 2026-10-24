"""Idempotency under real concurrency [BR1.3, NFR19.8].

**The sequential version of this test is worthless and the project has
already written that down once.** `tests/auth/test_ceilings.py` carries
the warning beside a test that was renamed after being found to run two
checkers one after another:

    A test whose NAME claims a property it does not exercise is worse
    than no test, because the next reader believes the property is
    covered.

A two-run sequential test here passes against an implementation with no
atomicity at all -- the exact implementation the constraint exists to
prevent. So: real threads, released together from a barrier, contending
on the same ``(enrollment_id, period)`` at the same moment, against real
PostgreSQL.

**The assertion is the OUTCOME, not the absence of an exception.** After
N overlapping runs there is exactly one cycle row per
``(enrollment_id, period)`` and the ledger's charged total equals one
period's charge. An implementation that swallowed every error would pass
an exception-free assertion and fail this one.

**`import threading` is at the top of this file.** The precedent in
`test_ceilings.py` imports it inside the function, which violates the
project's standing rule that imports live at the top; the shape is worth
copying and that detail is not.
"""

from __future__ import annotations

import datetime as dt
import threading
import uuid

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.fees.generation import generate_due_cycles
from app.money import Money
from tests.batches.conftest import TeacherFixture
from tests.fees.conftest import set_joined_on

#: How many runs contend. Eight matches the ceilings precedent and is
#: comfortably more than the two workers Phase 1 actually runs.
WORKERS = 8

IN_FEBRUARY = dt.date(2027, 2, 20)


def _charged_total(session: Session, enrollment_id: uuid.UUID) -> Money:
    """Total every charge entry for a seat.

    :param session: The session to read through
    :param enrollment_id: The seat
    :return: The charged total
    """
    raw = session.execute(
        sa.text(
            "SELECT coalesce(sum(amount), 0) FROM ledger_entry "
            "WHERE enrollment_id = :id AND kind = 'charge'"
        ),
        {"id": enrollment_id},
    ).scalar_one()
    return Money(raw)


def test_overlapping_generations_leave_exactly_one_cycle_per_period(
    restricted_engine: Engine,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))

    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    barrier = threading.Barrier(WORKERS)
    failures: list[BaseException] = []
    lock = threading.Lock()

    def run() -> None:
        session = factory()
        try:
            barrier.wait(timeout=30)
            generate_due_cycles(session, today=IN_FEBRUARY)
        except BaseException as error:  # noqa: BLE001  recorded, then asserted
            with lock:
                failures.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=run) for _ in range(WORKERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    # A conflict is the SUCCESS path, so a raising run is itself a
    # defect: generation must continue without raising [AC5.1.6].
    assert failures == [], (
        f"{len(failures)} of {WORKERS} racing runs raised, the first "
        f"being {failures[0]!r}. A conflict on (enrollment_id, period) "
        "is the success path, not an error [BR1.3]."
    )

    verify = factory()
    try:
        rows = verify.execute(
            sa.text(
                "SELECT period, count(*) FROM fee_cycle "
                "WHERE enrollment_id = :id GROUP BY period"
            ),
            {"id": seat},
        ).all()
        assert [(row[0], row[1]) for row in rows] == [("2027-02", 1)], (
            f"{rows} — the unique constraint did not hold under {WORKERS} "
            "concurrent runs, or an application-level guard was used in "
            "its place [BR1.3]"
        )

        # THE OUTCOME ASSERTION. One period's charge, not eight.
        assert _charged_total(verify, seat) == Money("1500.00"), (
            "the ledger was charged more than once for one period: the "
            "charge is appended on the created row only, and the "
            "conflict path must append nothing"
        )
    finally:
        verify.close()


def test_overlapping_generations_over_several_periods_each_charge_once(
    restricted_engine: Engine,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # Three periods racing at once. A per-period lock that happened to
    # work for a single period can still double-charge when several are
    # inserted in one run.
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2026, 12, 1))

    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    barrier = threading.Barrier(WORKERS)

    def run() -> None:
        session = factory()
        try:
            barrier.wait(timeout=30)
            generate_due_cycles(session, today=IN_FEBRUARY)
        finally:
            session.close()

    threads = [threading.Thread(target=run) for _ in range(WORKERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    verify = factory()
    try:
        counts = verify.execute(
            sa.text(
                "SELECT period, count(*) FROM fee_cycle "
                "WHERE enrollment_id = :id GROUP BY period ORDER BY period"
            ),
            {"id": seat},
        ).all()
        assert [(row[0], row[1]) for row in counts] == [
            ("2026-12", 1),
            ("2027-01", 1),
            ("2027-02", 1),
        ]

        # Three periods at 1500.00 each, charged exactly once apiece.
        assert _charged_total(verify, seat) == Money("4500.00")
    finally:
        verify.close()
