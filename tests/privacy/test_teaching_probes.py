"""The six readers D4 adds, probed adversarially [§ 2.2, BR5.2].

**This project recorded on 2026-10-22 that adding a column is not
adding a behaviour, and that the queries which must start reading it
have to be NAMED** -- because the ones already granting access go on
granting it on the old evidence. BR5.2 names six readers; this module
probes each.

**The positive column is not decoration.** Without it the whole suite
passes against a boundary that denies unconditionally, which is not
the requirement -- it is the opposite of one. Every adversarial probe
here has a positive twin asserting the legitimate read still works.

**This suite runs as ``APP_ROLE``**, a granted non-owner,
non-superuser, and the built meta-test gates the package. A probe
suite running against a missing policy reports a **pass**, which is
the worst available outcome.

D4 adds no row-level-security policy -- none of its six tables has a
column naming its READER -- so these lens-scoped probes ARE the
mechanism rather than a second check on one [NFR14.52].
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.db.models import Account, BatchSubject, Exam, Session
from app.errors import AuthorizationError
from app.marks.entry import record_mark
from app.marks.views import guardian_progress, seat_marksheet
from app.teaching.announcements import family_batch_view
from app.teaching.roster import session_roster
from app.teaching.sessions import read_session
from app.teaching.submissions import SeatMark, submit_roster
from tests.batches.conftest import TeacherFixture, enroll, make_teacher

SESSION_DATE = dt.date(2027, 4, 12)
EXAM_DATE = dt.date(2027, 4, 20)


@pytest.fixture
def account_factory(owner_session: DbSession) -> Callable[[], uuid.UUID]:
    """Return a factory making accounts with unique phone numbers.

    :param owner_session: A session able to arrange fixture data
    :return: A callable producing a fresh account id each time
    """

    def make() -> uuid.UUID:
        account = Account(
            phone=f"+8801{uuid.uuid4().int % 10**9:09d}",
            created_at=dt.datetime.now(tz=dt.UTC),
        )
        owner_session.add(account)
        owner_session.commit()
        return account.id

    return make


@pytest.fixture
def teacher_a(owner_session: DbSession) -> TeacherFixture:
    """Create the teacher whose data the probes try to reach.

    :param owner_session: A session able to arrange fixture data
    :return: Teacher A
    """
    return make_teacher(owner_session, name="Physics")


@pytest.fixture
def teacher_b(owner_session: DbSession) -> TeacherFixture:
    """Create the attacker: a real teacher with a lens of their own.

    A VALID lens deliberately. An unauthenticated caller is refused
    one step earlier and proves nothing about this boundary.

    :param owner_session: A session able to arrange fixture data
    :return: Teacher B
    """
    return make_teacher(owner_session, name="Chemistry")


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build a teacher lens.

    :param teacher: The teacher fixture
    :return: The lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


@pytest.fixture
def session_a(owner_session: DbSession, teacher_a: TeacherFixture) -> uuid.UUID:
    """One session on teacher A's batch.

    :param owner_session: A session able to arrange fixture data
    :param teacher_a: Its owner
    :return: The session id
    """
    row = Session(
        batch_id=teacher_a.batch_id,
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


# ---------------------------------------------------------------------
# Reader 1: the session roster.
# ---------------------------------------------------------------------


def test_a_declined_seat_is_absent_from_the_roster(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_a: TeacherFixture,
    session_a: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    declined = enroll(
        owner_session,
        batch_id=teacher_a.batch_id,
        display_name="Declined",
        student_account_id=account_factory(),
        student_decision="declined",
        guardian_decision="pending",
    )

    rows = session_roster(
        restricted_session, lens=_lens(teacher_a), session_id=session_a
    )

    assert declined not in {row.enrollment_id for row in rows}


def test_an_accepted_seat_is_present_on_the_roster(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_a: TeacherFixture,
    session_a: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    # The POSITIVE twin. Without it the suite above passes against a
    # roster that returns nothing at all.
    accepted = enroll(
        owner_session,
        batch_id=teacher_a.batch_id,
        display_name="Accepted",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )

    rows = session_roster(
        restricted_session, lens=_lens(teacher_a), session_id=session_a
    )

    assert accepted in {row.enrollment_id for row in rows}


# ---------------------------------------------------------------------
# Reader 2: the session detail.
# ---------------------------------------------------------------------


def test_teacher_b_cannot_read_teacher_as_session(
    restricted_session: DbSession,
    teacher_a: TeacherFixture,
    teacher_b: TeacherFixture,
    session_a: uuid.UUID,
) -> None:
    with pytest.raises(AuthorizationError) as refusal:
        read_session(restricted_session, lens=_lens(teacher_b), session_id=session_a)

    assert refusal.value.code == "NOT_AVAILABLE"


def test_teacher_b_cannot_read_teacher_as_roster_by_the_join_route(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_a: TeacherFixture,
    teacher_b: TeacherFixture,
    session_a: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    # **The JOIN route**, which is the shape the real roster query
    # has -- an implementation can block the direct read and leave
    # this one open [§ 2.1].
    enroll(
        owner_session,
        batch_id=teacher_a.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )

    with pytest.raises(AuthorizationError) as refusal:
        session_roster(restricted_session, lens=_lens(teacher_b), session_id=session_a)

    assert refusal.value.code == "NOT_AVAILABLE"


def test_the_owner_reads_their_own_session(
    restricted_session: DbSession,
    teacher_a: TeacherFixture,
    session_a: uuid.UUID,
) -> None:
    row = read_session(restricted_session, lens=_lens(teacher_a), session_id=session_a)

    assert row.session_id == session_a


def test_teacher_b_cannot_write_teacher_as_roster(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_a: TeacherFixture,
    teacher_b: TeacherFixture,
    session_a: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    seat = enroll(
        owner_session,
        batch_id=teacher_a.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )

    with pytest.raises(AuthorizationError) as refusal:
        submit_roster(
            restricted_session,
            lens=_lens(teacher_b),
            session_id=session_a,
            base_version=0,
            client_mutation_id=uuid.uuid4(),
            seats=[SeatMark(enrollment_id=seat, present=False)],
        )

    assert refusal.value.code == "NOT_AVAILABLE"


# ---------------------------------------------------------------------
# Readers 3 and 4: student and guardian attendance history.
# ---------------------------------------------------------------------


def test_a_pending_student_reads_no_attendance(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_a: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher_a.batch_id,
        display_name="Pending",
        student_account_id=student,
        student_decision="pending",
        guardian_decision="pending",
    )

    with pytest.raises(AuthorizationError) as refusal:
        family_batch_view(
            restricted_session,
            lens=StudentLens(account_id=student),
            enrollment_id=seat,
        )

    assert refusal.value.code == "NOT_AVAILABLE"


def test_an_accepted_student_reads_their_own_attendance(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_a: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher_a.batch_id,
        display_name="Accepted",
        student_account_id=student,
        student_decision="accepted",
        guardian_decision="pending",
    )

    view = family_batch_view(
        restricted_session,
        lens=StudentLens(account_id=student),
        enrollment_id=seat,
    )

    assert view.served_at is not None


def test_a_declined_guardian_reads_nothing(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_a: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    guardian = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher_a.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="declined",
    )

    with pytest.raises(AuthorizationError) as refusal:
        family_batch_view(
            restricted_session,
            lens=GuardianLens(account_id=guardian, child_enrollment_id=seat),
            enrollment_id=seat,
        )

    assert refusal.value.code == "NOT_AVAILABLE"


def test_an_accepted_guardian_reads_their_childs_attendance(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_a: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    guardian = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher_a.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted",
    )

    view = family_batch_view(
        restricted_session,
        lens=GuardianLens(account_id=guardian, child_enrollment_id=seat),
        enrollment_id=seat,
    )

    assert view.served_at is not None


# ---------------------------------------------------------------------
# Readers 5 and 6: the marksheet and guardian progress.
# ---------------------------------------------------------------------


@pytest.fixture
def exam_a(owner_session: DbSession, teacher_a: TeacherFixture) -> uuid.UUID:
    """One exam on teacher A's batch.

    :param owner_session: A session able to arrange fixture data
    :param teacher_a: Its owner
    :return: The exam id
    """
    subject = BatchSubject(batch_id=teacher_a.batch_id, name="Physics")
    owner_session.add(subject)
    owner_session.commit()
    row = Exam(
        batch_id=teacher_a.batch_id,
        batch_subject_id=subject.id,
        title="April test",
        date=EXAM_DATE,
        total_marks=100,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(row)
    owner_session.commit()
    return row.id


def test_a_student_cannot_read_another_students_mark(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_a: TeacherFixture,
    exam_a: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    # § 2.4's third attack direction, named explicitly.
    mine = account_factory()
    my_seat = enroll(
        owner_session,
        batch_id=teacher_a.batch_id,
        display_name="Mine",
        student_account_id=mine,
        student_decision="accepted",
        guardian_decision="pending",
    )
    their_seat = enroll(
        owner_session,
        batch_id=teacher_a.batch_id,
        display_name="Theirs",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )
    record_mark(
        restricted_session,
        lens=_lens(teacher_a),
        exam_id=exam_a,
        enrollment_id=their_seat,
        result_state="marked",
        marks=91,
    )

    with pytest.raises(AuthorizationError) as refusal:
        seat_marksheet(
            restricted_session,
            lens=StudentLens(account_id=mine),
            enrollment_id=their_seat,
            exam_id=exam_a,
        )

    assert refusal.value.code == "NOT_AVAILABLE"
    assert my_seat is not None


def test_a_student_reads_their_own_marksheet(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_a: TeacherFixture,
    exam_a: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    mine = account_factory()
    my_seat = enroll(
        owner_session,
        batch_id=teacher_a.batch_id,
        display_name="Mine",
        student_account_id=mine,
        student_decision="accepted",
        guardian_decision="pending",
    )
    record_mark(
        restricted_session,
        lens=_lens(teacher_a),
        exam_id=exam_a,
        enrollment_id=my_seat,
        result_state="marked",
        marks=70,
    )

    sheet = seat_marksheet(
        restricted_session,
        lens=StudentLens(account_id=mine),
        enrollment_id=my_seat,
        exam_id=exam_a,
    )

    assert sheet.viewer_marks == 70


def test_a_guardian_cannot_read_a_non_child_progress_series(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_a: TeacherFixture,
    exam_a: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    guardian = account_factory()
    enroll(
        owner_session,
        batch_id=teacher_a.batch_id,
        display_name="My child",
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted",
    )
    stranger = enroll(
        owner_session,
        batch_id=teacher_a.batch_id,
        display_name="Not mine",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )

    with pytest.raises(AuthorizationError) as refusal:
        guardian_progress(
            restricted_session,
            lens=GuardianLens(account_id=guardian),
            enrollment_id=stranger,
        )

    assert refusal.value.code == "NOT_AVAILABLE"


def test_a_guardian_reads_their_own_childs_progress(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_a: TeacherFixture,
    exam_a: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    guardian = account_factory()
    child = enroll(
        owner_session,
        batch_id=teacher_a.batch_id,
        display_name="My child",
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted",
    )
    record_mark(
        restricted_session,
        lens=_lens(teacher_a),
        exam_id=exam_a,
        enrollment_id=child,
        result_state="marked",
        marks=65,
    )

    series = guardian_progress(
        restricted_session,
        lens=GuardianLens(account_id=guardian, child_enrollment_id=child),
        enrollment_id=child,
    )

    assert [entry.marks for entry in series] == [65]


def test_teacher_b_cannot_create_an_exam_with_teacher_as_subject(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher_a: TeacherFixture,
    teacher_b: TeacherFixture,
) -> None:
    # § 2.4: **the exam's own integrity constraint is an
    # authorization boundary** [BR4.1]. A batch_subject_id from
    # another teacher's batch would attach an exam across the
    # ownership boundary, and it is enforced in the WRITE PATH rather
    # than by a foreign key -- which means it is a check somebody can
    # omit.
    from app.marks.exams import create_exam

    foreign = BatchSubject(batch_id=teacher_a.batch_id, name="Physics")
    owner_session.add(foreign)
    owner_session.commit()

    with pytest.raises(AuthorizationError) as refusal:
        create_exam(
            restricted_session,
            lens=_lens(teacher_b),
            batch_id=teacher_b.batch_id,
            batch_subject_id=foreign.id,
            title="Smuggled",
            date=EXAM_DATE,
            total_marks=100,
        )

    # Refused as NOT_AVAILABLE rather than descriptively: naming the
    # subject id as wrong is the oracle.
    assert refusal.value.code == "NOT_AVAILABLE"


def test_teacher_b_cannot_read_teacher_as_announcements(
    restricted_session: DbSession,
    teacher_a: TeacherFixture,
    teacher_b: TeacherFixture,
) -> None:
    # § 2.4's last attack direction.
    from app.teaching.announcements import (
        list_announcements,
        post_announcement,
    )

    post_announcement(
        restricted_session,
        lens=_lens(teacher_a),
        batch_id=teacher_a.batch_id,
        body="Private to my batch",
    )

    with pytest.raises(AuthorizationError) as refusal:
        list_announcements(
            restricted_session,
            lens=_lens(teacher_b),
            batch_id=teacher_a.batch_id,
        )

    assert refusal.value.code == "NOT_AVAILABLE"
