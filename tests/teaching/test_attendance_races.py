"""The version conflict and replay, under real concurrency.

**A roster write guarded by a version check passes every sequential
test against an implementation with NO guard at all**, because nothing
ever contends. BR3.4 is the rule that says so, and this is the exact
shape of D3's double-crediting defect: a race on a path the constraint
did not cover, with tests that never ran two writes at once.

So: N threads released together from a barrier, against real
PostgreSQL via testcontainers, each submitting a roster against version
V. The assertions are the outcomes BR3.4 names:

* exactly **one** success and **N-1** conflicts;
* ``attendance_version`` is **V+1 and not V+N**;
* the stored roster is **byte-identical to the one that won** -- not
  merely "some roster is stored", which an interleaved write would
  also satisfy.

**These tests were proved able to fail**, by replacing the conditional
``UPDATE ... WHERE attendance_version = :base`` with an unconditional
one: under that implementation the version reaches V+N and several
writes apply, and
``test_only_one_of_n_racing_rosters_applies`` fails. A concurrency test
that cannot fail is the easiest kind to write by accident.
"""

from __future__ import annotations

import datetime as dt
import threading
import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from app.authz.lenses import TeacherLens
from app.db.models import Session
from app.errors import ConflictError
from app.teaching.submissions import SeatMark, SubmissionResult, submit_roster
from tests.batches.conftest import TeacherFixture, enroll

#: How many writes contend. Eight matches the fee precedent.
WORKERS = 8

SESSION_DATE = dt.date(2027, 4, 12)


