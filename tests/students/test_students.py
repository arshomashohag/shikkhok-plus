"""A teacher's students, apart from any batch, end to end [0018].

Through the real app as the restricted role, so ownership scoping and the
privacy policy are what is under test rather than a service called with
a hand-built lens.

**Written after the implementation**, and from the decisions the owner
approved on 2026-11-05 (D1--D5) rather than from the code: each test
names the decision it pins.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Account, Batch, Enrollment, Student
from app.money import Money
from tests.batches.conftest import TeacherFixture, make_teacher
from tests.conftest import bearer

STUDENT_PHONE = "+8801812345678"
GUARDIAN_PHONE = "+8801711223344"


@pytest.fixture
def client(api_client: TestClient) -> Iterator[TestClient]:
    """Use the shared restricted-role client.

    :param api_client: The client
    :return: A context manager yielding it
    """
    yield api_client


def _second_batch(session: Session, teacher: TeacherFixture, name: str) -> uuid.UUID:
    """Give a teacher one more batch.

    :param session: An arranging session
    :param teacher: The teacher
    :param name: The batch's name
    :return: The new batch's id
    """
    batch = Batch(
        owner_id=teacher.owner_id,
        name=name,
        default_fee=Money("1200.00"),
        fee_due_day=5,
        marksheet_visible=True,
        active=True,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(batch)
    session.commit()
    return batch.id


def _account(session: Session, phone: str) -> uuid.UUID:
    """Sign a person up with a number.

    :param session: An arranging session
    :param phone: Their canonical number
    :return: The account id
    """
    account = Account(phone=phone, created_at=dt.datetime.now(tz=dt.UTC))
    session.add(account)
    session.commit()
    return account.id


@pytest.fixture
def teacher(owner_session: Session) -> TeacherFixture:
    """Create a teacher with one batch, "Physics".

    :param owner_session: An arranging session
    :return: The teacher
    """
    return make_teacher(owner_session, name="Physics")


def _create(
    client: TestClient,
    headers: dict[str, str],
    *,
    batches: list[uuid.UUID],
    phone: str | None = STUDENT_PHONE,
    name: str = "Rafiq Hasan",
) -> dict[str, object]:
    """Add a student through the API and return the body.

    :param client: The test client
    :param headers: The teacher's authorization
    :param batches: The batches to put them in
    :param phone: The student number
    :param name: The name
    :return: The response body
    """
    response = client.post(
        "/v1/students",
        headers=headers,
        json={
            "display_name": name,
            "student_phone": phone,
            "guardian_phone": GUARDIAN_PHONE,
            "enrollments": [{"batch_id": str(batch)} for batch in batches],
        },
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def test_one_student_sits_in_two_batches(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The change itself: one record, a seat in each batch.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    chemistry = _second_batch(owner_session, teacher, "Chemistry")
    headers = bearer(owner_session, teacher.account_id)

    created = _create(client, headers, batches=[teacher.batch_id, chemistry])

    listed = client.get("/v1/students", headers=headers).json()
    assert len(listed) == 1
    seats = listed[0]["enrollments"]
    assert [seat["batch_name"] for seat in seats] == ["Chemistry", "Physics"]
    # Each seat charges its own batch's fee unless told otherwise [D5].
    assert [seat["fee_amount"] for seat in seats] == ["1200.00", "1500.00"]

    for batch in (teacher.batch_id, chemistry):
        roster = client.get(f"/v1/batches/{batch}/roster", headers=headers).json()
        assert [row["student_id"] for row in roster] == [created["student_id"]]


def test_a_student_may_be_in_no_batch(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """D3: batches are suggested, never required.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    headers = bearer(owner_session, teacher.account_id)
    _create(client, headers, batches=[], name="Mehedi")
    _create(client, headers, batches=[teacher.batch_id], phone=None, name="Nusrat")

    unassigned = client.get("/v1/students?unassigned=true", headers=headers).json()
    in_physics = client.get(
        f"/v1/students?batch_id={teacher.batch_id}", headers=headers
    ).json()
    not_in_physics = client.get(
        f"/v1/students?exclude_batch_id={teacher.batch_id}", headers=headers
    ).json()

    assert [row["display_name"] for row in unassigned] == ["Mehedi"]
    assert unassigned[0]["enrollments"] == []
    assert [row["display_name"] for row in in_physics] == ["Nusrat"]
    assert [row["display_name"] for row in not_in_physics] == ["Mehedi"]


