"""The inbox reads only the kinds the client can show [PO-10].

**Written before the implementation.** Both clients drop a kind they do
not know, so a server that counts it in ``unread`` shows an old install a
badge with no message behind it. The rule pinned here: a client names
the kinds it can draw with ``?kind=``; the items and the unread count are
both taken over those; a client that names none is one built before the
announcement and gets the frozen legacy set; and "mark all read" leaves
a kind the client never drew unread for the client that will.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Notification
from app.notifications import inbox as kinds
from app.notifications.inbox import ClassChange, deliver
from tests.batches.conftest import TeacherFixture, enroll
from tests.conftest import bearer

NOW = dt.datetime(2026, 10, 20, 9, 0, tzinfo=dt.UTC)

#: Every kind the server publishes today.
EVERY = sorted(kinds.LEGACY_KINDS | {kinds.CLASS_CANCELLED, kinds.CLASS_RESCHEDULED})


def _student_with(
    session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
    stored: list[str],
) -> uuid.UUID:
    """Seat an accepted student and give them one unread item per kind.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :param stored: The kinds to deliver
    :return: The student's account
    """
    student = account_factory()
    seat = enroll(
        session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    for kind in stored:
        deliver(
            session,
            account_ids=[student],
            kind=kind,
            batch_name="Physics",
            now=NOW,
            enrollment_id=seat,
            source_id=uuid.uuid4(),
            class_change=ClassChange(
                class_date=dt.date(2099, 4, 14),
                class_time=dt.time(18, 0),
                moved_from_date=dt.date(2099, 4, 12),
                moved_from_time=dt.time(16, 0),
            )
            if kind == kinds.CLASS_RESCHEDULED
            else None,
        )
    session.commit()
    return student


def test_legacy_kinds_are_exactly_the_ten_before_announcement() -> None:
    """The frozen set never grows: that is what makes it a version.

    :return: None
    """
    assert sorted(kinds.LEGACY_KINDS) == sorted(
        [
            "fee_reminder",
            "payment_approved",
            "payment_partial",
            "payment_rejected",
            "payment_recorded",
            "notice",
            "exam_scheduled",
            "exam_cancelled",
            "marks_available",
            "claim_to_verify",
        ]
    )


def test_a_client_that_announces_nothing_counts_only_what_it_can_draw(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """An old install sees no class item and no badge for one.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = _student_with(
        owner_session,
        teacher,
        account_factory,
        [kinds.NOTICE, kinds.CLASS_CANCELLED, kinds.CLASS_RESCHEDULED],
    )

    found = api_client.get(
        "/v1/me/notifications", headers=bearer(owner_session, student)
    )

    assert found.status_code == 200
    assert [i["kind"] for i in found.json()["items"]] == ["notice"]
    assert found.json()["unread"] == 1


def test_a_client_that_announces_the_new_kinds_gets_them_and_counts_them(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Every published kind lists, and the count covers all of them.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = _student_with(owner_session, teacher, account_factory, EVERY)

    found = api_client.get(
        "/v1/me/notifications",
        params=[("kind", kind) for kind in EVERY],
        headers=bearer(owner_session, student),
    )

    assert found.status_code == 200
    assert sorted(i["kind"] for i in found.json()["items"]) == EVERY
    assert found.json()["unread"] == len(EVERY)


def test_the_count_matches_the_items_for_whatever_the_client_announces(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Announcing a subset, or a kind this server has never heard of.

    An unknown kind is ignored rather than refused, so a client newer
    than the server still reads its inbox.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = _student_with(owner_session, teacher, account_factory, EVERY)

    found = api_client.get(
        "/v1/me/notifications",
        params=[("kind", "class_cancelled"), ("kind", "from_the_future")],
        headers=bearer(owner_session, student),
    )

    assert found.status_code == 200
    assert [i["kind"] for i in found.json()["items"]] == ["class_cancelled"]
    assert found.json()["unread"] == 1


def test_a_class_change_carries_its_days_and_times_on_the_wire(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The client formats the dates itself, in the reader's language.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = _student_with(
        owner_session, teacher, account_factory, [kinds.CLASS_RESCHEDULED]
    )

    item = api_client.get(
        "/v1/me/notifications",
        params={"kind": "class_rescheduled"},
        headers=bearer(owner_session, student),
    ).json()["items"][0]

    assert item["batch_name"] == "Physics"
    assert item["class_date"] == "2099-04-14"
    assert item["class_time"] == "18:00:00"
    assert item["moved_from_date"] == "2099-04-12"
    assert item["moved_from_time"] == "16:00:00"
    assert item["preview"] is None

    detail = api_client.get(
        f"/v1/me/notifications/{item['notification_id']}",
        headers=bearer(owner_session, student),
    ).json()
    assert detail["available"] is True
    assert detail["class_date"] == "2099-04-14"


def test_mark_all_read_leaves_unannounced_kinds_unread(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """An old install's "Mark all read" does not mark a message it never drew.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = _student_with(
        owner_session, teacher, account_factory, [kinds.NOTICE, kinds.CLASS_CANCELLED]
    )
    headers = bearer(owner_session, student)

    marked = api_client.post("/v1/me/notifications/read", headers=headers)

    assert marked.status_code == 204
    unread = owner_session.scalars(
        sa.select(Notification.kind).where(
            Notification.account_id == student, Notification.read_at.is_(None)
        )
    ).all()
    assert unread == [kinds.CLASS_CANCELLED]

    api_client.post(
        "/v1/me/notifications/read",
        params=[("kind", kind) for kind in EVERY],
        headers=headers,
    )
    owner_session.expire_all()
    assert (
        owner_session.scalars(
            sa.select(Notification.kind).where(
                Notification.account_id == student, Notification.read_at.is_(None)
            )
        ).all()
        == []
    )
