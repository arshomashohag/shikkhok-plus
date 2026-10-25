"""Reschedule, cancel, ad-hoc and the topic log.

**BR1.7's whole content is that a reschedule preserves identity.**
Implemented as delete-and-recreate it silently discards the topic and
attendance already recorded against the class, so the assertion is that
the session id is unchanged and both survive -- not merely that the
date moved.

**BR2.2's distinction is asserted as a round trip**: a session never
written and one written as an empty string must produce different
``topic_logged`` values. Collapsing the two makes it impossible to tell
a class nobody logged from one logged as nothing.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import Session
from app.errors import AuthorizationError, ConflictError
from app.teaching.sessions import (
    cancel_session,
    create_ad_hoc_session,
    list_sessions,
    read_session,
    reschedule_session,
    write_session_subject,
)
from app.teaching.submissions import SeatMark, submit_roster, write_topic
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.teaching.conftest import add_subject

SESSION_DATE = dt.date(2027, 4, 12)
NEW_DATE = dt.date(2027, 4, 14)


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


def test_a_reschedule_preserves_identity_topic_and_attendance(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )
    write_topic(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        topic="Newton's laws",
    )
    submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        seats=[SeatMark(enrollment_id=seat, present=True)],
    )

    moved = reschedule_session(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        date=NEW_DATE,
        start_time=dt.time(18, 0),
    )

    assert moved.session_id == owned_session, (
        "the reschedule created a new row: the identity, the topic "
        "and the attendance would all be lost [BR1.7]"
    )
    assert moved.date == NEW_DATE
    assert moved.topic == "Newton's laws"
    rows = restricted_session.execute(
        sa.text("SELECT count(*) FROM attendance WHERE session_id = :id"),
        {"id": owned_session},
    ).scalar_one()
    assert rows == 1


def test_a_reschedule_onto_an_occupied_slot_conflicts(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    other = Session(
        batch_id=teacher.batch_id,
        date=NEW_DATE,
        start_time=dt.time(18, 0),
        status="scheduled",
        origin="recurrence",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(other)
    owner_session.commit()

    with pytest.raises(ConflictError) as refusal:
        reschedule_session(
            restricted_session,
            lens=_lens(teacher),
            session_id=owned_session,
            date=NEW_DATE,
            start_time=dt.time(18, 0),
        )

    assert refusal.value.code == "SESSION_ALREADY_EXISTS"


def test_an_ad_hoc_session_is_stored_with_its_origin(
    restricted_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    created = create_ad_hoc_session(
        restricted_session,
        lens=_lens(teacher),
        batch_id=teacher.batch_id,
        date=dt.date(2027, 4, 17),
        start_time=dt.time(10, 0),
    )

    assert created.origin == "ad_hoc"
    assert created.status == "scheduled"


def test_an_ad_hoc_session_with_another_batchs_subject_is_refused(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    # The refusal is NOT_AVAILABLE rather than a descriptive one,
    # because the subject id is an unreachable resource and naming it
    # as wrong is the oracle [BR4.1's reasoning, § 2.4].
    other = make_teacher(owner_session, name="Chemistry")
    foreign = add_subject(owner_session, batch_id=other.batch_id)

    with pytest.raises(AuthorizationError) as refusal:
        create_ad_hoc_session(
            restricted_session,
            lens=_lens(teacher),
            batch_id=teacher.batch_id,
            date=dt.date(2027, 4, 17),
            start_time=dt.time(10, 0),
            batch_subject_id=foreign,
        )

    assert refusal.value.code == "NOT_AVAILABLE"


def test_a_cancelled_session_is_still_readable(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    # `cancelled` is terminal for WRITES and not for reads: the row
    # and its history remain readable.
    cancel_session(restricted_session, lens=_lens(teacher), session_id=owned_session)

    row = read_session(
        restricted_session, lens=_lens(teacher), session_id=owned_session
    )
    assert row.status == "cancelled"


def test_an_unwritten_topic_differs_from_one_written_empty(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    # BR2.2, as a round trip. A reader that collapsed NULL and '' would
    # tell the teacher a class was logged as blank when nobody logged
    # it, which is the whole content of AC3.4.2.
    blank = Session(
        batch_id=teacher.batch_id,
        date=dt.date(2027, 4, 19),
        start_time=dt.time(16, 0),
        status="scheduled",
        origin="recurrence",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(blank)
    owner_session.commit()

    write_topic(
        restricted_session,
        lens=_lens(teacher),
        session_id=blank.id,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        topic="",
    )

    never_written = read_session(
        restricted_session, lens=_lens(teacher), session_id=owned_session
    )
    written_empty = read_session(
        restricted_session, lens=_lens(teacher), session_id=blank.id
    )

    assert never_written.topic_logged is False
    assert never_written.topic is None
    assert written_empty.topic_logged is True
    assert written_empty.topic == ""


def test_a_stale_topic_version_conflicts_without_disclosing_a_roster(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    write_topic(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        topic="First",
    )

    with pytest.raises(ConflictError) as refusal:
        write_topic(
            restricted_session,
            lens=_lens(teacher),
            session_id=owned_session,
            base_version=0,
            client_mutation_id=uuid.uuid4(),
            topic="Second",
        )

    assert refusal.value.code == "TOPIC_VERSION_CONFLICT"
    assert refusal.value.details is not None
    # The topic path carries NO current_state: a topic is one
    # teacher-authored string, not a roster.
    assert "current_state" not in refusal.value.details


def test_the_topic_and_attendance_versions_do_not_interfere(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    # The reason the two counters are separate [BR2.1]: one shared
    # counter would refuse a topic log because a roster arrived, which
    # is a conflict the teacher cannot act on.
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )
    submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        seats=[SeatMark(enrollment_id=seat, present=True)],
    )

    # The topic write still composes against version 0 and must apply.
    result = write_topic(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        topic="Newton's laws",
    )

    assert result.topic_version == 1


def test_a_past_session_nobody_recorded_stays_scheduled(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    # NFR19.45. `held` is reached by RECORDING, never by the clock
    # passing -- a clock-driven transition would quietly bury the
    # classes most needing attention.
    row = read_session(
        restricted_session, lens=_lens(teacher), session_id=owned_session
    )

    assert row.status == "scheduled"


def test_recording_a_roster_moves_the_session_to_held(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )

    submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        seats=[SeatMark(enrollment_id=seat, present=True)],
    )

    row = read_session(
        restricted_session, lens=_lens(teacher), session_id=owned_session
    )
    assert row.status == "held"


def test_another_teacher_cannot_list_this_batchs_sessions(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    other = make_teacher(owner_session, name="Chemistry")

    with pytest.raises(AuthorizationError) as refusal:
        list_sessions(
            restricted_session,
            lens=TeacherLens(account_id=other.account_id, owner_id=other.owner_id),
            batch_id=teacher.batch_id,
        )

    assert refusal.value.code == "NOT_AVAILABLE"


def test_a_session_subject_must_belong_to_its_own_batch(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    other = make_teacher(owner_session, name="Chemistry")
    foreign = add_subject(owner_session, batch_id=other.batch_id)

    with pytest.raises(AuthorizationError):
        write_session_subject(
            restricted_session,
            lens=_lens(teacher),
            session_id=owned_session,
            batch_subject_id=foreign,
        )

    own = add_subject(owner_session, batch_id=teacher.batch_id)
    updated = write_session_subject(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        batch_subject_id=own,
    )
    assert updated.subject_name == "Physics"
