"""Replay safety [BR3.8, § 5.2, § 5.3, NFR19.34].

Three properties, and **two of them are load-bearing in the sense that
the natural assertion passes against the defect**:

* ``created_at`` **unmoved**. A row-count assertion passes against an
  implementation that overwrites the original in place -- same row
  count, same version, and the original decision's timestamp
  destroyed. A replay must be observably a replay.
* A **cross-account** replay is a refusal and specifically **not** a
  200 carrying the other account's stored result. The uniqueness is
  scoped per account, so account B presenting account A's id is not a
  duplicate at all; the natural implementation looks up the id, finds
  a row and returns it, and § 5.2 names that as the shape that ships
  as a silent success. Asserting only "not 200" passes against a 500,
  so the negative half is asserted explicitly.

The concurrent half lives in ``test_attendance_races.py``: a sequential
replay test cannot distinguish a database constraint from an
application-level "have I seen this id?" guard.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import QueuedSubmission, Session
from app.errors import AuthorizationError
from app.teaching.submissions import SeatMark, submit_roster
from tests.batches.conftest import TeacherFixture, enroll, make_teacher

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
def seats(
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> list[uuid.UUID]:
    """Three seats on the teacher's batch.

    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :param account_factory: Makes student accounts
    :return: The three enrollment ids
    """
    return [
        enroll(
            owner_session,
            batch_id=teacher.batch_id,
            display_name=f"Student {index}",
            student_account_id=account_factory(),
            student_decision="accepted",
            guardian_decision="pending",
        )
        for index in range(3)
    ]


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the fixture teacher's lens.

    :param teacher: The teacher fixture
    :return: The lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def test_a_replayed_mutation_id_returns_the_original_and_writes_nothing(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    seats: list[uuid.UUID],
) -> None:
    mutation = uuid.uuid4()
    roster = [SeatMark(enrollment_id=seats[0], present=False)]

    first = submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=mutation,
        seats=roster,
    )
    second = submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=mutation,
        seats=roster,
    )

    assert first.attendance_version == 1
    assert second.attendance_version == 1, (
        "the replay incremented the version: a replay must write nothing at all [BR3.8]"
    )
    assert second.replayed is True
    assert first.replayed is False

    submissions = restricted_session.scalars(
        sa.select(QueuedSubmission).where(QueuedSubmission.session_id == owned_session)
    ).all()
    assert len(submissions) == 1


def test_a_replay_leaves_created_at_unmoved(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    seats: list[uuid.UUID],
) -> None:
    # **THE load-bearing assertion** [§ 5.3]. A row-count assertion
    # passes against an implementation that overwrites the original in
    # place: the row count is right, the version is right, and the
    # original decision's timestamp is destroyed.
    mutation = uuid.uuid4()
    roster = [SeatMark(enrollment_id=seats[0], present=True)]

    submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=mutation,
        seats=roster,
    )
    original = restricted_session.scalars(
        sa.select(QueuedSubmission.created_at).where(
            QueuedSubmission.client_mutation_id == mutation
        )
    ).one()

    submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=mutation,
        seats=roster,
    )

    after = restricted_session.scalars(
        sa.select(QueuedSubmission.created_at).where(
            QueuedSubmission.client_mutation_id == mutation
        )
    ).one()
    assert after == original, (
        "the replay moved created_at: the original decision's "
        "timestamp was destroyed, so a replay is no longer observably "
        "a replay [§ 5.3]"
    )


def test_a_replay_returns_the_ORIGINAL_roster_not_the_resubmitted_one(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    seats: list[uuid.UUID],
) -> None:
    # § B.7 says the ORIGINAL stored result. A second body under the
    # same id must change nothing -- an implementation that applied
    # the new body and returned 200 would look identical on a
    # count-only assertion.
    mutation = uuid.uuid4()
    submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=mutation,
        seats=[SeatMark(enrollment_id=seats[0], present=True)],
    )

    submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=mutation,
        seats=[SeatMark(enrollment_id=seats[0], present=False)],
    )

    stored = restricted_session.execute(
        sa.text(
            "SELECT present FROM attendance "
            "WHERE session_id = :s AND enrollment_id = :e"
        ),
        {"s": owned_session, "e": seats[0]},
    ).scalar_one()
    assert stored is True, (
        "the replay APPLIED a different body under the original id: "
        "a replay returns the original stored result and writes "
        "nothing [BR3.8]"
    )


def test_a_cross_account_replay_is_refused_and_is_not_a_success(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    seats: list[uuid.UUID],
) -> None:
    # § 5.2: the constraint is on the PAIR, so B's submission does not
    # collide with A's row -- the lookup must be scoped by the
    # authenticated account. A lookup on client_mutation_id alone
    # finds A's row and returns it, which is the implementation
    # everybody reaches for and ships as a silent success.
    mutation = uuid.uuid4()
    submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=mutation,
        seats=[SeatMark(enrollment_id=seats[0], present=True)],
    )

    other = make_teacher(owner_session, name="Chemistry")

    with pytest.raises(AuthorizationError) as refusal:
        submit_roster(
            restricted_session,
            lens=TeacherLens(account_id=other.account_id, owner_id=other.owner_id),
            session_id=owned_session,
            base_version=0,
            client_mutation_id=mutation,
            seats=[],
        )

    # The NEGATIVE half, asserted explicitly: "not a 200" alone passes
    # against a 500, and the specific thing forbidden is returning A's
    # stored result to B.
    assert refusal.value.code == "NOT_AVAILABLE"
    assert str(seats[0]) not in repr(refusal.value.details)

    # And nothing was written under B's name.
    count = restricted_session.scalars(
        sa.select(sa.func.count())
        .select_from(QueuedSubmission)
        .where(QueuedSubmission.submitted_by_account_id == other.account_id)
    ).one()
    assert count == 0


def test_the_same_mutation_id_from_two_accounts_is_not_a_collision(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    seats: list[uuid.UUID],
    account_factory: Callable[[], uuid.UUID],
) -> None:
    # The other direction of the same scoping rule: two teachers
    # legitimately generating the same UUID on their own sessions must
    # BOTH succeed. A constraint on client_mutation_id alone would
    # refuse the second, which is a correctness failure rather than a
    # security one -- and a suite that only probed the adversarial
    # direction would not notice.
    other = make_teacher(owner_session, name="Chemistry")
    other_session = Session(
        batch_id=other.batch_id,
        date=SESSION_DATE,
        start_time=dt.time(16, 0),
        status="scheduled",
        origin="recurrence",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(other_session)
    owner_session.commit()

    mine = Session(
        batch_id=teacher.batch_id,
        date=SESSION_DATE,
        start_time=dt.time(16, 0),
        status="scheduled",
        origin="recurrence",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(mine)
    owner_session.commit()

    shared = uuid.uuid4()
    first = submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=mine.id,
        base_version=0,
        client_mutation_id=shared,
        seats=[],
    )
    second = submit_roster(
        restricted_session,
        lens=TeacherLens(account_id=other.account_id, owner_id=other.owner_id),
        session_id=other_session.id,
        base_version=0,
        client_mutation_id=shared,
        seats=[],
    )

    assert first.replayed is False
    assert second.replayed is False, (
        "the second account's write was treated as a replay of the "
        "first: the constraint is on the PAIR, not on the id alone"
    )
