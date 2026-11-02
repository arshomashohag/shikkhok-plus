"""Teacher payment methods, and which family members may read them."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.batches.conftest import TeacherFixture, enroll
from tests.conftest import bearer

MOBILE_BODY = {"kind": "mobile", "provider": "bKash", "mobile_number": "01711000000"}
BANK_BODY = {
    "kind": "bank",
    "provider": "City Bank",
    "account_number": "1234567890",
    "account_name": "Najma Akter",
    "branch_name": "Dhanmondi",
}


def test_teacher_creates_lists_edits_and_retires_a_mobile_method(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A mobile method round-trips and a retired one leaves the list.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :return: None
    """
    headers = bearer(owner_session, teacher.account_id)

    created = api_client.post("/v1/payment-methods", json=MOBILE_BODY, headers=headers)
    assert created.status_code == 201
    method_id = created.json()["method_id"]
    assert created.json()["mobile_number"] == "01711000000"

    listed = api_client.get("/v1/payment-methods", headers=headers).json()
    assert [row["method_id"] for row in listed] == [method_id]

    edited = api_client.patch(
        f"/v1/payment-methods/{method_id}",
        json={**MOBILE_BODY, "provider": "Nagad", "note": "Send as personal"},
        headers=headers,
    )
    assert edited.status_code == 200
    assert edited.json()["provider"] == "Nagad"
    assert edited.json()["note"] == "Send as personal"

    retired = api_client.delete(f"/v1/payment-methods/{method_id}", headers=headers)
    assert retired.status_code == 204
    assert api_client.get("/v1/payment-methods", headers=headers).json() == []
    again = api_client.delete(f"/v1/payment-methods/{method_id}", headers=headers)
    assert again.status_code == 403