@pytest.fixture
def owned_session(owner_session: DbSession, teacher: TeacherFixture) -> uuid.UUID:
    """One session belonging to the fixture teacher.

    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :return: The session id
    """
    row = Session(
        batch_id=teacher.batch_id,
        date=SESSION_DATE,
        start_time=dt.time(16, 0),
        status="scheduled",
        origin="recurrence",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(row)
    owner_session.commit()
    return row.id


@pytest.fixture
def eight_seats(
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> list[uuid.UUID]:
    """Eight seats on the teacher's batch.

    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :param account_factory: Makes student accounts
    :return: The eight enrollment ids
    """
    return [
        enroll(
            owner_session,
            batch_id=teacher.batch_id,
            display_name=f"Student {index:02d}",
            student_account_id=account_factory(),
            student_decision="accepted",
            guardian_decision="pending",
        )
        for index in range(WORKERS)
    ]


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the fixture teacher's lens.

    :param teacher: The teacher fixture
    :return: The lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def _stored_roster(
    session: DbSession, session_id: uuid.UUID
) -> list[tuple[uuid.UUID, bool]]:
    """Read a session's roster as a comparable, ordered list.

    :param session: The session to read through
    :param session_id: The session
    :return: ``(enrollment_id, present)`` ordered by enrollment id
    """
    rows = session.execute(
        sa.text(
            "SELECT enrollment_id, present FROM attendance "
            "WHERE session_id = :id ORDER BY enrollment_id"
        ),
        {"id": session_id},
    ).all()
    return [(row[0], row[1]) for row in rows]


def test_only_one_of_n_racing_rosters_applies(
    restricted_engine: Engine,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    eight_seats: list[uuid.UUID],
) -> None:
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    barrier = threading.Barrier(WORKERS)
    lock = threading.Lock()
    applied: list[tuple[int, SubmissionResult]] = []
    conflicts: list[int] = []
    unexpected: list[BaseException] = []

    def run(index: int) -> None:
        # Each worker marks a DIFFERENT seat absent, so the winning
        # roster is identifiable: "some roster is stored" would be
        # satisfied by an interleaved write, and this is not.
        session = factory()
        try:
            roster = [
                SeatMark(enrollment_id=seat, present=position != index)
                for position, seat in enumerate(eight_seats)
            ]
            barrier.wait(timeout=30)
            result = submit_roster(
                session,
                lens=_lens(teacher),
                session_id=owned_session,
                base_version=0,
                client_mutation_id=uuid.uuid4(),
                seats=roster,
            )
            with lock:
                applied.append((index, result))
        except ConflictError:
            with lock:
                conflicts.append(index)
        except BaseException as error:  # noqa: BLE001  recorded, then asserted
            with lock:
                unexpected.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=run, args=(index,)) for index in range(WORKERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert unexpected == [], (
        f"{len(unexpected)} racing writes raised something other than "
        f"ConflictError, the first being {unexpected[0]!r}"
    )
    assert len(applied) == 1, (
        f"{len(applied)} of {WORKERS} racing rosters applied. Exactly "
        "one must apply and N-1 must be refused: never two applied, "
        "never a silent overwrite [BR3.4]."
    )
    assert len(conflicts) == WORKERS - 1

    verify = factory()
    try:
        version = verify.scalars(
            sa.select(Session.attendance_version).where(Session.id == owned_session)
        ).one()
        assert version == 1, (
            f"attendance_version is {version}, not 1. V+N means every "
            "write applied its increment, which is the unguarded "
            "implementation [BR3.4]."
        )

        # BYTE-IDENTICAL to the winner's roster, not merely non-empty.
        winner_index = applied[0][0]
        expected = sorted(
            (seat, position != winner_index)
            for position, seat in enumerate(eight_seats)
        )
        assert _stored_roster(verify, owned_session) == expected, (
            "the stored roster is not the one that won: a losing "
            "write interleaved its rows [BR3.4]"
        )

        # The second, INDEPENDENT guarantee: one submission row for
        # that version, which UNIQUE (session_id, resulting_version)
        # enforces whatever the update looks like.
        submissions = verify.execute(
            sa.text("SELECT count(*) FROM queued_submission WHERE session_id = :id"),
            {"id": owned_session},
        ).scalar_one()
        assert submissions == 1
    finally:
        verify.close()


def test_the_same_mutation_id_replayed_concurrently_writes_once(
    restricted_engine: Engine,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    eight_seats: list[uuid.UUID],
) -> None:
    # BR3.8's concurrent half: the case that distinguishes a database
    # constraint from an application-level "have I seen this id?"
    # guard, which passes sequentially and double-writes under two
    # workers.
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    barrier = threading.Barrier(WORKERS)
    mutation = uuid.uuid4()
    lock = threading.Lock()
    versions: list[int] = []
    errors: list[BaseException] = []

    roster = [SeatMark(enrollment_id=seat, present=True) for seat in eight_seats]

    def run() -> None:
        session = factory()
        try:
            barrier.wait(timeout=30)
            result = submit_roster(
                session,
                lens=_lens(teacher),
                session_id=owned_session,
                base_version=0,
                client_mutation_id=mutation,
                seats=roster,
            )
            with lock:
                versions.append(result.attendance_version)
        except BaseException as error:  # noqa: BLE001  recorded, then asserted
            with lock:
                errors.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=run) for _ in range(WORKERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    verify = factory()
    try:
        # ONE submission row for the whole storm, whatever each caller
        # observed: the unique constraint on the pair is what makes
        # this true rather than an application guard.
        submissions = verify.execute(
            sa.text(
                "SELECT count(*) FROM queued_submission WHERE client_mutation_id = :m"
            ),
            {"m": mutation},
        ).scalar_one()
        assert submissions == 1, (
            f"{submissions} submission rows for one mutation id under "
            f"{WORKERS} concurrent replays [BR3.8]"
        )

        version = verify.scalars(
            sa.select(Session.attendance_version).where(Session.id == owned_session)
        ).one()
        assert version == 1, (
            f"the version reached {version}: a replay must not "
            "increment it even once more [BR3.8]"
        )

        # Every caller that did not raise saw the SAME version.
        assert set(versions) <= {1}, f"callers observed {sorted(set(versions))}"

        # **The losers' failures are asserted, not merely collected.**
        # Every assertion above holds whatever the losers raised, so
        # without this one the test passes against workers failing with
        # a TypeError, a 500 or a dropped connection.
        #
        # Not `errors == []`: under a replay storm none of the losers
        # has committed its submission row yet, so their replay lookup
        # finds nothing and they correctly meet the version guard. The
        # device resends and sees the replay then. What must hold is
        # that every failure is THAT refusal and not something else.
        assert all(isinstance(error, ConflictError) for error in errors), (
            "a worker failed with something other than a ConflictError: "
            f"{[type(error).__name__ for error in errors]}"
        )
    finally:
        verify.close()


def test_re_applying_with_a_fresh_id_against_the_new_version_writes(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    eight_seats: list[uuid.UUID],
) -> None:
    # BR3.7's server half. **The obvious implementation reuses the old
    # id and fails silently in the worst possible way**: the id carries
    # a unique constraint and a duplicate returns the ORIGINAL stored
    # result with 200 and writes nothing -- so re-apply would report
    # success and change nothing, the exact opposite of what the
    # teacher asked for.
    #
    # The client half of this rule is the Android queue's; what is
    # asserted here is the server behaviour the client half depends
    # on, so the two cannot be proved by the same test.
    first = uuid.uuid4()
    submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=first,
        seats=[SeatMark(enrollment_id=seat, present=True) for seat in eight_seats],
    )

    # The refused attempt: a stale version.
    with pytest.raises(ConflictError):
        submit_roster(
            restricted_session,
            lens=_lens(teacher),
            session_id=owned_session,
            base_version=0,
            client_mutation_id=uuid.uuid4(),
            seats=[SeatMark(enrollment_id=seat, present=False) for seat in eight_seats],
        )

    # Re-apply: the CURRENT version and a FRESH id.
    reapplied = uuid.uuid4()
    result = submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=1,
        client_mutation_id=reapplied,
        seats=[SeatMark(enrollment_id=seat, present=False) for seat in eight_seats],
    )

    assert result.replayed is False, (
        "the re-apply was treated as a replay: reusing the refused "
        "attempt's mutation id reports success and changes nothing "
        "[BR3.7]"
    )
    assert result.attendance_version == 2
    assert _stored_roster(restricted_session, owned_session) == sorted(
        (seat, False) for seat in eight_seats
    )

    # The two submissions differ in BOTH the id and the base version,
    # which is what makes re-apply a new decision rather than a replay.
    rows = restricted_session.execute(
        sa.text(
            "SELECT client_mutation_id, base_version FROM "
            "queued_submission WHERE session_id = :id "
            "ORDER BY resulting_version"
        ),
        {"id": owned_session},
    ).all()
    assert [row[0] for row in rows] == [first, reapplied]
    assert [row[1] for row in rows] == [0, 1]
