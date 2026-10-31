"""The inbox on the wire: every kind, one item's detail, one item read.

**Written before the implementation.** Detail decides whose content an
account may open and whether a removed seat still shows it, so a wrong
answer is an authorization error: another account's id is refused in
the same shape as a missing one, and a seat that is gone yields
``available=false`` instead of the source's content.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import (
    Announcement,
    BatchSubject,
    Enrollment,
    Exam,
    Notification,
    PaymentClaim,
)
from app.money import Money
from app.notifications import inbox as kinds
from app.notifications.inbox import deliver
from tests.batches.conftest import TeacherFixture, enroll
from tests.conftest import bearer

NOW = dt.datetime(2026, 10, 20, 9, 0, tzinfo=dt.UTC)


def _student_seat(
    session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seat an accepted student.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: The student's account and the seat
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


def _deliver(
    session: Session,
    *,
    account_id: uuid.UUID,
    kind: str,
    seat: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Put one item in an inbox and return its id.

    :param session: An arranging session
    :param account_id: The recipient
    :param kind: The kind
    :param seat: The seat it is about
    :param source_id: The record behind it
    :return: The notification id
    """
    deliver(
        session,
        account_ids=[account_id],
        kind=kind,
        batch_name="Batch",
        now=NOW,
        enrollment_id=seat,
        source_id=source_id,
    )
    session.commit()
    return session.scalars(
        sa.select(Notification.id).where(
            Notification.account_id == account_id, Notification.kind == kind
        )
    ).one()


def _claim(
    session: Session,
    seat: uuid.UUID,
    *,
    status: str,
    approved: str | None,
    reason: str | None = None,
) -> uuid.UUID:
    """Create a claim of 1200 in the given state.

    :param session: An arranging session
    :param seat: The seat
    :param status: The stored status
    :param approved: The approved amount, if decided
    :param reason: The rejection reason, if rejected
    :return: The claim id
    """
    claim = PaymentClaim(
        enrollment_id=seat,
        period="2026-10",
        claimed_amount=Money("1200.00"),
        channel="bkash",
        submitted_at=NOW,
        status=status,
        approved_amount=None if approved is None else Money(approved),
        rejection_reason=reason,
    )
    session.add(claim)
    session.commit()
    return claim.id


