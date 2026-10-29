"""Fixtures for D3, built through the same helpers D2's suite uses.

**Test data goes through the application's own shapes**, so a seat in a
fee test carries the same invariants as one a teacher creates. The
helpers are imported from D2's conftest rather than copied: a second
copy of ``enroll`` would drift the moment either unit changed a decision
column, and the decision columns are exactly what D3 reads.

**Every session here is the RESTRICTED role unless it is arranging.**
The owner session exists only to insert fixture rows the policy would
otherwise deny; an assertion made as the owner proves nothing, because
a superuser or table owner bypasses row-level security entirely.

**The clock is injected, never patched.** The across-days test needs to
run the job as though it were a different day, and a patched module
global is both wider than the test and invisible at the call site. The
job takes ``today`` as a parameter, so a test simply passes one.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import Account, Enrollment
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll, make_teacher

__all__ = [
    "TeacherFixture",
    "enroll",
    "make_teacher",
]


@pytest.fixture
def teacher(owner_session: Session) -> TeacherFixture:
    """One teacher with an owner row and a batch.

    The batch carries ``default_fee`` 1500.00 and ``fee_due_day`` 10
    from the shared helper. Tests that care about either state their
    own.

    :param owner_session: A session able to arrange fixture data
    :return: The teacher, owner and batch ids
    """
    return make_teacher(owner_session, name="Physics")


@pytest.fixture
def account_factory(owner_session: Session) -> Callable[[], uuid.UUID]:
    """Return a factory making accounts with unique phone numbers.

    :param owner_session: A session able to arrange fixture data
    :return: A callable producing a fresh account id each time
    """

    def make() -> uuid.UUID:
        account = Account(
            phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
            created_at=dt.datetime.now(tz=dt.UTC),
        )
        owner_session.add(account)
        owner_session.commit()
        return account.id

    return make


@pytest.fixture
def seat(
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> uuid.UUID:
    """One accepted student seat on the teacher's batch.

    The commonest arrangement: a student who accepted, inheriting the
    batch's 1500.00 default fee.

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


def set_batch_fee(
    session: Session,
    *,
    batch_id: uuid.UUID,
    default_fee: Money | None = None,
    fee_due_day: int | None = None,
) -> None:
    """Set a batch's fee defaults, including to NULL.

    Written as an UPDATE rather than through the service because
    ``None`` must mean "set this column to NULL" here, while the
    service's optional parameters mean "leave unchanged".

    :param session: An arranging session
    :param batch_id: The batch to change
    :param default_fee: The new default fee, or None for NULL
    :param fee_due_day: The new anchor day, or None for NULL
    :return: None
    """
    session.execute(
        sa.text(
            "UPDATE batch SET default_fee = :fee, fee_due_day = :day "
            "WHERE id = :batch_id"
        ),
        {
            "fee": None if default_fee is None else default_fee.amount,
            "day": fee_due_day,
            "batch_id": batch_id,
        },
    )
    session.commit()


def set_decision(
    session: Session,
    *,
    enrollment_id: uuid.UUID,
    student: str | None = None,
    guardian: str | None = None,
) -> None:
    """Change a seat's per-link decisions.

    D1 owns the transition; D3 reads the result. Written directly
    because the point of a D3 test is the MONEY consequence of a
    decision, not the path that set it.

    :param session: An arranging session
    :param enrollment_id: The seat to change
    :param student: The student link's new decision, or None to leave
    :param guardian: The guardian link's new decision, or None to leave
    :return: None
    """
    record = session.get(Enrollment, enrollment_id)
    assert record is not None
    if student is not None:
        record.student_decision = student
    if guardian is not None:
        record.guardian_decision = guardian
    session.commit()


def set_inactive_from(
    session: Session,
    *,
    enrollment_id: uuid.UUID,
    when: dt.date | None,
) -> None:
    """Set or clear a seat's ``inactive_from`` date.

    :param session: An arranging session
    :param enrollment_id: The seat to change
    :param when: The date after which no cycle generates, or None
    :return: None
    """
    record = session.get(Enrollment, enrollment_id)
    assert record is not None
    record.inactive_from = when
    session.commit()


def set_joined_on(
    session: Session,
    *,
    enrollment_id: uuid.UUID,
    when: dt.date,
) -> None:
    """Set the date a seat's generation starts from.

    :param session: An arranging session
    :param enrollment_id: The seat to change
    :param when: The joining date
    :return: None
    """
    record = session.get(Enrollment, enrollment_id)
    assert record is not None
    record.joined_on = when
    session.commit()
