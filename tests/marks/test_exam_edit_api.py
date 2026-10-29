"""Editing an exam over HTTP: title, date and total, and nothing else.

**The subject is not part of an edit.** The route used to take the create
body, which requires ``batch_subject_id``, so a client editing a title
had to know a key the mark-entry screen never receives. An edit names
what changes; the subject stays where the exam was set.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from tests.batches.conftest import TeacherFixture, make_teacher
from tests.conftest import bearer


def test_an_exam_is_edited_without_naming_its_subject(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    exam: uuid.UUID,
) -> None:
    """Title, date and total change; the subject stays.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param exam: The exam
    :return: None
    """
    response = api_client.put(
        f"/v1/exams/{exam}",
        json={"title": "Mid-term", "date": "2026-04-20", "total_marks": 50},
        headers=bearer(owner_session, teacher.account_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["title"], body["date"], body["total_marks"], body["subject_name"]) == (
        "Mid-term",
        "2026-04-20",
        50,
        "Physics",
    )


def test_another_teacher_cannot_edit_the_exam(
    api_client: TestClient,
    owner_session: DbSession,
    exam: uuid.UUID,
) -> None:
    """A stranger's edit is refused.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param exam: The exam
    :return: None
    """
    stranger = make_teacher(owner_session, name="Other")

    response = api_client.put(
        f"/v1/exams/{exam}",
        json={"title": "Taken", "date": "2026-04-20", "total_marks": 50},
        headers=bearer(owner_session, stranger.account_id),
    )

    assert response.status_code == 403
