"""Cancelling an exam that has not been published [0019].

**Written before the route existed.** The authorization cases are the
test-first predicate's: a wrong answer lets one teacher call off
another's exam, or lets a family lens write. The rest are written from
the acceptance criteria: every family member the exam reached is told,
a published exam cannot be cancelled, a second cancel changes nothing,
and no mark or publish lands on a cancelled exam.

**Recipients follow ``exam_scheduled`` exactly**, because both go
through ``deliver_to_families``: an accepted student or guardian of a
seat still active today, and nobody whose link is still pending.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from app.db.models import Exam, Notification
from app.local_time import bangladesh_today
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.conftest import bearer

EXAM_DAY = "2027-04-20"


@dataclass(frozen=True, slots=True)
class Families:
    """The batch's families, by what they should hear.

    :ivar student: An accepted student, told
    :ivar guardian: An accepted guardian whose child has not accepted, told
    :ivar pending_student: A student who has not accepted, not told
    :ivar seat: The accepted student's seat
    """

    student: uuid.UUID
    guardian: uuid.UUID
    pending_student: uuid.UUID
    seat: uuid.UUID


def _families(
    session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> Families:
    """Seat three families with different acceptance on the batch.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: The accounts
    """
    student, guardian, pending = (account_factory() for _ in range(3))
    seat = enroll(
        session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
        guardian_decision="pending",
    )
    enroll(
        session,
        batch_id=teacher.batch_id,
        display_name="Karim",
        student_account_id=account_factory(),
        student_decision="pending",
        guardian_account_id=guardian,
        guardian_decision="accepted",
    )
    enroll(
        session,
        batch_id=teacher.batch_id,
        display_name="Salma",
        student_account_id=pending,
        student_decision="pending",
        guardian_decision="pending",
    )
    return Families(
        student=student, guardian=guardian, pending_student=pending, seat=seat
    )


def _create(
    client: TestClient,
    session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
    *,
    date: str = EXAM_DAY,
) -> str:
    """Schedule an exam over HTTP, so its families are told.

    :param client: The test client
    :param session: A session to issue the token through
    :param teacher: The batch's owner
    :param subject: The subject
    :param date: The exam date
    :return: The exam id
    """
    created = client.post(
        f"/v1/batches/{teacher.batch_id}/exams",
        json={
            "batch_subject_id": str(subject),
            "title": "Unit test",
            "date": date,
            "total_marks": 50,
        },
        headers=bearer(session, teacher.account_id),
    )
    assert created.status_code == 201, created.text
    exam_id: str = created.json()["exam_id"]
    return exam_id


def _cancel(
    client: TestClient,
    session: DbSession,
    account_id: uuid.UUID,
    exam_id: str,
    **body: object,
) -> object:
    """Cancel an exam as an account.

    :param client: The test client
    :param session: A session to issue the token through
    :param account_id: Who is asking
    :param exam_id: The exam
    :param body: The request body, if any
    :return: The response
    """
    return client.post(
        f"/v1/exams/{exam_id}/cancel",
        json=body or None,
        headers=bearer(session, account_id),
    )


def _items(session: DbSession, exam_id: str) -> set[tuple[uuid.UUID, str]]:
    """Read who holds which inbox item for an exam.

    :param session: A reading session
    :param exam_id: The exam
    :return: Each (account, kind) pair
    """
    return {
        (row.account_id, row.kind)
        for row in session.scalars(
            sa.select(Notification).where(Notification.source_id == uuid.UUID(exam_id))
        )
    }


def _status(response: object) -> int:
    """Read a response's status code.

    :param response: The response
    :return: The status
    """
    status: int = response.status_code  # type: ignore[attr-defined]
    return status


def _code(response: object) -> str:
    """Read the error code from an envelope.

    :param response: The response
    :return: The code
    """
    code: str = response.json()["error"]["code"]  # type: ignore[attr-defined]
    return code


def test_cancelling_tells_every_family_the_exam_reached(
    api_client: TestClient,
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The scheduled items are replaced by cancelled ones, for the same people.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param subject: The subject
    :param account_factory: Makes accounts
    :return: None
    """
    families = _families(owner_session, teacher, account_factory)
    exam_id = _create(api_client, owner_session, teacher, subject)
    assert _items(restricted_session, exam_id) == {
        (families.student, "exam_scheduled"),
        (families.guardian, "exam_scheduled"),
    }

    response = _cancel(
        api_client, owner_session, teacher.account_id, exam_id, reason="Hartal"
    )

    assert _status(response) == 200, response.text  # type: ignore[attr-defined]
    body = response.json()  # type: ignore[attr-defined]
    assert body["cancelled"] is True
    assert body["cancellation_reason"] == "Hartal"
    assert _items(restricted_session, exam_id) == {
        (families.student, "exam_cancelled"),
        (families.guardian, "exam_cancelled"),
    }
    previews = {
        row.preview
        for row in restricted_session.scalars(
            sa.select(Notification).where(Notification.kind == "exam_cancelled")
        )
    }
    assert previews == {f"Unit test · {EXAM_DAY}"}
    guardian_copy = restricted_session.scalars(
        sa.select(Notification).where(Notification.account_id == families.guardian)
    ).one()
    assert guardian_copy.child_name == "Karim"


