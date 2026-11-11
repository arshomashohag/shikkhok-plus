"""An exam's total is bounded at the schema, not by an int4 overflow [SEC-3].

``total_marks`` had a floor and no ceiling, against an ``Integer``
column. A total past int4 raised ``DataError`` at the INSERT, which no
handler mapped: the client got a 500, and the logged traceback carried
the statement's bound parameters.
"""

from __future__ import annotations

import datetime as dt
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from app.db.models import Exam
from app.schemas.marks import MAX_TOTAL_MARKS
from tests.batches.conftest import TeacherFixture
from tests.conftest import bearer

EXAM_DAY = "2027-04-20"


def _create(
    client: TestClient,
    session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
    total_marks: int,
) -> httpx.Response:
    """Post one exam with a chosen total.

    :param client: The test client
    :param session: A session to issue the token through
    :param teacher: The batch's owner
    :param subject: The subject
    :param total_marks: The total to send
    :return: The response
    """
    return client.post(
        f"/v1/batches/{teacher.batch_id}/exams",
        json={
            "batch_subject_id": str(subject),
            "title": "Overflow",
            "date": EXAM_DAY,
            "total_marks": total_marks,
        },
        headers=bearer(session, teacher.account_id),
    )


@pytest.mark.parametrize("total", [MAX_TOTAL_MARKS + 1, 3_000_000_000])
def test_a_total_past_the_bound_is_refused_without_a_500(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
    total: int,
) -> None:
    """Past the bound, and past int4, both answer the validation envelope.

    :param api_client: The test client
    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :param subject: The subject
    :param total: The total sent
    :return: None
    """
    response = _create(api_client, owner_session, teacher, subject, total)

    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "REQUEST_INVALID"
    assert error["retryable"] is False
    assert str(total) not in response.text


def test_the_bound_itself_is_accepted(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
) -> None:
    """The largest permitted total is a real exam.

    :param api_client: The test client
    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :param subject: The subject
    :return: None
    """
    response = _create(api_client, owner_session, teacher, subject, MAX_TOTAL_MARKS)

    assert response.status_code == 201, response.text


#: A total stored before the creation cap existed.
LEGACY_TOTAL = 1200


@pytest.fixture
def legacy_exam(
    owner_session: DbSession, teacher: TeacherFixture, subject: uuid.UUID
) -> uuid.UUID:
    """One exam stored with a total past today's creation cap.

    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :param subject: The subject
    :return: The exam id
    """
    assert LEGACY_TOTAL > MAX_TOTAL_MARKS
    row = Exam(
        batch_id=teacher.batch_id,
        batch_subject_id=subject,
        title="Term aggregate",
        date=dt.date.fromisoformat(EXAM_DAY),
        total_marks=LEGACY_TOTAL,
        created_at=dt.datetime.now(tz=dt.UTC),
        published_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(row)
    owner_session.commit()
    return row.id


def _edit(
    client: TestClient,
    session: DbSession,
    teacher: TeacherFixture,
    exam_id: uuid.UUID,
    total_marks: int,
) -> httpx.Response:
    """Put a renamed exam with a chosen total.

    :param client: The test client
    :param session: A session to issue the token through
    :param teacher: The batch's owner
    :param exam_id: The exam
    :param total_marks: The total to send
    :return: The response
    """
    return client.put(
        f"/v1/exams/{exam_id}",
        json={"title": "Renamed", "date": EXAM_DAY, "total_marks": total_marks},
        headers=bearer(session, teacher.account_id),
    )


def test_an_exam_stored_past_the_cap_can_still_be_edited(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    legacy_exam: uuid.UUID,
) -> None:
    """Keeping a stored total past the cap is not choosing one.

    :param api_client: The test client
    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :param legacy_exam: The exam stored at 1200
    :return: None
    """
    response = _edit(api_client, owner_session, teacher, legacy_exam, LEGACY_TOTAL)

    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Renamed"
    assert response.json()["total_marks"] == LEGACY_TOTAL


@pytest.mark.parametrize(
    ("total", "status", "code"),
    [
        (LEGACY_TOTAL + 1, 400, "EXAM_TOTAL_INVALID"),
        (3_000_000_000, 422, "REQUEST_INVALID"),
    ],
    ids=["past-the-cap", "past-int4"],
)
def test_an_edit_may_not_choose_a_new_total_past_the_cap(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    legacy_exam: uuid.UUID,
    total: int,
    status: int,
    code: str,
) -> None:
    """A raised total is refused as creation refuses it, and int4 still binds.

    :param api_client: The test client
    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :param legacy_exam: The exam stored at 1200
    :param total: The total sent
    :param status: The status expected
    :param code: The error code expected
    :return: None
    """
    response = _edit(api_client, owner_session, teacher, legacy_exam, total)

    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    assert str(total) not in response.text
