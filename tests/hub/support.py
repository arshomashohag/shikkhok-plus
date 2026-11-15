"""Arrangement helpers for the hub's owner-listing tests.

Everything here writes through the table-owner session, so a service under
test that is handed the restricted session is the only thing exercising the
application role's grants.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.db.models import (
    Account,
    Attendance,
    Batch,
    BatchSubject,
    Owner,
    OwnerMember,
    QueuedSubmission,
    ScheduleSlot,
)
from app.db.models import Session as ClassSession
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll, make_teacher

__all__ = [
    "CentreFixture",
    "add_attendance",
    "add_member",
    "areas",
    "assign_slot",
    "centre_lens",
    "centre_with_manager",
    "solo_lens",
]


def solo_lens(session: Session, *, name: str = "Batch") -> TeacherLens:
    """Arrange a solo tutor and return their lens.

    :param session: An arranging session
    :param name: The tutor's first batch name
    :return: The tutor's lens
    """
    teacher: TeacherFixture = make_teacher(session, name=name)
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def centre_lens(session: Session, *, name: str = "Udoy Coaching") -> TeacherLens:
    """Arrange a coaching centre and return a lens on it.

    :param session: An arranging session
    :param name: The centre's name
    :return: A lens whose owner is the centre
    """
    teacher = make_teacher(session)
    session.execute(
        sa.text(
            "UPDATE owner SET kind = 'organisation', name = :n, account_id = NULL "
            "WHERE id = :o"
        ),
        {"n": name, "o": teacher.owner_id},
    )
    session.commit()
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def areas(session: Session) -> tuple[str, str, str]:
    """Pick a district, one of its upazilas and a different district.

    :param session: Any session
    :return: ``(district, upazila_of_it, other_district)`` codes
    """
    row = session.execute(
        sa.text(
            "SELECT d.code, u.code FROM bd_area u JOIN bd_area d "
            "ON d.code = u.parent_code WHERE u.kind = 'upazila' "
            "ORDER BY u.code LIMIT 1"
        )
    ).one()
    other = session.execute(
        sa.text(
            "SELECT code FROM bd_area WHERE kind = 'district' AND code <> :d "
            "ORDER BY code LIMIT 1"
        ),
        {"d": row[0]},
    ).scalar_one()
    return str(row[0]), str(row[1]), str(other)


def add_attendance(
    session: Session,
    lens: TeacherLens,
    *,
    seats: int,
    accepted: int,
    last_recorded: dt.datetime | None,
) -> None:
    """Seat students and optionally record one attendance row.

    :param session: An arranging session
    :param lens: The owner whose batch gets the seats
    :param seats: How many seats to create
    :param accepted: How many of them the student has accepted
    :param last_recorded: When attendance was recorded, or None for never
    :return: None
    """
    batch_id = (
        session.execute(sa.select(Batch.id).where(Batch.owner_id == lens.owner_id))
        .scalars()
        .first()
    )
    assert batch_id is not None
    seat_ids = []
    for i in range(seats):
        seat_ids.append(
            enroll(
                session,
                batch_id=batch_id,
                display_name=f"Student {i}",
                student_decision="accepted" if i < accepted else "pending",
            )
        )
    if last_recorded is None:
        return
    now = dt.datetime.now(tz=dt.UTC)
    klass = ClassSession(
        batch_id=batch_id,
        date=last_recorded.date(),
        start_time=dt.time(16, 0),
        status="held",
        origin="ad_hoc",
        attendance_version=1,
        topic_version=0,
        created_at=now,
    )
    session.add(klass)
    session.commit()
    submission = QueuedSubmission(
        session_id=klass.id,
        submitted_by_account_id=lens.account_id,
        kind="attendance",
        client_mutation_id=uuid.uuid4(),
        base_version=0,
        resulting_version=1,
        created_at=now,
    )
    session.add(submission)
    session.commit()
    session.add(
        Attendance(
            session_id=klass.id,
            enrollment_id=seat_ids[0],
            present=True,
            recorded_at=last_recorded,
            recorded_by_account_id=lens.account_id,
            submission_id=submission.id,
        )
    )
    session.commit()


@dataclass(frozen=True, slots=True)
class CentreFixture:
    """A coaching centre with a manager, one batch and one subject.

    :ivar owner_id: The centre
    :ivar manager_account_id: The manager's account
    :ivar batch_id: The centre's batch
    """

    owner_id: uuid.UUID
    manager_account_id: uuid.UUID
    batch_id: uuid.UUID


def _account(session: Session) -> uuid.UUID:
    """Create an account with a unique phone number.

    :param session: An arranging session
    :return: The account id
    """
    account = Account(
        phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(account)
    session.commit()
    return account.id


def add_member(
    session: Session,
    centre: uuid.UUID,
    *,
    role: str = "teacher",
    decision: str = "accepted",
    revoked: bool = False,
    name: str = "Karim Sir",
    consented: bool = False,
    account_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Arrange a membership row directly.

    :param session: An arranging session
    :param centre: The centre
    :param role: ``manager`` or ``teacher``
    :param decision: The member's decision
    :param revoked: Whether the centre has ended it
    :param name: The member's name at the centre
    :param consented: Whether they agreed to be named publicly
    :param account_id: The member's account, or None for a new one
    :return: ``(member_id, account_id)``
    """
    account = account_id or _account(session)
    now = dt.datetime.now(tz=dt.UTC)
    member = OwnerMember(
        owner_id=centre,
        account_id=account,
        invited_phone=f"+88018{uuid.uuid4().int % 10**8:08d}",
        display_name=name,
        role=role,
        decision=decision,
        created_at=now,
        revoked_at=now if revoked else None,
        public_name_consent_at=now if consented else None,
    )
    session.add(member)
    session.commit()
    return member.id, account


def centre_with_manager(
    session: Session, *, name: str = "Udoy Coaching"
) -> CentreFixture:
    """Arrange a centre, its manager and a batch with one subject.

    :param session: An arranging session
    :param name: The centre's name
    :return: The ids
    """
    centre = Owner(
        account_id=None,
        kind="organisation",
        name=name,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(centre)
    session.commit()
    _, manager = add_member(session, centre.id, role="manager", name="Rina")
    batch = Batch(
        owner_id=centre.id,
        name="Class 9 Maths",
        default_fee=Money("1500.00"),
        fee_due_day=10,
        marksheet_visible=True,
        active=True,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(batch)
    session.commit()
    session.add(BatchSubject(batch_id=batch.id, name="Maths"))
    session.commit()
    return CentreFixture(centre.id, manager, batch.id)


def assign_slot(session: Session, batch_id: uuid.UUID, member_id: uuid.UUID) -> None:
    """Assign a centre member to one weekly slot of a batch.

    :param session: An arranging session
    :param batch_id: The batch
    :param member_id: The member who teaches the slot
    :return: None
    """
    session.add(
        ScheduleSlot(
            batch_id=batch_id,
            weekday=1,
            start_time=dt.time(16, 0),
            end_time=dt.time(17, 0),
            teacher_member_id=member_id,
        )
    )
    session.commit()
