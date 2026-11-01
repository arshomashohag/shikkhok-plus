"""The month calendar for teachers and families.

Written before the module existed. The family half is an authorization
surface: a child sees only their own seat's marks, nothing before the
seat began or after it ended, and nothing a teacher keeps private.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.db.models import Attendance, Batch, Enrollment, QueuedSubmission, Session
from app.errors import AuthorizationError, ValidationError
from app.local_time import DHAKA, bangladesh_today
from app.teaching.calendar import family_month, teacher_month
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.conftest import bearer
from tests.teaching.conftest import add_subject

NOW = dt.datetime(2027, 5, 10, 12, 0, tzinfo=DHAKA)
TODAY = NOW.date()


def _class(
    session: DbSession,
    batch_id: uuid.UUID,
    day: dt.date,
    start: dt.time = dt.time(16, 0),
    status: str = "scheduled",
    subject: uuid.UUID | None = None,
) -> uuid.UUID:
    """Add one class.

    :param session: An arranging session
    :param batch_id: The batch
    :param day: Its date
    :param start: Its start
    :param status: Its status
    :param subject: Its subject, if any
    :return: The session id
    """
    row = Session(
        batch_id=batch_id,
        batch_subject_id=subject,
        date=day,
        start_time=start,
        end_time=dt.time(start.hour + 1, 0),
        status=status,
        origin="recurrence",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(row)
    session.commit()
    return row.id


def _backdate(session: DbSession, batch_id: uuid.UUID) -> None:
    """Make the batch old enough to browse a spring month.

    :param session: An arranging session
    :param batch_id: The batch
    :return: None
    """
    batch = session.get_one(Batch, batch_id)
    batch.created_at = dt.datetime(2027, 1, 5, tzinfo=dt.UTC)
    session.commit()


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the fixture teacher's lens.

    :param teacher: The teacher
    :return: The lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def _teacher_month(session: DbSession, teacher: TeacherFixture, month: int = 5):
    """Read the teacher's month at the fixed clock.

    :param session: The session to read through
    :param teacher: The teacher
    :param month: The month, in 2027
    :return: The view
    """
    return teacher_month(
        session,
        lens=_lens(teacher),
        batch_id=teacher.batch_id,
        year=2027,
        month=month,
        now=NOW,
    )


def _by_day(view) -> dict[int, object]:
    """Index a view's days by day of month.

    :param view: The month view
    :return: Day number to day
    """
    return {day.date.day: day for day in view.days}


def test_class_states_follow_status_and_today(
    restricted_session, owner_session, teacher
) -> None:
    """Cancelled, taken, today, upcoming, not recorded.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :return: None
    """
    _backdate(owner_session, teacher.batch_id)
    batch = teacher.batch_id
    _class(owner_session, batch, dt.date(2027, 5, 3), status="held")
    _class(owner_session, batch, dt.date(2027, 5, 4), status="cancelled")
    _class(owner_session, batch, dt.date(2027, 5, 5))
    _class(owner_session, batch, TODAY, status="held")
    _class(owner_session, batch, dt.date(2027, 5, 12))

    days = _by_day(_teacher_month(restricted_session, teacher))

    assert days[3].state == "taken"
    assert days[4].state == "cancelled"
    assert days[5].state == "not_recorded"
    assert days[10].state == "taken"
    assert days[12].state == "upcoming"


def test_a_scheduled_class_today_is_today(
    restricted_session, owner_session, teacher
) -> None:
    """Scheduled and dated today is ``today``.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :return: None
    """
    _backdate(owner_session, teacher.batch_id)
    _class(owner_session, teacher.batch_id, TODAY)

    days = _by_day(_teacher_month(restricted_session, teacher))

    assert days[10].state == "today"
    assert days[10].classes[0].state == "today"


def test_day_state_uses_precedence(restricted_session, owner_session, teacher) -> None:
    """A taken class and an upcoming class on one day: the day is upcoming.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :return: None
    """
    _backdate(owner_session, teacher.batch_id)
    day = dt.date(2027, 5, 20)
    _class(owner_session, teacher.batch_id, day, dt.time(9, 0), status="held")
    _class(owner_session, teacher.batch_id, day, dt.time(16, 0))

    days = _by_day(_teacher_month(restricted_session, teacher))

    assert [c.state for c in days[20].classes] == ["taken", "upcoming"]
    assert days[20].state == "upcoming"


def test_only_days_with_classes_are_listed(
    restricted_session, owner_session, teacher
) -> None:
    """Empty days are absent.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :return: None
    """
    _backdate(owner_session, teacher.batch_id)
    _class(owner_session, teacher.batch_id, dt.date(2027, 5, 20))
    _class(owner_session, teacher.batch_id, dt.date(2027, 6, 1))

    view = _teacher_month(restricted_session, teacher)

    assert [d.date.day for d in view.days] == [20]
    assert (view.first_month, view.last_month) == ("2027-01", "2027-06")


def test_plannable_and_recordable_flip_at_start(
    restricted_session, owner_session, teacher
) -> None:
    """Before the start a class is plannable; from the start, recordable.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :return: None
    """
    _backdate(owner_session, teacher.batch_id)
    _class(owner_session, teacher.batch_id, TODAY, dt.time(16, 0))
    before = NOW.replace(hour=15, minute=59)
    at = NOW.replace(hour=16, minute=0)

    def read(now: dt.datetime):
        """Read the one class at a clock.

        :param now: The clock
        :return: The class
        """
        view = teacher_month(
            restricted_session,
            lens=_lens(teacher),
            batch_id=teacher.batch_id,
            year=2027,
            month=5,
            now=now,
        )
        return view.days[0].classes[0]

    early, late = read(before), read(at)
    assert (early.plannable, early.recordable) == (True, False)
    assert (late.plannable, late.recordable) == (False, True)
    assert early.mark is None


def test_cancelled_held_and_closed_batch_flags(
    restricted_session, owner_session, teacher
) -> None:
    """Cancelled and held are not plannable; a closed batch allows neither.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :return: None
    """
    _backdate(owner_session, teacher.batch_id)
    future = dt.date(2027, 5, 25)
    _class(owner_session, teacher.batch_id, future, dt.time(8, 0), "cancelled")
    _class(owner_session, teacher.batch_id, future, dt.time(9, 0), "held")
    _class(owner_session, teacher.batch_id, future, dt.time(10, 0))

    flags = [
        (c.plannable, c.recordable)
        for c in _by_day(_teacher_month(restricted_session, teacher))[25].classes
    ]
    assert flags == [(False, False), (False, False), (True, False)]

    batch = owner_session.get_one(Batch, teacher.batch_id)
    batch.active = False
    owner_session.commit()
    closed = _by_day(_teacher_month(restricted_session, teacher))[25].classes
    assert [(c.plannable, c.recordable) for c in closed] == [(False, False)] * 3


def test_subject_topic_and_notes_are_carried(
    restricted_session, owner_session, teacher
) -> None:
    """The subject name, topic and notes appear on the class.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :return: None
    """
    _backdate(owner_session, teacher.batch_id)
    subject = add_subject(owner_session, batch_id=teacher.batch_id, name="Physics")
    sid = _class(owner_session, teacher.batch_id, dt.date(2027, 5, 20), subject=subject)
    row = owner_session.get_one(Session, sid)
    row.topic, row.notes = "Optics", "bring prisms"
    owner_session.commit()

    cls = _by_day(_teacher_month(restricted_session, teacher))[20].classes[0]

    assert (cls.subject_name, cls.topic, cls.notes) == (
        "Physics",
        "Optics",
        "bring prisms",
    )
    assert cls.session_id == sid


def test_other_batch_teacher_is_refused(
    restricted_session, owner_session, teacher
) -> None:
    """Another teacher's lens cannot read this batch's month.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :return: None
    """
    _backdate(owner_session, teacher.batch_id)
    other = make_teacher(owner_session, name="Chemistry")

    with pytest.raises(AuthorizationError):
        teacher_month(
            restricted_session,
            lens=_lens(other),
            batch_id=teacher.batch_id,
            year=2027,
            month=5,
            now=NOW,
        )


@pytest.mark.parametrize(
    ("year", "month"),
    [(2026, 12), (2027, 7), (2030, 5)],
)
def test_month_out_of_range_is_refused(
    restricted_session, owner_session, teacher, year: int, month: int
) -> None:
    """Before the batch existed or past next month is refused.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param year: The year asked for
    :param month: The month asked for
    :return: None
    """
    _backdate(owner_session, teacher.batch_id)

    with pytest.raises(ValidationError) as raised:
        teacher_month(
            restricted_session,
            lens=_lens(teacher),
            batch_id=teacher.batch_id,
            year=year,
            month=month,
            now=NOW,
        )
    assert raised.value.code == "MONTH_OUT_OF_RANGE"
    assert raised.value.message_key == "teaching.calendar.month_out_of_range"


def test_the_range_edges_are_allowed(
    restricted_session, owner_session, teacher
) -> None:
    """The batch's first month and next month are both readable.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :return: None
    """
    _backdate(owner_session, teacher.batch_id)

    assert _teacher_month(restricted_session, teacher, month=1).days == []
    assert _teacher_month(restricted_session, teacher, month=6).days == []


def _family_batch(
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
    **seat_fields: object,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Seat an accepted student and give the batch a class.

    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :param seat_fields: Enrollment columns to set after creation
    :return: The student account, the seat, and the class
    """
    _backdate(owner_session, teacher.batch_id)
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    row = owner_session.get_one(Enrollment, seat)
    row.created_at = dt.datetime(2027, 1, 6, tzinfo=dt.UTC)
    for key, value in seat_fields.items():
        setattr(row, key, value)
    owner_session.commit()
    return student, seat, _class(owner_session, teacher.batch_id, dt.date(2027, 5, 5))


