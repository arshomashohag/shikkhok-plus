"""Arrangement helpers for the H4 review tests.

Everything here writes through the table-owner session, so the service under
test, handed the restricted session, is the only thing exercising the
application role's grants.

The hub's existing helpers seat students and record a single attendance row;
review eligibility needs **guardian** seats with chosen join dates and
**per-class** attendance, so those builders live here for every H4 task to
reuse [F16].
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    Attendance,
    Batch,
    BatchListing,
    OwnerListing,
    QueuedSubmission,
    Review,
)
from app.db.models import Session as ClassSession
from app.money import Money
from tests.batches.conftest import enroll, make_teacher

__all__ = [
    "PublicBatch",
    "account",
    "add_review",
    "attend",
    "guardian_seat",
    "hold_classes",
    "public_batch",
    "second_batch",
]

#: The first class date the class builder uses; far enough back that a
#: test choosing ``today`` never has to think about it.
_FIRST_CLASS = dt.date(2024, 1, 1)


@dataclass(frozen=True, slots=True)
class PublicBatch:
    """A batch whose owner and batch listings are arranged.

    :ivar owner_id: The batch's owner
    :ivar teacher_account_id: The owner's account
    :ivar batch_id: The batch
    """

    owner_id: uuid.UUID
    teacher_account_id: uuid.UUID
    batch_id: uuid.UUID


def account(session: Session) -> uuid.UUID:
    """Create an account with a unique phone number.

    :param session: An arranging session
    :return: The account id
    """
    row = Account(
        phone=f"+88019{uuid.uuid4().int % 10**8:08d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(row)
    session.commit()
    return row.id


def _list_batch(
    session: Session,
    owner_id: uuid.UUID,
    batch_id: uuid.UUID,
    *,
    title: str,
    status: str,
) -> None:
    """Insert one batch listing.

    :param session: An arranging session
    :param owner_id: The batch's owner
    :param batch_id: The batch
    :param title: The public title
    :param status: The listing status
    :return: None
    """
    session.add(
        BatchListing(
            batch_id=batch_id,
            owner_id=owner_id,
            slug=f"b-{uuid.uuid4().hex[:12]}",
            status=status,
            public_title=title,
            description_en="Weekend batch",
            show_fee=False,
            show_schedule=False,
            published_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    session.commit()


def public_batch(
    session: Session,
    *,
    title: str = "HSC Physics",
    owner_name: str = "Rahim Sir",
    batch_status: str = "published",
    owner_status: str = "published",
    active: bool = True,
) -> PublicBatch:
    """Arrange a solo tutor's batch with both listings.

    The defaults give a batch a guardian can review; each keyword breaks
    exactly one of spec §6 condition 3's three parts.

    :param session: An arranging session
    :param title: The batch listing's public title
    :param owner_name: The owner listing's public name
    :param batch_status: The batch listing's status
    :param owner_status: The owner listing's status
    :param active: Whether the batch itself is active
    :return: The ids
    """
    teacher = make_teacher(session, name=f"Private name of {title}")
    session.add(
        OwnerListing(
            owner_id=teacher.owner_id,
            slug=f"s-{uuid.uuid4().hex[:12]}",
            status=owner_status,
            public_name=owner_name,
            headline_en="Maths for SSC",
            published_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    session.commit()
    _list_batch(
        session, teacher.owner_id, teacher.batch_id, title=title, status=batch_status
    )
    if not active:
        session.execute(
            sa.update(Batch).where(Batch.id == teacher.batch_id).values(active=False)
        )
        session.commit()
    return PublicBatch(teacher.owner_id, teacher.account_id, teacher.batch_id)


def second_batch(
    session: Session, owner_id: uuid.UUID, *, title: str, status: str = "published"
) -> uuid.UUID:
    """Give an owner another listed batch.

    :param session: An arranging session
    :param owner_id: The owner
    :param title: The new batch listing's public title
    :param status: The new batch listing's status
    :return: The new batch's id
    """
    batch = Batch(
        owner_id=owner_id,
        name=f"Private name of {title}",
        default_fee=Money("1500.00"),
        fee_due_day=10,
        marksheet_visible=True,
        active=True,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(batch)
    session.commit()
    _list_batch(session, owner_id, batch.id, title=title, status=status)
    return batch.id


def guardian_seat(
    session: Session,
    batch_id: uuid.UUID,
    guardian_account_id: uuid.UUID,
    *,
    joined_on: dt.date | None,
    decision: str = "accepted",
    inactive_from: dt.date | None = None,
    relink_blocked: bool = False,
    created_at: dt.datetime | None = None,
) -> uuid.UUID:
    """Seat a child in a batch with a guardian link to an account.

    :param session: An arranging session
    :param batch_id: The batch
    :param guardian_account_id: The guardian
    :param joined_on: The teacher-entered join date, or None for unset
    :param decision: The guardian link's decision
    :param inactive_from: When the seat stopped, or None while active
    :param relink_blocked: Whether the guardian link is blocked from relinking
    :param created_at: When the seat row was created; now by default
    :return: The enrollment id
    """
    seat = enroll(
        session,
        batch_id=batch_id,
        display_name="Child",
        guardian_account_id=guardian_account_id,
        guardian_decision=decision,
    )
    now = dt.datetime.now(tz=dt.UTC)
    session.execute(
        sa.text(
            "UPDATE enrollment SET joined_on = :j, inactive_from = :i, "
            "guardian_relink_blocked_at = :b, created_at = :c WHERE id = :e"
        ),
        {
            "j": joined_on,
            "i": inactive_from,
            "b": now if relink_blocked else None,
            "c": created_at or now,
            "e": seat,
        },
    )
    session.commit()
    return seat


def hold_classes(
    session: Session, batch_id: uuid.UUID, count: int, *, status: str = "held"
) -> list[uuid.UUID]:
    """Create classes in a batch, each with one attendance submission.

    Each class lands on its own date, after any class this helper already
    made for the batch, so repeated calls never collide.

    :param session: An arranging session
    :param batch_id: The batch
    :param count: How many classes
    :param status: Each class's status: ``scheduled``, ``held``, ``cancelled``
    :return: The class ids, oldest first
    """
    existing = session.execute(
        sa.select(sa.func.count())
        .select_from(ClassSession)
        .where(ClassSession.batch_id == batch_id)
    ).scalar_one()
    now = dt.datetime.now(tz=dt.UTC)
    ids: list[uuid.UUID] = []
    for offset in range(existing, existing + count):
        klass = ClassSession(
            batch_id=batch_id,
            date=_FIRST_CLASS + dt.timedelta(days=offset),
            start_time=dt.time(16, 0),
            status=status,
            origin="ad_hoc",
            attendance_version=1,
            topic_version=0,
            created_at=now,
        )
        session.add(klass)
        session.flush()
        session.add(
            QueuedSubmission(
                session_id=klass.id,
                submitted_by_account_id=None,
                kind="attendance",
                client_mutation_id=uuid.uuid4(),
                base_version=0,
                resulting_version=1,
                created_at=now,
            )
        )
        ids.append(klass.id)
    session.commit()
    return ids


def attend(
    session: Session,
    class_ids: Iterable[uuid.UUID],
    enrollment_id: uuid.UUID,
    *,
    present: bool = True,
) -> None:
    """Record one seat's attendance at each of some classes.

    :param session: An arranging session
    :param class_ids: Classes made by :func:`hold_classes`
    :param enrollment_id: The seat
    :param present: Whether the child was present
    :return: None
    """
    for class_id in class_ids:
        submission_id = session.execute(
            sa.select(QueuedSubmission.id).where(
                QueuedSubmission.session_id == class_id,
                QueuedSubmission.kind == "attendance",
            )
        ).scalar_one()
        session.add(
            Attendance(
                session_id=class_id,
                enrollment_id=enrollment_id,
                present=present,
                recorded_at=dt.datetime.now(tz=dt.UTC),
                recorded_by_account_id=None,
                submission_id=submission_id,
            )
        )
    session.commit()


def add_review(
    session: Session,
    batch_id: uuid.UUID,
    author_account_id: uuid.UUID,
    *,
    enrollment_id: uuid.UUID | None = None,
    rating: int = 4,
    status: str = "pending",
    tenure: str = "lt_6m",
) -> uuid.UUID:
    """Insert a review directly, bypassing the write path.

    :param session: An arranging session
    :param batch_id: The reviewed batch
    :param author_account_id: The author
    :param enrollment_id: The evidencing seat, if any
    :param rating: 1 to 5
    :param status: A ``pending``-like status needing no extra columns
    :param tenure: The frozen tenure bucket
    :return: The review id
    """
    review = Review(
        batch_id=batch_id,
        author_account_id=author_account_id,
        enrollment_id=enrollment_id,
        author_role="guardian",
        rating=rating,
        status=status,
        tenure_bucket=tenure,
    )
    session.add(review)
    session.commit()
    return review.id
