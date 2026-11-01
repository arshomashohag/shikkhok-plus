"""Marks-available inbox items.

**Written before the implementation.** Whether a family is told its
result is out depends on the visibility toggle and on whether this is
the first live mark, so a wrong answer either leaks a result a teacher
chose to hide or tells a family twice.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import Batch, Notification
from app.marks.entry import record_mark
from app.marks.views import set_marksheet_visible
from app.notifications.inbox import MARKS_AVAILABLE
from tests.batches.conftest import TeacherFixture


def _set_visible(session: DbSession, teacher: TeacherFixture, visible: bool) -> None:
    """Force the stored toggle without going through the writer.

    :param session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :param visible: The stored value
    :return: None
    """
    batch = session.get(Batch, teacher.batch_id)
    assert batch is not None
    batch.marksheet_visible = visible
    session.commit()


def _mark(
    session: DbSession,
    lens: TeacherLens,
    exam: uuid.UUID,
    seat: uuid.UUID,
    value: int = 70,
) -> None:
    """Record a marked result.

    :param session: The session to work through
    :param lens: The teacher lens
    :param exam: The exam
    :param seat: The seat
    :param value: The mark
    :return: None
    """
    record_mark(
        session,
        lens=lens,
        exam_id=exam,
        enrollment_id=seat,
        result_state="marked",
        marks=value,
    )


def _rows(session: DbSession, account: uuid.UUID) -> list[Notification]:
    """List an account's marks-available rows.

    :param session: A session able to read
    :param account: The recipient
    :return: Its rows
    """
    session.expire_all()
    return list(
        session.scalars(
            sa.select(Notification).where(
                Notification.account_id == account,
                Notification.kind == MARKS_AVAILABLE,
            )
        )
    )


def test_first_mark_while_visible_notifies_the_seat(
    owner_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    """A first result on a visible batch reaches the seat's student."""
    _set_visible(owner_session, teacher, True)
    account = account_factory()
    seat = seat_factory(student_account_id=account)

    _mark(owner_session, teacher_lens, exam, seat)

    [row] = _rows(owner_session, account)
    assert (row.source_id, row.enrollment_id, row.preview) == (
        exam,
        seat,
        "April test",
    )


def test_mark_while_hidden_notifies_nobody(
    owner_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    """A hidden marksheet announces nothing."""
    _set_visible(owner_session, teacher, False)
    account = account_factory()
    seat = seat_factory(student_account_id=account)

    _mark(owner_session, teacher_lens, exam, seat)

    assert _rows(owner_session, account) == []


def test_turning_visibility_on_notifies_marked_seats_once(
    owner_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    """Showing the sheet tells marked seats, and toggling again adds none."""
    _set_visible(owner_session, teacher, False)
    marked_account, unmarked_account = account_factory(), account_factory()
    marked = seat_factory(student_account_id=marked_account)
    seat_factory(student_account_id=unmarked_account)
    _mark(owner_session, teacher_lens, exam, marked)

    set_marksheet_visible(
        owner_session, lens=teacher_lens, batch_id=teacher.batch_id, visible=True
    )
    set_marksheet_visible(
        owner_session, lens=teacher_lens, batch_id=teacher.batch_id, visible=False
    )
    set_marksheet_visible(
        owner_session, lens=teacher_lens, batch_id=teacher.batch_id, visible=True
    )

    assert len(_rows(owner_session, marked_account)) == 1
    assert _rows(owner_session, unmarked_account) == []


def test_correcting_a_mark_does_not_notify_again(
    owner_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    """Only the first live result announces; a correction is silent."""
    _set_visible(owner_session, teacher, True)
    account = account_factory()
    seat = seat_factory(student_account_id=account)

    _mark(owner_session, teacher_lens, exam, seat, 70)
    _mark(owner_session, teacher_lens, exam, seat, 75)

    assert len(_rows(owner_session, account)) == 1
