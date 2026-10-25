"""BR1.5's roster predicate, one test per clause.

A session's roster is the batch's enrollments that were **active on
that session's date** and whose **student link is not declined**.

The violation behaviour is concrete and is what each test here asserts
the negation of: a student who left in March appears on an April roster
and is marked absent every week, which then shows on a record nobody
can explain; or a seat someone declined -- the mistyped-digit case --
keeps appearing to be marked.

**One roster read, one expected membership set.** Four enrollments
differing only in ``inactive_from``, ``student_decision`` and
``joined_on`` is the arrangement BR1.5 itself names, and a per-clause
test is what distinguishes a predicate with all four clauses from one
with three.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import Session
from app.errors import AuthorizationError
from app.teaching.roster import session_roster
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.fees.conftest import set_inactive_from, set_joined_on

SESSION_DATE = dt.date(2027, 4, 12)


@pytest.fixture
def held_session(owner_session: DbSession, teacher: TeacherFixture) -> uuid.UUID:
    """One session on 2027-04-12 for the teacher's batch.

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
    """Build the teacher lens for this batch's owner.

    :param teacher: The teacher fixture
    :return: The lens carrying the owner id
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def test_the_four_clauses_select_exactly_the_expected_membership(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    held_session: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    # Four seats differing ONLY in the three columns the predicate
    # reads, which is BR1.5's own named arrangement.
    present = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Stays",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )
    left_in_march = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Left in March",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )
    set_inactive_from(
        owner_session, enrollment_id=left_in_march, when=dt.date(2027, 3, 31)
    )
    declined = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Declined",
        student_account_id=account_factory(),
        student_decision="declined",
        guardian_decision="pending",
    )
    joins_in_may = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Joins in May",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )
    set_joined_on(owner_session, enrollment_id=joins_in_may, when=dt.date(2027, 5, 1))

    rows = session_roster(
        restricted_session, lens=_lens(teacher), session_id=held_session
    )

    assert {row.enrollment_id for row in rows} == {present}, (
        "the roster must hold the one seat that was active, not "
        "declined and already joined on the session's date"
    )
    assert declined not in {row.enrollment_id for row in rows}
    assert left_in_march not in {row.enrollment_id for row in rows}
    assert joins_in_may not in {row.enrollment_id for row in rows}


def test_a_seat_inactive_from_after_the_session_date_is_on_the_roster(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    held_session: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    # The boundary the clause turns on: `inactive_from > D` means a
    # seat leaving LATER is still on this session's roster. A predicate
    # written with `>=` or with a bare NOT NULL check fails here.
    leaving_later = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Leaves in May",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )
    set_inactive_from(
        owner_session, enrollment_id=leaving_later, when=dt.date(2027, 5, 1)
    )

    rows = session_roster(
        restricted_session, lens=_lens(teacher), session_id=held_session
    )

    assert {row.enrollment_id for row in rows} == {leaving_later}


def test_a_pending_seat_is_on_the_roster(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    held_session: uuid.UUID,
) -> None:
    # The clause is `student_decision <> 'declined'`, NOT
    # `= 'accepted'`. Pending is the normal state of a new seat: a
    # teacher who adds twenty students on Monday must be able to mark
    # their attendance without each of them installing the app first.
    pending = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Not signed up yet",
        student_decision="pending",
        guardian_decision="pending",
    )

    rows = session_roster(
        restricted_session, lens=_lens(teacher), session_id=held_session
    )

    assert {row.enrollment_id for row in rows} == {pending}


def test_a_seat_with_no_joined_on_is_on_the_roster(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    held_session: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    # `joined_on IS NULL OR joined_on <= D`. A predicate written as a
    # bare comparison drops every seat whose joining date the teacher
    # never recorded, which is most of them.
    unrecorded = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="No joining date",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )

    rows = session_roster(
        restricted_session, lens=_lens(teacher), session_id=held_session
    )

    assert {row.enrollment_id for row in rows} == {unrecorded}


def test_another_teachers_session_is_refused(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    held_session: uuid.UUID,
) -> None:
    # BR5.2's first reader, adversarially. Teacher B holds a valid
    # teacher lens and must not reach teacher A's session.
    other = make_teacher(owner_session, name="Chemistry")

    with pytest.raises(AuthorizationError) as refusal:
        session_roster(
            restricted_session,
            lens=TeacherLens(account_id=other.account_id, owner_id=other.owner_id),
            session_id=held_session,
        )

    assert refusal.value.code == "NOT_AVAILABLE"


def test_an_invented_session_id_is_refused_identically(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    held_session: uuid.UUID,
) -> None:
    # The oracle rule: "does not exist" and "not yours" carry ONE code,
    # so a prober cannot read the difference and enumerate real ids.
    with pytest.raises(AuthorizationError) as refusal:
        session_roster(restricted_session, lens=_lens(teacher), session_id=uuid.uuid4())

    assert refusal.value.code == "NOT_AVAILABLE"


def test_the_roster_carries_no_account_id(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    held_session: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    # BR5.3 at the domain layer: a roster is literally a list of
    # people and is the most natural place in the product to leak a
    # global account key to a teacher. It exposes an ENROLLMENT id.
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )

    rows = session_roster(
        restricted_session, lens=_lens(teacher), session_id=held_session
    )

    fields = set(vars(rows[0]) if hasattr(rows[0], "__dict__") else {})
    fields |= set(getattr(type(rows[0]), "__slots__", ()))
    assert "student_account_id" not in fields
    assert "account_id" not in fields
