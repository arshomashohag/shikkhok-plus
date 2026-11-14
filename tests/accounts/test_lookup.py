"""The already-added lookup, and the absence at the heart of D1.

Two obligations, and they pull in opposite directions:

* The lookup **must** say that a seat exists, with the role, or the
  already-added path cannot lock its form [BR4.5, AC1.12.1].
* It must say **nothing else** -- no teacher, no batch and **no name**
  -- or it becomes an oracle for who teaches whom, readable by anyone
  who can type a phone number [BR2.3, AC1.12.2]. The name was dropped
  on 2026-11-07 (audit C-06): it is the child's name as a teacher typed
  it, and the route is public, so it tied a child's name to a phone
  number before anyone had proved they held that number.

And the one that no diff shows: **signing up does not accept**
[BR5.1, AC1.12.3]. Linking an account to a seat leaves its decision
exactly as it was. That is an *absence*, so this file is where it is
proved.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.accounts import service
from app.accounts.service import SignupRole, already_added, create_account
from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.authz.resolve import available_lenses
from app.batches.service import list_batches
from app.db.models import Enrollment
from app.schemas.accounts import AlreadyAddedResponse
from tests.batches.conftest import TeacherFixture, make_teacher
from tests.students_support import student_for


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
        student_id=student_for(session, teacher.batch_id),
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
    assert found.role is None


def test_a_recorded_number_reports_the_role_and_no_name(
    restricted_session: Session, owner_session: Session
) -> None:
    """Role locked, nothing pre-filled [BR4.5, AC1.12.1, C-06].

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
    assert found.role is SignupRole.GUARDIAN
    assert "Rahim" not in repr(found)


