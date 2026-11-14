"""ContactMatching: who a verified contact links, and what it never touches.

**Written before the matcher existed**, because both halves of the
test-first predicate hold for every rule here (rules.md BR2.1, BR3.2 to
BR3.6): which link a verified contact takes is knowable from the recorded
contacts alone, and a wrong answer is an authorization error -- a
stranger offered a child's seat, which becomes a lens the moment they
accept it.

The rules, as the teacher sees them:

* a recorded phone owns its link: only that phone's account takes it,
  even when an email is recorded beside it [BR2.1];
* an email links only a link that records no phone [BR3.3];
* matching fills empty links and never writes a decision [BR3.4];
* a link that already names an account is never moved [BR3.5];
* an erased link and a revoked invitation are never linked [BR3.6].

Through the real sign-up and contact routes, as the restricted role,
wherever a route exists; directly through the matcher only for the
properties no route can isolate.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.accounts.identifier import Identifier
from tests.accounts.contact_support import (
    account,
    address,
    auth,
    centre,
    code_for,
    invitation,
    member_link,
    number,
    seat,
    seat_links,
    signup_form,
)
from tests.accounts.signup_support import sign_up
from tests.batches.conftest import TeacherFixture, make_teacher


@pytest.fixture
def teacher(owner_session: Session) -> TeacherFixture:
    """Create a teacher with one batch.

    :param owner_session: An arranging session
    :return: The teacher
    """
    return make_teacher(owner_session, name="Physics")


def _second_batch(session: Session, teacher: TeacherFixture) -> uuid.UUID:
    """Give the teacher another batch, for seats that must not share one.

    :param session: An arranging session
    :param teacher: The teacher
    :return: The batch id
    """
    from app.db.models import Batch
    from app.money import Money

    batch = Batch(
        owner_id=teacher.owner_id,
        name=f"Batch {uuid.uuid4().hex[:6]}",
        default_fee=Money("1000.00"),
        fee_due_day=5,
        marksheet_visible=True,
        active=True,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(batch)
    session.commit()
    return batch.id


# ------------------------------------------------------------------ BR3.2


def test_a_phone_links_every_unlinked_unblocked_link_recording_it(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Signing up on a number takes both links and the live invitation.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    phone = number()
    other = account(owner_session)
    as_student = seat(owner_session, teacher.batch_id, student_phone=phone)
    as_guardian = seat(
        owner_session, _second_batch(owner_session, teacher), guardian_phone=phone
    )
    taken = seat(
        owner_session,
        _second_batch(owner_session, teacher),
        student_phone=phone,
        student_account_id=other,
    )
    blocked = seat(
        owner_session,
        _second_batch(owner_session, teacher),
        student_phone=phone,
        student_relink_blocked_at=dt.datetime.now(tz=dt.UTC),
    )
    hub = centre(owner_session)
    live = invitation(owner_session, hub, phone=phone)
    ended = invitation(owner_session, centre(owner_session), phone=phone, revoked=True)

    holder = sign_up(api_client, signup_form(phone=phone))

    assert seat_links(owner_session, as_student).student == holder
    assert seat_links(owner_session, as_guardian).guardian == holder
    assert seat_links(owner_session, taken).student == other
    assert seat_links(owner_session, blocked).student is None
    assert member_link(owner_session, live)[0] == holder
    assert member_link(owner_session, ended)[0] is None


# ------------------------------------------------------- BR3.3 and BR2.1


def test_an_email_links_only_links_that_record_no_phone(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """An address takes the email-only links and leaves phone-recorded ones.

    The phone beside the email belongs to nobody: the link still waits
    for that phone, because the teacher addressed it by that phone too.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    email = address()
    nobodys_phone = number()
    email_only = seat(owner_session, teacher.batch_id, student_email=email)
    guardian_email_only = seat(
        owner_session, _second_batch(owner_session, teacher), guardian_email=email
    )
    beside_a_phone = seat(
        owner_session,
        _second_batch(owner_session, teacher),
        student_email=email,
        student_phone=nobodys_phone,
        guardian_email=email,
        guardian_phone=number(),
    )
    hub = centre(owner_session)
    by_email = invitation(owner_session, hub, email=email)
    by_both = invitation(
        owner_session, centre(owner_session), phone=number(), email=email
    )

    holder = sign_up(api_client, signup_form(email=email))

    assert seat_links(owner_session, email_only).student == holder
    assert seat_links(owner_session, guardian_email_only).guardian == holder
    both = seat_links(owner_session, beside_a_phone)
    assert both.student is None
    assert both.guardian is None
    assert member_link(owner_session, by_email)[0] == holder
    assert member_link(owner_session, by_both)[0] is None


