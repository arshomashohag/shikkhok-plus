"""A join request never seats anyone; the owner does, through the roster.

**Written before the implementation** (Review Focus 5, the acceptance
predicate). Closing a request with ``added`` records what the owner did;
it is not how they did it. The owner adds the student with the ordinary
"add student" path, prefilled from the request, and that seat starts
``pending`` for the guardian exactly as any other: the guardian holds an
invitation and no guardian lens until they accept. Nothing in
``app.hub.enquiries`` reaches a seat at all, which
``tests/gates/test_enquiries_imports.py`` holds mechanically and
:func:`test_enquiry_changes_no_seat` holds by observation.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.accounts.decisions import accept_seat
from app.authz.invitations import available_invitations
from app.authz.lenses import GuardianLens, InvitationLens
from app.authz.resolve import available_lenses
from app.hub.enquiries import owner, sending
from app.students.service import SeatRequest, create_student
from tests.enquiries.support import EnquirableWorld, enquirable_owner, guardian
from tests.reviews.support import guardian_seat

NOW = dt.datetime(2026, 11, 19, 4, 0, tzinfo=dt.UTC)
LATER = NOW + dt.timedelta(hours=3)


def _send(
    session: Session,
    account: uuid.UUID,
    world: EnquirableWorld,
    *,
    share_contact: bool = True,
) -> uuid.UUID:
    """Send a request about the world's batch and return its id.

    :param session: The restricted session
    :param account: The guardian
    :param world: The owner asked
    :param share_contact: Whether the guardian shares their contact
    :return: The request id
    """
    return sending.send(
        session,
        account,
        world.owner_slug,
        student_name="Nadia Rahman",
        class_level="class_8",
        message=None,
        batch_id=world.batch_id,
        share_contact=share_contact,
        now=NOW,
    ).id


def _guardian_lenses(session: Session, account: uuid.UUID) -> list[GuardianLens]:
    """Read the guardian lenses an account holds right now.

    :param session: The restricted session
    :param account: The account
    :return: Its guardian lenses
    """
    return [
        lens
        for lens in available_lenses(session, account)
        if isinstance(lens, GuardianLens)
    ]


def test_student_added_from_enquiry_starts_pending(
    owner_session: Session, restricted_session: Session
) -> None:
    """Review Focus 5: a seat added from a request waits for the guardian."""
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session)
    sent = _send(restricted_session, caller, world)

    prefill = owner.get(restricted_session, world.lens, sent)
    assert prefill.guardian_phone == "+8801712345678"
    assert prefill.batch_id == world.batch_id
    student = create_student(
        restricted_session,
        lens=world.lens,
        display_name=prefill.student_name,
        guardian_phone=prefill.guardian_phone,
        seats=[SeatRequest(batch_id=world.batch_id)],
    )
    owner.close(restricted_session, world.lens, sent, "added", LATER)

    (seat,) = student.seats
    stored = owner_session.execute(
        sa.text(
            "SELECT guardian_account_id, guardian_decision FROM enrollment "
            "WHERE id = :e"
        ),
        {"e": seat.enrollment_id},
    ).one()
    assert stored.guardian_account_id == caller
    assert stored.guardian_decision == "pending"
    invitations = available_invitations(restricted_session, caller)
    assert [i.enrollment_id for i in invitations] == [seat.enrollment_id]
    assert _guardian_lenses(restricted_session, caller) == []

    accept_seat(
        restricted_session,
        lens=InvitationLens(account_id=caller, enrollment_id=seat.enrollment_id),
    )

    assert len(_guardian_lenses(restricted_session, caller)) == 1


def _seats(session: Session) -> list[str]:
    """Read every seat, byte for byte, in a stable order.

    :param session: An arranging session
    :return: Each ``enrollment`` row as JSON text, by id
    """
    session.rollback()
    return list(
        session.execute(
            sa.text("SELECT row_to_json(e)::text FROM enrollment e ORDER BY e.id")
        ).scalars()
    )


def test_enquiry_changes_no_seat(
    owner_session: Session, restricted_session: Session
) -> None:
    """Sending, every close and withdrawing leave every seat byte-identical.

    One guardian already holds a seat with this owner, so a request from a
    known family is the case an implementation would most plausibly "help"
    with.
    """
    world = enquirable_owner(owner_session)
    owner_session.execute(
        sa.text(
            "UPDATE owner_listing SET public_contact_phone = '+8801911223344' "
            "WHERE owner_id = :o"
        ),
        {"o": world.lens.owner_id},
    )
    owner_session.commit()
    known = guardian(owner_session)
    guardian_seat(owner_session, world.batch_id, known, joined_on=None)
    pending_family = guardian(owner_session, phone="01812345678")
    guardian_seat(
        owner_session,
        world.batch_id,
        pending_family,
        joined_on=None,
        decision="pending",
    )
    others = [guardian(owner_session, phone=f"0191234567{n}") for n in range(3)]
    before = _seats(owner_session)
    assert len(before) == 2

    closed = {
        outcome: _send(restricted_session, account, world)
        for outcome, account in zip(
            ("added", "not_now", "call_us"),
            (known, pending_family, others[0]),
            strict=True,
        )
    }
    for outcome, enquiry_id in closed.items():
        owner.close(restricted_session, world.lens, enquiry_id, outcome, LATER)
    withdrawn_open = _send(restricted_session, others[1], world, share_contact=False)
    sending.withdraw(restricted_session, others[1], withdrawn_open)
    sending.withdraw(restricted_session, pending_family, closed["not_now"])
    _send(restricted_session, others[2], world)

    assert _seats(owner_session) == before