def test_cancelling_twice_changes_nothing(
    api_client: TestClient,
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A second cancel succeeds and sends nobody a second item.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param subject: The subject
    :param account_factory: Makes accounts
    :return: None
    """
    families = _families(owner_session, teacher, account_factory)
    exam_id = _create(api_client, owner_session, teacher, subject)
    first = _cancel(api_client, owner_session, teacher.account_id, exam_id)
    when = restricted_session.get_one(Exam, uuid.UUID(exam_id)).cancelled_at

    second = _cancel(
        api_client, owner_session, teacher.account_id, exam_id, reason="Later"
    )

    assert _status(first) == 200
    assert _status(second) == 200
    assert second.json()["cancelled"] is True  # type: ignore[attr-defined]
    restricted_session.expire_all()
    stored = restricted_session.get_one(Exam, uuid.UUID(exam_id))
    assert stored.cancelled_at == when
    assert stored.cancellation_reason is None
    told = restricted_session.scalars(
        sa.select(Notification).where(Notification.account_id == families.student)
    ).all()
    assert [row.kind for row in told] == ["exam_cancelled"]


def test_a_published_exam_cannot_be_cancelled(
    api_client: TestClient,
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    exam: uuid.UUID,
) -> None:
    """Results families have read are corrected, never cancelled away.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param exam: A published exam
    :return: None
    """
    response = _cancel(api_client, owner_session, teacher.account_id, str(exam))

    assert _status(response) == 409
    assert _code(response) == "EXAM_PUBLISHED"
    assert restricted_session.get_one(Exam, exam).cancelled_at is None


def test_another_teacher_cannot_cancel(
    api_client: TestClient,
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
) -> None:
    """Teacher B gets the same refusal for A's exam as for no exam at all.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: Teacher A
    :param subject: A's subject
    :return: None
    """
    exam_id = _create(api_client, owner_session, teacher, subject)
    other = make_teacher(owner_session, name="Chemistry")

    theirs = _cancel(api_client, owner_session, other.account_id, exam_id)
    absent = _cancel(api_client, owner_session, other.account_id, str(uuid.uuid4()))

    assert _status(theirs) == 403
    assert _code(theirs) == "NOT_AVAILABLE"
    assert theirs.json() == absent.json()  # type: ignore[attr-defined]
    assert restricted_session.get_one(Exam, uuid.UUID(exam_id)).cancelled_at is None


def test_a_family_lens_cannot_cancel(
    api_client: TestClient,
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The batch's own student cannot call its exam off.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param subject: The subject
    :param account_factory: Makes accounts
    :return: None
    """
    families = _families(owner_session, teacher, account_factory)
    exam_id = _create(api_client, owner_session, teacher, subject)

    response = _cancel(api_client, owner_session, families.student, exam_id)

    assert _status(response) == 403
    assert restricted_session.get_one(Exam, uuid.UUID(exam_id)).cancelled_at is None


def test_no_mark_publish_or_edit_lands_on_a_cancelled_exam(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Writes against a cancelled exam are refused; its results read unwritable.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param subject: The subject
    :param account_factory: Makes accounts
    :return: None
    """
    families = _families(owner_session, teacher, account_factory)
    exam_id = _create(
        api_client,
        owner_session,
        teacher,
        subject,
        date=(bangladesh_today() - dt.timedelta(days=1)).isoformat(),
    )
    _cancel(api_client, owner_session, teacher.account_id, exam_id)
    headers = bearer(owner_session, teacher.account_id)

    mark = api_client.post(
        f"/v1/exams/{exam_id}/marks",
        json={
            "enrollment_id": str(families.seat),
            "result_state": "marked",
            "marks": 40,
        },
        headers=headers,
    )
    publish = api_client.post(f"/v1/exams/{exam_id}/publish", headers=headers)
    edit = api_client.put(
        f"/v1/exams/{exam_id}",
        json={"title": "Renamed", "date": EXAM_DAY, "total_marks": 50},
        headers=headers,
    )
    results = api_client.get(f"/v1/exams/{exam_id}/results", headers=headers)

    for refused in (mark, publish, edit):
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"]["code"] == "EXAM_CANCELLED"
    assert results.status_code == 200
    assert results.json()["writable"] is False
    assert results.json()["exam"]["cancelled"] is True


def test_the_teacher_list_keeps_it_marked_cancelled(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
) -> None:
    """The batch's exam list still shows it, flagged, in its place.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param subject: The subject
    :return: None
    """
    kept = _create(api_client, owner_session, teacher, subject)
    called_off = _create(api_client, owner_session, teacher, subject)
    _cancel(api_client, owner_session, teacher.account_id, called_off)

    listed = api_client.get(
        f"/v1/batches/{teacher.batch_id}/exams",
        headers=bearer(owner_session, teacher.account_id),
    )

    assert listed.status_code == 200
    flags = {row["exam_id"]: row["cancelled"] for row in listed.json()}
    assert flags == {kept: False, called_off: True}


def test_upcoming_and_today_views_leave_it_out(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Teacher's next exam and today, family's batch view: no cancelled exam.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param subject: The subject
    :param account_factory: Makes accounts
    :return: None
    """
    families = _families(owner_session, teacher, account_factory)
    exam_id = _create(
        api_client,
        owner_session,
        teacher,
        subject,
        date=dt.datetime.now(tz=dt.UTC).date().isoformat(),
    )
    _cancel(api_client, owner_session, teacher.account_id, exam_id)
    teacher_headers = bearer(owner_session, teacher.account_id)
    family_headers = bearer(owner_session, families.student)

    overview = api_client.get("/v1/me/overview", headers=teacher_headers)
    today = api_client.get("/v1/me/today", headers=teacher_headers)
    family = api_client.get(
        f"/v1/me/batches/{families.seat}/teaching", headers=family_headers
    )
    one = api_client.get(
        f"/v1/me/enrollments/{families.seat}/exams/{exam_id}",
        headers=family_headers,
    )

    assert overview.status_code == 200, overview.text
    assert overview.json()["next_exam"] is None
    assert today.status_code == 200, today.text
    assert exam_id not in today.text
    assert family.status_code == 200, family.text
    assert family.json()["upcoming_exam"] is None
    assert family.json()["exams"] == []
    assert one.status_code == 403


def test_the_inbox_item_opens_to_the_cancelled_exam(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The family's item lists under the new kind and opens to the exam.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param subject: The subject
    :param account_factory: Makes accounts
    :return: None
    """
    families = _families(owner_session, teacher, account_factory)
    exam_id = _create(api_client, owner_session, teacher, subject)
    _cancel(api_client, owner_session, teacher.account_id, exam_id)
    headers = bearer(owner_session, families.student)

    listed = api_client.get("/v1/me/notifications", headers=headers)
    assert listed.status_code == 200, listed.text
    [item] = listed.json()["items"]
    assert item["kind"] == "exam_cancelled"

    opened = api_client.get(
        f"/v1/me/notifications/{item['notification_id']}", headers=headers
    )
    assert opened.status_code == 200, opened.text
    assert opened.json()["available"] is True
    assert opened.json()["exam"]["exam_id"] == exam_id
    assert opened.json()["exam"]["cancelled"] is True
