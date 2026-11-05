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
