"""A guardian's children, grouped from the seats they accepted (G1).

Until G1 a guardian saw a list of seats. The board shows children --
"তাসনিম জাহান · 3 batches" -- so seats are grouped here: **two seats are
one child when the same student account holds both**; a seat with no
student account yet is a child of its own.

**Only this guardian's accepted seats are ever grouped** [BR1.1, BR5.3].
Grouping never reaches out to the student's other seats: a guardian
recorded by one teacher does not see the same child's seat with another
teacher who recorded someone else, which is the merge BR5.3 forbids.

A child is keyed by its first seat's id -- an id the guardian can already
read -- and named by the seat in the first batch alphabetically, as the
teacher typed it [TC-13].
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens
from app.db.models import Batch, Enrollment
from app.errors import AuthorizationError
from app.errors.codes import NOT_AVAILABLE

__all__ = ["Child", "ChildSeat", "child_of", "children_of"]


@dataclass(frozen=True, slots=True)
class ChildSeat:
    """One of a child's seats.

    :ivar enrollment_id: The seat
    :ivar batch_id: Its batch
    :ivar batch_name: The batch's name
    :ivar teacher_name: The teacher's name for students, if set
    """

    enrollment_id: uuid.UUID
    batch_id: uuid.UUID
    batch_name: str
    teacher_name: str | None


@dataclass(frozen=True, slots=True)
class Child:
    """One child, as their guardian sees them.

    :ivar key: The first seat's id, which names the child on the wire
    :ivar display_name: The teacher-typed name of the first seat
    :ivar seats: Their seats, by batch name
    """

    key: uuid.UUID
    display_name: str
    seats: list[ChildSeat]


def children_of(session: Session, *, lens: GuardianLens) -> list[Child]:
    """Group this guardian's accepted seats into children.

    :param session: The session to read through
    :param lens: The guardian lens
    :return: One entry per child, ordered by name
    """
    rows = session.execute(
        sa.select(
            Enrollment.id,
            Enrollment.student_account_id,
            Enrollment.display_name,
            Batch.id,
            Batch.name,
            Batch.teacher_display_name,
        )
        .join(Batch, Batch.id == Enrollment.batch_id)
        .where(
            Enrollment.guardian_account_id == lens.account_id,
            Enrollment.guardian_decision == "accepted",
        )
        .order_by(Batch.name, Enrollment.id)
    ).all()

    groups: dict[uuid.UUID, list[tuple[str, ChildSeat]]] = {}
    for seat_id, student, name, batch_id, batch_name, teacher in rows:
        groups.setdefault(student or seat_id, []).append(
            (name, ChildSeat(seat_id, batch_id, batch_name, teacher))
        )
    children = [
        Child(
            key=min(seat.enrollment_id for _, seat in members),
            display_name=members[0][0],
            seats=[seat for _, seat in members],
        )
        for members in groups.values()
    ]
    return sorted(children, key=lambda child: (child.display_name, child.key))


def child_of(
    session: Session, *, lens: GuardianLens, enrollment_id: uuid.UUID
) -> Child:
    """Return the child holding this seat, with all of their seats.

    :param session: The session to read through
    :param lens: The guardian lens
    :param enrollment_id: Any one of the child's seats
    :return: The child
    :raises AuthorizationError: This guardian has not accepted the seat
    """
    for child in children_of(session, lens=lens):
        if any(seat.enrollment_id == enrollment_id for seat in child.seats):
            return child
    raise AuthorizationError(code=NOT_AVAILABLE, message_key="fees.not_available")
