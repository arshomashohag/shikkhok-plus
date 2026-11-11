"""Families hear when a class is cancelled or moved [PO-1].

**Written before the implementation.** Who receives is an
authorization-shaped decision: a seat whose student or guardian has not
accepted is a number a teacher typed, not that person's agreement, and
telling them a class time names a child's whereabouts. So the recipient
rule is pinned first -- accepted links receive, pending and declined
links and the teacher do not -- and then what the item carries, that a
second reschedule replaces rather than stacks, and that a refused or
past change writes nothing.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import Notification, Session
from app.errors import ConflictError
from app.notifications.inbox import CLASS_CANCELLED, CLASS_RESCHEDULED
from app.teaching.sessions import cancel_session, reschedule_session
from tests.batches.conftest import TeacherFixture, enroll

#: Far enough ahead that "today" never overtakes it.
CLASS_DAY = dt.date(2099, 4, 12)
MOVED_DAY = dt.date(2099, 4, 14)
MOVED_AGAIN = dt.date(2099, 4, 16)
FOUR_PM = dt.time(16, 0)
SIX_PM = dt.time(18, 0)


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the fixture teacher's lens.

    :param teacher: The teacher fixture
    :return: The lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def _class(
    session: DbSession,
    teacher: TeacherFixture,
    *,
    on: dt.date = CLASS_DAY,
    status: str = "scheduled",
) -> uuid.UUID:
    """Add one session to the teacher's batch.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param on: Its date
    :param status: Its stored status
    :return: The session id
    """
    row = Session(
        batch_id=teacher.batch_id,
        date=on,
        start_time=FOUR_PM,
        status=status,
        origin="recurrence",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(row)
    session.commit()
    return row.id


def _items(session: DbSession, source_id: uuid.UUID) -> list[Notification]:
    """Every inbox row a session produced, by recipient.

    :param session: A session to read through
    :param source_id: The session
    :return: The rows
    """
    return list(
        session.scalars(
            sa.select(Notification)
            .where(Notification.source_id == source_id)
            .order_by(Notification.account_id)
        )
    )


@pytest.fixture
def family(
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> dict[str, uuid.UUID]:
    """One accepted seat, one pending seat and one declined seat.

    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: Accounts by role, plus the accepted seat
    """
    people = {
        name: account_factory()
        for name in (
            "student",
            "guardian",
            "pending_student",
            "pending_guardian",
            "declined_student",
            "declined_guardian",
        )
    }
    people["seat"] = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=people["student"],
        guardian_account_id=people["guardian"],
        student_decision="accepted",
        guardian_decision="accepted",
    )
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Karim",
        student_account_id=people["pending_student"],
        guardian_account_id=people["pending_guardian"],
        student_decision="pending",
        guardian_decision="pending",
    )
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Salma",
        student_account_id=people["declined_student"],
        guardian_account_id=people["declined_guardian"],
        student_decision="declined",
        guardian_decision="declined",
    )
    return people


# ------------------------------------------------------- who receives


@pytest.mark.parametrize("change", ["cancel", "reschedule"])
def test_only_accepted_family_members_hear_of_a_class_change(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    family: dict[str, uuid.UUID],
    change: str,
) -> None:
    """Accepted student and guardian receive; pending, declined and teacher do not.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param teacher: The batch's owner
    :param family: The seats
    :param change: Which write the teacher makes
    :return: None
    """
    class_id = _class(owner_session, teacher)

    if change == "cancel":
        cancel_session(restricted_session, lens=_lens(teacher), session_id=class_id)
    else:
        reschedule_session(
            restricted_session,
            lens=_lens(teacher),
            session_id=class_id,
            date=MOVED_DAY,
            start_time=FOUR_PM,
        )

    received = {row.account_id for row in _items(owner_session, class_id)}
    assert received == {family["student"], family["guardian"]}
    for nobody in (
        "pending_student",
        "pending_guardian",
        "declined_student",
        "declined_guardian",
    ):
        assert family[nobody] not in received, f"{nobody} was told of the class"
    assert teacher.account_id not in received


def test_a_seat_that_has_left_before_the_class_hears_nothing(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Membership is judged on the class's own date, not on today.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    leaving = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=leaving,
        student_decision="accepted",
    )
    owner_session.execute(
        sa.text("UPDATE enrollment SET inactive_from = :day WHERE id = :id"),
        {"day": CLASS_DAY - dt.timedelta(days=1), "id": seat},
    )
    owner_session.commit()
    class_id = _class(owner_session, teacher)

    cancel_session(restricted_session, lens=_lens(teacher), session_id=class_id)

    assert _items(owner_session, class_id) == []


# --------------------------------------------------- what it carries


def test_a_cancellation_carries_the_batch_the_class_and_its_source(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    family: dict[str, uuid.UUID],
) -> None:
    """Exactly one ``class_cancelled`` item each, naming the class.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param teacher: The batch's owner
    :param family: The seats
    :return: None
    """
    class_id = _class(owner_session, teacher)

    cancel_session(restricted_session, lens=_lens(teacher), session_id=class_id)

    rows = _items(owner_session, class_id)
    assert len(rows) == 2
    for row in rows:
        assert row.kind == CLASS_CANCELLED
        assert row.source_id == class_id
        assert row.enrollment_id == family["seat"]
        assert row.batch_name == "Physics"
        assert (row.class_date, row.class_time) == (CLASS_DAY, FOUR_PM)
        assert (row.moved_from_date, row.moved_from_time) == (None, None)
        assert row.read_at is None
    by_account = {row.account_id: row.child_name for row in rows}
    assert by_account == {family["student"]: None, family["guardian"]: "Rahim"}


def test_a_reschedule_carries_the_old_and_the_new_time(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    family: dict[str, uuid.UUID],
) -> None:
    """One ``class_rescheduled`` item each, with where it was and is.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param teacher: The batch's owner
    :param family: The seats
    :return: None
    """
    class_id = _class(owner_session, teacher)

    reschedule_session(
        restricted_session,
        lens=_lens(teacher),
        session_id=class_id,
        date=MOVED_DAY,
        start_time=SIX_PM,
    )

    rows = _items(owner_session, class_id)
    assert {row.account_id for row in rows} == {family["student"], family["guardian"]}
    for row in rows:
        assert row.kind == CLASS_RESCHEDULED
        assert (row.class_date, row.class_time) == (MOVED_DAY, SIX_PM)
        assert (row.moved_from_date, row.moved_from_time) == (CLASS_DAY, FOUR_PM)


def test_a_second_reschedule_replaces_the_first_item(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    family: dict[str, uuid.UUID],
) -> None:
    """One item per person, from where they last knew it, to where it is now.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param teacher: The batch's owner
    :param family: The seats
    :return: None
    """
    class_id = _class(owner_session, teacher)
    for day in (MOVED_DAY, MOVED_AGAIN):
        reschedule_session(
            restricted_session,
            lens=_lens(teacher),
            session_id=class_id,
            date=day,
            start_time=FOUR_PM,
        )

    rows = _items(owner_session, class_id)
    assert len(rows) == 2, "a second reschedule stacked a second item"
    for row in rows:
        assert row.class_date == MOVED_AGAIN
        # The item replaces one the family may never have opened, so it
        # says where the class was before ANY move, not mid-way.
        assert row.moved_from_date == CLASS_DAY


def test_moving_a_class_back_to_its_first_time_still_says_where_it_went(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    family: dict[str, uuid.UUID],
) -> None:
    """Back to the original slot: the item names the move just made.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param teacher: The batch's owner
    :param family: The seats
    :return: None
    """
    class_id = _class(owner_session, teacher)
    for day in (MOVED_DAY, CLASS_DAY):
        reschedule_session(
            restricted_session,
            lens=_lens(teacher),
            session_id=class_id,
            date=day,
            start_time=FOUR_PM,
        )

    rows = _items(owner_session, class_id)
    assert len(rows) == 2
    for row in rows:
        assert (row.moved_from_date, row.class_date) == (MOVED_DAY, CLASS_DAY)


def test_cancelling_a_moved_class_replaces_the_move(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    family: dict[str, uuid.UUID],
) -> None:
    """An inbox never holds "moved to Wednesday" beside "cancelled".

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param teacher: The batch's owner
    :param family: The seats
    :return: None
    """
    class_id = _class(owner_session, teacher)
    reschedule_session(
        restricted_session,
        lens=_lens(teacher),
        session_id=class_id,
        date=MOVED_DAY,
        start_time=FOUR_PM,
    )

    cancel_session(restricted_session, lens=_lens(teacher), session_id=class_id)

    rows = _items(owner_session, class_id)
    assert {row.kind for row in rows} == {CLASS_CANCELLED}
    assert len(rows) == 2
    assert {row.class_date for row in rows} == {MOVED_DAY}


def test_a_reschedule_to_the_same_time_tells_nobody(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    family: dict[str, uuid.UUID],
) -> None:
    """Nothing moved, so there is nothing to say.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param teacher: The batch's owner
    :param family: The seats
    :return: None
    """
    class_id = _class(owner_session, teacher)

    reschedule_session(
        restricted_session,
        lens=_lens(teacher),
        session_id=class_id,
        date=CLASS_DAY,
        start_time=FOUR_PM,
    )

    assert _items(owner_session, class_id) == []


# ------------------------------------------- refused or past: nothing


def test_cancelling_an_already_cancelled_class_keeps_its_error_and_writes_nothing(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    family: dict[str, uuid.UUID],
) -> None:
    """``SESSION_CANCELLED`` as before, and no second round of messages.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param teacher: The batch's owner
    :param family: The seats
    :return: None
    """
    class_id = _class(owner_session, teacher, status="cancelled")

    with pytest.raises(ConflictError) as cancel_refused:
        cancel_session(restricted_session, lens=_lens(teacher), session_id=class_id)
    restricted_session.rollback()
    with pytest.raises(ConflictError) as move_refused:
        reschedule_session(
            restricted_session,
            lens=_lens(teacher),
            session_id=class_id,
            date=MOVED_DAY,
            start_time=FOUR_PM,
        )
    restricted_session.rollback()

    assert cancel_refused.value.code == "SESSION_CANCELLED"
    assert move_refused.value.code == "SESSION_CANCELLED"
    assert _items(owner_session, class_id) == []


def test_a_reschedule_onto_an_occupied_slot_writes_nothing(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    family: dict[str, uuid.UUID],
) -> None:
    """A refused move rolls its messages back with it.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param teacher: The batch's owner
    :param family: The seats
    :return: None
    """
    class_id = _class(owner_session, teacher)
    _class(owner_session, teacher, on=MOVED_DAY)

    with pytest.raises(ConflictError) as refusal:
        reschedule_session(
            restricted_session,
            lens=_lens(teacher),
            session_id=class_id,
            date=MOVED_DAY,
            start_time=FOUR_PM,
        )

    assert refusal.value.code == "SESSION_ALREADY_EXISTS"
    assert _items(owner_session, class_id) == []


def test_changing_a_past_class_tells_nobody(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    family: dict[str, uuid.UUID],
) -> None:
    """A class that has already happened is a correction, not news.

    There is no refusal for a past class -- a teacher may still tidy
    one up -- so the write succeeds as it always has and only the
    message is withheld.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param teacher: The batch's owner
    :param family: The seats
    :return: None
    """
    past = _class(owner_session, teacher, on=dt.date(2020, 1, 6))
    other_past = _class(owner_session, teacher, on=dt.date(2020, 1, 13))

    cancel_session(restricted_session, lens=_lens(teacher), session_id=past)
    reschedule_session(
        restricted_session,
        lens=_lens(teacher),
        session_id=other_past,
        date=dt.date(2020, 1, 14),
        start_time=FOUR_PM,
    )

    assert _items(owner_session, past) == []
    assert _items(owner_session, other_past) == []


def test_moving_a_past_class_into_the_future_is_news(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    family: dict[str, uuid.UUID],
) -> None:
    """A missed class put back on the calendar is one the family can attend.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param teacher: The batch's owner
    :param family: The seats
    :return: None
    """
    past = _class(owner_session, teacher, on=dt.date(2020, 1, 6))

    reschedule_session(
        restricted_session,
        lens=_lens(teacher),
        session_id=past,
        date=MOVED_DAY,
        start_time=FOUR_PM,
    )

    rows = _items(owner_session, past)
    assert {row.account_id for row in rows} == {family["student"], family["guardian"]}


def test_a_held_class_is_not_announced_as_cancelled(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    family: dict[str, uuid.UUID],
) -> None:
    """Only a class still to be held is news when it changes.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param teacher: The batch's owner
    :param family: The seats
    :return: None
    """
    held = _class(owner_session, teacher, status="held")

    cancel_session(restricted_session, lens=_lens(teacher), session_id=held)

    assert _items(owner_session, held) == []