def test_a_guardian_contact_is_found_before_any_account_exists(
    restricted_session: Session, owner_session: Session
) -> None:
    """The lookup's real order: it runs BEFORE signup [BR4.5].

    The test above creates the account first and only then asks, which
    is the one order the form never uses -- the lookup is called while
    the signup form renders, when no account exists yet. Asked in that
    order it must still find the teacher-typed number on the seat.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    phone = _phone()
    _guardian_seat(owner_session, teacher=teacher, guardian_phone=phone)

    found = already_added(restricted_session, phone)

    assert found.exists is True
    assert found.role is SignupRole.GUARDIAN
    assert "Rahim" not in repr(found)


def test_a_student_number_is_found_before_any_account_exists(
    restricted_session: Session, owner_session: Session
) -> None:
    """A student seat locks the form to Student [BR4.5].

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    phone = _phone()
    owner_session.add(
        Enrollment(
            batch_id=teacher.batch_id,
            student_id=student_for(owner_session, teacher.batch_id),
            display_name="Karim Hossain",
            student_phone=phone,
            student_decision="pending",
            guardian_decision="pending",
            created_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    owner_session.commit()

    found = already_added(restricted_session, phone)

    assert found.exists is True
    assert found.role is SignupRole.STUDENT
    assert "Karim" not in repr(found)


def test_a_relink_blocked_seat_is_not_reported(
    restricted_session: Session, owner_session: Session
) -> None:
    """An erased number is not offered its old seat back [BR6.2].

    Signup will not relink a blocked seat, so pre-filling from one
    would promise a link that never happens.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    phone = _phone()
    owner_session.add(
        Enrollment(
            batch_id=teacher.batch_id,
            student_id=student_for(owner_session, teacher.batch_id),
            display_name="Karim Hossain",
            student_phone=phone,
            student_decision="pending",
            guardian_decision="pending",
            student_relink_blocked_at=dt.datetime.now(tz=dt.UTC),
            created_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    owner_session.commit()

    found = already_added(restricted_session, phone)

    assert found.exists is False


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

    # **No name on the service type at all** [C-06]: a field nobody
    # fills today is the field a later edit fills. The wire keeps its
    # `display_name` key for clients already in the field, and
    # `test_the_public_lookup_never_returns_a_name` asserts it never
    # carries one.
    assert service_fields == {"exists", "role"}
    assert wire_fields == {"already_added", "display_name", "role"}
    assert "Rahim" not in repr(found)
    assert "Karim" not in repr(found)


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
    # And, since C-06, no name either: the statement selects no column
    # that could carry one, so no handler edit can surface it.
    assert "display_name" not in statement


def test_the_public_lookup_never_returns_a_name(
    client: TestClient, owner_session: Session
) -> None:
    """The child's name never crosses the public route [C-06].

    Asserted on the BYTES at the boundary an attacker observes, not on
    the service value: the route is unauthenticated, so the only thing
    between a typed phone number and a child's name is what this
    response contains. ``display_name`` stays on the wire for clients
    already installed -- an empty string where a seat exists, because
    the Android mapper refuses a seat whose name is null -- and never
    carries the name a teacher typed.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    guardian = _phone()
    _guardian_seat(owner_session, teacher=teacher, guardian_phone=guardian)

    found = client.get("/v1/accounts/already-added", params={"phone": guardian})
    absent = client.get("/v1/accounts/already-added", params={"phone": _phone()})

    assert found.status_code == 200, found.text
    assert found.json() == {
        "already_added": True,
        "display_name": "",
        "role": "guardian",
    }
    assert "Rahim" not in found.text
    assert absent.json() == {
        "already_added": False,
        "display_name": None,
        "role": None,
    }


# --------------------------------------------------------------------------
# The email form [U2: BR4.1 to BR4.3, NFR1.1]. Written BEFORE the email
# form existed: what the lookup may say is knowable from the recorded
# seats, and a wider answer is an oracle on a guessable identifier.
# --------------------------------------------------------------------------

_NOTHING = {"already_added": False, "display_name": None, "role": None}


def _email_lookup(client: TestClient, email: str) -> object:
    """Ask the public lookup about an address.

    :param client: A client against the restricted engine
    :param email: The address typed into the form
    :return: The response
    """
    return client.get("/v1/accounts/already-added", params={"email": email})


def test_an_email_recorded_on_an_email_only_seat_reports_its_role(
    client: TestClient, owner_session: Session
) -> None:
    """The student link is preferred; the answer is existence and role only.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    from tests.accounts.contact_support import address, seat

    teacher = make_teacher(owner_session, name="Physics")
    as_student, as_guardian = address(), address()
    seat(owner_session, teacher.batch_id, student_email=as_student)
    seat(owner_session, teacher.batch_id, guardian_email=as_guardian)

    student = _email_lookup(client, as_student.upper())
    guardian = _email_lookup(client, as_guardian)

    assert student.status_code == 200, student.text
    assert student.json() == {
        "already_added": True,
        "display_name": "",
        "role": "student",
    }
    assert guardian.json() == {
        "already_added": True,
        "display_name": "",
        "role": "guardian",
    }
    assert "Rahim" not in student.text + guardian.text


def test_an_email_answers_alike_whether_or_not_an_account_holds_it(
    client: TestClient, owner_session: Session
) -> None:
    """Three cases, one byte-identical answer [BR4.3, NFR1.1].

    An address recorded on no seat; an address held by an account that
    IS linked to a seat, which records only a phone; and an address never
    seen. A true answer would mean "an account holds this email", an
    account-existence oracle on a guessable identifier.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    from tests.accounts.contact_support import account, address, number, seat

    teacher = make_teacher(owner_session, name="Physics")
    held = address()
    holder = account(owner_session, phone=number(), email=held)
    seat(
        owner_session,
        teacher.batch_id,
        student_phone=number(),
        student_account_id=holder,
        guardian_phone=number(),
        guardian_account_id=holder,
    )

    answers = [
        _email_lookup(client, held),
        _email_lookup(client, address()),
        _email_lookup(client, "never-seen@example.com"),
    ]

    assert {response.status_code for response in answers} == {200}
    assert [response.json() for response in answers] == [_NOTHING] * 3
    assert len({response.content for response in answers}) == 1
    headers = [
        {k: v for k, v in response.headers.items() if k.lower() != "x-correlation-id"}
        for response in answers
    ]
    assert headers[0] == headers[1] == headers[2]


def test_an_email_recorded_beside_a_phone_reports_nothing(
    client: TestClient, owner_session: Session
) -> None:
    """The phone owns that link, so the email would never link it [BR4.3].

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    from tests.accounts.contact_support import address, number, seat

    teacher = make_teacher(owner_session, name="Physics")
    email = address()
    seat(
        owner_session,
        teacher.batch_id,
        guardian_email=email,
        guardian_phone=number(),
        student_email=email,
        student_phone=number(),
    )

    assert _email_lookup(client, email).json() == _NOTHING


def test_an_erased_email_link_reports_nothing(
    client: TestClient, owner_session: Session
) -> None:
    """Sign-up will not relink it, so the form must not promise it [BR4.3].

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    from tests.accounts.contact_support import address, seat

    teacher = make_teacher(owner_session, name="Physics")
    email = address()
    seat(
        owner_session,
        teacher.batch_id,
        student_email=email,
        student_relink_blocked_at=dt.datetime.now(tz=dt.UTC),
    )

    assert _email_lookup(client, email).json() == _NOTHING


def test_the_lookup_takes_exactly_one_of_phone_or_email(client: TestClient) -> None:
    """Neither and both are refused before anything is counted [BR4.1].

    :param client: A client against the restricted engine
    :return: None
    """
    neither = client.get("/v1/accounts/already-added")
    both = client.get(
        "/v1/accounts/already-added",
        params={"phone": _phone(), "email": "a@example.com"},
    )

    assert neither.status_code == 422
    assert both.status_code == 422