def test_the_phone_owner_signing_up_after_the_email_owner_takes_the_seat(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Order of sign-up does not hand a phone-recorded link to the email.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    phone, email = number(), address()
    recorded = seat(
        owner_session, teacher.batch_id, student_phone=phone, student_email=email
    )

    email_owner = sign_up(api_client, signup_form(email=email))
    assert seat_links(owner_session, recorded).student is None

    phone_owner = sign_up(api_client, signup_form(phone=phone))
    assert phone_owner != email_owner
    assert seat_links(owner_session, recorded).student == phone_owner


def test_adding_an_email_to_an_account_links_its_email_only_seats(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    outbound: list[tuple[str, str]],
) -> None:
    """Proving an address on an existing account reaches what it names.

    Before U2 only an added phone matched anything (BR3.1, moment 2).

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :param outbound: The captured sends
    :return: None
    """
    email = address()
    recorded = seat(owner_session, teacher.batch_id, guardian_email=email)
    holder = account(owner_session, phone=number())
    headers = auth(api_client, owner_session, holder)

    asked = api_client.post("/v1/me/contact", json={"email": email}, headers=headers)
    assert asked.status_code == 200, asked.text
    assert seat_links(owner_session, recorded).guardian is None

    proved = api_client.post(
        "/v1/me/contact/verify",
        json={"email": email, "code": code_for(outbound, email)},
        headers=headers,
    )
    assert proved.status_code == 200, proved.text
    assert seat_links(owner_session, recorded).guardian == holder


# ------------------------------------------------------------------ BR3.4


def test_matching_sets_links_and_never_decisions(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A linked seat is offered, not accepted: both decisions stay pending.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    email = address()
    recorded = seat(
        owner_session, teacher.batch_id, student_email=email, guardian_email=email
    )
    hub = centre(owner_session)
    offered = invitation(owner_session, hub, email=email)

    holder = sign_up(api_client, signup_form(email=email))

    links = seat_links(owner_session, recorded)
    assert (links.student, links.guardian) == (holder, holder)
    assert (links.student_decision, links.guardian_decision) == ("pending", "pending")
    assert member_link(owner_session, offered) == (holder, "pending")


# ------------------------------------------------------------------ BR3.5


def test_a_recycled_contact_links_only_records_still_unlinked(
    restricted_session: Session, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Whoever verifies a contact next never takes a link someone holds.

    One seat recording E was linked to its first holder before E left
    that account; a second seat recording E is still unlinked. The new
    holder of E takes the second and only the second.

    :param restricted_session: The application's role
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from app.accounts.matching import match_contact

    email = address()
    first_holder = account(owner_session, phone=number())
    held = seat(
        owner_session,
        teacher.batch_id,
        student_email=email,
        student_account_id=first_holder,
    )
    free = seat(
        owner_session, _second_batch(owner_session, teacher), student_email=email
    )
    hub = centre(owner_session)
    held_offer = invitation(owner_session, hub, email=email, account_id=first_holder)
    new_holder = account(owner_session, email=email)

    match_contact(
        restricted_session, account_id=new_holder, contact=Identifier.email(email)
    )
    restricted_session.commit()

    assert seat_links(owner_session, held).student == first_holder
    assert seat_links(owner_session, free).student == new_holder
    assert member_link(owner_session, held_offer)[0] == first_holder


# ------------------------------------------------------------------ BR3.6


def test_an_erased_link_and_a_revoked_invitation_are_never_linked(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The blocked guardian link stays empty; its unblocked student link fills.

    The block is per LINK: the same seat's other link, recording the same
    address and not erased, is linked as normal.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    email = address()
    recorded = seat(
        owner_session,
        teacher.batch_id,
        student_email=email,
        guardian_email=email,
        guardian_relink_blocked_at=dt.datetime.now(tz=dt.UTC),
    )
    ended = invitation(owner_session, centre(owner_session), email=email, revoked=True)

    holder = sign_up(api_client, signup_form(email=email))

    links = seat_links(owner_session, recorded)
    assert links.student == holder
    assert links.guardian is None
    assert member_link(owner_session, ended)[0] is None


def test_the_matcher_never_links_a_blocked_or_revoked_record_directly(
    restricted_session: Session, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The same rule, at the matcher's own boundary, for a phone.

    :param restricted_session: The application's role
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from app.accounts.matching import match_contact

    phone = number()
    erased = seat(
        owner_session,
        teacher.batch_id,
        student_phone=phone,
        guardian_phone=phone,
        student_relink_blocked_at=dt.datetime.now(tz=dt.UTC),
        guardian_relink_blocked_at=dt.datetime.now(tz=dt.UTC),
    )
    ended = invitation(owner_session, centre(owner_session), phone=phone, revoked=True)
    holder = account(owner_session, phone=phone)

    match_contact(
        restricted_session, account_id=holder, contact=Identifier.phone(phone)
    )
    restricted_session.commit()

    links = seat_links(owner_session, erased)
    assert (links.student, links.guardian) == (None, None)
    assert member_link(owner_session, ended)[0] is None


# --------------------------------------------------------------------------
# Test-after: written from BR3.7, BR3.8, NFR4.6 and NFR8.4.
# --------------------------------------------------------------------------


def test_a_second_student_seat_in_one_batch_is_skipped_not_failed(
    restricted_session: Session, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The oldest candidate is linked; the other waits; nothing fails [BR3.7].

    Two seats in ONE batch record the same address (two of the teacher's
    students, so not the same record), and a third batch already seats the
    account as a student, so its candidate is skipped too.

    :param restricted_session: The application's role
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from app.accounts.matching import match_contact
    from app.db.models import Enrollment, Student

    email = address()
    holder = account(owner_session, email=email)
    first = seat(owner_session, teacher.batch_id, student_email=email)
    now = dt.datetime.now(tz=dt.UTC)
    other_student = Student(
        owner_id=teacher.owner_id, display_name="Twin", created_at=now
    )
    owner_session.add(other_student)
    owner_session.flush()
    second = Enrollment(
        batch_id=teacher.batch_id,
        student_id=other_student.id,
        display_name="Twin",
        student_email=email,
        student_decision="pending",
        guardian_decision="pending",
        created_at=now,
    )
    owner_session.add(second)
    owner_session.commit()
    full = _second_batch(owner_session, teacher)
    seat(owner_session, full, student_phone=number(), student_account_id=holder)
    blocked_by_batch = seat(owner_session, full, guardian_phone=number())
    owner_session.execute(
        Enrollment.__table__.update()
        .where(Enrollment.id == blocked_by_batch)
        .values(student_email=email)
    )
    owner_session.commit()

    match_contact(
        restricted_session, account_id=holder, contact=Identifier.email(email)
    )
    restricted_session.commit()

    assert seat_links(owner_session, first).student == holder
    assert seat_links(owner_session, second.id).student is None
    assert seat_links(owner_session, blocked_by_batch).student is None


def test_matching_twice_changes_nothing(
    restricted_session: Session, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A second run finds no empty link left to fill [BR3.8].

    :param restricted_session: The application's role
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from app.accounts.matching import match_contact

    phone = number()
    holder = account(owner_session, phone=phone)
    recorded = seat(owner_session, teacher.batch_id, guardian_phone=phone)
    offer = invitation(owner_session, centre(owner_session), phone=phone)

    for _ in range(2):
        match_contact(
            restricted_session, account_id=holder, contact=Identifier.phone(phone)
        )
        restricted_session.commit()
        once = (seat_links(owner_session, recorded), member_link(owner_session, offer))

    assert once == (
        seat_links(owner_session, recorded),
        member_link(owner_session, offer),
    )
    assert once[0].guardian == holder


def test_a_rolled_back_creation_leaves_no_link(
    restricted_session: Session, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Matching rides on its trigger's transaction [NFR4.6].

    :param restricted_session: The application's role
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    import sqlalchemy as sa

    from app.accounts.service import SignupRole, create_account_rows

    email = address()
    recorded = seat(owner_session, teacher.batch_id, student_email=email)

    created = create_account_rows(
        restricted_session,
        email=email,
        role=SignupRole.STUDENT,
        self_name="Mitu",
    )
    inside = restricted_session.execute(
        sa.text("SELECT student_account_id FROM enrollment WHERE id = :e"),
        {"e": recorded},
    ).scalar_one()
    assert inside == created.account_id  # linked inside the transaction
    restricted_session.rollback()

    assert seat_links(owner_session, recorded).student is None


def test_matching_costs_the_same_statements_for_one_seat_or_twenty(
    restricted_session: Session, owner_session: Session
) -> None:
    """Set-based statements, never a loop over rows [NFR8.4].

    :param restricted_session: The application's role
    :param owner_session: An arranging session
    :return: None
    """
    import sqlalchemy as sa

    from app.accounts.matching import match_contact

    def statements(seats: int) -> int:
        """Count the matcher's statements for one contact with N seats.

        :param seats: How many seats record the contact
        :return: The statement count
        """
        email = address()
        for _ in range(seats):
            seat(
                owner_session,
                make_teacher(owner_session).batch_id,
                guardian_email=email,
            )
        holder = account(owner_session, email=email)
        counted: list[str] = []

        def count(*args: object) -> None:
            """Record one statement.

            :param args: The cursor event's arguments
            :return: None
            """
            counted.append(str(args[2]))

        bind = restricted_session.connection()
        sa.event.listen(bind, "before_cursor_execute", count)
        try:
            match_contact(
                restricted_session, account_id=holder, contact=Identifier.email(email)
            )
        finally:
            sa.event.remove(bind, "before_cursor_execute", count)
        restricted_session.commit()
        return len(counted)

    assert statements(1) == statements(20) == 4