def test_a_number_already_on_the_list_is_refused(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """D2: duplicates are found by student number, per teacher.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    headers = bearer(owner_session, teacher.account_id)
    _create(client, headers, batches=[])

    again = client.post(
        "/v1/students",
        headers=headers,
        json={"display_name": "Someone Else", "student_phone": STUDENT_PHONE},
    )

    assert again.status_code == 409
    assert again.json()["error"]["code"] == "STUDENT_PHONE_TAKEN"


def test_the_same_number_is_a_different_student_for_another_teacher(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """D2's uniqueness is per teacher: two tutors may teach one child.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    other = make_teacher(owner_session, name="Maths")
    _create(client, bearer(owner_session, teacher.account_id), batches=[])
    _create(client, bearer(owner_session, other.account_id), batches=[])

    assert owner_session.execute(sa.select(sa.func.count(Student.id))).scalar() == 2


def test_adding_a_known_number_to_a_batch_reuses_the_student(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The roster's own add path seats the existing student [D2].

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    chemistry = _second_batch(owner_session, teacher, "Chemistry")
    headers = bearer(owner_session, teacher.account_id)
    created = _create(client, headers, batches=[teacher.batch_id])

    response = client.post(
        f"/v1/batches/{chemistry}/enrollments",
        headers=headers,
        json={"display_name": "Rafiq", "student_phone": STUDENT_PHONE},
    )

    assert response.status_code == 201, response.text
    assert response.json()["student_id"] == created["student_id"]
    detail = client.get(f"/v1/students/{created['student_id']}", headers=headers)
    assert len(detail.json()["enrollments"]) == 2


def test_another_teachers_student_is_unreachable(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Every route scopes on the lens; a foreign id is a 404, not a 403.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    other = make_teacher(owner_session, name="Maths")
    mine = _create(client, bearer(owner_session, teacher.account_id), batches=[])
    theirs = bearer(owner_session, other.account_id)
    sid = mine["student_id"]

    assert client.get(f"/v1/students/{sid}", headers=theirs).status_code == 404
    assert (
        client.patch(
            f"/v1/students/{sid}", headers=theirs, json={"display_name": "X"}
        ).status_code
        == 404
    )
    assert client.delete(f"/v1/students/{sid}", headers=theirs).status_code == 404
    assert (
        client.post(
            f"/v1/students/{sid}/enrollments",
            headers=theirs,
            json={"batch_id": str(other.batch_id)},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/v1/batches/{other.batch_id}/students",
            headers=theirs,
            json={"student_ids": [sid]},
        ).status_code
        == 404
    )
    assert client.get("/v1/students", headers=theirs).json() == []
    # Nor can a teacher seat their own student in a foreign batch.
    assert (
        client.post(
            "/v1/students",
            headers=theirs,
            json={
                "display_name": "Y",
                "enrollments": [{"batch_id": str(teacher.batch_id)}],
            },
        ).status_code
        == 404
    )
    assert owner_session.execute(sa.select(sa.func.count(Student.id))).scalar() == 1


def test_one_acceptance_covers_every_batch_of_the_student(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """D1: one invitation per student, and accepting it accepts every seat.

    A seat added later for the same student starts accepted for the
    person who already accepted, and pending for anyone else.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    chemistry = _second_batch(owner_session, teacher, "Chemistry")
    maths = _second_batch(owner_session, teacher, "Maths")
    student_account = _account(owner_session, STUDENT_PHONE)
    headers = bearer(owner_session, teacher.account_id)
    created = _create(client, headers, batches=[teacher.batch_id, chemistry])

    student = bearer(owner_session, student_account)
    invitations = client.get("/v1/invitations", headers=student).json()
    assert len(invitations) == 1
    assert len(invitations[0]["also_covers"]) == 1

    accepted = client.post(
        f"/v1/invitations/{invitations[0]['enrollment_id']}/accept", headers=student
    )
    assert accepted.status_code in (200, 204), accepted.text

    decisions = owner_session.execute(
        sa.select(Enrollment.student_decision, Enrollment.guardian_decision).where(
            Enrollment.student_id == uuid.UUID(str(created["student_id"]))
        )
    ).all()
    assert [row[0] for row in decisions] == ["accepted", "accepted"]
    # The guardian has decided nothing, and nothing was decided for them.
    assert [row[1] for row in decisions] == ["pending", "pending"]
    assert client.get("/v1/invitations", headers=student).json() == []

    later = client.post(
        f"/v1/students/{created['student_id']}/enrollments",
        headers=headers,
        json={"batch_id": str(maths)},
    )
    assert later.status_code == 201, later.text
    new_seat = owner_session.execute(
        sa.select(Enrollment.student_decision, Enrollment.guardian_decision).where(
            Enrollment.batch_id == maths
        )
    ).one()
    assert tuple(new_seat) == ("accepted", "pending")
    assert later.json()["student_state"] == "accepted"


def test_an_acceptance_is_never_carried_to_somebody_new(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A changed number resets that link, so nobody inherits a lens.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    headers = bearer(owner_session, teacher.account_id)
    created = _create(client, headers, batches=[teacher.batch_id], phone=None)
    _account(owner_session, "+8801799000111")

    edited = client.patch(
        f"/v1/students/{created['student_id']}",
        headers=headers,
        json={"student_phone": "+8801799000111"},
    )

    assert edited.status_code == 200, edited.text
    seat = owner_session.execute(
        sa.select(Enrollment.student_decision, Enrollment.student_phone).where(
            Enrollment.batch_id == teacher.batch_id
        )
    ).one()
    assert tuple(seat) == ("pending", "+8801799000111")


def test_a_rename_reaches_every_seat(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The seats' copies stay in step with the student.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    chemistry = _second_batch(owner_session, teacher, "Chemistry")
    headers = bearer(owner_session, teacher.account_id)
    created = _create(client, headers, batches=[teacher.batch_id, chemistry])

    client.patch(
        f"/v1/students/{created['student_id']}",
        headers=headers,
        json={"display_name": "Rafiqul Hasan"},
    )

    for batch in (teacher.batch_id, chemistry):
        roster = client.get(f"/v1/batches/{batch}/roster", headers=headers).json()
        assert [row["display_name"] for row in roster] == ["Rafiqul Hasan"]


def test_an_accepted_number_cannot_be_changed(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Changing it would hand that person's view of the child to another.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    student_account = _account(owner_session, STUDENT_PHONE)
    headers = bearer(owner_session, teacher.account_id)
    created = _create(client, headers, batches=[teacher.batch_id])
    student = bearer(owner_session, student_account)
    invitation = client.get("/v1/invitations", headers=student).json()[0]
    client.post(
        f"/v1/invitations/{invitation['enrollment_id']}/accept", headers=student
    )

    refused = client.patch(
        f"/v1/students/{created['student_id']}",
        headers=headers,
        json={"student_phone": "+8801799000222"},
    )

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "STUDENT_NUMBER_ACCEPTED"


def test_a_student_in_an_active_batch_cannot_be_removed(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """D4: leave every batch first.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    headers = bearer(owner_session, teacher.account_id)
    created = _create(client, headers, batches=[teacher.batch_id])

    refused = client.delete(f"/v1/students/{created['student_id']}", headers=headers)

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "STUDENT_IN_ACTIVE_BATCH"
    assert created["is_removable"] is False


def test_a_student_with_no_seats_is_deleted(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """D4: nothing to keep, so nothing is kept.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    headers = bearer(owner_session, teacher.account_id)
    created = _create(client, headers, batches=[])

    removed = client.delete(f"/v1/students/{created['student_id']}", headers=headers)

    assert removed.status_code == 204
    assert owner_session.execute(sa.select(sa.func.count(Student.id))).scalar() == 0


def test_a_student_who_left_is_archived_with_their_history(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """D4: the seats outlive the removal; the student leaves the list.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    headers = bearer(owner_session, teacher.account_id)
    created = _create(client, headers, batches=[teacher.batch_id])
    seat = created["enrollments"][0]["enrollment_id"]  # type: ignore[index]
    client.patch(
        f"/v1/enrollments/{seat}/inactive-from",
        headers=headers,
        json={"inactive_from": "2026-11-01"},
    )

    removed = client.delete(f"/v1/students/{created['student_id']}", headers=headers)

    assert removed.status_code == 204, removed.text
    assert client.get("/v1/students", headers=headers).json() == []
    assert owner_session.execute(sa.select(sa.func.count(Enrollment.id))).scalar() == 1
    # The number brings the archived student back, history and all.
    again = _create(client, headers, batches=[])
    assert again["student_id"] == created["student_id"]
    assert len(again["enrollments"]) == 1  # type: ignore[arg-type]


def test_the_roster_picker_seats_existing_students_at_once(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """All or nothing: one student already seated refuses the whole add.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    chemistry = _second_batch(owner_session, teacher, "Chemistry")
    headers = bearer(owner_session, teacher.account_id)
    first = _create(client, headers, batches=[], phone=None, name="Tanvir")
    second = _create(client, headers, batches=[chemistry], phone=None, name="Sadia")

    refused = client.post(
        f"/v1/batches/{chemistry}/students",
        headers=headers,
        json={"student_ids": [first["student_id"], second["student_id"]]},
    )
    assert refused.status_code == 409
    assert (
        client.get(f"/v1/batches/{chemistry}/roster", headers=headers).json()[0][
            "display_name"
        ]
        == "Sadia"
    )

    added = client.post(
        f"/v1/batches/{teacher.batch_id}/students",
        headers=headers,
        json={"student_ids": [first["student_id"], second["student_id"]]},
    )
    assert added.status_code == 201
    assert added.json() == {"added": 2}


def test_money_crosses_as_strings(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Every amount on a student is a JSON string [TC-7].

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    headers = bearer(owner_session, teacher.account_id)
    response = client.post(
        "/v1/students",
        headers=headers,
        json={
            "display_name": "Fee Override",
            "enrollments": [
                {"batch_id": str(teacher.batch_id), "fee_amount": "900.00"}
            ],
        },
    )

    body = response.json()
    assert body["total_outstanding"] == "0.00"
    assert body["enrollments"][0]["fee_amount"] == "900.00"
    assert body["enrollments"][0]["outstanding"] == "0.00"


def test_keyset_pages_walk_the_same_list_the_unpaged_read_returns(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """``limit`` and ``after`` page the list; no parameters, the whole list.

    Names that differ only in case sort case-insensitively, so the cursor
    is the server's ``(lower(name), id)`` and never a client comparison.
    A cursor naming another teacher's student is a 404 [C-14].

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    headers = bearer(owner_session, teacher.account_id)
    for name in ("delwar", "Ayesha", "Babul", "chandni", "Esha"):
        _create(client, headers, batches=[], phone=None, name=name)

    whole = client.get("/v1/students", headers=headers).json()
    assert [row["display_name"] for row in whole] == [
        "Ayesha",
        "Babul",
        "chandni",
        "delwar",
        "Esha",
    ]

    pages: list[list[dict[str, object]]] = []
    after: object = None
    while True:
        query = "?limit=2" + ("" if after is None else f"&after={after}")
        page = client.get(f"/v1/students{query}", headers=headers).json()
        pages.append(page)
        if len(page) < 2:
            break
        after = page[-1]["student_id"]
    assert [len(page) for page in pages] == [2, 2, 1]
    assert [row for page in pages for row in page] == whole

    other = make_teacher(owner_session, name="Maths")
    foreign = _create(
        client, bearer(owner_session, other.account_id), batches=[], phone=None
    )
    refused = client.get(
        f"/v1/students?limit=2&after={foreign['student_id']}", headers=headers
    )
    assert refused.status_code == 404
    assert client.get("/v1/students?limit=0", headers=headers).status_code == 422


# --------------------------------------------------------------------------
# Contacts by email: relinking, refusals and the edit-versus-accept race
# [U2: BR2.1, BR2.3, BR2.4, BR2.6]. Written BEFORE the implementation:
# which account a link names after an edit is knowable from the recorded
# contacts alone, and a wrong answer is an authorization error.
# --------------------------------------------------------------------------


def _email_seat_owned_by(
    client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    *,
    student_email: str,
    batches: list[uuid.UUID],
) -> dict[str, object]:
    """Record a student by email through the API.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :param student_email: The student's address
    :param batches: The batches to seat them in
    :return: The response body
    """
    response = client.post(
        "/v1/students",
        headers=bearer(owner_session, teacher.account_id),
        json={
            "display_name": "Mitu",
            "student_email": student_email,
            "enrollments": [{"batch_id": str(batch)} for batch in batches],
        },
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def _links(session: Session, student_id: object) -> list[tuple[object, ...]]:
    """Read every seat's student and guardian links and decisions.

    :param session: An arranging session
    :param student_id: The student
    :return: One tuple per seat, by seat id
    """
    session.expire_all()
    rows = session.execute(
        sa.text(
            "SELECT student_account_id, student_decision, guardian_account_id, "
            "guardian_decision FROM enrollment WHERE student_id = :s ORDER BY id"
        ),
        {"s": student_id},
    ).all()
    session.commit()
    return [tuple(row) for row in rows]


def test_a_save_never_links_an_email_where_a_phone_is_recorded(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The phone owns the link even when only the email has an account [BR2.1].

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from tests.accounts.contact_support import account, address, number

    email = address()
    account(owner_session, email=email)
    response = client.post(
        "/v1/students",
        headers=bearer(owner_session, teacher.account_id),
        json={
            "display_name": "Mitu",
            "student_phone": number(),
            "student_email": email,
            "enrollments": [{"batch_id": str(teacher.batch_id)}],
        },
    )

    assert response.status_code == 201, response.text
    assert _links(owner_session, response.json()["student_id"]) == [
        (None, "pending", None, "pending")
    ]


def test_a_save_links_an_email_only_link_to_that_emails_account(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """With no phone recorded, the email's account takes the link, pending.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from tests.accounts.contact_support import account, address

    email = address()
    holder = account(owner_session, email=email)
    created = _email_seat_owned_by(
        client, owner_session, teacher, student_email=email, batches=[teacher.batch_id]
    )

    assert _links(owner_session, created["student_id"]) == [
        (holder, "pending", None, "pending")
    ]


def test_changing_a_recorded_email_relinks_every_seat_and_resets_it(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A different address is a different person, who agreed to nothing [BR2.3].

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from tests.accounts.contact_support import account, address

    first, second = address(), address()
    first_holder = account(owner_session, email=first)
    second_holder = account(owner_session, email=second)
    other_batch = _second_batch(owner_session, teacher, "Chemistry")
    created = _email_seat_owned_by(
        client,
        owner_session,
        teacher,
        student_email=first,
        batches=[teacher.batch_id, other_batch],
    )
    owner_session.execute(
        sa.text(
            "UPDATE enrollment SET student_decision = 'declined' WHERE student_id = :s"
        ),
        {"s": created["student_id"]},
    )
    owner_session.commit()
    assert {row[0] for row in _links(owner_session, created["student_id"])} == {
        first_holder
    }

    edited = client.patch(
        f"/v1/students/{created['student_id']}",
        headers=bearer(owner_session, teacher.account_id),
        json={"student_email": second},
    )

    assert edited.status_code == 200, edited.text
    assert edited.json()["student_email"] == second
    assert _links(owner_session, created["student_id"]) == [
        (second_holder, "pending", None, "pending"),
        (second_holder, "pending", None, "pending"),
    ]


def test_clearing_a_guardian_email_unlinks_and_resets_that_link_only(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Null clears it; the link empties and the student link is untouched.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from tests.accounts.contact_support import account, address

    guardian_email = address()
    guardian = account(owner_session, email=guardian_email)
    response = client.post(
        "/v1/students",
        headers=bearer(owner_session, teacher.account_id),
        json={
            "display_name": "Mitu",
            "guardian_email": guardian_email,
            "enrollments": [{"batch_id": str(teacher.batch_id)}],
        },
    )
    assert response.status_code == 201, response.text
    student_id = response.json()["student_id"]
    assert _links(owner_session, student_id) == [(None, "pending", guardian, "pending")]

    cleared = client.patch(
        f"/v1/students/{student_id}",
        headers=bearer(owner_session, teacher.account_id),
        json={"guardian_email": None},
    )

    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["guardian_email"] is None
    assert cleared.json()["guardian_state"] == "absent"
    assert _links(owner_session, student_id) == [(None, "pending", None, "pending")]


def test_an_accepted_email_cannot_be_changed(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The existing refusal now covers an email [BR2.4].

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from tests.accounts.contact_support import account, address

    email = address()
    holder = account(owner_session, email=email)
    created = _email_seat_owned_by(
        client, owner_session, teacher, student_email=email, batches=[teacher.batch_id]
    )
    owner_session.execute(
        sa.text(
            "UPDATE enrollment SET student_decision = 'accepted' WHERE student_id = :s"
        ),
        {"s": created["student_id"]},
    )
    owner_session.commit()

    refused = client.patch(
        f"/v1/students/{created['student_id']}",
        headers=bearer(owner_session, teacher.account_id),
        json={"student_email": address()},
    )

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "STUDENT_NUMBER_ACCEPTED"
    assert _links(owner_session, created["student_id"]) == [
        (holder, "accepted", None, "pending")
    ]


def test_an_erased_email_link_cannot_be_changed(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Changing it would reattach records the person deleted [BR2.4].

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from tests.accounts.contact_support import address

    email = address()
    created = _email_seat_owned_by(
        client, owner_session, teacher, student_email=email, batches=[teacher.batch_id]
    )
    owner_session.execute(
        sa.text(
            "UPDATE enrollment SET guardian_relink_blocked_at = now() "
            "WHERE student_id = :s"
        ),
        {"s": created["student_id"]},
    )
    owner_session.commit()

    refused = client.patch(
        f"/v1/students/{created['student_id']}",
        headers=bearer(owner_session, teacher.account_id),
        json={"guardian_email": address()},
    )

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "STUDENT_NUMBER_ERASED"


def _accept_held_open(
    engine: sa.Engine, *, holder: uuid.UUID, seat_id: uuid.UUID
) -> Session:
    """Run the holder's accept in its own transaction and leave it open.

    :param engine: The restricted engine, the application's role
    :param holder: The account accepting
    :param seat_id: The seat accepted through
    :return: The session holding the uncommitted accept
    """
    from app.accounts.decisions import _SET_DECISION

    session = Session(bind=engine)
    session.execute(
        _SET_DECISION,
        {"account_id": holder, "enrollment_id": seat_id, "decision": "accepted"},
    )
    return session


def test_an_accept_committed_first_makes_the_concurrent_edit_refuse(
    restricted_engine: sa.Engine, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Accept first: the edit waits on the seat row, then sees accepted [BR2.6].

    Without the seat-row lock the edit read ``pending`` before the accept
    committed, and its write reset an accepted link to ``pending`` on a
    new number -- an accepted decision silently undone.

    :param restricted_engine: The application's role
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    import threading

    from app.authz.lenses import TeacherLens
    from app.errors import ConflictError
    from app.students.service import StudentChanges, update_student
    from tests.accounts.contact_support import number, seat

    phone = STUDENT_PHONE
    holder = _account(owner_session, phone)
    seat_id = seat(
        owner_session, teacher.batch_id, student_phone=phone, student_account_id=holder
    )
    student_id = owner_session.execute(
        sa.text("SELECT student_id FROM enrollment WHERE id = :e"), {"e": seat_id}
    ).scalar_one()
    owner_session.commit()

    accept = _accept_held_open(restricted_engine, holder=holder, seat_id=seat_id)
    outcome: list[object] = []

    def edit() -> None:
        """Run the teacher's edit on a second connection.

        :return: None
        """
        with Session(bind=restricted_engine, expire_on_commit=False) as session:
            try:
                update_student(
                    session,
                    lens=TeacherLens(
                        account_id=teacher.account_id, owner_id=teacher.owner_id
                    ),
                    student_id=student_id,
                    changes=StudentChanges(
                        student_phone=number(), student_phone_set=True
                    ),
                )
                outcome.append("edited")
            except ConflictError as refusal:
                outcome.append(refusal.code)

    worker = threading.Thread(target=edit)
    worker.start()
    worker.join(timeout=1.0)
    assert worker.is_alive(), "the edit must wait for the open accept"
    accept.commit()
    accept.close()
    worker.join(timeout=10.0)

    assert outcome == ["STUDENT_NUMBER_ACCEPTED"]
    assert _links(owner_session, student_id) == [(holder, "accepted", None, "pending")]


def test_an_edit_committed_first_makes_the_concurrent_accept_change_nothing(
    restricted_engine: sa.Engine, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Edit first: the accept finds the link re-pointed and writes nothing [BR2.6].

    :param restricted_engine: The application's role
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    import threading

    from app.authz.lenses import TeacherLens
    from app.students.service import StudentChanges, update_student
    from tests.accounts.contact_support import address, seat

    email = address()
    holder = _account(owner_session, STUDENT_PHONE)
    seat_id = seat(
        owner_session, teacher.batch_id, student_email=email, student_account_id=holder
    )
    student_id = owner_session.execute(
        sa.text("SELECT student_id FROM enrollment WHERE id = :e"), {"e": seat_id}
    ).scalar_one()
    owner_session.commit()

    release = threading.Event()
    edited = threading.Event()
    edit_session = Session(bind=restricted_engine, expire_on_commit=False)
    real_commit = edit_session.commit

    def held_commit() -> None:
        """Hold the edit's commit until the accept is waiting on it.

        :return: None
        """
        edited.set()
        release.wait(timeout=10.0)
        real_commit()

    edit_session.commit = held_commit  # type: ignore[method-assign]

    def edit() -> None:
        """Run the teacher's edit, held open at its commit.

        :return: None
        """
        update_student(
            edit_session,
            lens=TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id),
            student_id=student_id,
            changes=StudentChanges(student_email=address(), student_email_set=True),
        )

    editor = threading.Thread(target=edit)
    editor.start()
    assert edited.wait(timeout=10.0)

    def accept() -> None:
        """Run the holder's accept; it must wait for the edit.

        :return: None
        """
        with Session(bind=restricted_engine) as session:
            from app.accounts.decisions import _SET_DECISION

            session.execute(
                _SET_DECISION,
                {
                    "account_id": holder,
                    "enrollment_id": seat_id,
                    "decision": "accepted",
                },
            )
            session.commit()

    acceptor = threading.Thread(target=accept)
    acceptor.start()
    acceptor.join(timeout=1.0)
    assert acceptor.is_alive(), "the accept must wait for the open edit"
    release.set()
    editor.join(timeout=10.0)
    acceptor.join(timeout=10.0)
    edit_session.close()

    assert _links(owner_session, student_id) == [(None, "pending", None, "pending")]


# --------------------------------------------------------------------------
# Test-after: recording emails [U2: BR1.1 to BR1.7, BR2.5, NFR1.4], written
# from the rules.
# --------------------------------------------------------------------------


def _post_student(
    client: TestClient, owner_session: Session, teacher: TeacherFixture, **body: object
) -> object:
    """Record a student through the API, returning the raw response.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :param body: The request fields besides the name
    :return: The response
    """
    return client.post(
        "/v1/students",
        headers=bearer(owner_session, teacher.account_id),
        json={"display_name": "Mitu", **body},
    )


def test_recorded_emails_are_stored_canonical_and_blank_is_absent(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Trimmed and lowercased; an empty field records nobody [BR1.1].

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    response = _post_student(
        client,
        owner_session,
        teacher,
        student_email="  Mitu.Rahman@Example.COM ",
        guardian_email="   ",
        enrollments=[{"batch_id": str(teacher.batch_id)}],
    )

    assert response.status_code == 201, response.text  # type: ignore[attr-defined]
    body = response.json()  # type: ignore[attr-defined]
    assert body["student_email"] == "mitu.rahman@example.com"
    assert body["guardian_email"] is None
    owner_session.expire_all()
    seat = owner_session.execute(
        sa.select(Enrollment).where(Enrollment.student_id == body["student_id"])
    ).scalar_one()
    assert (seat.student_email, seat.guardian_email) == (
        "mitu.rahman@example.com",
        None,
    )


def test_a_malformed_email_is_refused_with_its_own_key(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Nothing is written [BR1.1].

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    response = _post_student(
        client, owner_session, teacher, student_email="not-an-address"
    )

    assert response.status_code == 400  # type: ignore[attr-defined]
    assert response.json()["error"]["message_key"] == "email.invalid"  # type: ignore[attr-defined]


def test_a_student_email_is_unique_per_teacher_and_a_guardian_email_is_not(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The student's address names one record; a parent's names many [BR1.2, BR1.3].

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from tests.accounts.contact_support import address

    shared_guardian = address()
    taken = address()
    first = _post_student(
        client,
        owner_session,
        teacher,
        student_email=taken,
        guardian_email=shared_guardian,
    )
    sibling = _post_student(
        client,
        owner_session,
        teacher,
        student_email=address(),
        guardian_email=shared_guardian,
    )
    clash = _post_student(client, owner_session, teacher, student_email=taken)
    other_teacher = make_teacher(owner_session, name="Maths")
    elsewhere = _post_student(client, owner_session, other_teacher, student_email=taken)
    edited = client.patch(
        f"/v1/students/{sibling.json()['student_id']}",  # type: ignore[attr-defined]
        headers=bearer(owner_session, teacher.account_id),
        json={"student_email": taken},
    )

    assert first.status_code == sibling.status_code == 201  # type: ignore[attr-defined]
    assert clash.status_code == 409  # type: ignore[attr-defined]
    assert clash.json()["error"]["code"] == "STUDENT_EMAIL_TAKEN"  # type: ignore[attr-defined]
    assert clash.json()["error"]["message_key"] == "student.email.taken"  # type: ignore[attr-defined]
    assert elsewhere.status_code == 201  # type: ignore[attr-defined]
    assert edited.status_code == 409
    assert edited.json()["error"]["message_key"] == "student.email.taken"


def test_an_email_belonging_to_an_archived_student_revives_them(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """With no number, the address identifies the student [BR1.7].

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from tests.accounts.contact_support import address

    email = address()
    archived = Student(
        owner_id=teacher.owner_id,
        display_name="Old name",
        student_email=email,
        archived_at=dt.datetime.now(tz=dt.UTC),
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(archived)
    owner_session.commit()

    again = _post_student(client, owner_session, teacher, student_email=email)

    assert again.status_code == 201, again.text  # type: ignore[attr-defined]
    assert again.json()["student_id"] == str(archived.id)  # type: ignore[attr-defined]
    assert again.json()["display_name"] == "Mitu"  # type: ignore[attr-defined]


def test_the_phone_identifies_first_and_the_email_must_agree(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A number of one student beside another student's address is refused [BR1.7].

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from tests.accounts.contact_support import address, number

    email = address()
    _post_student(client, owner_session, teacher, student_email=email)

    refused = _post_student(
        client, owner_session, teacher, student_phone=number(), student_email=email
    )

    assert refused.status_code == 409  # type: ignore[attr-defined]
    assert refused.json()["error"]["code"] == "STUDENT_EMAIL_TAKEN"  # type: ignore[attr-defined]


def test_a_guardian_recorded_only_by_email_reads_the_same_with_or_without_an_account(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Pending either way, never absent: the teacher learns nothing [BR1.6, NFR1.4].

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from tests.accounts.contact_support import account, address

    with_account = address()
    account(owner_session, email=with_account)
    states = []
    for email in (with_account, address()):
        created = _post_student(
            client,
            owner_session,
            teacher,
            guardian_email=email,
            enrollments=[
                {"batch_id": str(_second_batch(owner_session, teacher, email))}
            ],
        )
        assert created.status_code == 201, created.text  # type: ignore[attr-defined]
        body = created.json()  # type: ignore[attr-defined]
        roster = client.get(
            f"/v1/batches/{body['enrollments'][0]['batch_id']}/roster",
            headers=bearer(owner_session, teacher.account_id),
        ).json()
        states.append((body["guardian_state"], roster[0]["guardian_state"]))

    assert states == [("pending", "pending"), ("pending", "pending")]


def test_a_save_never_seats_one_account_twice_in_a_batch(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The address's account already sits in the batch: a clear refusal [BR2.5].

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from tests.accounts.contact_support import account, address, number, seat

    email = address()
    holder = account(owner_session, email=email)
    seat(
        owner_session,
        teacher.batch_id,
        student_phone=number(),
        student_account_id=holder,
    )

    refused = _post_student(
        client,
        owner_session,
        teacher,
        student_email=email,
        enrollments=[{"batch_id": str(teacher.batch_id)}],
    )

    assert refused.status_code == 409  # type: ignore[attr-defined]
    assert (
        refused.json()["error"]["message_key"] == "enrollment.student_already_in_batch"
    )  # type: ignore[attr-defined]


def test_reviving_a_student_cannot_change_an_accepted_link(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The revive path refuses as the edit path does [BR2.4; review R-06].

    Written BEFORE the fix: a revive that re-pointed an accepted guardian
    link would hand that person's view of the child to a new address.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from tests.accounts.contact_support import account, address, seat

    guardian = account(owner_session, email=address())
    seat_id = seat(
        owner_session,
        teacher.batch_id,
        student_phone=STUDENT_PHONE,
        guardian_account_id=guardian,
        guardian_decision="accepted",
    )
    owner_session.execute(
        sa.text(
            "UPDATE student SET archived_at = now() WHERE id = "
            "(SELECT student_id FROM enrollment WHERE id = :e)"
        ),
        {"e": seat_id},
    )
    owner_session.commit()

    refused = _post_student(
        client,
        owner_session,
        teacher,
        student_phone=STUDENT_PHONE,
        guardian_email=address(),
    )

    assert refused.status_code == 409, refused.text  # type: ignore[attr-defined]
    assert refused.json()["error"]["code"] == "STUDENT_NUMBER_ACCEPTED"  # type: ignore[attr-defined]
    owner_session.expire_all()
    kept = owner_session.execute(
        sa.text(
            "SELECT guardian_account_id, guardian_decision FROM enrollment "
            "WHERE id = :e"
        ),
        {"e": seat_id},
    ).one()
    assert tuple(kept) == (guardian, "accepted")
