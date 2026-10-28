"""The invitation grant. Written to FAIL against today's code.

A fourth lens type rather than a branch inside the resolver, and its
**own statement** rather than a fourth scalar on the hot-path query
[ADR-011, NFR20.3]: an invitation grant is a SET -- a person may hold
several pending seats -- and ``_LENS_QUERY`` returns scalars for one
account.

``declined`` is granted deliberately alongside ``pending`` [BR1.3].
BR5.4 makes a decline reversible by its holder, which requires the
holder to still reach the seat; a grant restricted to ``pending`` would
make the reversal unreachable and quietly convert a mis-tap into a
permanent lockout.

The width of what an invitation discloses is a response-SCHEMA
obligation rather than a filter [BR1.4]: three teacher-authored fields,
so the pending read crosses no privacy boundary and there is nothing to
leak.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.invitations import available_invitations, read_invitation
from app.authz.lenses import InvitationLens
from app.authz.summary import lens_summary
from app.db.models import Account, Enrollment
from app.money import Money
from tests.batches.conftest import TeacherFixture, make_teacher


@pytest.fixture
def account(owner_session: Session) -> uuid.UUID:
    """Create one account holding nothing at all.

    :param owner_session: A session able to arrange fixture data
    :return: The new account's id
    """
    record = Account(
        phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(record)
    owner_session.commit()
    return record.id


def _seat(
    session: Session,
    *,
    teacher: TeacherFixture,
    student_account_id: uuid.UUID | None = None,
    guardian_account_id: uuid.UUID | None = None,
    student_decision: str = "pending",
    guardian_decision: str = "pending",
) -> uuid.UUID:
    """Create one seat in a real batch, with both decisions stated.

    A real batch rather than a random ``batch_id``, because an
    invitation renders the batch's name, subject and fee.

    :param session: An arranging session
    :param teacher: The teacher whose batch holds the seat
    :param student_account_id: The student link, or None
    :param guardian_account_id: The guardian link, or None
    :param student_decision: The student link's decision
    :param guardian_decision: The guardian link's decision
    :return: The new enrollment's id
    """
    record = Enrollment(
        batch_id=teacher.batch_id,
        student_account_id=student_account_id,
        guardian_account_id=guardian_account_id,
        student_decision=student_decision,
        guardian_decision=guardian_decision,
        display_name="Teacher Typed Name",
        fee_amount=Money("1200.00"),
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    session.commit()
    return record.id


def test_pending_and_declined_links_grant_an_invitation_lens(
    restricted_session: Session, owner_session: Session, account: uuid.UUID
) -> None:
    """Both unaccepted states reach the seat [BR1.3, BR5.4, AC1.13.1].

    A SET, not a scalar: this account holds two unaccepted seats and
    both must be reachable, which a fourth branch on the hot-path query
    could not express.

    Two batches, because ``uq_enrollment_batch_student`` permits one
    seat per student per batch -- which is itself the reason the set
    matters: a person's several unaccepted seats are in several
    teachers' batches.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param account: The account named on both seats
    :return: None
    """
    physics = make_teacher(owner_session, name="Physics")
    chemistry = make_teacher(owner_session, name="Chemistry")
    pending = _seat(
        owner_session,
        teacher=physics,
        student_account_id=account,
        student_decision="pending",
    )
    declined = _seat(
        owner_session,
        teacher=chemistry,
        student_account_id=account,
        student_decision="declined",
    )

    lenses = available_invitations(restricted_session, account)

    assert {lens.enrollment_id for lens in lenses} == {pending, declined}
    assert all(isinstance(lens, InvitationLens) for lens in lenses)


def test_an_accepted_link_grants_no_invitation_lens(
    restricted_session: Session, owner_session: Session, account: uuid.UUID
) -> None:
    """An accepted seat has left the invitations [BR1.3, BR5.5].

    The negation of the role grant, and the half that fails if someone
    implements "not accepted" as "pending" in one query and as
    "anything" in the other.

    Both links on this seat name the same account and both accepted, so
    a per-link implementation that checked only one column would still
    be caught by the deduplication assertion below.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param account: The account named on the seat
    :return: None
    """
    teacher = make_teacher(owner_session, name="Chemistry")
    _seat(
        owner_session,
        teacher=teacher,
        student_account_id=account,
        guardian_account_id=account,
        student_decision="accepted",
        guardian_decision="accepted",
    )

    assert available_invitations(restricted_session, account) == []


def test_one_account_on_both_links_sees_the_seat_once(
    restricted_session: Session, owner_session: Session, account: uuid.UUID
) -> None:
    """A person accepts their own seat once, not twice [BR5.3].

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param account: The account holding BOTH links
    :return: None
    """
    teacher = make_teacher(owner_session, name="Maths")
    enrollment_id = _seat(
        owner_session,
        teacher=teacher,
        student_account_id=account,
        guardian_account_id=account,
    )

    lenses = available_invitations(restricted_session, account)

    assert [lens.enrollment_id for lens in lenses] == [enrollment_id]


def test_the_invitation_lens_carries_only_the_enrollment_it_scopes(
    restricted_session: Session, owner_session: Session, account: uuid.UUID
) -> None:
    """The lens is the scoping value, and carries nothing else [BR1.4].

    ``account_id`` comes from the base :class:`~app.authz.lenses.Lens`;
    the only field this type adds is the one enrollment it reaches, so
    a handler cannot widen the read to a second seat.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param account: The account named on the seat
    :return: None
    """
    teacher = make_teacher(owner_session, name="Biology")
    _seat(owner_session, teacher=teacher, student_account_id=account)

    lens = available_invitations(restricted_session, account)[0]

    fields = {field.name for field in dataclasses.fields(lens)}
    assert fields == {"account_id", "enrollment_id"}


def test_reading_a_seat_removed_mid_request_raises_rather_than_rendering(
    restricted_session: Session, owner_session: Session, account: uuid.UUID
) -> None:
    """The race the lens cannot close on its own [BR7.1].

    A teacher may legitimately remove an unaccepted seat, and the
    window between resolving the lens and reading the row is real.
    Raising is what stops a caller rendering an invitation with a blank
    batch name and a null fee, which looks like a product defect rather
    than a seat that is simply gone.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param account: The account named on the seat
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    enrollment_id = _seat(owner_session, teacher=teacher, student_account_id=account)
    lens = InvitationLens(account_id=account, enrollment_id=enrollment_id)

    owner_session.execute(sa.delete(Enrollment).where(Enrollment.id == enrollment_id))
    owner_session.commit()

    with pytest.raises(LookupError):
        read_invitation(restricted_session, lens=lens)


def test_the_lens_summary_counts_the_lenses_a_picker_offers(
    restricted_session: Session, owner_session: Session, account: uuid.UUID
) -> None:
    """``lens_count`` is what decides whether a picker is shown.

    The app skips its picker at one and explains itself at zero, so
    this value drives a screen rather than describing one. Asserted at
    zero and at one across the same account, because an implementation
    returning a constant would satisfy either alone.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param account: The account under test
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    enrollment_id = _seat(owner_session, teacher=teacher, student_account_id=account)

    assert lens_summary(restricted_session, account).lens_count == 0

    owner_session.execute(
        sa.update(Enrollment)
        .where(Enrollment.id == enrollment_id)
        .values(student_decision="accepted")
    )
    owner_session.commit()

    assert lens_summary(restricted_session, account).lens_count == 1
