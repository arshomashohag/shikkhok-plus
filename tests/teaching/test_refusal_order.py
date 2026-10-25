"""Authorization precedes the version check [§ 5.4, BR3.10].

**The hazard is concrete and is the reason this file exists.**
``ATTENDANCE_VERSION_CONFLICT`` carries ``current_version`` and
``current_state`` in ``error.details`` -- and ``current_state`` **IS
the roster**. Emitting it before the authorization check would hand a
stranger the class's attendance in an error body.

**Both version cases are run, and that is the point.** A probe using
only a NON-MATCHING version cannot distinguish correct ordering from an
implementation that happens to check authorization first by accident of
control flow: with a mismatched version, an implementation that
compares versions first still reaches the conflict, and one that
authorizes first reaches the refusal -- but with a MATCHING version,
the version-first implementation sails past the comparison and would
APPLY a stranger's roster. Running both is what separates the two.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import Session
from app.errors import AuthorizationError, ConflictError
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


def _stranger(owner_session: DbSession) -> TeacherLens:
    """Build a valid teacher lens for a DIFFERENT teacher.

    A valid lens, deliberately: the probe is about reach, not about
    authentication, and an unauthenticated caller would be refused one
    step earlier and prove nothing about this ordering.

    :param owner_session: A session able to arrange fixture data
    :return: Another teacher's lens
    """
    other = make_teacher(owner_session, name="Chemistry")
    return TeacherLens(account_id=other.account_id, owner_id=other.owner_id)


def test_a_stranger_with_a_matching_version_gets_not_available(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    # THE case that separates the two orderings. The version MATCHES,
    # so an implementation that compares versions first would sail
    # past the comparison entirely and apply a stranger's roster.
    with pytest.raises(AuthorizationError) as refusal:
        submit_roster(
            restricted_session,
            lens=_stranger(owner_session),
            session_id=owned_session,
            base_version=0,
            client_mutation_id=uuid.uuid4(),
            seats=[],
        )

    assert refusal.value.code == "NOT_AVAILABLE"


def test_a_stranger_with_a_stale_version_gets_not_available_too(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    # The non-matching half. Never ATTENDANCE_VERSION_CONFLICT, whose
    # details carry the roster.
    with pytest.raises(AuthorizationError) as refusal:
        submit_roster(
            restricted_session,
            lens=_stranger(owner_session),
            session_id=owned_session,
            base_version=99,
            client_mutation_id=uuid.uuid4(),
            seats=[],
        )

    assert refusal.value.code == "NOT_AVAILABLE"
    assert refusal.value.code != "ATTENDANCE_VERSION_CONFLICT"


def test_the_stranger_refusal_is_byte_identical_to_an_invented_id(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    # **An EQUALITY over the two refusals** [§ 2.3], not two
    # independent "is a refusal" assertions -- both of those pass
    # while the bodies differ, and the difference is the leak.
    lens = _stranger(owner_session)

    with pytest.raises(AuthorizationError) as real_id:
        submit_roster(
            restricted_session,
            lens=lens,
            session_id=owned_session,
            base_version=0,
            client_mutation_id=uuid.uuid4(),
            seats=[],
        )
    with pytest.raises(AuthorizationError) as invented_id:
        submit_roster(
            restricted_session,
            lens=lens,
            session_id=uuid.uuid4(),
            base_version=0,
            client_mutation_id=uuid.uuid4(),
            seats=[],
        )

    assert (
        real_id.value.code,
        real_id.value.message_key,
        real_id.value.status,
        real_id.value.details,
    ) == (
        invented_id.value.code,
        invented_id.value.message_key,
        invented_id.value.status,
        invented_id.value.details,
    )


def test_no_conflict_body_ever_reaches_a_stranger(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    account_factory: object,
) -> None:
    # Arrange a real roster on the session so `current_state` would
    # actually carry something if the ordering were wrong -- a probe
    # against an empty session cannot tell a leak from an absence.
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_decision="pending",
        guardian_decision="pending",
    )
    submit_roster(
        restricted_session,
        lens=TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        seats=[SeatMark(enrollment_id=seat, present=False)],
    )

    with pytest.raises(AuthorizationError) as refusal:
        submit_roster(
            restricted_session,
            lens=_stranger(owner_session),
            session_id=owned_session,
            base_version=0,
            client_mutation_id=uuid.uuid4(),
            seats=[],
        )

    rendered = repr(refusal.value.details)
    assert str(seat) not in rendered, (
        "a stranger's refusal carried an enrollment id from the "
        "roster: current_state IS the roster and must never be "
        "reachable before authorization [§ 5.4]"
    )
    assert "Rahim" not in rendered


def test_the_owner_with_a_stale_version_does_get_the_conflict(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    # The positive half: the descriptive code IS permitted once
    # authorization has passed, and a suite that only asserted
    # refusals would pass against an implementation that never emits
    # it at all.
    with pytest.raises(ConflictError) as conflict:
        submit_roster(
            restricted_session,
            lens=TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id),
            session_id=owned_session,
            base_version=99,
            client_mutation_id=uuid.uuid4(),
            seats=[],
        )

    assert conflict.value.code == "ATTENDANCE_VERSION_CONFLICT"
    assert conflict.value.details is not None
    assert conflict.value.details["current_version"] == "0"
    assert conflict.value.details["expected_version"] == "99"
