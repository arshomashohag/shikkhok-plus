"""A seat a teacher creates reaches the person it names.

**Written before the linking existed**, because both halves of the
test-first predicate hold: who a seat links to is knowable from the
numbers alone, and a wrong answer is an authorization error -- the wrong
person offered a child's records, or the right person never offered them.

**The gap this closes.** A teacher could name a student only by display
name: ``student_phone`` was accepted by the API and discarded, and a seat
had nowhere to keep it. So no student a teacher added could ever reach
their own seat. Guardians were linked only when their account was created
AFTER the teacher added them; a guardian already signed up was never
linked at all.

**Linking is not agreeing** [BR5.1]. Every link here leaves the decision
``pending``: the person is offered an invitation, never a lens, until
they accept.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV, issue_pair
from app.db.models import Enrollment
from tests.accounts.conftest import make_account
from tests.batches.conftest import TeacherFixture, make_teacher


@pytest.fixture
def client(
    restricted_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Build a client whose app uses the restricted test engine.

    :param restricted_engine: The non-superuser engine
    :param monkeypatch: The patcher
    :return: A context manager yielding the client
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")
    monkeypatch.setenv(JWT_KEYS_ENV, "k1:test-signing-key-padded-to-thirty-two")
    monkeypatch.setenv(JWT_ACTIVE_KID_ENV, "k1")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_APP_HASH", "AAAAAAAAAAA")
    from app.main import create_app

    app = create_app()
    app.state.engine = restricted_engine
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def teacher(owner_session: Session) -> TeacherFixture:
    """Create a teacher with one batch.

    :param owner_session: A session able to arrange fixture data
    :return: The teacher
    """
    return make_teacher(owner_session, name="Physics")


def _number() -> str:
    """Return a fresh, valid, canonical mobile number.

    :return: ``+88017`` and eight random digits
    """
    return f"+88017{uuid.uuid4().int % 10**8:08d}"


def _auth(session: Session, account_id: uuid.UUID) -> dict[str, str]:
    """Authorize as an account.

    :param session: A session to write the token family through
    :param account_id: The account
    :return: The header mapping
    """
    pair = issue_pair(session, account_id=account_id, correlation_id=uuid.uuid4())
    return {"Authorization": f"Bearer {pair.access_token}"}


def _add_seat(
    client: TestClient,
    session: Session,
    teacher: TeacherFixture,
    **body: str,
) -> uuid.UUID:
    """Add a seat through the API, as the teacher does.

    :param client: The test client
    :param session: An arranging session
    :param teacher: The teacher
    :param body: The request body's phone fields
    :return: The new seat's id
    """
    response = client.post(
        f"/v1/batches/{teacher.batch_id}/enrollments",
        json={"display_name": "Rahim", **body},
        headers=_auth(session, teacher.account_id),
    )
    assert response.status_code in (200, 201), response.text
    return uuid.UUID(response.json()["enrollment_id"])


def _seat(session: Session, seat_id: uuid.UUID) -> Enrollment:
    """Read a seat fresh from the database.

    :param session: An arranging session
    :param seat_id: The seat
    :return: The enrollment row
    """
    session.expire_all()
    return session.execute(
        sa.select(Enrollment).where(Enrollment.id == seat_id)
    ).scalar_one()


def _signup(client: TestClient, phone: str, role: str) -> None:
    """Create an account through sign-up, as a new person does.

    :param client: The test client
    :param phone: Their number, in any spelling
    :param role: The role they choose
    :return: None
    """
    response = client.post(
        "/v1/accounts",
        json={"phone": phone, "role": role, "self_name": "Someone"},
    )
    assert response.status_code in (200, 201), response.text


# --------------------------------------------------------------- at creation


def test_the_students_number_is_kept_canonical(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The number was discarded; now it is stored, in the one form.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    seat = _add_seat(client, owner_session, teacher, student_phone="01755-000111")

    assert _seat(owner_session, seat).student_phone == "+8801755000111"


def test_an_existing_student_is_linked_and_left_pending(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A student already signed up is offered the seat, not given it.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    number = _number()
    student = make_account(owner_session, phone=number)

    seat = _seat(
        owner_session,
        _add_seat(client, owner_session, teacher, student_phone=number),
    )

    assert seat.student_account_id == student
    assert seat.student_decision == "pending"


def test_an_existing_guardian_is_linked_and_left_pending(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The case that was never handled: a guardian who signed up first.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    number = _number()
    guardian = make_account(owner_session, phone=number)

    seat = _seat(
        owner_session,
        _add_seat(client, owner_session, teacher, guardian_phone=number),
    )

    assert seat.guardian_account_id == guardian
    assert seat.guardian_decision == "pending"


def test_a_differently_spelled_number_still_links(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """``01711-...`` from the teacher finds ``+88017...`` on the account.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    number = _number()
    student = make_account(owner_session, phone=number)
    local = "0" + number[4:7] + "-" + number[7:]

    seat = _seat(
        owner_session, _add_seat(client, owner_session, teacher, student_phone=local)
    )

    assert seat.student_account_id == student