def test_every_stored_kind_is_published(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """All eight kinds list without raising.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, seat = _student_seat(owner_session, teacher, account_factory)
    every = [
        kinds.FEE_REMINDER,
        kinds.PAYMENT_APPROVED,
        kinds.PAYMENT_PARTIAL,
        kinds.PAYMENT_REJECTED,
        kinds.NOTICE,
        kinds.EXAM_SCHEDULED,
        kinds.MARKS_AVAILABLE,
        kinds.CLAIM_TO_VERIFY,
    ]
    for kind in every:
        _deliver(owner_session, account_id=student, kind=kind, seat=seat)

    found = api_client.get(
        "/v1/me/notifications", headers=bearer(owner_session, student)
    )

    assert found.status_code == 200
    assert sorted(i["kind"] for i in found.json()["items"]) == sorted(every)


def test_detail_of_another_accounts_item_is_404_shaped_authorization_error(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A foreign id and a missing id are refused identically.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, seat = _student_seat(owner_session, teacher, account_factory)
    theirs = _deliver(
        owner_session, account_id=student, kind=kinds.FEE_REMINDER, seat=seat
    )
    stranger = bearer(owner_session, account_factory())

    foreign = api_client.get(f"/v1/me/notifications/{theirs}", headers=stranger)
    missing = api_client.get(f"/v1/me/notifications/{uuid.uuid4()}", headers=stranger)

    assert foreign.status_code == missing.status_code
    assert foreign.json() == missing.json()
    assert foreign.json()["error"]["message_key"] == "inbox.not_available"


def test_detail_after_seat_removed_is_unavailable_not_an_error(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A removed seat gives available=false and no content.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, seat = _student_seat(owner_session, teacher, account_factory)
    notice = Announcement(batch_id=teacher.batch_id, body="Hello", created_at=NOW)
    owner_session.add(notice)
    owner_session.commit()
    item = _deliver(
        owner_session,
        account_id=student,
        kind=kinds.NOTICE,
        seat=seat,
        source_id=notice.id,
    )
    headers = bearer(owner_session, student)
    owner_session.execute(
        sa.update(Enrollment)
        .where(Enrollment.id == seat)
        .values(student_account_id=None)
    )
    owner_session.commit()

    found = api_client.get(f"/v1/me/notifications/{item}", headers=headers)

    assert found.status_code == 200
    assert found.json()["available"] is False
    assert found.json().get("notice") is None


def test_deleted_notice_is_unavailable(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A soft-deleted notice is unavailable.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :param account_factory: Makes accounts
    :return: None
    """
    student, seat = _student_seat(owner_session, teacher, account_factory)
    notice = Announcement(
        batch_id=teacher.batch_id, body="Hello", created_at=NOW, deleted_at=NOW
    )
    owner_session.add(notice)
    owner_session.commit()
    item = _deliver(
        owner_session,
        account_id=student,
        kind=kinds.NOTICE,
        seat=seat,
        source_id=notice.id,
    )

    found = api_client.get(
        f"/v1/me/notifications/{item}", headers=bearer(owner_session, student)
    )

    assert found.json()["available"] is False


def test_notice_detail_carries_current_body_after_edit(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The detail reads the notice as it is now, not as it was sent.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, seat = _student_seat(owner_session, teacher, account_factory)
    notice = Announcement(batch_id=teacher.batch_id, body="Old", created_at=NOW)
    owner_session.add(notice)
    owner_session.commit()
    item = _deliver(
        owner_session,
        account_id=student,
        kind=kinds.NOTICE,
        seat=seat,
        source_id=notice.id,
    )
    notice.body = "New"
    notice.edited_at = NOW + dt.timedelta(hours=1)
    owner_session.commit()

    found = api_client.get(
        f"/v1/me/notifications/{item}", headers=bearer(owner_session, student)
    ).json()

    assert found["available"] is True
    assert found["notice"]["body"] == "New"
    assert found["notice"]["edited_at"] is not None
    assert found["exam"] is None


def test_exam_detail_carries_topics_and_subject(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """An exam item opens to its title, subject, marks and topics.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, seat = _student_seat(owner_session, teacher, account_factory)
    subject = BatchSubject(batch_id=teacher.batch_id, name="Physics")
    owner_session.add(subject)
    owner_session.commit()
    exam = Exam(
        batch_id=teacher.batch_id,
        batch_subject_id=subject.id,
        title="Unit test",
        date=dt.date(2026, 11, 5),
        total_marks=50,
        topics=["Motion", "Force"],
        created_at=NOW,
    )
    owner_session.add(exam)
    owner_session.commit()
    item = _deliver(
        owner_session,
        account_id=student,
        kind=kinds.EXAM_SCHEDULED,
        seat=seat,
        source_id=exam.id,
    )

    found = api_client.get(
        f"/v1/me/notifications/{item}", headers=bearer(owner_session, student)
    ).json()

    assert found["exam"] == {
        "exam_id": str(exam.id),
        "title": "Unit test",
        "date": "2026-11-05",
        "subject_name": "Physics",
        "total_marks": 50,
        "topics": ["Motion", "Force"],
    }


def test_payment_detail_carries_reason(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A rejected payment opens with its reason; partial and pending too.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, seat = _student_seat(owner_session, teacher, account_factory)
    headers = bearer(owner_session, student)
    cases = [
        (kinds.PAYMENT_REJECTED, "rejected", None, "Wrong number", "rejected"),
        (kinds.PAYMENT_PARTIAL, "approved_partial", "800.00", None, "partial"),
        (kinds.PAYMENT_APPROVED, "approved_full", "1200.00", None, "approved"),
    ]
    for kind, status, approved, reason, outcome in cases:
        claim = _claim(
            owner_session, seat, status=status, approved=approved, reason=reason
        )
        item = _deliver(
            owner_session,
            account_id=student,
            kind=kind,
            seat=seat,
            source_id=claim,
        )

        found = api_client.get(f"/v1/me/notifications/{item}", headers=headers).json()

        assert found["payment"]["outcome"] == outcome
        assert found["payment"]["reason"] == reason
        assert found["payment"]["claimed"] == "1200.00"
        assert found["payment"]["approved"] == approved


def test_claim_to_verify_is_available_to_the_owning_teacher_only(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The teacher sees it; once the claim is gone it is unavailable.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    _, seat = _student_seat(owner_session, teacher, account_factory)
    claim = _claim(owner_session, seat, status="pending", approved=None)
    item = _deliver(
        owner_session,
        account_id=teacher.account_id,
        kind=kinds.CLAIM_TO_VERIFY,
        seat=seat,
        source_id=claim,
    )
    headers = bearer(owner_session, teacher.account_id)

    first = api_client.get(f"/v1/me/notifications/{item}", headers=headers)
    owner_session.execute(sa.delete(PaymentClaim))
    owner_session.commit()
    second = api_client.get(f"/v1/me/notifications/{item}", headers=headers)

    assert first.json()["available"] is True
    assert second.json()["available"] is False


def test_read_one_marks_only_that_item(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Reading one leaves the others unread; detail alone marks nothing.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, seat = _student_seat(owner_session, teacher, account_factory)
    first = _deliver(
        owner_session, account_id=student, kind=kinds.FEE_REMINDER, seat=seat
    )
    _deliver(owner_session, account_id=student, kind=kinds.MARKS_AVAILABLE, seat=seat)
    headers = bearer(owner_session, student)

    api_client.get(f"/v1/me/notifications/{first}", headers=headers)
    opened = api_client.get("/v1/me/notifications", headers=headers).json()
    marked = api_client.post(f"/v1/me/notifications/{first}/read", headers=headers)
    after = api_client.get("/v1/me/notifications", headers=headers).json()

    assert opened["unread"] == 2
    assert marked.status_code == 204
    assert after["unread"] == 1
    assert {i["notification_id"]: i["read"] for i in after["items"]}[str(first)] is True
