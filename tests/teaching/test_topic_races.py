"""The topic version conflict and replay, under real concurrency.

**A topic write guarded by a version check passes every sequential
test against an implementation with NO guard at all**, because nothing
ever contends -- the same argument ``test_attendance_races.py`` makes
for the roster, and it applies here for the same reason: BR2.1 puts
the topic log on the same device queue under the same rules, and the
queue is exactly what produces two stale writes arriving together.

N threads released together from a barrier, against real PostgreSQL
via testcontainers. Two storms:

* **the conflict** -- N topic writes all composed against version V:
  exactly one applies and N-1 are refused, and ``topic_version``
  reaches V+1 and not V+N;
* **the replay** -- N writes under ONE mutation id: one submission
  row for the whole storm, and the version incremented once. Some
  workers are refused rather than replayed, and that is correct:
  with none of them committed yet the replay lookup finds nothing and
  the losers meet the version guard. The device resends and sees the
  replay. What must never happen is a second row or a second
  increment.

Both were proved able to fail; what was broken and what failed is
recorded in the code-generation report rather than guessed at here.
"""

from __future__ import annotations

import datetime as dt
import threading
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from app.authz.lenses import TeacherLens
from app.db.models import Session
from app.errors import ConflictError
from app.teaching.submissions import TOPIC_KIND, TopicResult, write_topic
from tests.batches.conftest import TeacherFixture

#: How many writes contend. Eight matches the roster precedent.
WORKERS = 8

SESSION_DATE = dt.date(2027, 5, 17)


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


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the fixture teacher's lens.

    :param teacher: The teacher fixture
    :return: The lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def test_only_one_of_n_racing_topic_writes_applies(
    restricted_engine: Engine,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    barrier = threading.Barrier(WORKERS)
    lock = threading.Lock()
    applied: list[tuple[int, TopicResult]] = []
    conflicts: list[int] = []
    unexpected: list[BaseException] = []

    def run(index: int) -> None:
        # Each worker writes a DIFFERENT topic, so the winner is
        # identifiable: "some topic is stored" would be satisfied by
        # an interleaved write and this is not.
        session = factory()
        try:
            barrier.wait(timeout=30)
            result = write_topic(
                session,
                lens=_lens(teacher),
                session_id=owned_session,
                base_version=0,
                client_mutation_id=uuid.uuid4(),
                topic=f"Topic {index:02d}",
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
        f"{len(unexpected)} racing topic writes raised something other "
        f"than ConflictError, the first being {unexpected[0]!r}"
    )
    assert len(applied) == 1, (
        f"{len(applied)} of {WORKERS} racing topic writes applied. "
        "Exactly one must apply and N-1 must be refused [BR2.1]."
    )
    assert len(conflicts) == WORKERS - 1

    verify = factory()
    try:
        version = verify.scalars(
            sa.select(Session.topic_version).where(Session.id == owned_session)
        ).one()
        assert version == 1, (
            f"topic_version is {version}, not 1. V+N means every write "
            "applied its increment, which is the unguarded "
            "implementation [BR2.1]."
        )

        # The WINNER's topic, not merely a non-null one.
        stored = verify.scalars(
            sa.select(Session.topic).where(Session.id == owned_session)
        ).one()
        assert stored == f"Topic {applied[0][0]:02d}", (
            "the stored topic is not the one that won: a losing write "
            "applied its body [BR2.1]"
        )

        # The second, INDEPENDENT guarantee: one topic submission row
        # for that version, which UNIQUE (session_id, kind,
        # resulting_version) enforces whatever the update looks like.
        rows = verify.execute(
            sa.text(
                "SELECT count(*) FROM queued_submission "
                "WHERE session_id = :id AND kind = :k"
            ),
            {"id": owned_session, "k": TOPIC_KIND},
        ).scalar_one()
        assert rows == 1
    finally:
        verify.close()


def test_the_same_topic_mutation_id_replayed_concurrently_writes_once(
    restricted_engine: Engine,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    # BR3.8's concurrent half on the second queued path: the case
    # that distinguishes a database constraint from an
    # application-level "have I seen this id?" guard, which passes
    # sequentially and double-writes under two workers.
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    barrier = threading.Barrier(WORKERS)
    mutation = uuid.uuid4()
    lock = threading.Lock()
    versions: list[int] = []
    errors: list[BaseException] = []

    def run() -> None:
        session = factory()
        try:
            barrier.wait(timeout=30)
            result = write_topic(
                session,
                lens=_lens(teacher),
                session_id=owned_session,
                base_version=0,
                client_mutation_id=mutation,
                topic="Refraction",
            )
            with lock:
                versions.append(result.topic_version)
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

    # Collected and then ASSERTED. A list of exceptions gathered and
    # never read is a test that passes while every worker raised
    # something unexpected.
    #
    # A ConflictError here is CORRECT and is not a defect: when N
    # copies of one write arrive together, none has committed its
    # submission row yet, so the replay lookup finds nothing and the
    # losers meet the version guard instead. The teacher's device
    # resends and sees the replay. What must never happen is a second
    # row or a second increment, and that is asserted below.
    assert all(isinstance(error, ConflictError) for error in errors), (
        f"a concurrent replay raised something other than ConflictError: {errors!r}"
    )
    assert len(errors) < WORKERS, "every worker raised; none applied"

    verify = factory()
    try:
        # ONE submission row for the whole storm, whatever each caller
        # observed: the unique constraint on the pair is what makes
        # this true rather than an application guard.
        rows = verify.execute(
            sa.text(
                "SELECT count(*) FROM queued_submission WHERE client_mutation_id = :m"
            ),
            {"m": mutation},
        ).scalar_one()
        assert rows == 1, (
            f"{rows} submission rows for one mutation id under "
            f"{WORKERS} concurrent topic replays [BR3.8]"
        )

        version = verify.scalars(
            sa.select(Session.topic_version).where(Session.id == owned_session)
        ).one()
        assert version == 1, (
            f"topic_version reached {version}: a replay must not "
            "increment it even once more [BR3.8]"
        )

        # Every caller that did not raise saw the SAME version.
        assert set(versions) <= {1}, f"callers observed {sorted(set(versions))}"
    finally:
        verify.close()
