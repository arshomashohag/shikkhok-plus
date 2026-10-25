"""Replay safety on the SECOND queued path [BR2.1, BR3.8, § B.7].

**This file exists because the topic log shipped without it.** The
request body declared ``client_mutation_id``, the route handler bound
the body and never forwarded the field, and ``write_topic`` had no
parameter for it -- so a queued topic write resent after a flaky send
re-executed, on exactly the path the device queue was built for. The
docstring on the handler asserted the opposite of what its own call
did.

**Nothing in the 1202-test suite failed.** The contract test asserts
that exactly two request bodies *declare* the field, which is a
wire-level property and passes with one path implemented; and every
topic test generated a fresh mutation id per call, so dropping the
field entirely changed no outcome. Declaration is not implementation,
and this file asserts the implementation.

The properties mirror ``test_replay.py``'s, because the rule is the
same rule:

* the replay returns the ORIGINAL stored result and writes nothing --
  including ``created_at`` **unmoved**, which is the load-bearing half:
  a row-count assertion passes against an implementation that
  overwrites the original in place;
* a **cross-account** replay is refused and specifically is not a 200
  carrying the other account's result;
* the two kinds **do not collide** on the version constraint, which is
  the regression the ``kind`` column exists to prevent.

The concurrent half is in ``test_topic_races.py``: a sequential test
cannot distinguish a database constraint from an application-level
"have I seen this id?" guard.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import QueuedSubmission, Session
from app.errors import AuthorizationError, ConflictError
from app.teaching.submissions import (
    ATTENDANCE_KIND,
    TOPIC_KIND,
    SeatMark,
    submit_roster,
    write_topic,
)
from tests.batches.conftest import TeacherFixture, make_teacher

SESSION_DATE = dt.date(2027, 5, 10)


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


def test_a_replayed_topic_write_returns_the_original_and_writes_nothing(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    mutation = uuid.uuid4()

    first = write_topic(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=mutation,
        topic="Refraction",
    )
    second = write_topic(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=mutation,
        topic="Refraction",
    )

    assert first.replayed is False
    assert second.replayed is True, (
        "the resent topic write was applied again rather than replayed: "
        "a queued write resent after a flaky send must return the "
        "original stored result [BR2.1, BR3.8]"
    )
    assert first.topic_version == 1
    assert second.topic_version == 1, (
        "the replay incremented topic_version: the next legitimate "
        "write is now refused as stale for a change the teacher "
        "already made"
    )
    assert second.submission_id == first.submission_id

    rows = restricted_session.scalars(
        sa.select(QueuedSubmission).where(
            QueuedSubmission.session_id == owned_session,
            QueuedSubmission.kind == TOPIC_KIND,
        )
    ).all()
    assert len(rows) == 1


def test_a_replayed_topic_write_leaves_created_at_unmoved(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    # **THE load-bearing assertion** [§ 5.3]. A row-count check passes
    # against an implementation that overwrites the original in place:
    # one row, the right version, and the original decision's
    # timestamp destroyed.
    mutation = uuid.uuid4()

    write_topic(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=mutation,
        topic="Refraction",
    )
    original = restricted_session.scalars(
        sa.select(QueuedSubmission.created_at).where(
            QueuedSubmission.client_mutation_id == mutation
        )
    ).one()

    write_topic(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=mutation,
        topic="Refraction",
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


def test_a_replayed_topic_write_does_not_apply_a_different_body(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    # § B.7 says the ORIGINAL stored result. A second body under the
    # same id must change nothing -- an implementation that applied
    # the new body and returned the same version would look identical
    # on a count-only assertion.
    mutation = uuid.uuid4()
    write_topic(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=mutation,
        topic="Refraction",
    )
    write_topic(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=mutation,
        topic="Reflection",
    )

    stored = restricted_session.scalars(
        sa.select(Session.topic).where(Session.id == owned_session)
    ).one()
    assert stored == "Refraction", (
        "the replay APPLIED a different body under the original id: a "
        "replay returns the original stored result and writes nothing "
        "[BR3.8]"
    )


def test_a_cross_account_topic_replay_is_refused_and_is_not_a_success(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    # § 5.2: the uniqueness is on the PAIR, so B's write does not
    # collide with A's row -- the lookup must be scoped by the
    # authenticated account. A lookup on client_mutation_id alone
    # finds A's row and returns A's version, which is the
    # implementation everybody reaches for and ships as a silent
    # success. Authorization refuses it first [§ 5.4].
    mutation = uuid.uuid4()
    write_topic(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=mutation,
        topic="Refraction",
    )

    other = make_teacher(owner_session, name="Chemistry")

    with pytest.raises(AuthorizationError) as refusal:
        write_topic(
            restricted_session,
            lens=TeacherLens(account_id=other.account_id, owner_id=other.owner_id),
            session_id=owned_session,
            base_version=0,
            client_mutation_id=mutation,
            topic="Anything",
        )

    # The NEGATIVE half, asserted explicitly: "not a success" alone
    # passes against a 500, and the specific thing forbidden is
    # handing B the result stored under A's name.
    assert refusal.value.code == "NOT_AVAILABLE"
    assert "Refraction" not in repr(refusal.value.details)

    # And nothing was written under B's name.
    count = restricted_session.scalars(
        sa.select(sa.func.count())
        .select_from(QueuedSubmission)
        .where(QueuedSubmission.submitted_by_account_id == other.account_id)
    ).one()
    assert count == 0


def test_a_roster_and_a_topic_write_reaching_version_one_both_succeed(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    seat: uuid.UUID,
) -> None:
    # **The `kind` column's own regression.** Both writes produce
    # resulting_version 1 on the same session. Under the original
    # UNIQUE (session_id, resulting_version) the second would be
    # refused by a constraint describing nothing the teacher did --
    # which is why reusing the table unchanged for both paths, as the
    # upstream design proposed, could not work.
    roster = submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        seats=[SeatMark(enrollment_id=seat, present=True)],
    )
    topic = write_topic(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        topic="Refraction",
    )

    assert roster.attendance_version == 1
    assert topic.topic_version == 1

    kinds = set(
        restricted_session.scalars(
            sa.select(QueuedSubmission.kind).where(
                QueuedSubmission.session_id == owned_session,
                QueuedSubmission.resulting_version == 1,
            )
        ).all()
    )
    assert kinds == {ATTENDANCE_KIND, TOPIC_KIND}, (
        f"both writes reached version 1 and the stored kinds are "
        f"{sorted(kinds)}: the version constraint must be scoped by "
        "kind or the two counters refuse each other [BR2.1]"
    )


def test_one_mutation_id_cannot_be_spent_on_both_queued_paths(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    seat: uuid.UUID,
) -> None:
    # The other side of the scoping decision. `kind` is deliberately
    # NOT in the replay constraint: one account's mutation id is one
    # client decision whatever endpoint it reaches. Presenting it on
    # the other path is refused rather than silently returning the
    # stored row's version, which would be a version from the wrong
    # counter.
    mutation = uuid.uuid4()
    submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=mutation,
        seats=[SeatMark(enrollment_id=seat, present=True)],
    )

    with pytest.raises(ConflictError) as refusal:
        write_topic(
            restricted_session,
            lens=_lens(teacher),
            session_id=owned_session,
            base_version=0,
            client_mutation_id=mutation,
            topic="Refraction",
        )

    assert refusal.value.code == "MUTATION_ID_ALREADY_USED"
    # And the topic was not written: the refusal happened before the
    # guarded update, not after it.
    stored = restricted_session.scalars(
        sa.select(Session.topic_version).where(Session.id == owned_session)
    ).one()
    assert stored == 0
