"""A create retried after a lost response makes one student [audit C-25].

A student with no phone number was always created afresh, and the seat
constraint deduplicates only when the SAME student is reseated. So a
teacher on a Bangladeshi mobile network whose "Add" timed out and who
tapped again got two students and two seats, each billed every month.
Both create routes now take an optional ``client_mutation_id``; a resend
under the same key returns what the first created.
"""

from __future__ import annotations

import threading
import uuid

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Enrollment, Student
from tests.batches.conftest import make_teacher
from tests.conftest import bearer


def _students(session: Session, owner_id: uuid.UUID) -> int:
    """Count a teacher's students.

    :param session: A session to read through
    :param owner_id: The teacher's owner id
    :return: How many students they have
    """
    return (
        session.scalar(
            sa.select(sa.func.count())
            .select_from(Student)
            .where(Student.owner_id == owner_id)
        )
        or 0
    )


def test_resending_a_new_student_returns_the_first(
    api_client: TestClient, owner_session: Session
) -> None:
    """Same key, no phone: one student, the same id both times.

    :param api_client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    headers = bearer(owner_session, teacher.account_id)
    body = {"display_name": "Rahim", "client_mutation_id": str(uuid.uuid4())}

    first = api_client.post("/v1/students", json=body, headers=headers)
    again = api_client.post("/v1/students", json=body, headers=headers)

    assert first.status_code == 201, first.text
    assert again.status_code == 201, again.text
    assert again.json()["student_id"] == first.json()["student_id"]
    assert _students(owner_session, teacher.owner_id) == 1


def test_resending_a_seat_returns_the_first_seat(
    api_client: TestClient, owner_session: Session
) -> None:
    """Same key on the roster's add: one student, one seat.

    :param api_client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    headers = bearer(owner_session, teacher.account_id)
    path = f"/v1/batches/{teacher.batch_id}/enrollments"
    body = {"display_name": "Karim", "client_mutation_id": str(uuid.uuid4())}

    first = api_client.post(path, json=body, headers=headers)
    again = api_client.post(path, json=body, headers=headers)

    assert first.status_code == 201, first.text
    assert again.status_code == 201, again.text
    assert again.json()["enrollment_id"] == first.json()["enrollment_id"]
    seats = owner_session.scalar(
        sa.select(sa.func.count())
        .select_from(Enrollment)
        .where(Enrollment.batch_id == teacher.batch_id)
    )
    assert seats == 1


def test_two_resends_at_once_still_make_one_student(
    api_client: TestClient, owner_session: Session
) -> None:
    """The race the key exists for: both arrive before either commits.

    :param api_client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    body = {"display_name": "Sumi", "client_mutation_id": str(uuid.uuid4())}
    headers = [bearer(owner_session, teacher.account_id) for _ in range(2)]
    barrier = threading.Barrier(2)
    ids: list[str] = []
    guard = threading.Lock()

    def create(header: dict[str, str]) -> None:
        """Send the create.

        :param header: This worker's authorization
        :return: None
        """
        barrier.wait(timeout=30)
        response = api_client.post("/v1/students", json=body, headers=header)
        assert response.status_code == 201, response.text
        with guard:
            ids.append(response.json()["student_id"])

    threads = [threading.Thread(target=create, args=(h,)) for h in headers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(thread.is_alive() for thread in threads)

    assert len(ids) == 2 and ids[0] == ids[1]
    assert _students(owner_session, teacher.owner_id) == 1


def test_a_create_without_a_key_is_unchanged(
    api_client: TestClient, owner_session: Session
) -> None:
    """Old clients that send no key keep today's behaviour.

    :param api_client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    headers = bearer(owner_session, teacher.account_id)

    api_client.post("/v1/students", json={"display_name": "A"}, headers=headers)
    api_client.post("/v1/students", json={"display_name": "A"}, headers=headers)

    assert _students(owner_session, teacher.owner_id) == 2
