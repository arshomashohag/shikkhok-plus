"""The teacher's Today screen (T1): money owed, today's classes, payments.

**Written before the read existed.** Two of its figures are money --
what is owed, and what of it is overdue -- and one is a scoping read
across every batch a teacher owns, so a wrong answer is a money error or
another teacher's data. Every expected value below is computed from the
fixture's charges and dates without an implementation.

**"Today" is Bangladesh's date, not UTC's.** At 1 am in Dhaka it is
still yesterday in UTC; a teacher opening the app before 6 am would
otherwise see yesterday's classes and an overdue figure a day stale.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.analytics.today import today_view
from app.db.models import Enrollment, FeeCycle
from app.db.models import Session as ClassSession
from app.fees.claims import submit_claim
from app.local_time import DHAKA
from app.money import Money
from tests.analytics.conftest import add_exam, lens_for, seat_with_ledger
from tests.batches.conftest import TeacherFixture

#: 17 Oct 2026, 3:25 pm in Dhaka.
NOW = dt.datetime(2026, 10, 17, 15, 25, tzinfo=DHAKA)


def _cycle(session: Session, seat: uuid.UUID, period: str, due: dt.date) -> None:
    """Record a fee period's due date.

    :param session: An arranging session
    :param seat: The enrollment
    :param period: The period
    :param due: Its due date
    :return: None
    """
    session.add(
        FeeCycle(
            enrollment_id=seat,
            period=period,
            due_date=due,
            created_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    session.commit()


def _class(
    session: Session, batch_id: uuid.UUID, day: dt.date, start: dt.time
) -> uuid.UUID:
    """Add one scheduled class.

    :param session: An arranging session
    :param batch_id: The batch
    :param day: Its date
    :param start: Its start time
    :return: The session id
    """
    row = ClassSession(
        batch_id=batch_id,
        date=day,
        start_time=start,
        end_time=dt.time(start.hour + 1, start.minute),
        status="scheduled",
        origin="ad_hoc",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(row)
    session.commit()
    return row.id


def test_outstanding_splits_overdue_by_the_due_date(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """3600 owed, 2400 of it past its due date, by one student.

    Asha owes September (due 10 Sep) and October (due 10 Oct): both are
    past due on 17 Oct. Bilal owes October with a due date of 20 Oct,
    which has not passed.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batches' owner
    :return: None
    """
    asha = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Asha",
        entries=[("charge", "2026-09", "1200.00"), ("charge", "2026-10", "1200.00")],
    )
    _cycle(owner_session, asha, "2026-09", dt.date(2026, 9, 10))
    _cycle(owner_session, asha, "2026-10", dt.date(2026, 10, 10))
    bilal = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Bilal",
        entries=[("charge", "2026-10", "1200.00")],
    )
    _cycle(owner_session, bilal, "2026-10", dt.date(2026, 10, 20))

    owed = today_view(restricted_session, lens=lens_for(teacher), now=NOW).outstanding

    assert owed.total == Money("3600.00")
    assert owed.overdue == Money("2400.00")
    assert owed.overdue_students == 1
    assert owed.batch_count == 1


def test_a_period_paid_off_is_not_overdue(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """A past due date with nothing owing contributes nothing.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batches' owner
    :return: None
    """
    seat = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Asha",
        entries=[
            ("charge", "2026-09", "1200.00"),
            ("receipt", "2026-09", "1200.00"),
            ("charge", "2026-10", "1200.00"),
        ],
    )
    _cycle(owner_session, seat, "2026-09", dt.date(2026, 9, 10))
    _cycle(owner_session, seat, "2026-10", dt.date(2026, 10, 20))

    owed = today_view(restricted_session, lens=lens_for(teacher), now=NOW).outstanding

    assert owed.total == Money("1200.00")
    assert owed.overdue == Money.ZERO
    assert owed.overdue_students == 0


def test_another_teachers_money_and_classes_never_appear(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    other_teacher: TeacherFixture,
) -> None:
    """Every figure is scoped to the batches this lens owns.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The teacher asking
    :param other_teacher: An unrelated teacher with debt and a class
    :return: None
    """
    seat = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=other_teacher.batch_id,
        display_name="Stranger",
        entries=[("charge", "2026-09", "5000.00")],
    )
    _cycle(owner_session, seat, "2026-09", dt.date(2026, 9, 10))
    _class(owner_session, other_teacher.batch_id, NOW.date(), dt.time(16, 0))

    view = today_view(restricted_session, lens=lens_for(teacher), now=NOW)

    assert view.outstanding.total == Money.ZERO
    assert view.classes == []
    assert view.to_verify_count == 0


def test_todays_classes_use_bangladesh_date_and_name_the_next(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """At 3:25 pm the 10 am class is past and the 4 pm one is next, in 35.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batches' owner
    :return: None
    """
    morning = _class(owner_session, teacher.batch_id, NOW.date(), dt.time(10, 0))
    afternoon = _class(owner_session, teacher.batch_id, NOW.date(), dt.time(16, 0))
    _class(
        owner_session,
        teacher.batch_id,
        NOW.date() - dt.timedelta(days=1),
        dt.time(16, 0),
    )

    classes = today_view(restricted_session, lens=lens_for(teacher), now=NOW).classes

    assert [row.session_id for row in classes] == [morning, afternoon]
    assert [row.is_next for row in classes] == [False, True]
    assert [row.starts_in_minutes for row in classes] == [None, 35]


def test_one_in_the_morning_in_dhaka_is_already_today(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """At 1 am local (7 pm UTC the day before) today's classes show.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batches' owner
    :return: None
    """
    early = dt.datetime(2026, 10, 17, 1, 0, tzinfo=DHAKA)
    session_id = _class(
        owner_session, teacher.batch_id, dt.date(2026, 10, 17), dt.time(10, 0)
    )

    view = today_view(
        restricted_session, lens=lens_for(teacher), now=early.astimezone(dt.UTC)
    )

    assert view.date == dt.date(2026, 10, 17)
    assert [row.session_id for row in view.classes] == [session_id]


def test_an_exam_today_attaches_to_its_batchs_class(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """Attach an exam sat today to its batch's class, for the Marks button.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batches' owner
    :return: None
    """
    _class(owner_session, teacher.batch_id, NOW.date(), dt.time(16, 0))
    exam = add_exam(
        owner_session, batch_id=teacher.batch_id, title="Class test 2", date=NOW.date()
    )

    [row] = today_view(restricted_session, lens=lens_for(teacher), now=NOW).classes

    assert row.exam_id == exam
    assert row.exam_title == "Class test 2"


def test_payments_waiting_are_counted(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """The "To verify · N" heading, from the same queue T4 shows.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batches' owner
    :return: None
    """
    seat = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Asha",
        entries=[("charge", "2026-10", "1200.00")],
    )
    _cycle(owner_session, seat, "2026-10", dt.date(2026, 10, 10))
    student = owner_session.get(Enrollment, seat)
    assert student is not None and student.student_account_id is not None
    submit_claim(
        owner_session,
        enrollment_id=seat,
        submitted_by_account_id=student.student_account_id,
        claimed_amount=Money("1200.00"),
        channel="bKash",
        transaction_id="TX-1",
    )

    view = today_view(restricted_session, lens=lens_for(teacher), now=NOW)

    assert view.to_verify_count == 1
    assert [item.display_name for item in view.to_verify] == ["Asha"]


def test_the_today_route_sends_money_as_strings(
    client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    signed_in_teacher: TeacherFixture,
    teacher_token: str,
) -> None:
    """One read for the screen, through the real route.

    :param client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param signed_in_teacher: The teacher the token belongs to
    :param teacher_token: Their bearer token
    :return: None
    """
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=signed_in_teacher.batch_id,
        display_name="Asha",
        entries=[("charge", "2026-09", "1200.00")],
    )

    response = client.get(
        "/v1/me/today", headers={"Authorization": f"Bearer {teacher_token}"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outstanding"]["total"] == "1200.00"
    assert body["to_verify_count"] == 0
    assert body["has_batches"] is True
    assert isinstance(body["classes"], list)
