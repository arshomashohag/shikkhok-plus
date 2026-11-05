"""Arrange a teacher's student for a seat a test builds by hand [0018].

Every seat belongs to one of its owner's students, so a test that builds
an ``Enrollment`` directly needs a student first. This arranges one for
the batch's owner, or -- for the tests that seat a person in a batch id
nobody created, because only the seat matters to them -- for a throwaway
owner of its own.
"""

from __future__ import annotations

import datetime as dt
import secrets
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import Account, Batch, Owner, Student

__all__ = ["student_for"]


def student_for(
    session: Session,
    batch_id: uuid.UUID,
    *,
    display_name: str = "Teacher Typed Name",
    student_phone: str | None = None,
    guardian_phone: str | None = None,
) -> uuid.UUID:
    """Create a student for the owner of ``batch_id`` and return its id.

    :param session: An arranging session
    :param batch_id: The batch the seat will sit in
    :param display_name: The teacher-typed name
    :param student_phone: The student's number, canonical
    :param guardian_phone: The guardian's number, canonical
    :return: The new student's id
    """
    now = dt.datetime.now(tz=dt.UTC)
    owner_id = session.execute(
        sa.select(Batch.owner_id).where(Batch.id == batch_id)
    ).scalar_one_or_none()
    if owner_id is None:
        account = Account(
            phone="+88017" + "".join(secrets.choice("0123456789") for _ in range(8)),
            created_at=now,
        )
        session.add(account)
        session.flush()
        owner = Owner(account_id=account.id, created_at=now)
        session.add(owner)
        session.flush()
        owner_id = owner.id
    student = Student(
        owner_id=owner_id,
        display_name=display_name,
        student_phone=student_phone,
        guardian_phone=guardian_phone,
        created_at=now,
    )
    session.add(student)
    session.flush()
    return student.id
