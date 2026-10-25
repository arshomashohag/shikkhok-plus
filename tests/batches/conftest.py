"""Fixtures for U4, shaped so a correct implementation can fail them.

**Every fixture here states which wrong implementation it rejects.** This
Unit's reviews found the same defect three times -- the assertion was
real and the setup made it vacuous -- so a fixture whose shape is not
load-bearing does not belong in this file.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy.orm import Session

from app.db.models import Account, Enrollment, Owner
from app.money import Money


@dataclass(frozen=True, slots=True)
class TeacherFixture:
    """One teacher, their owner row and one batch.

    :ivar account_id: The teacher's account
    :ivar owner_id: The owner row their batches hang from
    :ivar batch_id: A batch they own
    """

    account_id: uuid.UUID
    owner_id: uuid.UUID
    batch_id: uuid.UUID


def _account(session: Session) -> uuid.UUID:
    """Create one account with a unique phone number.

    :param session: An arranging session
    :return: The new account's id
    """
    account = Account(
        phone=f"+8801{uuid.uuid4().int % 10**9:09d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(account)
    session.commit()
    return account.id


def make_teacher(session: Session, *, name: str = "Batch") -> TeacherFixture:
    """Create a teacher with an owner row and one batch.

    :param session: An arranging session
    :param name: The batch's name
    :return: The teacher, owner and batch ids
    """
    from app.db.models import Batch

    account_id = _account(session)
    owner = Owner(account_id=account_id, created_at=dt.datetime.now(tz=dt.UTC))
    session.add(owner)
    session.commit()

    batch = Batch(
        owner_id=owner.id,
        name=name,
        default_fee=Money("1500.00"),
        fee_due_day=10,
        marksheet_visible=True,
        active=True,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(batch)
    session.commit()
    return TeacherFixture(account_id=account_id, owner_id=owner.id, batch_id=batch.id)


def enroll(
    session: Session,
    *,
    batch_id: uuid.UUID,
    display_name: str,
    student_account_id: uuid.UUID | None = None,
    guardian_account_id: uuid.UUID | None = None,
    guardian_phone: str | None = None,
    fee_amount: Money | None = None,
    student_decision: str | None = None,
    guardian_decision: str | None = None,
) -> uuid.UUID:
    """Create one enrollment seat in a batch.

    **A decision left unstated here follows the LINK, mirroring
    ``0004``'s conditional backfill**: ``accepted`` where the link
    names an account, ``pending`` otherwise [ADR-013]. This helper
    predates D1, and every merged test using it seats a person who --
    under the superseded model, where naming WAS claiming -- was
    already using their lens. Reproducing the migration's own rule is
    what keeps those tests asserting what they were written to assert.

    It is NOT a default on the column or on the service:
    ``add_enrollment`` states ``pending`` explicitly, as a teacher
    creating a seat does, and the database carries no default at all.
    Defaulting flatly to ``accepted`` here would be worse than either:
    it would arrange ``accepted`` beside a NULL link, a state no code
    path can produce, and the erased-seat refusal test would then be
    refused as *claimed* for a reason that does not exist.

    D1's own tests state both decisions explicitly rather than
    inheriting any of this.

    :param session: An arranging session
    :param batch_id: The batch the seat belongs to
    :param display_name: The teacher-typed name
    :param student_account_id: The student, or None for a dormant seat
    :param guardian_account_id: The guardian, if one is recorded
    :param guardian_phone: The teacher-typed guardian contact
    :param fee_amount: This seat's fee, or None to inherit
    :param student_decision: The student link's decision, or None to
        follow the link
    :param guardian_decision: The guardian link's decision, or None to
        follow the link
    :return: The new enrollment's id
    """
    if student_decision is None:
        student_decision = "accepted" if student_account_id else "pending"
    if guardian_decision is None:
        guardian_decision = "accepted" if guardian_account_id else "pending"

    record = Enrollment(
        batch_id=batch_id,
        student_account_id=student_account_id,
        guardian_account_id=guardian_account_id,
        guardian_phone=guardian_phone,
        fee_amount=fee_amount,
        display_name=display_name,
        student_decision=student_decision,
        guardian_decision=guardian_decision,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    session.commit()
    return record.id


@pytest.fixture
def two_teachers(owner_session: Session) -> Iterator[tuple[TeacherFixture, ...]]:
    """Two teachers who each enrolled the SAME student account.

    **This is the fixture U3 could not build.** With one account and one
    party, every isolation claim was about a mechanism rather than an
    outcome -- there was no second teacher for data to leak to. A roster
    query scoped on a caller-supplied id rather than on the lens passes
    every single-teacher test and fails here.

    :param owner_session: A session able to arrange fixture data
    :return: A context manager yielding both teachers
    """
    first = make_teacher(owner_session, name="Physics")
    second = make_teacher(owner_session, name="Chemistry")

    shared_student = _account(owner_session)
    enroll(
        owner_session,
        batch_id=first.batch_id,
        display_name="Rahim (physics)",
        student_account_id=shared_student,
    )
    enroll(
        owner_session,
        batch_id=second.batch_id,
        display_name="Rahim (chemistry)",
        student_account_id=shared_student,
    )
    yield first, second
