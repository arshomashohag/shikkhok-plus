"""Fixtures for the help centre and the administration surface.

People are arranged through the same helpers the batch and fee suites
use, so a student here holds a seat with the same decision columns a
real one does -- which is what lens and identity resolution read.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import Account, Owner, OwnerMember
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.fees.conftest import account_factory

__all__ = ["People", "account_factory", "people", "phone_of"]

#: What the teacher shows their students, and so what an administrator
#: may see.
TEACHER_NAME = "Karim Sir"

#: Names a teacher typed for the student; an administrator must never
#: see them.
STUDENT_SEAT_NAME = "Rahim Uddin"


@dataclass(frozen=True, slots=True)
class People:
    """One of each kind of account.

    :ivar teacher: A solo tutor with a named batch
    :ivar student: An accepted student in that batch
    :ivar guardian: The student's accepted guardian
    :ivar centre_id: A coaching centre
    :ivar member: A live manager of that centre
    :ivar stranger: Signed up, holds nothing
    """

    teacher: TeacherFixture
    student: uuid.UUID
    guardian: uuid.UUID
    centre_id: uuid.UUID
    member: uuid.UUID
    stranger: uuid.UUID


def phone_of(session: Session, account_id: uuid.UUID) -> str:
    """Read an account's stored number.

    :param session: Any session
    :param account_id: The account
    :return: Its phone number
    """
    return str(
        session.execute(
            sa.text("SELECT phone FROM account WHERE id = :a"), {"a": account_id}
        ).scalar_one()
    )


@pytest.fixture
def people(owner_session: Session, account_factory: Callable[[], uuid.UUID]) -> People:
    """Arrange one of each kind of account, all signed in at least once.

    :param owner_session: An arranging session
    :param account_factory: Makes accounts
    :return: The people
    """
    now = dt.datetime.now(tz=dt.UTC)
    teacher = make_teacher(owner_session, name="Physics")
    owner_session.execute(
        sa.text("UPDATE batch SET teacher_display_name = :n WHERE id = :b"),
        {"n": TEACHER_NAME, "b": teacher.batch_id},
    )
    student = account_factory()
    guardian = account_factory()
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name=STUDENT_SEAT_NAME,
        student_account_id=student,
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted",
    )
    centre = Owner(
        account_id=None, kind="organisation", name="Udoy Coaching", created_at=now
    )
    owner_session.add(centre)
    owner_session.commit()
    member = account_factory()
    owner_session.add(
        OwnerMember(
            owner_id=centre.id,
            account_id=member,
            invited_phone=phone_of(owner_session, member),
            display_name="Nasrin Apa",
            role="manager",
            decision="accepted",
            created_at=now,
        )
    )
    stranger = account_factory()
    owner_session.execute(
        sa.update(Account)
        .where(Account.activated_at.is_(None))
        .values(activated_at=now)
    )
    owner_session.commit()
    return People(
        teacher=teacher,
        student=student,
        guardian=guardian,
        centre_id=centre.id,
        member=member,
        stranger=stranger,
    )
