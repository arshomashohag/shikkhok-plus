"""Reminders and the inbox, through real routes.

The service tests in ``test_reminders_in_app.py`` pin who may send and
who receives; these pin that the routes reach them with the caller's
own identity and nothing from the request.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.fees.ledger_writer import append_entry
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.conftest import bearer


def _owing_seat(
    session: Session, teacher: TeacherFixture, student: uuid.UUID
) -> uuid.UUID:
    """Seat an accepted student owing October's 1200.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param student: The student's account
    :return: The seat
    """
    seat = enroll(
        session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    append_entry(
        session,
        enrollment_id=seat,
        period="2026-10",
        kind="charge",
        amount=Money("1200.00"),
    )
    session.commit()
    return seat


def test_a_teacher_reminds_and_the_student_reads_and_clears_it(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Send, read with an unread badge, mark read, read again.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = _owing_seat(owner_session, teacher, student)

    sent = api_client.post(
        "/v1/reminders",
        json={"enrollment_ids": [str(seat)]},
        headers=bearer(owner_session, teacher.account_id),
    )
    as_student = bearer(owner_session, student)
    before = api_client.get("/v1/me/notifications", headers=as_student)
    cleared = api_client.post("/v1/me/notifications/read", headers=as_student)
    after = api_client.get("/v1/me/notifications", headers=as_student)

    assert sent.json() == {"sent": 1, "skipped": 0}
    assert before.json()["unread"] == 1
    [item] = before.json()["items"]
    assert (item["kind"], item["amount"], item["period"]) == (
        "fee_reminder",
        "1200.00",
        "2026-10",
    )
    assert cleared.status_code == 204
    assert after.json()["unread"] == 0


def test_another_teachers_seat_is_refused(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A stranger's seat is a 403, and nothing reaches the student.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = _owing_seat(owner_session, teacher, student)
    stranger = make_teacher(owner_session, name="Chemistry")

    response = api_client.post(
        "/v1/reminders",
        json={"enrollment_ids": [str(seat)]},
        headers=bearer(owner_session, stranger.account_id),
    )
    inbox = api_client.get(
        "/v1/me/notifications", headers=bearer(owner_session, student)
    )

    assert response.status_code == 403
    assert inbox.json() == {"items": [], "unread": 0}


def test_the_inbox_needs_a_credential(api_client: TestClient) -> None:
    """No token, no inbox.

    :param api_client: The test client
    :return: None
    """
    assert api_client.get("/v1/me/notifications").status_code == 401
    assert api_client.post("/v1/me/notifications/read").status_code == 401


def test_the_dues_rows_show_the_reminder(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """After a reminder the dues row says when.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _owing_seat(owner_session, teacher, account_factory())
    headers = bearer(owner_session, teacher.account_id)

    api_client.post(
        "/v1/reminders", json={"enrollment_ids": [str(seat)]}, headers=headers
    )
    [row] = api_client.get("/v1/me/dues", headers=headers).json()["rows"]

    assert row["last_reminded_at"] is not None
    assert row["remindable"] is False