def test_an_unknown_number_links_nobody(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """No account, no link: the number waits on the seat.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    seat = _seat(
        owner_session,
        _add_seat(client, owner_session, teacher, student_phone=_number()),
    )

    assert seat.student_account_id is None


# --------------------------------------------------------------- at sign-up


def test_signing_up_links_the_seat_waiting_on_your_number(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The student signs up after the teacher added them.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    number = _number()
    seat_id = _add_seat(client, owner_session, teacher, student_phone=number)

    _signup(client, number, "student")

    seat = _seat(owner_session, seat_id)
    assert seat.student_account_id is not None
    assert seat.student_decision == "pending"


def test_signing_up_in_another_spelling_still_links(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The student types their number differently from the teacher.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    number = _number()
    seat_id = _add_seat(client, owner_session, teacher, student_phone=number)

    _signup(client, "0" + number[4:], "student")

    assert _seat(owner_session, seat_id).student_account_id is not None


def test_a_blocked_seat_is_never_relinked(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A number whose account was erased cannot reattach [BR6.2].

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    number = _number()
    seat_id = _add_seat(client, owner_session, teacher, student_phone=number)
    owner_session.execute(
        sa.text(
            "UPDATE enrollment SET student_relink_blocked_at = now() WHERE id = :id"
        ),
        {"id": seat_id},
    )
    owner_session.commit()

    _signup(client, number, "student")

    assert _seat(owner_session, seat_id).student_account_id is None


# --------------------------------------------------------------- end to end


def test_the_linked_student_is_offered_the_seat_and_given_nothing(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The invitation appears; the student lens does not, until accepted.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    number = _number()
    student = make_account(owner_session, phone=number)
    seat_id = _add_seat(client, owner_session, teacher, student_phone=number)
    headers = _auth(owner_session, student)

    invitations = client.get("/v1/invitations", headers=headers).json()
    me = client.get("/v1/me", headers=headers).json()

    assert [row["enrollment_id"] for row in invitations] == [str(seat_id)]
    assert invitations[0]["role"] == "student"
    assert all(lens["kind"] != "student" for lens in me["lenses"])


# ------------------------------------------------- what a linked person sees


def test_a_guardian_does_not_see_a_seat_they_have_not_accepted(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Accepting one child's seat must not list every seat linked to you.

    **The leak linking at creation made likely.** The guardian lens is
    granted by ANY accepted guardian link, and the children list had no
    acceptance predicate of its own -- so a guardian who accepted their
    own child's seat also saw a seat a teacher created by mistyping a
    digit into their number: a stranger's child's name and batch. The
    fee and marks reads were safe, because they check acceptance per
    seat; the list was not.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    number = _number()
    guardian = make_account(owner_session, phone=number)
    mine = _add_seat(client, owner_session, teacher, guardian_phone=number)
    stranger = _add_seat(client, owner_session, teacher, guardian_phone=number)
    headers = _auth(owner_session, guardian)
    accepted = client.post(f"/v1/invitations/{mine}/accept", headers=headers)
    assert accepted.status_code in (200, 204), accepted.text

    listed = [
        row["enrollment_id"]
        for row in client.get("/v1/guardian/children", headers=headers).json()
    ]

    assert listed == [str(mine)]
    assert str(stranger) not in listed


def _accept(
    client: TestClient, session: Session, account: uuid.UUID, seat: uuid.UUID
) -> None:
    """Accept a seat as the person it names.

    :param client: The test client
    :param session: An arranging session
    :param account: The person
    :param seat: The seat
    :return: None
    """
    response = client.post(
        f"/v1/invitations/{seat}/accept", headers=_auth(session, account)
    )
    assert response.status_code in (200, 204), response.text


def test_a_student_lists_their_accepted_batches(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """S1's source: the student's own batches, once accepted.

    No route listed them, so once a student accepted a seat nothing in
    the app could reach it again.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    number = _number()
    student = make_account(owner_session, phone=number)
    accepted = _add_seat(client, owner_session, teacher, student_phone=number)
    # The unaccepted seat is in ANOTHER teacher's batch: one student has
    # at most one seat per batch, which the next test asserts.
    elsewhere = make_teacher(owner_session, name="Chemistry")
    _add_seat(client, owner_session, elsewhere, student_phone=number)
    _accept(client, owner_session, student, accepted)

    rows = client.get(
        "/v1/me/enrollments", headers=_auth(owner_session, student)
    ).json()

    assert [row["enrollment_id"] for row in rows] == [str(accepted)]
    assert rows[0]["batch_name"]


def test_a_student_cannot_list_someone_elses_seat(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Two students, two lists, no overlap.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    first, second = _number(), _number()
    one = make_account(owner_session, phone=first)
    two = make_account(owner_session, phone=second)
    seat_one = _add_seat(client, owner_session, teacher, student_phone=first)
    seat_two = _add_seat(client, owner_session, teacher, student_phone=second)
    _accept(client, owner_session, one, seat_one)
    _accept(client, owner_session, two, seat_two)

    rows = client.get("/v1/me/enrollments", headers=_auth(owner_session, one)).json()

    assert [row["enrollment_id"] for row in rows] == [str(seat_one)]


def test_a_student_reads_progress_for_their_own_seat_only(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The results list S2 shows, refused for a seat that is not theirs.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    mine_number, other_number = _number(), _number()
    student = make_account(owner_session, phone=mine_number)
    other = make_account(owner_session, phone=other_number)
    mine = _add_seat(client, owner_session, teacher, student_phone=mine_number)
    theirs = _add_seat(client, owner_session, teacher, student_phone=other_number)
    _accept(client, owner_session, student, mine)
    _accept(client, owner_session, other, theirs)
    owner_session.execute(
        sa.text("UPDATE batch SET marksheet_visible = true WHERE id = :id"),
        {"id": teacher.batch_id},
    )
    owner_session.commit()
    headers = _auth(owner_session, student)

    own = client.get(f"/v1/me/enrollments/{mine}/progress", headers=headers)
    other_seat = client.get(f"/v1/me/enrollments/{theirs}/progress", headers=headers)

    assert own.status_code == 200, own.text
    assert other_seat.status_code in (403, 404)


def test_the_same_student_twice_in_one_batch_is_refused_not_a_crash(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A second seat for one number is a clear 409 (T8's error state).

    It was a 500: the unique seat constraint fired once linking made
    both seats name the same account.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    number = _number()
    make_account(owner_session, phone=number)
    _add_seat(client, owner_session, teacher, student_phone=number)

    response = client.post(
        f"/v1/batches/{teacher.batch_id}/enrollments",
        json={"display_name": "Rahim again", "student_phone": number},
        headers=_auth(owner_session, teacher.account_id),
    )

    assert response.status_code == 409
    assert (
        response.json()["error"]["message_key"] == "enrollment.student_already_in_batch"
    )


def test_two_waiting_seats_for_one_number_cannot_exist(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Refused before sign-up too, so sign-up never collides on linking.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    number = _number()
    _add_seat(client, owner_session, teacher, student_phone=number)

    response = client.post(
        f"/v1/batches/{teacher.batch_id}/enrollments",
        json={"display_name": "Rahim again", "student_phone": number},
        headers=_auth(owner_session, teacher.account_id),
    )

    assert response.status_code == 409
    _signup(client, number, "student")
