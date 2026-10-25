"""Fixtures for D4, built through D2's helpers rather than copies.

**Test data goes through the application's own shapes**, so a seat in a
teaching test carries the same invariants as one a teacher creates. The
helpers are imported from D2's conftest rather than copied: a second
copy of ``enroll`` would drift the moment either unit changed a decision
column, and the decision columns are exactly what D4's six readers
filter on.

**Every session here is the RESTRICTED role unless it is arranging.**
The owner session exists only to insert fixture rows; an assertion made
as the owner proves nothing, because a superuser or table owner bypasses
row-level security entirely.

**The clock is injected, never patched.** Generation takes ``today`` as
a parameter, exactly as D3's does, so a test that needs a different day
simply passes one.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session as DbSession

from app.db.models import Account, BatchSubject, ScheduleSlot
from tests.batches.conftest import TeacherFixture, enroll, make_teacher

__all__ = [
    "TeacherFixture",
    "add_slot",
    "add_subject",
    "enroll",
    "make_teacher",
]

#: Monday, as ``ScheduleSlot.weekday`` numbers it (0 = Monday).
MONDAY = 0


def add_slot(
    session: DbSession,
    *,
    batch_id: uuid.UUID,
    weekday: int = MONDAY,
    start_time: dt.time = dt.time(16, 0),
    end_time: dt.time = dt.time(17, 30),
) -> uuid.UUID:
    """Add one weekly recurring slot to a batch.

    :param session: An arranging session
    :param batch_id: The batch the slot belongs to
    :param weekday: 0-6, Monday through Sunday
    :param start_time: When the class starts
    :param end_time: When the class ends
    :return: The new slot's id
    """
    slot = ScheduleSlot(
        batch_id=batch_id,
        weekday=weekday,
        start_time=start_time,
        end_time=end_time,
    )
    session.add(slot)
    session.commit()
    return slot.id


def add_subject(
    session: DbSession,
    *,
    batch_id: uuid.UUID,
    name: str = "Physics",
) -> uuid.UUID:
    """Add one subject to a batch.

    :param session: An arranging session
    :param batch_id: The batch the subject belongs to
    :param name: The subject's name
    :return: The new subject's id
    """
    subject = BatchSubject(batch_id=batch_id, name=name)
    session.add(subject)
    session.commit()
    return subject.id


@pytest.fixture
def teacher(owner_session: DbSession) -> TeacherFixture:
    """One teacher with an owner row and an active batch.

    :param owner_session: A session able to arrange fixture data
    :return: The teacher, owner and batch ids
    """
    return make_teacher(owner_session, name="Physics")


@pytest.fixture
def account_factory(owner_session: DbSession) -> Callable[[], uuid.UUID]:
    """Return a factory making accounts with unique phone numbers.

    :param owner_session: A session able to arrange fixture data
    :return: A callable producing a fresh account id each time
    """

    def make() -> uuid.UUID:
        account = Account(
            phone=f"+8801{uuid.uuid4().int % 10**9:09d}",
            created_at=dt.datetime.now(tz=dt.UTC),
        )
        owner_session.add(account)
        owner_session.commit()
        return account.id

    return make


@pytest.fixture
def monday_slot(owner_session: DbSession, teacher: TeacherFixture) -> uuid.UUID:
    """Add a Monday 16:00 slot to the teacher's batch.

    The arrangement BR1.1's own ``violation_behaviour`` names: after
    generation over a four-week horizon exactly four sessions exist,
    one per Monday, each at 16:00.

    :param owner_session: A session able to arrange fixture data
    :param teacher: The teacher whose batch gets the slot
    :return: The slot id
    """
    return add_slot(owner_session, batch_id=teacher.batch_id)


@pytest.fixture
def seat(
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> uuid.UUID:
    """One accepted student seat on the teacher's batch.

    :param owner_session: A session able to arrange fixture data
    :param teacher: The teacher whose batch the seat sits in
    :param account_factory: Makes the student's account
    :return: The enrollment id
    """
    return enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )
