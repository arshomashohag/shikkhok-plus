"""The merged readers D1's columns break. Written to FAIL today.

``remove_enrollment`` refuses when ``student_account_id IS NOT NULL``,
and the roster computes ``is_dormant = student_account_id is None``.
Under the superseded model both were correct, because signing in *was*
acceptance. After BR5.1 signing up links the account while the decision
stays ``pending``, so both start reporting *claimed* for a seat nobody
has accepted.

**The removal case is the one that would have shipped as a real
defect** [BR7.1]. A teacher who records a wrong number cannot remove
that seat the instant the stranger on that number signs up -- closing
the single recovery path the whole unit exists to open, in a merged,
routed write path rather than on a screen.

The dormancy case is wrong in a way somebody notices [BR7.2]: the
roster shows a seat as claimed the moment a stranger signs up, which is
the opposite of the signal the teacher needs to spot the mistake.

These are authorization decisions on merged code and their correct
output is knowable from AC2.5.1a without writing the fix, so they are
test-first.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.batches.service import (
    EnrollmentNotRemovable,
    list_roster,
    remove_enrollment,
)
from app.db.models import Account, Enrollment
from tests.batches.conftest import TeacherFixture, make_teacher


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the teacher lens the service requires.

    :param teacher: The teacher to build a lens for
    :return: That teacher's lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def _account(session: Session) -> uuid.UUID:
    """Create one account with a unique number.

    :param session: An arranging session
    :return: The new account's id
    """
    record = Account(
        phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    session.commit()
    return record.id


def _seat(
    session: Session,
    *,
    batch_id: uuid.UUID,
    display_name: str,
    student_account_id: uuid.UUID | None = None,
    student_decision: str = "pending",
    guardian_decision: str = "pending",
) -> uuid.UUID:
    """Create one seat with both decisions stated explicitly.

    :param session: An arranging session
    :param batch_id: The batch the seat belongs to
    :param display_name: The teacher-typed name
    :param student_account_id: The student link, or None
    :param student_decision: The student link's decision
    :param guardian_decision: The guardian link's decision
    :return: The new enrollment's id
    """
    record = Enrollment(
        batch_id=batch_id,
        student_account_id=student_account_id,
        student_decision=student_decision,
        guardian_decision=guardian_decision,
        display_name=display_name,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    session.commit()
    return record.id


# ---------------------------------------------------------------------------
# BR7.1 -- removability reads the decision, not the link.
# ---------------------------------------------------------------------------


def test_a_seat_stays_removable_after_the_named_person_signs_up(
    restricted_session: Session, owner_session: Session
) -> None:
    """The mistyped-number recovery path [BR7.1, AC2.5.1a].

    The stranger on the mistyped number has signed up, so the link
    names an account -- and has accepted nothing. Today's predicate
    reads the link and refuses.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    stranger = _account(owner_session)
    enrollment_id = _seat(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Mistyped number",
        student_account_id=stranger,
        student_decision="pending",
    )

    remove_enrollment(
        restricted_session, lens=_lens(teacher), enrollment_id=enrollment_id
    )

    owner_session.expire_all()
    assert owner_session.get(Enrollment, enrollment_id) is None


def test_a_declined_seat_is_removable_for_the_same_reason(
    restricted_session: Session, owner_session: Session
) -> None:
    """Nobody accepted, so nothing is destroyed [BR7.1, AC2.5.1a].

    Re-adding the number creates a fresh seat the person is free to
    decline again, so removal does not defeat the decline's durability.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    refuser = _account(owner_session)
    enrollment_id = _seat(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Refused",
        student_account_id=refuser,
        student_decision="declined",
    )

    remove_enrollment(
        restricted_session, lens=_lens(teacher), enrollment_id=enrollment_id
    )

    owner_session.expire_all()
    assert owner_session.get(Enrollment, enrollment_id) is None


def test_an_accepted_seat_is_still_refused(
    restricted_session: Session, owner_session: Session
) -> None:
    """A teacher cannot make an accepted person's records go away.

    The positive half: without it a predicate that permitted every
    removal would pass the two above. [BR7.1, ADR-003]

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    joiner = _account(owner_session)
    enrollment_id = _seat(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Accepted",
        student_account_id=joiner,
        student_decision="accepted",
    )

    with pytest.raises(EnrollmentNotRemovable) as refusal:
        remove_enrollment(
            restricted_session, lens=_lens(teacher), enrollment_id=enrollment_id
        )

    assert refusal.value.code == "ENROLLMENT_CLAIMED"


# ---------------------------------------------------------------------------
# BR7.2 -- dormancy is "no link has accepted".
# ---------------------------------------------------------------------------


def test_the_roster_shows_a_signed_up_but_unaccepted_seat_as_not_claimed(
    restricted_session: Session, owner_session: Session
) -> None:
    """Dormant means nobody accepted, not nobody signed up [BR7.2].

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    stranger = _account(owner_session)
    _seat(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Mistyped number",
        student_account_id=stranger,
        student_decision="pending",
    )

    rows = list_roster(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id
    )

    assert len(rows) == 1
    assert rows[0].is_dormant is True


def test_the_roster_shows_an_accepted_seat_as_claimed(
    restricted_session: Session, owner_session: Session
) -> None:
    """Acceptance by either link is what claims the seat [BR7.2].

    The guardian link accepts and the student link does not, which is
    the case an implementation reading only ``student_decision`` gets
    wrong while passing every other test in this file.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    _seat(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Guardian accepted",
        student_decision="pending",
        guardian_decision="accepted",
    )

    rows = list_roster(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id
    )

    assert len(rows) == 1
    assert rows[0].is_dormant is False
