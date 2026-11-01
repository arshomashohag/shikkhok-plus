"""Exam topics, and the exam-scheduled inbox item.

Written from the acceptance criteria: order survives, an empty list is
valid, the limits refuse at the edge, a new exam reaches accepted family
members, and only a real change re-flags the item unread.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import Enrollment
from app.marks.exams import create_exam, update_exam
from app.notifications.inbox import EXAM_SCHEDULED, inbox, mark_read
from tests.batches.conftest import TeacherFixture, enroll
from tests.conftest import bearer
from tests.marks.conftest import EXAM_DATE, TOTAL_MARKS


def _post(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
    **extra: object,
) -> object:
    """Create an exam over HTTP.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param subject: The subject
    :param extra: Extra body fields
    :return: The response
    """
    return api_client.post(
        f"/v1/batches/{teacher.batch_id}/exams",
        json={
            "batch_subject_id": str(subject),
            "title": "Unit test",
            "date": "2027-04-20",
            "total_marks": 50,
            **extra,
        },
        headers=bearer(owner_session, teacher.account_id),
    )


def test_topics_round_trip_in_order(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
) -> None:
    created = _post(
        api_client,
        owner_session,
        teacher,
        subject,
        topics=["  Motion ", "Force", "Energy"],
    )
    assert created.status_code == 201
    assert created.json()["topics"] == ["Motion", "Force", "Energy"]

    listed = api_client.get(
        f"/v1/batches/{teacher.batch_id}/exams",
        headers=bearer(owner_session, teacher.account_id),
    )
    assert listed.json()[0]["topics"] == ["Motion", "Force", "Energy"]

    edited = api_client.put(
        f"/v1/exams/{created.json()['exam_id']}",
        json={
            "title": "Unit test",
            "date": "2027-04-20",
            "total_marks": 50,
            "topics": ["Energy", "Motion"],
        },
        headers=bearer(owner_session, teacher.account_id),
    )
    assert edited.json()["topics"] == ["Energy", "Motion"]


def test_no_topics_is_valid(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
) -> None:
    created = _post(api_client, owner_session, teacher, subject)
    assert created.status_code == 201
    assert created.json()["topics"] == []


@pytest.mark.parametrize(
    "topics",
    [["t"] * 21, ["x" * 121], [""], ["   "]],
    ids=["twenty-one", "121-chars", "empty", "blank"],
)
def test_twenty_one_topics_or_a_121_char_topic_is_refused(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
    topics: list[str],
) -> None:
    refused = _post(api_client, owner_session, teacher, subject, topics=topics)
    assert refused.status_code == 422


def test_the_limits_themselves_are_accepted(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
) -> None:
    accepted = _post(
        api_client, owner_session, teacher, subject, topics=["x" * 120] * 20
    )
    assert accepted.status_code == 201


def test_creating_an_exam_delivers_to_family(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    subject: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
    account_factory: Callable[[], uuid.UUID],
) -> None:
    student = account_factory()
    seat_factory(student_account_id=student)
    row = create_exam(
        restricted_session,
        lens=teacher_lens,
        batch_id=teacher.batch_id,
        batch_subject_id=subject,
        title="Unit test",
        date=EXAM_DATE,
        total_marks=TOTAL_MARKS,
        topics=["Motion"],
    )
    items = inbox(restricted_session, account_id=student).items
    assert [(i.kind, i.source_id, i.preview) for i in items] == [
        (EXAM_SCHEDULED, row.exam_id, "Unit test")
    ]


def _scheduled(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    subject: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
    account_factory: Callable[[], uuid.UUID],
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create an exam, read its item, and return student and exam ids.

    :param restricted_session: The application session
    :param teacher: The batch's owner
    :param teacher_lens: The teacher lens
    :param subject: The subject
    :param seat_factory: Makes accepted seats
    :param account_factory: Makes accounts
    :return: The student account and the exam
    """
    student = account_factory()
    seat_factory(student_account_id=student)
    row = create_exam(
        restricted_session,
        lens=teacher_lens,
        batch_id=teacher.batch_id,
        batch_subject_id=subject,
        title="Unit test",
        date=EXAM_DATE,
        total_marks=TOTAL_MARKS,
        topics=["Motion"],
    )
    mark_read(restricted_session, account_id=student)
    assert inbox(restricted_session, account_id=student).unread == 0
    return student, row.exam_id


def test_editing_topics_marks_the_item_unread(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    subject: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
    account_factory: Callable[[], uuid.UUID],
) -> None:
    student, exam_id = _scheduled(
        restricted_session,
        teacher,
        teacher_lens,
        subject,
        seat_factory,
        account_factory,
    )
    update_exam(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam_id,
        title="Unit test",
        date=EXAM_DATE,
        total_marks=TOTAL_MARKS,
        topics=["Motion", "Force"],
    )
    assert inbox(restricted_session, account_id=student).unread == 1


def test_editing_nothing_leaves_it_read(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    subject: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
    account_factory: Callable[[], uuid.UUID],
) -> None:
    student, exam_id = _scheduled(
        restricted_session,
        teacher,
        teacher_lens,
        subject,
        seat_factory,
        account_factory,
    )
    update_exam(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam_id,
        title="Unit test",
        date=EXAM_DATE,
        total_marks=60,
        topics=["Motion"],
    )
    assert inbox(restricted_session, account_id=student).unread == 0


def test_editing_an_exam_leaves_a_declined_guardian_untouched(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    subject: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A guardian who declined keeps the old preview and stays read.

    :param owner_session: An arranging session
    :param restricted_session: The application session
    :param teacher: The batch's owner
    :param teacher_lens: The teacher lens
    :param subject: The subject
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted",
    )
    row = create_exam(
        restricted_session,
        lens=teacher_lens,
        batch_id=teacher.batch_id,
        batch_subject_id=subject,
        title="Unit test",
        date=EXAM_DATE,
        total_marks=TOTAL_MARKS,
        topics=["Motion"],
    )
    mark_read(restricted_session, account_id=guardian)
    owner_session.get_one(Enrollment, seat).guardian_decision = "declined"
    owner_session.commit()

    update_exam(
        restricted_session,
        lens=teacher_lens,
        exam_id=row.exam_id,
        title="Renamed",
        date=EXAM_DATE,
        total_marks=TOTAL_MARKS,
        topics=["Motion", "Force"],
    )

    after = inbox(restricted_session, account_id=guardian)
    assert (after.unread, after.items[0].preview) == (0, "Unit test")


def test_an_edit_without_topics_keeps_them_and_stays_read(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """An installed older app's PUT carries no topics; it must not wipe them.

    Client and server version independently [D-26], so a body without
    the field means "unchanged", not "none", and an unchanged exam does
    not re-flag the families' item.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param subject: The subject
    :param seat_factory: Makes accepted seats
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat_factory(student_account_id=student)
    created = _post(
        api_client, owner_session, teacher, subject, topics=["Motion", "Force"]
    )
    mark_read(owner_session, account_id=student)

    edited = api_client.put(
        f"/v1/exams/{created.json()['exam_id']}",
        json={"title": "Unit test", "date": "2027-04-20", "total_marks": 60},
        headers=bearer(owner_session, teacher.account_id),
    )

    assert edited.status_code == 200
    assert edited.json()["topics"] == ["Motion", "Force"]
    assert inbox(owner_session, account_id=student).unread == 0
