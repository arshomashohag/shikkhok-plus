"""The per-link state machine. Written to FAIL against today's code.

The practice names these by name: *acceptance state transitions in D1 --
a seat moving from pending to accepted or declined grants or withholds a
guardian lens, so a wrong answer is an authorization error and the
predicate holds. This is the gap the re-cut exists to close and it is
test-first* [team: Testing Posture, 2026-10-22].

**Four transitions exist and one absence is load-bearing.**
``pending -> accepted``, ``pending -> declined`` and
``declined -> accepted`` are the three the holder can make; nothing
returns a link to ``pending`` [BR6.1], and no teacher action moves one at
all [BR5.4].

The hardest case to get right is the last test in this file, because
BR5.2 and BR5.3 read as a contradiction unless both are implemented:
a decision is stored **per link** and never speaks for the other person,
*and* one action moves both columns when one account holds both links.
An implementation satisfying either alone passes half of this file.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy.orm import Session

from app.accounts.decisions import accept_seat, decline_seat
from app.authz.lenses import InvitationLens
from app.db.models import Account, Enrollment


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


@pytest.fixture
def student(owner_session: Session) -> uuid.UUID:
    """Build the account that holds the student link.

    :param owner_session: A session able to arrange fixture data
    :return: The account id
    """
    return _account(owner_session)


@pytest.fixture
def guardian(owner_session: Session) -> uuid.UUID:
    """Build a DIFFERENT account, holding the guardian link.

    :param owner_session: A session able to arrange fixture data
    :return: The account id
    """
    return _account(owner_session)


def _seat(
    session: Session,
    *,
    student_account_id: uuid.UUID | None = None,
    guardian_account_id: uuid.UUID | None = None,
    student_decision: str = "pending",
    guardian_decision: str = "pending",
) -> uuid.UUID:
    """Create one seat with both decisions stated explicitly.

    :param session: An arranging session
    :param student_account_id: The student link, or None
    :param guardian_account_id: The guardian link, or None
    :param student_decision: The student link's decision
    :param guardian_decision: The guardian link's decision
    :return: The new enrollment's id
    """
    record = Enrollment(
        batch_id=uuid.uuid4(),
        student_account_id=student_account_id,
        guardian_account_id=guardian_account_id,
        student_decision=student_decision,
        guardian_decision=guardian_decision,
        display_name="Teacher Typed Name",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    session.commit()
    return record.id


def _decisions(session: Session, enrollment_id: uuid.UUID) -> tuple[str, str]:
    """Read both decision columns back from the database.

    Read through a fresh query rather than from an ORM identity map, so
    a service that mutated an in-memory object without committing fails
    here rather than passing.

    :param session: A session to read through
    :param enrollment_id: The seat to read
    :return: The student and guardian decisions, in that order
    """
    session.expire_all()
    record = session.get(Enrollment, enrollment_id)
    assert record is not None
    return record.student_decision, record.guardian_decision


def _lens(account_id: uuid.UUID, enrollment_id: uuid.UUID) -> InvitationLens:
    """Build the invitation lens the decision services require.

    :param account_id: The holder making the decision
    :param enrollment_id: The one seat the lens reaches
    :return: The lens
    """
    return InvitationLens(account_id=account_id, enrollment_id=enrollment_id)


def test_pending_to_accepted_moves_only_the_holders_link(
    restricted_session: Session,
    owner_session: Session,
    student: uuid.UUID,
    guardian: uuid.UUID,
) -> None:
    """A student's acceptance says nothing for the guardian [BR5.2].

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param student: The student link's holder
    :param guardian: The guardian link's holder
    :return: None
    """
    enrollment_id = _seat(
        owner_session,
        student_account_id=student,
        guardian_account_id=guardian,
    )

    accept_seat(restricted_session, lens=_lens(student, enrollment_id))

    assert _decisions(owner_session, enrollment_id) == ("accepted", "pending")


def test_pending_to_declined_moves_only_the_holders_link(
    restricted_session: Session,
    owner_session: Session,
    student: uuid.UUID,
    guardian: uuid.UUID,
) -> None:
    """A guardian's decline leaves the student's seat standing [BR5.2].

    The role-dependent half this project recorded on 2026-10-22: a
    guardian's refusal withdraws only the guardian's own lens.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param student: The student link's holder
    :param guardian: The guardian link's holder
    :return: None
    """
    enrollment_id = _seat(
        owner_session,
        student_account_id=student,
        guardian_account_id=guardian,
        student_decision="accepted",
    )

    decline_seat(restricted_session, lens=_lens(guardian, enrollment_id))

    assert _decisions(owner_session, enrollment_id) == ("accepted", "declined")


def test_declined_to_accepted_is_reversible_by_its_holder(
    restricted_session: Session,
    owner_session: Session,
    student: uuid.UUID,
) -> None:
    """A mis-tap does not lock a person out permanently [BR5.4].

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param student: The student link's holder
    :return: None
    """
    enrollment_id = _seat(
        owner_session,
        student_account_id=student,
        student_decision="declined",
    )

    accept_seat(restricted_session, lens=_lens(student, enrollment_id))

    assert _decisions(owner_session, enrollment_id) == ("accepted", "pending")


def test_no_decision_service_resets_a_link_to_pending(
    restricted_session: Session,
    owner_session: Session,
    student: uuid.UUID,
) -> None:
    """Nothing in D1 clears a decision [BR6.1].

    The absence BR5.4's asymmetry depends on. Asserted by exercising
    every write path D1 offers against an already-declined link and
    reading the column back: after accept and after decline, the value
    is never ``pending`` again.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param student: The student link's holder
    :return: None
    """
    enrollment_id = _seat(
        owner_session,
        student_account_id=student,
        student_decision="declined",
    )

    decline_seat(restricted_session, lens=_lens(student, enrollment_id))
    assert _decisions(owner_session, enrollment_id)[0] == "declined"

    accept_seat(restricted_session, lens=_lens(student, enrollment_id))
    assert _decisions(owner_session, enrollment_id)[0] == "accepted"

    accept_seat(restricted_session, lens=_lens(student, enrollment_id))
    assert _decisions(owner_session, enrollment_id)[0] == "accepted"


def test_one_account_on_both_links_decides_once_for_both(
    restricted_session: Session,
    owner_session: Session,
    student: uuid.UUID,
) -> None:
    """One action moves both columns when one person holds both [BR5.3].

    **The case that reads as a contradiction of BR5.2 and is not.**
    BR5.2 governs the DATA -- a decision per link; BR5.3 governs the
    ACTION -- one action may carry both decisions when one account
    holds both links. An implementation that moved only the student
    column here would leave a person accepted as student and pending as
    guardian for themselves.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param student: The account holding BOTH links
    :return: None
    """
    enrollment_id = _seat(
        owner_session,
        student_account_id=student,
        guardian_account_id=student,
    )

    accept_seat(restricted_session, lens=_lens(student, enrollment_id))

    assert _decisions(owner_session, enrollment_id) == ("accepted", "accepted")
