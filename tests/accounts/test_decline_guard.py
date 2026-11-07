"""Declining one seat never flips a sibling the person already accepted.

**The rewrite covers every seat of the student** [audit C-31]: acceptance
is per student, so one decision is written to each batch that student
sits in. It relied on an application invariant -- all of a student's
seats share each link's decision -- and wrote the new value whatever the
old one was. Where seats have diverged (data from before the invariant,
or a backfill), declining a pending seat turned an accepted sibling to
declined, and the nightly void then forgave that sibling's arrears.

The guard: a decline moves only links that are not already accepted,
except on the very seat being declined.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.orm import Session

from app.accounts.decisions import accept_seat, decline_seat
from app.authz.lenses import InvitationLens
from app.db.models import Enrollment, Student
from app.money import Money
from tests.accounts.conftest import make_account
from tests.batches.conftest import make_teacher


def _sibling_seats(
    owner_session: Session, account: uuid.UUID, decisions: tuple[str, str]
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seat one student in two batches with the given guardian decisions.

    :param owner_session: An arranging session
    :param account: The guardian holding both links
    :param decisions: The guardian decision on each seat
    :return: The two seat ids
    """
    teacher = make_teacher(owner_session)
    second = make_teacher(owner_session, name="Second")
    student = Student(
        owner_id=teacher.owner_id,
        display_name="Rahim Uddin",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(student)
    owner_session.flush()
    seats = []
    for batch_id, decision in zip(
        (teacher.batch_id, second.batch_id), decisions, strict=True
    ):
        record = Enrollment(
            batch_id=batch_id,
            student_id=student.id,
            guardian_account_id=account,
            display_name="Rahim Uddin",
            fee_amount=Money("1200.00"),
            student_decision="pending",
            guardian_decision=decision,
            created_at=dt.datetime.now(tz=dt.UTC),
        )
        owner_session.add(record)
        owner_session.flush()
        seats.append(record.id)
    owner_session.commit()
    return seats[0], seats[1]


def _decision(session: Session, seat: uuid.UUID) -> str:
    """Read a seat's guardian decision afresh.

    :param session: A session to read through
    :param seat: The seat
    :return: The decision
    """
    session.expire_all()
    record = session.get(Enrollment, seat)
    assert record is not None
    return record.guardian_decision


def test_declining_a_pending_seat_leaves_an_accepted_sibling_accepted(
    restricted_session: Session, owner_session: Session
) -> None:
    """The divergent case the audit named.

    :param restricted_session: The application's role
    :param owner_session: An arranging session
    :return: None
    """
    guardian = make_account(owner_session)
    pending, accepted = _sibling_seats(owner_session, guardian, ("pending", "accepted"))

    decline_seat(
        restricted_session,
        lens=InvitationLens(account_id=guardian, enrollment_id=pending),
    )

    assert _decision(owner_session, pending) == "declined"
    assert _decision(owner_session, accepted) == "accepted"


def test_declining_still_reaches_every_pending_sibling(
    restricted_session: Session, owner_session: Session
) -> None:
    """The per-student rule is unchanged where seats agree.

    :param restricted_session: The application's role
    :param owner_session: An arranging session
    :return: None
    """
    guardian = make_account(owner_session)
    first, second = _sibling_seats(owner_session, guardian, ("pending", "pending"))

    decline_seat(
        restricted_session,
        lens=InvitationLens(account_id=guardian, enrollment_id=first),
    )

    assert _decision(owner_session, first) == "declined"
    assert _decision(owner_session, second) == "declined"


def test_accepting_still_moves_a_declined_sibling(
    restricted_session: Session, owner_session: Session
) -> None:
    """Acceptance is unguarded: accepting covers every seat of the student.

    :param restricted_session: The application's role
    :param owner_session: An arranging session
    :return: None
    """
    guardian = make_account(owner_session)
    first, second = _sibling_seats(owner_session, guardian, ("pending", "declined"))

    accept_seat(
        restricted_session,
        lens=InvitationLens(account_id=guardian, enrollment_id=first),
    )

    assert _decision(owner_session, first) == "accepted"
    assert _decision(owner_session, second) == "accepted"
