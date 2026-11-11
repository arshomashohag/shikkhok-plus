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

import contextlib
import datetime as dt
import threading
import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from app.authz.lenses import TeacherLens
from app.db.models import Notification, Session
from app.errors import ConflictError
from app.local_time import DHAKA
from app.notifications.inbox import CLASS_CANCELLED, CLASS_RESCHEDULED
from app.teaching import sessions as sessions_module
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


# --------------------------------------- today: the start time decides

#: Moments on the class's own day, in Bangladesh: before its 4 pm start
#: and after it.
BEFORE_CLASS = dt.datetime.combine(CLASS_DAY, dt.time(14, 0), tzinfo=DHAKA)
AFTER_CLASS = dt.datetime.combine(CLASS_DAY, dt.time(18, 30), tzinfo=DHAKA)


@pytest.mark.parametrize(
    ("now", "told"),
    [(BEFORE_CLASS, True), (AFTER_CLASS, False)],
    ids=["later-today", "earlier-today"],
)
def test_cancelling_a_class_today_is_news_only_before_it_starts(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    family: dict[str, uuid.UUID],
    now: dt.datetime,
    told: bool,
) -> None:
    """A class held this morning and cancelled tonight tells nobody.

    The date alone said "today, so still to come"; the start time says
    whether it already happened.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param teacher: The batch's owner
    :param family: The seats
    :param now: The present, on the class's day
    :param told: Whether the family should hear of it
    :return: None
    """
    class_id = _class(owner_session, teacher)

    cancel_session(
        restricted_session, lens=_lens(teacher), session_id=class_id, now=now
    )

    received = {row.account_id for row in _items(owner_session, class_id)}
    assert received == ({family["student"], family["guardian"]} if told else set())


@pytest.mark.parametrize(
    ("now", "to", "told"),
    [
        # Both slots already passed: a correction to the record.
        (AFTER_CLASS, (CLASS_DAY, dt.time(17, 0)), False),
        # The old slot passed, the new one is still to come.
        (AFTER_CLASS, (CLASS_DAY, dt.time(20, 0)), True),
        # The old slot is still to come and the new one is in the past:
        # the class the family expects will not happen.
        (BEFORE_CLASS, (CLASS_DAY, dt.time(9, 0)), True),
    ],
    ids=["past-to-past", "past-to-later-today", "future-to-past"],
)
def test_a_move_today_is_news_when_either_slot_is_still_to_come(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    family: dict[str, uuid.UUID],
    now: dt.datetime,
    to: tuple[dt.date, dt.time],
    told: bool,
) -> None:
    """The old slot or the new one starting now or later makes a move news.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param teacher: The batch's owner
    :param family: The seats
    :param now: The present, on the class's day
    :param to: The new date and start time
    :param told: Whether the family should hear of it
    :return: None
    """
    class_id = _class(owner_session, teacher)

    reschedule_session(
        restricted_session,
        lens=_lens(teacher),
        session_id=class_id,
        date=to[0],
        start_time=to[1],
        now=now,
    )

    received = {row.account_id for row in _items(owner_session, class_id)}
    assert received == ({family["student"], family["guardian"]} if told else set())


# ------------------------------------- a cancel racing a reschedule


def test_a_cancel_and_a_reschedule_racing_on_one_class_cannot_both_apply(
    owner_session: DbSession,
    restricted_engine: Engine,
    teacher: TeacherFixture,
    family: dict[str, uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cancel reads first; the reschedule must then see it cancelled.

    Each write reads the row's status and then writes. Without the row
    lock both pass the cancelled check, and the class ends up cancelled
    at its NEW date with a ``class_cancelled`` and a ``class_rescheduled``
    item side by side. The race is widened deterministically: once the
    cancel has read the row the reschedule is released to read it too,
    and each waits up to a short timeout for the other to have read
    before writing. Under the lock the reschedule cannot read until the
    cancel commits, so the wait times out and the reschedule then sees
    the cancellation.

    :param owner_session: An arranging session
    :param restricted_engine: The application role's engine
    :param teacher: The batch's owner
    :param family: The seats
    :param monkeypatch: The patcher
    :return: None
    """
    class_id = _class(owner_session, teacher)
    real = sessions_module.writable_session
    cancel_has_read = threading.Event()
    both_read = threading.Barrier(2)

    def widened(
        session: DbSession,
        *,
        lens: TeacherLens,
        session_id: uuid.UUID,
        lock: bool = False,
    ) -> Session:
        """Read as the service does, then hold the read open.

        :param session: Passed through
        :param lens: Passed through
        :param session_id: Passed through
        :param lock: Passed through
        :return: The row
        """
        row = real(session, lens=lens, session_id=session_id, lock=lock)
        cancel_has_read.set()
        with contextlib.suppress(threading.BrokenBarrierError):
            both_read.wait(timeout=2)
        return row

    monkeypatch.setattr(sessions_module, "writable_session", widened)
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    outcomes: dict[str, str] = {}
    guard = threading.Lock()

    def run(name: str) -> None:
        """Make one write in its own session, recording how it ended.

        :param name: ``cancel`` or ``reschedule``
        :return: None
        """
        db = factory()
        try:
            if name == "cancel":
                cancel_session(db, lens=_lens(teacher), session_id=class_id)
            else:
                cancel_has_read.wait(timeout=30)
                reschedule_session(
                    db,
                    lens=_lens(teacher),
                    session_id=class_id,
                    date=MOVED_DAY,
                    start_time=FOUR_PM,
                )
            result = "applied"
        except ConflictError as error:
            result = error.code
        except BaseException as error:  # noqa: BLE001  recorded, then asserted
            result = repr(error)
        finally:
            db.close()
        with guard:
            outcomes[name] = result

    threads = [
        threading.Thread(target=run, args=(name,)) for name in ("cancel", "reschedule")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert outcomes == {"cancel": "applied", "reschedule": "SESSION_CANCELLED"}
    owner_session.expire_all()
    stored = owner_session.get_one(Session, class_id)
    assert (stored.status, stored.date) == ("cancelled", CLASS_DAY)
    rows = _items(owner_session, class_id)
    assert {row.kind for row in rows} == {CLASS_CANCELLED}
    assert {row.class_date for row in rows} == {CLASS_DAY}
    assert {row.account_id for row in rows} == {family["student"], family["guardian"]}