def _mark(
    owner_session: DbSession,
    session_id: uuid.UUID,
    seat: uuid.UUID,
    present: bool,
    teacher_account: uuid.UUID,
) -> None:
    """Record one attendance row.

    :param owner_session: An arranging session
    :param session_id: The class
    :param seat: The seat
    :param present: Whether present
    :param teacher_account: The recording teacher's account
    :return: None
    """
    now = dt.datetime.now(tz=dt.UTC)
    submission = QueuedSubmission(
        session_id=session_id,
        submitted_by_account_id=teacher_account,
        kind="attendance",
        client_mutation_id=uuid.uuid4(),
        base_version=0,
        resulting_version=owner_session.query(QueuedSubmission)
        .filter_by(session_id=session_id)
        .count()
        + 1,
        created_at=now,
    )
    owner_session.add(submission)
    owner_session.commit()
    owner_session.add(
        Attendance(
            session_id=session_id,
            enrollment_id=seat,
            present=present,
            recorded_at=now,
            recorded_by_account_id=teacher_account,
            submission_id=submission.id,
        )
    )
    owner_session.commit()


def _family_marks(session: DbSession, student: uuid.UUID, seat: uuid.UUID):
    """Read the student's month and map day to mark.

    :param session: The restricted session
    :param student: The student account
    :param seat: The seat
    :return: Day number to mark
    """
    view = family_month(
        session,
        lens=StudentLens(account_id=student),
        enrollment_id=seat,
        year=2027,
        month=5,
        now=NOW,
    )
    return {d.date.day: [c.mark for c in d.classes] for d in view.days}


