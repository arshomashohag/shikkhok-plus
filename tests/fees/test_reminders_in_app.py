"""Fee reminders delivered to the app's inbox, and the inbox itself.

**Written before either existed.** A reminder is an authorization act --
a teacher reaches into someone else's inbox -- so the scoping is
test-first: only the teacher who owns the batch can send one, only the
accounts that ACCEPTED the seat receive it [BR5.2], and an inbox shows
its owner's notifications and nobody else's.

**At most one reminder per seat a day.** A teacher tapping "Remind" twice
should not send a student two identical nudges, and the second tap says
how many were skipped rather than failing.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.errors import AuthorizationError
from app.fees.ledger_writer import append_entry
from app.fees.reminders import remind
from app.money import Money
from app.notifications.inbox import inbox, mark_read
from tests.batches.conftest import TeacherFixture, enroll, make_teacher


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build a teacher's lens.

    :param teacher: The teacher
    :return: Their lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def _owing_seat(
    session: Session,
    teacher: TeacherFixture,
    student: uuid.UUID,
    guardian: uuid.UUID | None = None,
    guardian_decision: str = "accepted",
) -> uuid.UUID:
    """Seat a student who owes October's 1200.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param student: The student's account
    :param guardian: The guardian's account, if any
    :param guardian_decision: The guardian link's decision
    :return: The seat
    """
    seat = enroll(
        session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision=guardian_decision if guardian else None,
    )
    append_entry(
        session,
        enrollment_id=seat,
        period="2026-10",
        kind="charge",
        amount=Money("1200.00"),
    )
    session.commit()
    return seat


def test_a_reminder_reaches_the_student_and_guardian_who_accepted(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Both accepted accounts get one notification naming what is owed.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, guardian = account_factory(), account_factory()
    seat = _owing_seat(owner_session, teacher, student, guardian)

    result = remind(restricted_session, lens=_lens(teacher), enrollment_ids=[seat])

    assert (result.sent, result.skipped) == (1, 0)
    for account in (student, guardian):
        [note] = inbox(restricted_session, account_id=account).items
        assert note.kind == "fee_reminder"
        assert note.amount == Money("1200.00")
        assert note.period == "2026-10"
        assert note.read is False


def test_a_guardian_who_has_not_accepted_receives_nothing(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A pending link is a stranger to this seat until they accept [BR5.2].

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, guardian = account_factory(), account_factory()
    seat = _owing_seat(
        owner_session, teacher, student, guardian, guardian_decision="pending"
    )

    remind(restricted_session, lens=_lens(teacher), enrollment_ids=[seat])

    assert inbox(restricted_session, account_id=guardian).items == []
    assert len(inbox(restricted_session, account_id=student).items) == 1


def test_another_teacher_cannot_remind_this_batch(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Reaching a stranger's seat is refused, and nothing is delivered.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = _owing_seat(owner_session, teacher, student)
    stranger = make_teacher(owner_session, name="Chemistry")

    with pytest.raises(AuthorizationError):
        remind(restricted_session, lens=_lens(stranger), enrollment_ids=[seat])

    assert inbox(restricted_session, account_id=student).items == []


def test_a_second_reminder_the_same_day_is_skipped(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Tapping twice sends once, and says one was skipped.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = _owing_seat(owner_session, teacher, student)
    lens = _lens(teacher)

    remind(restricted_session, lens=lens, enrollment_ids=[seat])
    again = remind(restricted_session, lens=lens, enrollment_ids=[seat])
    later = remind(
        restricted_session,
        lens=lens,
        enrollment_ids=[seat],
        now=dt.datetime.now(tz=dt.UTC) + dt.timedelta(days=2),
    )

    assert (again.sent, again.skipped) == (0, 1)
    assert later.sent == 1
    assert len(inbox(restricted_session, account_id=student).items) == 2


def test_a_seat_that_owes_nothing_is_not_reminded(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A paid-up student is never nudged about money.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = _owing_seat(owner_session, teacher, student)
    append_entry(
        owner_session,
        enrollment_id=seat,
        period="2026-10",
        kind="receipt",
        amount=Money("1200.00"),
    )
    owner_session.commit()

    result = remind(restricted_session, lens=_lens(teacher), enrollment_ids=[seat])

    assert (result.sent, result.skipped) == (0, 1)
    assert inbox(restricted_session, account_id=student).items == []


def test_an_inbox_counts_unread_and_reading_clears_it(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The badge's number, and that opening the inbox clears it.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = _owing_seat(owner_session, teacher, student)
    remind(restricted_session, lens=_lens(teacher), enrollment_ids=[seat])

    before = inbox(restricted_session, account_id=student)
    mark_read(restricted_session, account_id=student)
    after = inbox(restricted_session, account_id=student)

    assert before.unread == 1
    assert after.unread == 0
    assert after.items[0].read is True


def test_an_inbox_is_its_owners_alone(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Another account's notifications never appear, and reading one's
    own inbox leaves theirs unread.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, stranger = account_factory(), account_factory()
    seat = _owing_seat(owner_session, teacher, student)
    remind(restricted_session, lens=_lens(teacher), enrollment_ids=[seat])

    mark_read(restricted_session, account_id=stranger)

    assert inbox(restricted_session, account_id=stranger).items == []
    assert inbox(restricted_session, account_id=student).unread == 1
