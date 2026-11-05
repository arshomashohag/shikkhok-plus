"""The family batch page: exams with topics, and the teacher block.

Written before the fields existed.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from app.db.models import Batch, Exam, Mark
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.conftest import bearer
from tests.teaching.conftest import add_subject


def _exam(
    session: DbSession,
    batch_id: uuid.UUID,
    subject: uuid.UUID,
    title: str,
    date: dt.date,
    topics: list[str] | None = None,
) -> uuid.UUID:
    """Add one exam.

    :param session: An arranging session
    :param batch_id: The batch
    :param subject: Its subject
    :param title: Its title
    :param date: Its date
    :param topics: What it covers
    :return: The exam id
    """
    exam = Exam(
        batch_id=batch_id,
        batch_subject_id=subject,
        title=title,
        date=date,
        total_marks=50,
        topics=topics or [],
        created_at=dt.datetime.now(tz=dt.UTC),
        published_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(exam)
    session.commit()
    return exam.id


def _seat(
    session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> tuple[uuid.UUID, uuid.UUID]:
    """Enroll an accepted student.

    :param session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: The student account and the seat
    """
    student = account_factory()
    seat = enroll(
        session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    return student, seat


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


def test_teacher_block_has_display_name_and_subjects_and_no_phone_or_address(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Name and subjects only.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    batch = owner_session.get(Batch, teacher.batch_id)
    assert batch is not None
    batch.teacher_display_name = "Karim Sir"
    owner_session.commit()
    add_subject(owner_session, batch_id=teacher.batch_id, name="Physics")
    student, seat = _seat(owner_session, teacher, account_factory)

    body = api_client.get(
        f"/v1/me/batches/{seat}/teaching", headers=bearer(owner_session, student)
    ).json()

    assert body["teacher"] == {"display_name": "Karim Sir", "subjects": ["Physics"]}
    for key in _keys(body):
        assert not any(bad in key for bad in ("phone", "address", "self_name"))


def test_blank_display_name_is_null(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A blank name is no name.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    batch = owner_session.get(Batch, teacher.batch_id)
    assert batch is not None
    batch.teacher_display_name = "   "
    owner_session.commit()
    student, seat = _seat(owner_session, teacher, account_factory)

    body = api_client.get(
        f"/v1/me/batches/{seat}/teaching", headers=bearer(owner_session, student)
    ).json()

    assert body["teacher"]["display_name"] is None


def test_exams_grouped_upcoming_then_done(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Upcoming soonest first; done newest first; a marked exam is done.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    subject = add_subject(owner_session, batch_id=teacher.batch_id, name="Math")
    batch = teacher.batch_id
    _exam(owner_session, batch, subject, "Late", dt.date(2099, 6, 1), ["Algebra"])
    _exam(owner_session, batch, subject, "Soon", dt.date(2099, 5, 1))
    _exam(owner_session, batch, subject, "Old", dt.date(2020, 1, 1))
    _exam(owner_session, batch, subject, "Older", dt.date(2019, 1, 1))
    marked = _exam(owner_session, batch, subject, "Marked", dt.date(2099, 7, 1))
    student, seat = _seat(owner_session, teacher, account_factory)
    owner_session.add(
        Mark(
            exam_id=marked,
            enrollment_id=seat,
            result_state="marked",
            marks=40,
            recorded_at=dt.datetime.now(tz=dt.UTC),
            created_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    owner_session.commit()

    body = api_client.get(
        f"/v1/me/batches/{seat}/teaching", headers=bearer(owner_session, student)
    ).json()

    assert [(e["title"], e["state"]) for e in body["exams"]] == [
        ("Soon", "upcoming"),
        ("Late", "upcoming"),
        ("Marked", "done"),
        ("Old", "done"),
        ("Older", "done"),
    ]
    assert body["exams"][1]["topics"] == ["Algebra"]
    assert body["exams"][0]["subject_name"] == "Math"


def test_exam_detail_of_another_batch_is_refused(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Own batch's exam reads; another batch's is refused.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    mine = add_subject(owner_session, batch_id=teacher.batch_id)
    other = make_teacher(owner_session, name="Chemistry")
    theirs = add_subject(owner_session, batch_id=other.batch_id)
    own_exam = _exam(
        owner_session, teacher.batch_id, mine, "Mine", dt.date(2099, 5, 1), ["A"]
    )
    foreign = _exam(
        owner_session, other.batch_id, theirs, "Theirs", dt.date(2099, 5, 1)
    )
    student, seat = _seat(owner_session, teacher, account_factory)
    headers = bearer(owner_session, student)

    ok = api_client.get(f"/v1/me/enrollments/{seat}/exams/{own_exam}", headers=headers)
    bad = api_client.get(f"/v1/me/enrollments/{seat}/exams/{foreign}", headers=headers)

    assert ok.status_code == 200
    assert ok.json()["topics"] == ["A"]
    assert bad.status_code == 403


def test_guardian_route_serves_the_same_shape(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The guardian's two routes carry the student's shape.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    subject = add_subject(owner_session, batch_id=teacher.batch_id, name="Math")
    exam = _exam(
        owner_session, teacher.batch_id, subject, "Quiz", dt.date(2099, 5, 1), ["X"]
    )
    guardian = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        guardian_account_id=guardian,
        guardian_decision="accepted",
    )
    headers = bearer(owner_session, guardian)

    body = api_client.get(f"/v1/children/{seat}/teaching", headers=headers).json()
    detail = api_client.get(f"/v1/children/{seat}/exams/{exam}", headers=headers)

    assert body["teacher"]["subjects"] == ["Math"]
    assert [e["title"] for e in body["exams"]] == ["Quiz"]
    assert detail.status_code == 200
    assert detail.json() == body["exams"][0]
