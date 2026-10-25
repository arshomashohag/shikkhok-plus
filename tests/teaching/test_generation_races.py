"""Session-generation idempotency under real concurrency [BR1.3].

**The sequential version of this test is worthless**, and BR1.3's own
``violation_behaviour`` says so: an application-level "has this run?"
guard passes a sequential test and creates two sessions for one class
under two workers. Two sessions for one class means each has its own
roster, so attendance marked on one is invisible on the other and the
student's record shows them absent from a class they attended.

So: real threads, released together from a barrier, contending on the
same ``(batch_id, date, start_time)`` at the same moment, against real
PostgreSQL via testcontainers. The shape is copied from
``tests/fees/test_generation_races.py`` rather than invented.

**The assertion is the OUTCOME, not the absence of an exception.** A
conflict is the SUCCESS path here [BR1.3], so a raising run is itself a
defect -- an implementation that swallowed every error would pass an
exception-free assertion and fail the row-count one.

**This guard was proved to fire.** Replacing the ``ON CONFLICT DO
NOTHING`` insert with a read-then-insert makes
``test_overlapping_generations_leave_exactly_one_session`` fail with
duplicate rows, which is what distinguishes this from a concurrency
test that cannot fail.
"""

from __future__ import annotations

import datetime as dt
import threading
import uuid

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from app.teaching.generation import generate_sessions
from tests.batches.conftest import TeacherFixture

#: How many runs contend. Eight matches the fee precedent and is
#: comfortably more than the two workers Phase 1 actually runs.
WORKERS = 8

IN_FEBRUARY = dt.date(2027, 2, 7)

#: Four Mondays in February 2027 plus five in March, computed rather
#: than assumed -- the horizon is the current calendar month and the
#: next.
EXPECTED_SESSIONS = 9


def _session_rows(
    session: DbSession, batch_id: uuid.UUID
) -> list[tuple[dt.date, dt.time, int]]:
    """Group a batch's sessions by occurrence, with their row counts.

    :param session: The session to read through
    :param batch_id: The batch
    :return: One ``(date, start_time, count)`` per occurrence
    """
    rows = session.execute(
        sa.text(
            "SELECT date, start_time, count(*) FROM session "
            "WHERE batch_id = :id GROUP BY date, start_time "
            "ORDER BY date, start_time"
        ),
        {"id": batch_id},
    ).all()
    return [(row[0], row[1], row[2]) for row in rows]


def test_overlapping_generations_leave_exactly_one_session(
    restricted_engine: Engine,
    teacher: TeacherFixture,
    monday_slot: uuid.UUID,
) -> None:
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    barrier = threading.Barrier(WORKERS)
    failures: list[BaseException] = []
    lock = threading.Lock()

    results: list[int] = []

    def run() -> None:
        session = factory()
        try:
            barrier.wait(timeout=30)
            outcome = generate_sessions(session, today=IN_FEBRUARY)
            with lock:
                results.append(outcome.batches_failed)
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

    assert failures == [], (
        f"{len(failures)} of {WORKERS} racing runs raised, the first "
        f"being {failures[0]!r}. A conflict on "
        "(batch_id, date, start_time) is the success path, not an "
        "error [BR1.3]."
    )

    # **The assertion that makes this test able to fail.** The unique
    # constraint protects the DATA whatever the insert looks like, so a
    # row-count assertion alone passes against a read-then-insert guard
    # -- measured, not reasoned: under that implementation seven of
    # eight workers raise IntegrityError, the per-slot `except`
    # swallows it, and every count assertion below still holds. What
    # distinguishes the constraint-based insert is that the conflict is
    # the SUCCESS path and NOTHING is reported as failed.
    assert results == [0] * WORKERS, (
        f"racing runs reported {results} failed slots. A conflict must "
        "be the success path, which means ON CONFLICT DO NOTHING "
        "rather than a read-then-insert guard whose IntegrityError is "
        "caught and counted [BR1.3]."
    )

    verify = factory()
    try:
        occurrences = _session_rows(verify, teacher.batch_id)
        assert len(occurrences) == EXPECTED_SESSIONS
        duplicated = [entry for entry in occurrences if entry[2] != 1]
        assert duplicated == [], (
            f"{duplicated} — the unique constraint did not hold under "
            f"{WORKERS} concurrent runs, or an application-level guard "
            "was used in its place [BR1.3]"
        )
    finally:
        verify.close()


def test_overlapping_generations_across_two_slots_each_create_once(
    owner_session: DbSession,
    restricted_engine: Engine,
    teacher: TeacherFixture,
    monday_slot: uuid.UUID,
) -> None:
    # Two slots racing at once. A per-slot guard that happened to work
    # for a single slot can still duplicate when several are inserted
    # in one run.
    from tests.teaching.conftest import add_slot

    add_slot(
        owner_session,
        batch_id=teacher.batch_id,
        weekday=2,
        start_time=dt.time(9, 0),
    )

    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    barrier = threading.Barrier(WORKERS)

    def run() -> None:
        session = factory()
        try:
            barrier.wait(timeout=30)
            generate_sessions(session, today=IN_FEBRUARY)
        finally:
            session.close()

    threads = [threading.Thread(target=run) for _ in range(WORKERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    verify = factory()
    try:
        occurrences = _session_rows(verify, teacher.batch_id)
        assert [entry[2] for entry in occurrences] == [1] * len(occurrences)
        assert {entry[1] for entry in occurrences} == {
            dt.time(16, 0),
            dt.time(9, 0),
        }
    finally:
        verify.close()


def test_an_ad_hoc_session_survives_concurrent_generation(
    owner_session: DbSession,
    restricted_engine: Engine,
    teacher: TeacherFixture,
    monday_slot: uuid.UUID,
) -> None:
    # BR1.4 under contention: generation must never delete, and a
    # reconciling implementation under eight workers is the version
    # most likely to.
    from app.db.models import Session as SessionRow

    ad_hoc = SessionRow(
        batch_id=teacher.batch_id,
        date=dt.date(2027, 2, 6),
        start_time=dt.time(10, 0),
        status="scheduled",
        origin="ad_hoc",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(ad_hoc)
    owner_session.commit()
    ad_hoc_id = ad_hoc.id

    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    barrier = threading.Barrier(WORKERS)

    def run() -> None:
        session = factory()
        try:
            barrier.wait(timeout=30)
            generate_sessions(session, today=IN_FEBRUARY)
        finally:
            session.close()

    threads = [threading.Thread(target=run) for _ in range(WORKERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    verify = factory()
    try:
        survivor = verify.get(SessionRow, ad_hoc_id)
        assert survivor is not None
        assert survivor.origin == "ad_hoc"
    finally:
        verify.close()
