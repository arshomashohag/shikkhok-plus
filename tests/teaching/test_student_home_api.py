"""What S1 and S2 read: the next class, the last result, the coming exam.

**Written before the fields existed.** Every value is a comparison of
dates, a rank, or a choice of "which one is next" -- decisions the
server makes and the phone renders [TC-9].

Dates are far in the future so "next" does not depend on the day the
suite runs.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from app.db.models import Exam, FeeCycle, Session
from app.fees.claims import submit_claim
from app.fees.ledger_writer import append_entry
from app.fees.verification import verify_claim
from app.local_time import DHAKA
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.conftest import bearer
from tests.teaching.conftest import add_slot, add_subject

MONDAY, WEDNESDAY = 0, 2
FIRST = dt.date(2099, 3, 2)
MOVED = dt.date(2099, 3, 4)


def _class(
    session: DbSession,
    batch_id: uuid.UUID,
    day: dt.date,
    start: dt.time,
    subject: uuid.UUID | None = None,
) -> None:
    """Add one scheduled recurring class.

    :param session: An arranging session
    :param batch_id: The batch
    :param day: Its date
    :param start: Its start
    :param subject: Its subject, if any
    :return: None
    """
    session.add(
        Session(
            batch_id=batch_id,
            batch_subject_id=subject,
            date=day,
            start_time=start,
            end_time=dt.time(start.hour + 1, 30),
            status="scheduled",
            origin="recurrence",
            attendance_version=0,
            topic_version=0,
            created_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    session.commit()


def test_the_batch_page_names_the_next_class_the_moved_one_and_the_exam(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Monday as usual, Wednesday moved to 18:00, a test on the Saturday.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    for weekday in (MONDAY, WEDNESDAY):
        add_slot(owner_session, batch_id=teacher.batch_id, weekday=weekday)
    subject = add_subject(owner_session, batch_id=teacher.batch_id, name="1st paper")
    _class(owner_session, teacher.batch_id, FIRST, dt.time(16, 0), subject)
    _class(owner_session, teacher.batch_id, MOVED, dt.time(18, 0))
    owner_session.add(
        Exam(
            batch_id=teacher.batch_id,
            batch_subject_id=subject,
            title="Monthly test",
            date=dt.date(2099, 3, 7),
            total_marks=100,
            created_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    owner_session.commit()
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )

    body = api_client.get(
        f"/v1/me/batches/{seat}/teaching", headers=bearer(owner_session, student)
    ).json()

    assert body["next_session"] == {
        "date": "2099-03-02",
        "start_time": "16:00:00",
        "end_time": "17:30:00",
        "starts_in_minutes": None,
        "moved": False,
        "subject_name": "1st paper",
    }
    assert [(s["date"], s["moved"]) for s in body["following_sessions"]] == [
        ("2099-03-04", True)
    ]
    assert body["upcoming_exam"] == {
        "title": "Monthly test",
        "date": "2099-03-07",
        "total_marks": 100,
        "subject_name": "1st paper",
    }


def test_the_batch_list_marks_one_next_class_across_batches(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Two batches; the earlier class is THE next one.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The first batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    other = make_teacher(owner_session, name="Chemistry")
    _class(owner_session, teacher.batch_id, MOVED, dt.time(16, 0))
    _class(owner_session, other.batch_id, FIRST, dt.time(16, 0))
    student = account_factory()
    for batch in (teacher.batch_id, other.batch_id):
        enroll(
            owner_session,
            batch_id=batch,
            display_name="Rahim",
            student_account_id=student,
            student_decision="accepted",
        )

    rows = api_client.get(
        "/v1/me/enrollments", headers=bearer(owner_session, student)
    ).json()

    flagged = {row["batch_name"]: row["is_next"] for row in rows}
    assert flagged == {"Chemistry": True, "Physics": False}
    assert {row["batch_name"]: row["next_session"]["date"] for row in rows} == {
        "Chemistry": "2099-03-02",
        "Physics": "2099-03-04",
    }
    assert all(row["last_result"] is None for row in rows)


def test_the_fee_line_says_charged_verifying_and_paid_on(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Show the charged amount, then Verifying, then the day it was paid.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    append_entry(
        owner_session,
        enrollment_id=seat,
        period="2026-10",
        kind="charge",
        amount=Money("1500.00"),
    )
    owner_session.add(
        FeeCycle(
            enrollment_id=seat,
            period="2026-10",
            due_date=dt.date(2026, 10, 10),
            created_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    owner_session.commit()
    headers = bearer(owner_session, student)

    def fee() -> dict[str, object]:
        [row] = api_client.get("/v1/me/enrollments", headers=headers).json()
        line: dict[str, object] = row["current_fee"]
        return line

    unpaid = fee()
    claim = submit_claim(
        owner_session,
        enrollment_id=seat,
        submitted_by_account_id=student,
        claimed_amount=Money("1500.00"),
        channel="bKash",
        transaction_id="TX-1",
    )
    checking = fee()
    verify_claim(
        owner_session,
        claim_id=claim.id,
        approved_amount=Money("1500.00"),
        shortfall_disposition=None,
        verified_by_account_id=teacher.account_id,
    )
    paid = fee()

    assert (unpaid["charged"], unpaid["verifying"], unpaid["paid_on"]) == (
        "1500.00",
        False,
        None,
    )
    assert checking["verifying"] is True
    assert (paid["status"], paid["verifying"], paid["paid_on"]) == (
        "paid",
        False,
        dt.datetime.now(tz=DHAKA).date().isoformat(),
    )
