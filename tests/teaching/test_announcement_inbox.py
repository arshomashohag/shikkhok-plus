"""Notices reach the inbox and stay in step with the notice.

Written from the acceptance criteria: who receives, one row per child,
edit re-flags unread, delete removes, and a refused post writes nothing.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import Enrollment, Notification
from app.errors import AuthorizationError
from app.notifications.inbox import NOTICE, inbox, mark_read
from app.teaching.announcements import (
    PREVIEW_LENGTH,
    delete_announcement,
    edit_announcement,
    post_announcement,
)
from tests.batches.conftest import TeacherFixture, enroll, make_teacher


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the fixture teacher's lens.

    :param teacher: The teacher fixture
    :return: The lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def test_posting_a_notice_reaches_every_accepted_family_member(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    student, guardian, stranger = (
        account_factory(),
        account_factory(),
        account_factory(),
    )
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted",
    )
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Pending",
        student_account_id=stranger,
        student_decision="pending",
    )
    posted = post_announcement(
        restricted_session,
        lens=_lens(teacher),
        batch_id=teacher.batch_id,
        body="x" * 200,
    )
    for account in (student, guardian):
        items = inbox(restricted_session, account_id=account).items
        assert [(i.kind, i.source_id) for i in items] == [
            (NOTICE, posted.announcement_id)
        ]
        assert items[0].preview == "x" * 59 + "\u2026"
    assert inbox(restricted_session, account_id=stranger).items == []


def test_guardian_with_two_children_gets_one_item_per_child(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    guardian = account_factory()
    for name in ("Rahim", "Karim"):
        enroll(
            owner_session,
            batch_id=teacher.batch_id,
            display_name=name,
            guardian_account_id=guardian,
            guardian_decision="accepted",
        )
    post_announcement(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id, body="Hi"
    )
    items = inbox(restricted_session, account_id=guardian).items
    assert sorted(i.child_name or "" for i in items) == ["Karim", "Rahim"]
    assert len({i.enrollment_id for i in items}) == 2


def test_editing_a_notice_marks_it_unread_again_and_updates_preview(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    student = account_factory()
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    posted = post_announcement(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id, body="old"
    )
    mark_read(restricted_session, account_id=student)
    assert inbox(restricted_session, account_id=student).unread == 0

    edit_announcement(
        restricted_session,
        lens=_lens(teacher),
        announcement_id=posted.announcement_id,
        body="new",
    )
    after = inbox(restricted_session, account_id=student)
    assert after.unread == 1
    assert after.items[0].preview == "new"


def test_editing_a_notice_leaves_people_who_lost_access_untouched(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """An edit reaches only the people the notice would reach today.

    A guardian who declined after the notice was posted, and a seat that
    has since left, keep their copy as it was -- old preview, still read
    -- because an edit flagged unread to someone who lost access is the
    new text leaking to them [BR5.2].

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, guardian, leaver = account_factory(), account_factory(), account_factory()
    kept = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted",
    )
    gone = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Karim",
        student_account_id=leaver,
        student_decision="accepted",
    )
    posted = post_announcement(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id, body="old"
    )
    for account in (student, guardian, leaver):
        mark_read(restricted_session, account_id=account)
    owner_session.get_one(Enrollment, kept).guardian_decision = "declined"
    owner_session.get_one(Enrollment, gone).inactive_from = dt.date(2000, 1, 1)
    owner_session.commit()

    edit_announcement(
        restricted_session,
        lens=_lens(teacher),
        announcement_id=posted.announcement_id,
        body="new",
    )

    for lost in (guardian, leaver):
        after = inbox(restricted_session, account_id=lost)
        assert (after.unread, after.items[0].preview) == (0, "old")
    still = inbox(restricted_session, account_id=student)
    assert (still.unread, still.items[0].preview) == (1, "new")


def test_deleting_a_read_notice_removes_it_and_unread_count_stays_correct(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    student = account_factory()
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    read = post_announcement(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id, body="a"
    )
    mark_read(restricted_session, account_id=student)
    unread = post_announcement(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id, body="b"
    )

    delete_announcement(
        restricted_session, lens=_lens(teacher), announcement_id=read.announcement_id
    )
    after = inbox(restricted_session, account_id=student)
    assert [i.source_id for i in after.items] == [unread.announcement_id]
    assert after.unread == 1


def test_notice_rows_commit_with_the_notice(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    student = account_factory()
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    other = make_teacher(owner_session, name="Other")
    with pytest.raises(AuthorizationError):
        post_announcement(
            restricted_session,
            lens=TeacherLens(account_id=other.account_id, owner_id=other.owner_id),
            batch_id=teacher.batch_id,
            body="nope",
        )
    count = owner_session.scalar(
        sa.select(sa.func.count())
        .select_from(Notification)
        .where(Notification.kind == NOTICE)
    )
    assert count == 0


def test_fan_out_is_one_insert_whatever_the_batch_size(
    owner_session: DbSession,
    restricted_session: DbSession,
    restricted_engine: sa.Engine,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A notice to many seats writes its inbox rows in one statement.

    Row-by-row ORM inserts cost about ten times as much at a thousand
    seats; this keeps the fan-out from sliding back to them.
    """
    seats = 25
    for index in range(seats):
        enroll(
            owner_session,
            batch_id=teacher.batch_id,
            display_name=f"Child {index}",
            student_account_id=account_factory(),
            guardian_account_id=account_factory(),
            student_decision="accepted",
            guardian_decision="accepted",
        )
    inserts: list[str] = []

    def count(*args: object) -> None:
        statement = str(args[2])
        if statement.lstrip().upper().startswith("INSERT INTO NOTIFICATION"):
            inserts.append(statement)

    sa.event.listen(restricted_engine, "before_cursor_execute", count)
    try:
        post_announcement(
            restricted_session,
            lens=_lens(teacher),
            batch_id=teacher.batch_id,
            body="Hi",
        )
    finally:
        sa.event.remove(restricted_engine, "before_cursor_execute", count)

    assert len(inserts) == 1
    written = restricted_session.scalar(
        sa.select(sa.func.count()).select_from(Notification)
    )
    assert written == seats * 2


def test_preview_length_is_the_inbox_line_length() -> None:
    assert PREVIEW_LENGTH == 60