def test_family_sees_only_own_mark(
    restricted_session, owner_session, teacher, account_factory
) -> None:
    """A classmate's absence never shows on this child's calendar.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, seat, class_id = _family_batch(owner_session, teacher, account_factory)
    classmate = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Karim",
        student_account_id=account_factory(),
        student_decision="accepted",
    )
    _mark(owner_session, class_id, classmate, False, teacher.account_id)

    assert _family_marks(restricted_session, student, seat) == {5: ["not_marked"]}

    _mark(owner_session, class_id, seat, True, teacher.account_id)
    assert _family_marks(restricted_session, student, seat) == {5: ["present"]}


def test_family_absent_mark(
    restricted_session, owner_session, teacher, account_factory
) -> None:
    """An absent row reads absent.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, seat, class_id = _family_batch(owner_session, teacher, account_factory)
    _mark(owner_session, class_id, seat, False, teacher.account_id)

    assert _family_marks(restricted_session, student, seat) == {5: ["absent"]}


def test_child_who_joined_mid_month_sees_not_enrolled_before_join(
    restricted_session, owner_session, teacher, account_factory
) -> None:
    """Classes before ``joined_on`` are ``not_enrolled``, not ``not_marked``.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, seat, _ = _family_batch(
        owner_session, teacher, account_factory, joined_on=dt.date(2027, 5, 8)
    )
    _class(owner_session, teacher.batch_id, dt.date(2027, 5, 8))
    _class(owner_session, teacher.batch_id, dt.date(2027, 5, 12))

    assert _family_marks(restricted_session, student, seat) == {
        5: ["not_enrolled"],
        8: ["not_marked"],
        12: ["not_marked"],
    }


def test_seat_without_joined_on_starts_at_its_creation_date(
    restricted_session, owner_session, teacher, account_factory
) -> None:
    """With no ``joined_on`` the seat starts when it was created.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, seat, _ = _family_batch(
        owner_session,
        teacher,
        account_factory,
        created_at=dt.datetime(2027, 5, 6, 3, 0, tzinfo=dt.UTC),
    )

    assert _family_marks(restricted_session, student, seat) == {5: ["not_enrolled"]}