def test_methods_are_listed_in_creation_order(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Position follows creation, one past the highest.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :return: None
    """
    headers = bearer(owner_session, teacher.account_id)
    first = api_client.post("/v1/payment-methods", json=MOBILE_BODY, headers=headers)
    second = api_client.post("/v1/payment-methods", json=BANK_BODY, headers=headers)

    listed = api_client.get("/v1/payment-methods", headers=headers).json()

    assert [row["method_id"] for row in listed] == [
        first.json()["method_id"],
        second.json()["method_id"],
    ]


def test_bank_method_requires_all_four_fields(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A bank method missing any of its fields is refused.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :return: None
    """
    headers = bearer(owner_session, teacher.account_id)
    for missing in ("provider", "account_number", "account_name", "branch_name"):
        body = {key: value for key, value in BANK_BODY.items() if key != missing}
        response = api_client.post("/v1/payment-methods", json=body, headers=headers)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "METHOD_FIELDS_INCOMPLETE"


def test_mobile_method_rejects_a_bad_number_and_bank_fields(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A mobile method needs a valid number and carries no bank fields.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :return: None
    """
    headers = bearer(owner_session, teacher.account_id)
    bad = api_client.post(
        "/v1/payment-methods",
        json={**MOBILE_BODY, "mobile_number": "12345"},
        headers=headers,
    )
    mixed = api_client.post(
        "/v1/payment-methods",
        json={**MOBILE_BODY, "account_number": "99"},
        headers=headers,
    )
    long_note = api_client.post(
        "/v1/payment-methods",
        json={**MOBILE_BODY, "note": "x" * 201},
        headers=headers,
    )

    assert bad.status_code == 400
    assert mixed.json()["error"]["code"] == "METHOD_FIELDS_INCOMPLETE"
    assert long_note.json()["error"]["code"] == "METHOD_FIELD_TOO_LONG"


def test_custom_service_name_is_accepted(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A mobile service outside the suggestions is accepted.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :return: None
    """
    headers = bearer(owner_session, teacher.account_id)
    response = api_client.post(
        "/v1/payment-methods",
        json={**MOBILE_BODY, "provider": "Upay"},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["provider"] == "Upay"


def test_teacher_cannot_touch_another_owners_method(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Another owner's method is neither listed, edited nor retired.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    from tests.batches.conftest import make_teacher

    other = make_teacher(owner_session, name="Chemistry")
    mine = bearer(owner_session, teacher.account_id)
    theirs = bearer(owner_session, other.account_id)
    method_id = api_client.post(
        "/v1/payment-methods", json=MOBILE_BODY, headers=mine
    ).json()["method_id"]

    patched = api_client.patch(
        f"/v1/payment-methods/{method_id}", json=MOBILE_BODY, headers=theirs
    )
    deleted = api_client.delete(f"/v1/payment-methods/{method_id}", headers=theirs)

    assert patched.status_code == 403
    assert deleted.status_code == 403
    assert api_client.get("/v1/payment-methods", headers=theirs).json() == []
    assert len(api_client.get("/v1/payment-methods", headers=mine).json()) == 1


def _method(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> str:
    """Create one mobile method for the teacher.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :return: The method id
    """
    headers = bearer(owner_session, teacher.account_id)
    created = api_client.post("/v1/payment-methods", json=MOBILE_BODY, headers=headers)
    return str(created.json()["method_id"])


def test_accepted_student_sees_their_teachers_methods(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """An accepted student reads the owner's methods.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    method_id = _method(api_client, owner_session, teacher)
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )

    response = api_client.get(
        f"/v1/me/enrollments/{seat}/payment-methods",
        headers=bearer(owner_session, student),
    )

    assert response.status_code == 200
    body = response.json()
    assert [row["method_id"] for row in body["methods"]] == [method_id]
    assert body["methods"][0]["mobile_number"] == "01711000000"


def test_family_list_carries_the_service_suggestions(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The server supplies the mobile service names, even with no method.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )

    body = api_client.get(
        f"/v1/me/enrollments/{seat}/payment-methods",
        headers=bearer(owner_session, student),
    ).json()

    assert body["methods"] == []
    assert body["services"] == ["bKash", "Nagad", "Rocket"]


def test_retired_method_is_hidden_from_the_family(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A retired method stops being offered to families.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    method_id = _method(api_client, owner_session, teacher)
    api_client.delete(
        f"/v1/payment-methods/{method_id}",
        headers=bearer(owner_session, teacher.account_id),
    )
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )

    body = api_client.get(
        f"/v1/me/enrollments/{seat}/payment-methods",
        headers=bearer(owner_session, student),
    ).json()

    assert body["methods"] == []


def test_pending_seat_sees_no_methods(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A seat the student has not accepted reaches nothing.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    _method(api_client, owner_session, teacher)
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="pending",
    )

    response = api_client.get(
        f"/v1/me/enrollments/{seat}/payment-methods",
        headers=bearer(owner_session, student),
    )

    assert response.status_code == 403


def test_accepted_guardian_sees_methods_and_another_childs_guardian_is_refused(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A guardian reaches their own child's seat and no other.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    _method(api_client, owner_session, teacher)
    guardian = account_factory()
    stranger = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        guardian_decision="accepted",
    )

    allowed = api_client.get(
        f"/v1/children/{seat}/payment-methods",
        headers=bearer(owner_session, guardian),
    )
    refused = api_client.get(
        f"/v1/children/{seat}/payment-methods",
        headers=bearer(owner_session, stranger),
    )

    assert allowed.status_code == 200
    assert len(allowed.json()["methods"]) == 1
    assert refused.status_code == 403


def test_guardian_of_another_child_is_refused(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A guardian whose own child sits elsewhere cannot read this seat.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    _method(api_client, owner_session, teacher)
    guardian = account_factory()
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Mine",
        guardian_account_id=guardian,
        guardian_decision="accepted",
    )
    others = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Not mine",
        student_account_id=account_factory(),
    )

    response = api_client.get(
        f"/v1/children/{others}/payment-methods",
        headers=bearer(owner_session, guardian),
    )

    assert response.status_code == 403
