"""Fixtures for D4's marks half, reusing D2's enrollment helpers.

The helpers are imported rather than copied for the same reason D3's
conftest imports them: a second copy of ``enroll`` drifts the moment
either unit changes a decision column, and the decision columns are
what the marksheet's lens-scoped reads filter on.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import Account, BatchSubject, Exam
from tests.batches.conftest import TeacherFixture, enroll, make_teacher

__all__ = [
    "TeacherFixture",
    "enroll",
    "make_teacher",
]

EXAM_DATE = dt.date(2027, 4, 20)

#: The denominator every fixture exam uses. 100 so a mark reads as a
#: percentage without a conversion, which is the case the band edges
#: are most likely to be wrong at -- a full 100 must land in a band.
TOTAL_MARKS = 100


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
            phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
            created_at=dt.datetime.now(tz=dt.UTC),
        )
        owner_session.add(account)
        owner_session.commit()
        return account.id

    return make


@pytest.fixture
def subject(owner_session: DbSession, teacher: TeacherFixture) -> uuid.UUID:
    """One subject on the teacher's batch.

    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :return: The subject id
    """
    row = BatchSubject(batch_id=teacher.batch_id, name="Physics")
    owner_session.add(row)
    owner_session.commit()
    return row.id


@pytest.fixture
def exam(
    owner_session: DbSession,
    teacher: TeacherFixture,
    subject: uuid.UUID,
) -> uuid.UUID:
    """One exam out of 100 on the teacher's batch.

    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :param subject: The subject assessed
    :return: The exam id
    """
    row = Exam(
        batch_id=teacher.batch_id,
        batch_subject_id=subject,
        title="April test",
        date=EXAM_DATE,
        total_marks=TOTAL_MARKS,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(row)
    owner_session.commit()
    return row.id


@pytest.fixture
def teacher_lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the fixture teacher's lens.

    :param teacher: The teacher fixture
    :return: The lens carrying the owner id
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


@pytest.fixture
def seat_factory(
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> Callable[..., uuid.UUID]:
    """Return a factory making accepted seats on the teacher's batch.

    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :param account_factory: Makes student accounts
    :return: A callable producing a seat, optionally with a join date
    """

    def make(
        name: str = "Student",
        joined_on: dt.date | None = None,
        student_account_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        seat = enroll(
            owner_session,
            batch_id=teacher.batch_id,
            display_name=name,
            student_account_id=student_account_id or account_factory(),
            student_decision="accepted",
            guardian_decision="pending",
        )
        if joined_on is not None:
            from app.db.models import Enrollment

            record = owner_session.get(Enrollment, seat)
            assert record is not None
            record.joined_on = joined_on
            owner_session.commit()
        return seat

    return make
