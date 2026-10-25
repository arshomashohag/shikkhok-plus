"""The roster is one atomic write [BR3.5], and the state refusals.

**A per-student write leaves attendance half-saved after a mid-roster
connection drop, and a retry cannot reconcile that on screen**
[AC3.1.5]. So the assertion is not "the write failed" but "the session
has ZERO attendance rows and an unchanged version" -- not k-1 rows,
which is exactly what a per-seat loop would leave.

The state refusals carry the same second half: **a refusal that has
already written is a refusal in name only** [§ 5.6], so each asserts
that existing rows are untouched rather than merely that an exception
was raised.
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
from app.errors import ConflictError
from app.teaching.submissions import SeatMark, submit_roster
from tests.batches.conftest import TeacherFixture, enroll

SESSION_DATE = dt.date(2027, 4, 12)

#: Twelve seats, so a failure on the k-th leaves a visibly partial
#: roster if the write is not atomic.
SEAT_COUNT = 12

#: The seat the injected failure lands on.
FAILING_SEAT = 7


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
def twelve_seats(
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> list[uuid.UUID]:
    """Twelve seats on the teacher's batch.

    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :param account_factory: Makes student accounts
    :return: The twelve enrollment ids
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
        for index in range(SEAT_COUNT)
    ]


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the fixture teacher's lens.

    :param teacher: The teacher fixture
    :return: The lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def _attendance_count(session: DbSession, session_id: uuid.UUID) -> int:
    """Count a session's attendance rows.

    :param session: The session to read through
    :param session_id: The session
    :return: How many rows exist
    """
    return int(
        session.execute(
            sa.text("SELECT count(*) FROM attendance WHERE session_id = :id"),
            {"id": session_id},
        ).scalar_one()
    )


def test_a_failure_on_the_seventh_seat_leaves_zero_rows(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    twelve_seats: list[uuid.UUID],
) -> None:
    # The failure is injected by naming a seat that does not exist, so
    # the foreign key refuses it mid-roster. That is a real database
    # failure on the k-th entry rather than a patched function, which
    # is what makes the test about the TRANSACTION rather than about
    # a mock.
    roster = [SeatMark(enrollment_id=seat, present=True) for seat in twelve_seats]
    roster[FAILING_SEAT] = SeatMark(enrollment_id=uuid.uuid4(), present=True)

    with pytest.raises(Exception):  # noqa: B017  any failure must be total
        submit_roster(
            restricted_session,
            lens=_lens(teacher),
            session_id=owned_session,
            base_version=0,
            client_mutation_id=uuid.uuid4(),
            seats=roster,
        )
    restricted_session.rollback()

    assert _attendance_count(restricted_session, owned_session) == 0, (
        "a mid-roster failure left attendance half-saved. The roster "
        "is ONE atomic write: not k-1 rows, zero [BR3.5, AC3.1.5]"
    )
    version = restricted_session.scalars(
        sa.select(Session.attendance_version).where(Session.id == owned_session)
    ).one()
    assert version == 0, "the version moved for a write that did not apply"


def test_a_successful_roster_writes_every_seat_and_bumps_once(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    twelve_seats: list[uuid.UUID],
) -> None:
    result = submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        seats=[
            SeatMark(enrollment_id=seat, present=index % 3 != 0)
            for index, seat in enumerate(twelve_seats)
        ],
    )

    assert result.attendance_version == 1
    assert _attendance_count(restricted_session, owned_session) == SEAT_COUNT


def test_a_resubmission_replaces_rather_than_appends(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    twelve_seats: list[uuid.UUID],
) -> None:
    # BR3.5: one row per seat per session. A correction rewrites the
    # roster; an appending implementation would double every row and
    # the unique constraint is what makes that impossible.
    submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        seats=[SeatMark(enrollment_id=seat, present=True) for seat in twelve_seats],
    )
    submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=1,
        client_mutation_id=uuid.uuid4(),
        seats=[SeatMark(enrollment_id=seat, present=False) for seat in twelve_seats],
    )

    assert _attendance_count(restricted_session, owned_session) == SEAT_COUNT
    marks = (
        restricted_session.execute(
            sa.text("SELECT DISTINCT present FROM attendance WHERE session_id = :id"),
            {"id": owned_session},
        )
        .scalars()
        .all()
    )
    assert set(marks) == {False}


def test_a_cancelled_session_refuses_and_touches_nothing(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    twelve_seats: list[uuid.UUID],
) -> None:
    # BR1.6, with the second half that matters: assert the existing
    # rows are UNTOUCHED. A refusal that has already written is a
    # refusal in name only [§ 5.6].
    submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        seats=[SeatMark(enrollment_id=seat, present=True) for seat in twelve_seats],
    )
    owner_session.execute(
        sa.text("UPDATE session SET status = 'cancelled' WHERE id = :id"),
        {"id": owned_session},
    )
    owner_session.commit()

    with pytest.raises(ConflictError) as refusal:
        submit_roster(
            restricted_session,
            lens=_lens(teacher),
            session_id=owned_session,
            base_version=1,
            client_mutation_id=uuid.uuid4(),
            seats=[
                SeatMark(enrollment_id=seat, present=False) for seat in twelve_seats
            ],
        )

    assert refusal.value.code == "SESSION_CANCELLED"
    assert _attendance_count(restricted_session, owned_session) == SEAT_COUNT
    marks = (
        restricted_session.execute(
            sa.text("SELECT DISTINCT present FROM attendance WHERE session_id = :id"),
            {"id": owned_session},
        )
        .scalars()
        .all()
    )
    assert set(marks) == {True}, "the refused write changed the roster"


def test_an_inactive_batch_refuses_and_touches_nothing(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
    twelve_seats: list[uuid.UUID],
) -> None:
    # BR5.5. An inactive batch collapses to read-only history: writes
    # refuse and reads keep working.
    submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=owned_session,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        seats=[SeatMark(enrollment_id=seat, present=True) for seat in twelve_seats],
    )
    owner_session.execute(
        sa.text("UPDATE batch SET active = false WHERE id = :id"),
        {"id": teacher.batch_id},
    )
    owner_session.commit()

    with pytest.raises(ConflictError) as refusal:
        submit_roster(
            restricted_session,
            lens=_lens(teacher),
            session_id=owned_session,
            base_version=1,
            client_mutation_id=uuid.uuid4(),
            seats=[],
        )

    assert refusal.value.code == "BATCH_INACTIVE"
    assert _attendance_count(restricted_session, owned_session) == SEAT_COUNT

    # The read still works: read-only history, not disappearance.
    from app.teaching.roster import session_roster

    rows = session_roster(
        restricted_session, lens=_lens(teacher), session_id=owned_session
    )
    assert len(rows) == SEAT_COUNT


def test_a_seat_outside_the_roster_predicate_is_refused(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    owned_session: uuid.UUID,
) -> None:
    # The write must accept exactly the seats the READ shows [BR1.5].
    # A write that accepted a declined seat would record attendance
    # against a student who is not in the class, and the correction
    # history would then faithfully record it.
    declined = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Declined",
        student_decision="declined",
        guardian_decision="pending",
    )

    with pytest.raises(ConflictError) as refusal:
        submit_roster(
            restricted_session,
            lens=_lens(teacher),
            session_id=owned_session,
            base_version=0,
            client_mutation_id=uuid.uuid4(),
            seats=[SeatMark(enrollment_id=declined, present=True)],
        )

    assert refusal.value.code == "SEAT_NOT_ON_ROSTER"
    assert _attendance_count(restricted_session, owned_session) == 0
