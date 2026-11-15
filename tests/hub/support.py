"""Arrangement helpers for the hub's owner-listing tests.

Everything here writes through the table-owner session, so a service under
test that is handed the restricted session is the only thing exercising the
application role's grants.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.db.models import Attendance, Batch, QueuedSubmission
from app.db.models import Session as ClassSession
from tests.batches.conftest import TeacherFixture, enroll, make_teacher

__all__ = ["add_attendance", "areas", "centre_lens", "solo_lens"]


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