def test_left_seat_sees_not_enrolled_after_inactive_from(
    restricted_session, owner_session, teacher, account_factory
) -> None:
    """On and after ``inactive_from`` a class is ``not_enrolled``.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, seat, _ = _family_batch(
        owner_session, teacher, account_factory, inactive_from=dt.date(2027, 5, 12)
    )
    _class(owner_session, teacher.batch_id, dt.date(2027, 5, 11))
    _class(owner_session, teacher.batch_id, dt.date(2027, 5, 12))

    assert _family_marks(restricted_session, student, seat) == {
        5: ["not_marked"],
        11: ["not_marked"],
        12: ["not_enrolled"],
    }


def test_guardian_reads_the_childs_calendar(
    restricted_session, owner_session, teacher, account_factory
) -> None:
    """An accepted guardian reads the child's own marks.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    _backdate(owner_session, teacher.batch_id)
    guardian = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        guardian_account_id=guardian,
        guardian_decision="accepted",
    )
    class_id = _class(owner_session, teacher.batch_id, dt.date(2027, 5, 5))
    row = owner_session.get_one(Enrollment, seat)
    row.created_at = dt.datetime(2027, 1, 6, tzinfo=dt.UTC)
    owner_session.commit()
    _mark(owner_session, class_id, seat, True, teacher.account_id)

    view = family_month(
        restricted_session,
        lens=GuardianLens(account_id=guardian, child_enrollment_id=seat),
        enrollment_id=seat,
        year=2027,
        month=5,
        now=NOW,
    )

    assert view.days[0].classes[0].mark == "present"


@pytest.mark.parametrize("decision", ["pending", "declined"])
def test_pending_or_declined_link_is_refused(
    restricted_session, owner_session, teacher, account_factory, decision: str
) -> None:
    """A student who has not accepted the seat reaches nothing.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :param decision: The student's decision
    :return: None
    """
    student, seat, _ = _family_batch(
        owner_session, teacher, account_factory, student_decision=decision
    )

    with pytest.raises(AuthorizationError):
        _family_marks(restricted_session, student, seat)


def test_someone_elses_seat_is_refused(
    restricted_session, owner_session, teacher, account_factory
) -> None:
    """A student cannot read another student's seat.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    _, seat, _ = _family_batch(owner_session, teacher, account_factory)

    with pytest.raises(AuthorizationError):
        _family_marks(restricted_session, account_factory(), seat)


def test_routes_authorize_and_validate(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Each route answers its own lens, and the query is validated.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    today = bangladesh_today()
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    query = f"?year={today.year}&month={today.month}"
    mine = bearer(owner_session, student)
    theirs = bearer(owner_session, teacher.account_id)

    assert (
        api_client.get(
            f"/v1/batches/{teacher.batch_id}/calendar{query}", headers=theirs
        )
    ).status_code == 200
    assert (
        api_client.get(f"/v1/me/enrollments/{seat}/calendar{query}", headers=mine)
    ).status_code == 200
    assert (
        api_client.get(f"/v1/batches/{teacher.batch_id}/calendar{query}", headers=mine)
    ).status_code in (403, 404)
    assert (
        api_client.get(
            f"/v1/me/enrollments/{seat}/calendar?year={today.year}&month=13",
            headers=mine,
        )
    ).status_code == 422
    refused = api_client.get(
        f"/v1/me/enrollments/{seat}/calendar?year=2001&month=1", headers=mine
    )
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "MONTH_OUT_OF_RANGE"


def _keys(value: object) -> list[str]:
    """Collect every key in a JSON value.

    :param value: Decoded JSON
    :return: All keys, recursively
    """
    if isinstance(value, dict):
        return [str(k) for k in value] + [
            key for child in value.values() for key in _keys(child)
        ]
    if isinstance(value, list):
        return [key for child in value for key in _keys(child)]
    return []


def test_response_has_no_phone_address_or_self_name(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A family's month carries no contact or private-profile field.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    today = bangladesh_today()
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    _class(owner_session, teacher.batch_id, today)

    body = api_client.get(
        f"/v1/me/enrollments/{seat}/calendar?year={today.year}&month={today.month}",
        headers=bearer(owner_session, student),
    ).json()

    assert body["days"]
    for key in _keys(body):
        assert not any(bad in key for bad in ("phone", "address", "self_name"))
