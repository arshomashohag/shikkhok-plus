"""The already-added lookup, and the absence at the heart of D1.

Two obligations, and they pull in opposite directions:

* The lookup **must** say that a seat exists, with the teacher-typed
  name and the role, or the already-added path cannot pre-fill and lock
  its form [BR4.5, AC1.12.1].
* It must say **nothing else** -- no teacher, no batch -- or it becomes
  an oracle for who teaches whom, readable by anyone who can type a
  phone number [BR2.3, AC1.12.2].

And the one that no diff shows: **signing up does not accept**
[BR5.1, AC1.12.3]. Linking an account to a seat leaves its decision
exactly as it was. That is an *absence*, so this file is where it is
proved.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

from sqlalchemy.orm import Session

from app.accounts import service
from app.accounts.service import SignupRole, already_added, create_account
from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.authz.resolve import available_lenses
from app.batches.service import list_batches
from app.db.models import Enrollment
from app.schemas.accounts import AlreadyAddedResponse
from tests.batches.conftest import TeacherFixture, make_teacher


def _phone() -> str:
    """Generate a unique number for one test.

    :return: A number in international form
    """
    return f"+88017{uuid.uuid4().int % 10**8:08d}"


def _guardian_seat(
    session: Session, *, teacher: TeacherFixture, guardian_phone: str
) -> uuid.UUID:
    """Record a seat naming a guardian number nobody has signed up on.

    The shape a teacher actually creates: the number is typed, no
    account exists for it yet, and both decisions are ``pending``
    because naming somebody is not their agreement.

    :param session: An arranging session
    :param teacher: The teacher whose batch holds the seat
    :param guardian_phone: The teacher-typed guardian contact
    :return: The new enrollment's id
    """
    record = Enrollment(
        batch_id=teacher.batch_id,
        display_name="Rahim Uddin",
        guardian_phone=guardian_phone,
        student_decision="pending",
        guardian_decision="pending",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    session.commit()
    return record.id


def test_an_unknown_number_reports_no_seat(
    restricted_session: Session,
) -> None:
    """The empty form path [W1, AC1.11.1].

    :param restricted_session: A session as the application role
    :return: None
    """
    found = already_added(restricted_session, _phone())

    assert found.exists is False
    assert found.display_name is None
    assert found.role is None


def test_a_recorded_number_reports_the_name_and_the_role(
    restricted_session: Session, owner_session: Session
) -> None:
    """Pre-fill as correctable, role locked [BR4.5, AC1.12.1].

    The number was recorded as a GUARDIAN contact, so the role the form
    locks to is Guardian -- derived from which link matched rather than
    from anything stored about the person.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    phone = _phone()
    _guardian_seat(owner_session, teacher=teacher, guardian_phone=phone)

    created = create_account(
        restricted_session,
        phone=phone,
        role=SignupRole.GUARDIAN,
        self_name="Guardian's own name",
    )
    assert created.account_id is not None

    found = already_added(restricted_session, phone)

    assert found.exists is True
    assert found.display_name == "Rahim Uddin"
    assert found.role is SignupRole.GUARDIAN


def test_the_lookup_response_names_neither_teacher_nor_batch(
    restricted_session: Session, owner_session: Session
) -> None:
    """The width bound, asserted on the TYPE [BR2.3, AC1.16.4].

    Asserted over the dataclass's fields rather than over one
    response's values: a value assertion passes while a field nobody
    populated today sits there waiting for a later handler edit to fill
    it. The absences are the requirement, so the absences are what is
    checked.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Chemistry With Mr Karim")
    phone = _phone()
    _guardian_seat(owner_session, teacher=teacher, guardian_phone=phone)
    create_account(
        restricted_session,
        phone=phone,
        role=SignupRole.GUARDIAN,
        self_name="Guardian",
    )

    found = already_added(restricted_session, phone)
    service_fields = {field.name for field in dataclasses.fields(found)}
    wire_fields = set(AlreadyAddedResponse.model_fields)

    assert service_fields == {"exists", "display_name", "role"}
    assert wire_fields == {"already_added", "display_name", "role"}

    # And the value it does carry is the SEAT's name, never the
    # batch's: a teacher who names a batch after themselves would
    # otherwise leak their own identity through the pre-fill.
    assert found.display_name == "Rahim Uddin"
    assert "Karim" not in str(found.display_name)


def test_signing_up_leaves_an_existing_seat_pending(
    restricted_session: Session, owner_session: Session
) -> None:
    """**The single most important absence in this Unit** [BR5.1].

    Linking the account must not move a decision. If signing up quietly
    accepted, every other rule in D1 would be decoration and the
    unconsented-guardian exposure would reopen exactly as it was.

    Asserted on BOTH columns: the account is now named on the guardian
    link, and neither its own decision nor the student's may move.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    phone = _phone()
    enrollment_id = _guardian_seat(owner_session, teacher=teacher, guardian_phone=phone)

    created = create_account(
        restricted_session,
        phone=phone,
        role=SignupRole.GUARDIAN,
        self_name="Guardian",
    )

    owner_session.expire_all()
    seat = owner_session.get(Enrollment, enrollment_id)
    assert seat is not None

    # The link WAS made -- without this the test would pass against an
    # implementation that simply never linked anything, which is a
    # different product rather than a safer one.
    assert seat.guardian_account_id == created.account_id
    assert seat.student_decision == "pending"
    assert seat.guardian_decision == "pending"


def test_a_signed_up_but_unaccepted_seat_grants_no_lens(
    restricted_session: Session, owner_session: Session
) -> None:
    """The consequence of BR5.1, end to end [AC1.11.3, AC1.2.3a].

    The behavioural half of the previous test: the columns being
    untouched is only meaningful because resolution reads them.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    phone = _phone()
    _guardian_seat(owner_session, teacher=teacher, guardian_phone=phone)

    created = create_account(
        restricted_session,
        phone=phone,
        role=SignupRole.GUARDIAN,
        self_name="Guardian",
    )

    lenses = available_lenses(restricted_session, created.account_id)

    assert not any(isinstance(lens, GuardianLens) for lens in lenses)
    assert not any(isinstance(lens, StudentLens) for lens in lenses)


def test_a_teacher_signup_reaches_an_empty_batch_list(
    restricted_session: Session,
) -> None:
    """The other side of the fork [AC1.11.2].

    One signup path produces a working teacher and a student with no
    access, which is the Unit's thesis. Without this half, a predicate
    that withheld every lens would satisfy the test above.

    :param restricted_session: A session as the application role
    :return: None
    """
    created = create_account(
        restricted_session,
        phone=_phone(),
        role=SignupRole.TEACHER,
        self_name="Karim Teacher",
    )

    lenses = available_lenses(restricted_session, created.account_id)
    teacher_lens = next(lens for lens in lenses if isinstance(lens, TeacherLens))

    assert list_batches(restricted_session, lens=teacher_lens) == []


def test_the_lookup_does_not_join_a_batch_at_all() -> None:
    """The absence, asserted structurally [BR2.3].

    A value assertion proves today's handler does not leak the batch;
    this proves the query has **no batch columns to leak**. The rule
    says the bound is on the width of the disclosure, and the
    cheapest durable way to hold a width bound is to have nothing
    wider in hand.

    :return: None
    """
    statement = str(service._LOOKUP_QUERY).lower()

    assert "batch" not in statement
    assert "owner" not in statement
