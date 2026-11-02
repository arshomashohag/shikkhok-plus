"""The progress dashboard: one shape, three lenses.

Every expected figure follows from the rows seeded in each test, written
down before the module existed. Percentages are whole numbers rounded
half up, and the comparison figures are numbers, never names.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from app.analytics.dashboard import percent_of, seat_dashboard
from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.db.models import Attendance, Batch, Enrollment, QueuedSubmission, Session
from app.errors import AuthorizationError
from app.fees.views import enrollment_fee_history
from app.marks.entry import record_mark
from tests.analytics.conftest import add_exam, lens_for, seat_with_ledger
from tests.batches.conftest import TeacherFixture, _account, enroll
from tests.conftest import bearer

TODAY = dt.date(2026, 11, 3)
JOINED = dt.date(2026, 8, 1)


def _held(
    owner_session: DbSession,
    batch_id: uuid.UUID,
    date: dt.date,
    *,
    status: str = "held",
) -> uuid.UUID:
    """Add one session of a batch.

    :param owner_session: An arranging session
    :param batch_id: The batch
    :param date: The session's date
    :param status: scheduled, held or cancelled
    :return: The session id
    """
    row = Session(
        batch_id=batch_id,
        date=date,
        start_time=dt.time(16, 0),
        status=status,
        origin="recurrence",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(row)
    owner_session.commit()
    return row.id


def _attend(
    owner_session: DbSession,
    session_id: uuid.UUID,
    seat: uuid.UUID,
    present: bool,
) -> None:
    """Record one seat's attendance at a session.

    :param owner_session: An arranging session
    :param session_id: The session
    :param seat: The enrollment
    :param present: Whether they attended
    :return: None
    """
    now = dt.datetime.now(tz=dt.UTC)
    submission = QueuedSubmission(
        session_id=session_id,
        submitted_by_account_id=_account(owner_session),
        kind="attendance",
        client_mutation_id=uuid.uuid4(),
        base_version=0,
        resulting_version=1,
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
            submission_id=submission.id,
        )
    )
    owner_session.commit()


def _seat(
    owner_session: DbSession,
    batch_id: uuid.UUID,
    name: str,
    *,
    student: uuid.UUID | None = None,
    guardian: uuid.UUID | None = None,
) -> uuid.UUID:
    """Create an accepted seat that started on ``JOINED``.

    :param owner_session: An arranging session
    :param batch_id: The batch
    :param name: The teacher-typed name
    :param student: The student account, or a fresh one
    :param guardian: The guardian account, if any
    :return: The enrollment id
    """
    seat = enroll(
        owner_session,
        batch_id=batch_id,
        display_name=name,
        student_account_id=student or _account(owner_session),
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted" if guardian else "pending",
    )
    record = owner_session.get(Enrollment, seat)
    assert record is not None
    record.joined_on = JOINED
    owner_session.commit()
    return seat


def _mark(
    restricted_session: DbSession,
    lens: TeacherLens,
    exam: uuid.UUID,
    seat: uuid.UUID,
    marks: int,
) -> None:
    """Record a mark.

    :param restricted_session: The application-role session
    :param lens: The teacher
    :param exam: The exam
    :param seat: The enrollment
    :param marks: Marks out of 100
    :return: None
    """
    record_mark(
        restricted_session,
        lens=lens,
        exam_id=exam,
        enrollment_id=seat,
        result_state="marked",
        marks=marks,
    )


def _marked_batch(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    values: list[int],
) -> tuple[uuid.UUID, list[uuid.UUID], uuid.UUID]:
    """Make one exam on 1 October with one seat per value.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The teacher
    :param values: The marks, first is the viewer's
    :return: The exam, the seats and the first seat's student account
    """
    viewer = _account(owner_session)
    exam = add_exam(
        owner_session,
        batch_id=teacher.batch_id,
        title="Test 1",
        date=dt.date(2026, 10, 1),
    )
    seats = [
        _seat(
            owner_session,
            teacher.batch_id,
            f"Seat {index}",
            student=viewer if index == 0 else None,
        )
        for index in range(len(values))
    ]
    for seat, value in zip(seats, values, strict=True):
        _mark(restricted_session, lens_for(teacher), exam, seat, value)
    return exam, seats, viewer


def test_percent_rounds_half_up_with_integers() -> None:
    """1 of 8 is 12.5 and rounds to 13; no denominator is no percent.

    :return: None
    """
    assert percent_of(1, 8) == 13
    assert percent_of(1, 3) == 33
    assert percent_of(2, 3) == 67
    assert percent_of(0, 0) is None


def test_attendance_counts_held_not_cancelled(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    """Two held (one present), one cancelled, one before the seat began.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The teacher
    :return: None
    """
    seat = _seat(owner_session, teacher.batch_id, "Rahim")
    first = _held(owner_session, teacher.batch_id, dt.date(2026, 10, 5))
    second = _held(owner_session, teacher.batch_id, dt.date(2026, 10, 12))
    _held(owner_session, teacher.batch_id, dt.date(2026, 10, 19), status="cancelled")
    _held(owner_session, teacher.batch_id, dt.date(2026, 7, 5))
    _attend(owner_session, first, seat, True)
    _attend(owner_session, second, seat, False)

    dash = seat_dashboard(
        restricted_session,
        lens=lens_for(teacher),
        enrollment_id=seat,
        range_="6m",
        today=TODAY,
    )

    assert (dash.tiles.present, dash.tiles.held) == (1, 2)
    assert dash.tiles.attendance_percent == 50
    october = next(m for m in dash.attendance_by_month if m.period == "2026-10")
    assert (october.held, october.present, october.percent) == (2, 1, 50)
    assert october.in_progress is False
    november = dash.attendance_by_month[-1]
    assert (november.period, november.in_progress) == ("2026-11", True)
    assert november.percent is None


def test_range_picks_the_months(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    """6m is six months, year starts in January, all starts at the seat.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The teacher
    :return: None
    """
    seat = _seat(owner_session, teacher.batch_id, "Rahim")

    def periods(range_: str) -> list[str]:
        dash = seat_dashboard(
            restricted_session,
            lens=lens_for(teacher),
            enrollment_id=seat,
            range_=range_,  # type: ignore[arg-type]
            today=TODAY,
        )
        return [m.period for m in dash.attendance_by_month]

    assert periods("6m") == [
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
        "2026-11",
    ]
    assert periods("year")[0] == "2026-01"
    assert periods("all") == ["2026-08", "2026-09", "2026-10", "2026-11"]


def test_average_and_highest_need_three_marked_seats(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    """Two marked give nothing; a third gives mean 60 and highest 90.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The teacher
    :return: None
    """
    exam, seats, _ = _marked_batch(owner_session, restricted_session, teacher, [90, 50])

    two = seat_dashboard(
        restricted_session,
        lens=lens_for(teacher),
        enrollment_id=seats[0],
        range_="6m",
        today=TODAY,
    )
    assert (two.exams[0].batch_average, two.exams[0].batch_highest) == (None, None)

    third = _seat(owner_session, teacher.batch_id, "Seat 2")
    _mark(restricted_session, lens_for(teacher), exam, third, 40)

    three = seat_dashboard(
        restricted_session,
        lens=lens_for(teacher),
        enrollment_id=seats[0],
        range_="6m",
        today=TODAY,
    )
    only = three.exams[0]
    assert (only.batch_average, only.batch_highest) == (60, 90)
    assert (only.marks, only.total, only.percent) == (90, 100, 90)
    assert three.tiles.exam_average_percent == 90
    assert three.tiles.direction is None


def test_family_gets_no_comparison_when_marksheet_hidden(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    """Hidden marksheet: guardian and student see nothing, teacher does.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The teacher
    :return: None
    """
    viewer = _account(owner_session)
    guardian = _account(owner_session)
    exam = add_exam(
        owner_session,
        batch_id=teacher.batch_id,
        title="Test 1",
        date=dt.date(2026, 10, 1),
    )
    mine = _seat(
        owner_session, teacher.batch_id, "Mine", student=viewer, guardian=guardian
    )
    others = [_seat(owner_session, teacher.batch_id, f"O{i}") for i in range(3)]
    for seat, value in zip([mine, *others], [70, 60, 50, 40], strict=True):
        _mark(restricted_session, lens_for(teacher), exam, seat, value)
    batch = owner_session.get(Batch, teacher.batch_id)
    assert batch is not None
    batch.marksheet_visible = False
    owner_session.commit()

    def read(
        lens: StudentLens | GuardianLens | TeacherLens,
    ) -> tuple[int | None, int | None]:
        dash = seat_dashboard(
            restricted_session, lens=lens, enrollment_id=mine, range_="6m", today=TODAY
        )
        return dash.exams[0].batch_average, dash.exams[0].batch_highest

    assert read(StudentLens(account_id=viewer)) == (None, None)
    assert read(GuardianLens(account_id=guardian, child_enrollment_id=mine)) == (
        None,
        None,
    )
    assert read(lens_for(teacher)) == (55, 70)

    batch.marksheet_visible = True
    owner_session.commit()
    assert read(StudentLens(account_id=viewer)) == (55, 70)


def test_highest_carries_no_name(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    """No field of the exam object equals another seat's name.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The teacher
    :return: None
    """
    exam, seats, viewer = _marked_batch(
        owner_session, restricted_session, teacher, [50, 99, 60, 70]
    )
    dash = seat_dashboard(
        restricted_session,
        lens=StudentLens(account_id=viewer),
        enrollment_id=seats[0],
        range_="6m",
        today=TODAY,
    )
    values = {str(getattr(dash.exams[0], f)) for f in dash.exams[0].__slots__}
    names = {f"Seat {i}" for i in range(1, 4)}
    assert values.isdisjoint(names)
    assert dash.exams[0].batch_highest == 99
    assert exam == dash.exams[0].exam_id


def test_direction_comes_from_the_summary(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    """Two exams, 40 then 60, read as up with an average of 50.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The teacher
    :return: None
    """
    seat = _seat(owner_session, teacher.batch_id, "Rahim")
    for title, date, value in (
        ("A", dt.date(2026, 9, 1), 40),
        ("B", dt.date(2026, 10, 1), 60),
    ):
        exam = add_exam(
            owner_session, batch_id=teacher.batch_id, title=title, date=date
        )
        _mark(restricted_session, lens_for(teacher), exam, seat, value)

    dash = seat_dashboard(
        restricted_session,
        lens=lens_for(teacher),
        enrollment_id=seat,
        range_="6m",
        today=TODAY,
    )

    assert dash.tiles.direction == "up"
    assert dash.tiles.exam_average_percent == 50
    assert [e.title for e in dash.exams] == ["A", "B"]


def test_fee_months_match_enrollment_history(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    """The strip is the Task 6 strip and owed is the seat's balance.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The teacher
    :return: None
    """
    seat = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        entries=[
            ("charge", "2026-09", "1000.00"),
            ("receipt", "2026-09", "1000.00"),
            ("charge", "2026-10", "1000.00"),
        ],
    )
    lens = lens_for(teacher)

    dash = seat_dashboard(
        restricted_session, lens=lens, enrollment_id=seat, range_="6m", today=TODAY
    )
    history = enrollment_fee_history(
        restricted_session, lens=lens, enrollment_id=seat, months=6, today=TODAY
    )

    assert [(m.period, m.state) for m in dash.fee_months] == [
        (row.period, row.state) for row in history.month_states
    ]
    assert dash.fee_months
    assert dash.tiles.owed == history.total_outstanding


def test_guardian_cannot_read_a_non_child_dashboard(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    """A guardian of someone else's child, and a stranger student, are refused.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The teacher
    :return: None
    """
    seat = _seat(owner_session, teacher.batch_id, "Rahim")
    stranger = _account(owner_session)

    with pytest.raises(AuthorizationError):
        seat_dashboard(
            restricted_session,
            lens=GuardianLens(account_id=stranger, child_enrollment_id=None),
            enrollment_id=seat,
            range_="6m",
            today=TODAY,
        )
    with pytest.raises(AuthorizationError):
        seat_dashboard(
            restricted_session,
            lens=StudentLens(account_id=stranger),
            enrollment_id=seat,
            range_="6m",
            today=TODAY,
        )


def test_the_three_routes_serve_one_shape(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_for: Callable[[], uuid.UUID],
) -> None:
    """Teacher, student and guardian each read it; a stranger gets 403.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :param account_for: Makes accounts
    :return: None
    """
    student = account_for()
    guardian = account_for()
    seat = _seat(
        owner_session, teacher.batch_id, "Rahim", student=student, guardian=guardian
    )
    teacher_headers = bearer(owner_session, teacher.account_id)

    teacher_body = api_client.get(
        f"/v1/enrollments/{seat}/dashboard?range=all", headers=teacher_headers
    )
    student_body = api_client.get(
        f"/v1/me/enrollments/{seat}/dashboard", headers=bearer(owner_session, student)
    )
    guardian_body = api_client.get(
        f"/v1/children/{seat}/dashboard", headers=bearer(owner_session, guardian)
    )

    assert teacher_body.status_code == 200
    assert student_body.status_code == 200
    assert guardian_body.status_code == 200
    assert set(teacher_body.json()) == {
        "tiles",
        "attendance_by_month",
        "exams",
        "fee_months",
    }
    assert teacher_body.json()["tiles"]["owed"] == "0.00"
    assert (
        api_client.get(
            f"/v1/children/{seat}/dashboard", headers=bearer(owner_session, student)
        ).status_code
        == 403
    )
    assert (
        api_client.get(
            f"/v1/enrollments/{seat}/dashboard?range=bogus", headers=teacher_headers
        ).status_code
        == 422
    )
