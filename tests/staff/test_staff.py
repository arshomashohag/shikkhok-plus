"""The Teachers & staff console [0023].

Written before the code, from the design's rules:

* A staff record is what the manager typed and grants nothing; app access
  is a separate membership, and inviting a teacher creates both at once.
* Other staff never get app access.
* Pay terms pair a basis with a rate: a paid basis needs a rate above
  zero, and ``none`` takes none.
* Leaving ends pay and, when a membership is linked, revokes it in the
  same transaction -- an authorization change, so it is test-first.
* Only a manager of that centre reaches a staff record; a solo workspace
  has no staff.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Account, OwnerMember, Staff
from app.local_time import bangladesh_today
from tests.accounts.signup_support import sign_up
from tests.batches.conftest import make_teacher
from tests.conftest import bearer

ADDRESS = {
    "address_house": "House 12",
    "address_road": "Road 5",
    "address_city": "Dhaka",
    "address_postcode": "1205",
}


def _phone() -> str:
    """Generate a unique number.

    :return: A number in international form
    """
    return f"+88017{uuid.uuid4().int % 10**8:08d}"


def _manager(client: TestClient) -> uuid.UUID:
    """Sign up a coaching centre and return its manager's account.

    :param client: The test client
    :return: The account id
    """
    # Form and code: the account is created at verify [C-07].
    return sign_up(
        client,
        {
            "phone": _phone(),
            "role": "coaching",
            "self_name": "Rina",
            "centre_name": "Udoy Coaching",
            **ADDRESS,
        },
    )


def _invite_teacher(
    client: TestClient, session: Session, manager: uuid.UUID, **body: object
) -> object:
    """Invite a teacher through the console.

    :param client: The test client
    :param session: A session to issue the token through
    :param manager: The manager's account
    :param body: Fields overriding the default request
    :return: The response
    """
    request: dict[str, object] = {
        "display_name": "Sumi Akter",
        "phone": _phone(),
        "email": "sumi@example.com",
        "staff_house": "Flat 3B",
        "staff_road": "Mirpur Road",
        "staff_city": "Dhaka",
        "staff_postcode": "1207",
        "pay_basis": "per_class",
        "pay_rate": "500.00",
    }
    request.update(body)
    return client.post(
        "/v1/centre/staff/teachers", json=request, headers=bearer(session, manager)
    )


def _add_other(
    client: TestClient, session: Session, manager: uuid.UUID, **body: object
) -> object:
    """Add another staff member through the console.

    :param client: The test client
    :param session: A session to issue the token through
    :param manager: The manager's account
    :param body: Fields overriding the default request
    :return: The response
    """
    request: dict[str, object] = {
        "display_name": "Karim",
        "role_label": "Receptionist",
        "pay_basis": "monthly",
        "pay_rate": "8000.00",
    }
    request.update(body)
    return client.post(
        "/v1/centre/staff", json=request, headers=bearer(session, manager)
    )


def _code(response: object) -> str:
    """Read an error code.

    :param response: The response
    :return: The code
    """
    code: str = response.json()["error"]["code"]  # type: ignore[attr-defined]
    return code


def test_inviting_a_teacher_records_them_and_offers_access_that_grants_nothing(
    api_client: TestClient, owner_session: Session
) -> None:
    """One request: a staff record with the details, and a pending membership."""
    manager = _manager(api_client)
    response = _invite_teacher(api_client, owner_session, manager)
    assert response.status_code == 201, response.text  # type: ignore[attr-defined]
    body = response.json()  # type: ignore[attr-defined]
    assert body["kind"] == "teacher"
    assert body["access"] == "invited"
    assert body["status"] == "active"
    assert body["staff_city"] == "Dhaka"
    assert body["email"] == "sumi@example.com"
    assert body["pay_rate"] == "500.00"

    staff = owner_session.get(Staff, uuid.UUID(body["staff_id"]))
    assert staff is not None
    member = owner_session.get(OwnerMember, staff.member_id)
    assert member is not None
    assert (member.role, member.decision, member.revoked_at) == (
        "teacher",
        "pending",
        None,
    )


def test_accepting_the_offer_shows_as_active_access(
    api_client: TestClient, owner_session: Session
) -> None:
    """The staff record reads the membership's own state."""
    manager = _manager(api_client)
    phone = _phone()
    teacher = Account(phone=phone, created_at=dt.datetime.now(tz=dt.UTC))
    owner_session.add(teacher)
    owner_session.commit()

    created = _invite_teacher(api_client, owner_session, manager, phone=phone).json()  # type: ignore[attr-defined]
    offers = api_client.get(
        "/v1/memberships", headers=bearer(owner_session, teacher.id)
    )
    accepted = api_client.post(
        f"/v1/memberships/{offers.json()[0]['member_id']}/accept",
        headers=bearer(owner_session, teacher.id),
    )
    assert accepted.status_code == 200, accepted.text

    detail = api_client.get(
        f"/v1/centre/staff/{created['staff_id']}",
        headers=bearer(owner_session, manager),
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["access"] == "active"


def test_other_staff_have_no_app_access(
    api_client: TestClient, owner_session: Session
) -> None:
    """A receptionist is a record and a salary, never a login."""
    manager = _manager(api_client)
    response = _add_other(api_client, owner_session, manager)
    assert response.status_code == 201, response.text  # type: ignore[attr-defined]
    body = response.json()  # type: ignore[attr-defined]
    assert (body["kind"], body["access"], body["role_label"]) == (
        "other",
        "none",
        "Receptionist",
    )
    assert body["phone"] is None
    assert (
        owner_session.scalar(sa.select(sa.func.count()).select_from(OwnerMember)) == 1
    )


def test_pay_terms_pair_a_basis_with_a_rate(
    api_client: TestClient, owner_session: Session
) -> None:
    """A paid basis needs a rate above zero; no basis takes no rate."""
    manager = _manager(api_client)
    cases = [
        ({"pay_basis": "monthly", "pay_rate": None}, "STAFF_PAY_RATE_REQUIRED"),
        ({"pay_basis": "per_class", "pay_rate": "0.00"}, "STAFF_PAY_RATE_REQUIRED"),
        ({"pay_basis": "none", "pay_rate": "100.00"}, "STAFF_PAY_RATE_NOT_ALLOWED"),
    ]
    for body, code in cases:
        response = _add_other(api_client, owner_session, manager, **body)
        assert response.status_code == 400, (body, response.text)  # type: ignore[attr-defined]
        assert _code(response) == code
    unpaid = _add_other(
        api_client, owner_session, manager, pay_basis="none", pay_rate=None
    )
    assert unpaid.status_code == 201, unpaid.text  # type: ignore[attr-defined]


def test_a_refused_invitation_leaves_no_staff_record(
    api_client: TestClient, owner_session: Session
) -> None:
    """The record and the membership are one transaction."""
    manager = _manager(api_client)
    phone = _phone()
    first = _invite_teacher(api_client, owner_session, manager, phone=phone)
    again = _invite_teacher(api_client, owner_session, manager, phone=phone)
    assert first.status_code == 201  # type: ignore[attr-defined]
    assert again.status_code == 409, again.text  # type: ignore[attr-defined]
    assert _code(again) == "MEMBER_ALREADY_INVITED"
    assert owner_session.scalar(sa.select(sa.func.count()).select_from(Staff)) == 1


def test_leaving_ends_app_access_in_the_same_step(
    api_client: TestClient, owner_session: Session
) -> None:
    """The record stays, marked left; the membership is revoked."""
    manager = _manager(api_client)
    created = _invite_teacher(api_client, owner_session, manager).json()  # type: ignore[attr-defined]
    today = bangladesh_today().isoformat()

    left = api_client.post(
        f"/v1/centre/staff/{created['staff_id']}/leave",
        json={"left_on": today},
        headers=bearer(owner_session, manager),
    )
    assert left.status_code == 200, left.text
    assert (left.json()["status"], left.json()["left_on"], left.json()["access"]) == (
        "left",
        today,
        "revoked",
    )
    staff = owner_session.get(Staff, uuid.UUID(created["staff_id"]))
    assert staff is not None
    member = owner_session.get(OwnerMember, staff.member_id)
    owner_session.refresh(member)
    assert member is not None and member.revoked_at is not None

    again = api_client.post(
        f"/v1/centre/staff/{created['staff_id']}/leave",
        json={},
        headers=bearer(owner_session, manager),
    )
    assert again.status_code == 409, again.text
    assert _code(again) == "STAFF_ALREADY_LEFT"


def test_leaving_before_joining_is_refused(
    api_client: TestClient, owner_session: Session
) -> None:
    """A leaving date earlier than the joining date is a typing error."""
    manager = _manager(api_client)
    created = _add_other(
        api_client, owner_session, manager, joined_on="2026-11-01"
    ).json()  # type: ignore[attr-defined]
    response = api_client.post(
        f"/v1/centre/staff/{created['staff_id']}/leave",
        json={"left_on": "2026-10-31"},
        headers=bearer(owner_session, manager),
    )
    assert response.status_code == 400, response.text
    assert _code(response) == "STAFF_LEFT_BEFORE_JOINED"


def test_a_manager_corrects_details_and_pay_terms(
    api_client: TestClient, owner_session: Session
) -> None:
    """Every typed fact is editable; the kind is not."""
    manager = _manager(api_client)
    created = _add_other(api_client, owner_session, manager).json()  # type: ignore[attr-defined]
    response = api_client.patch(
        f"/v1/centre/staff/{created['staff_id']}",
        json={
            "display_name": "Karim Uddin",
            "staff_city": "Gazipur",
            "pay_basis": "monthly",
            "pay_rate": "9000.00",
        },
        headers=bearer(owner_session, manager),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["display_name"], body["staff_city"], body["pay_rate"]) == (
        "Karim Uddin",
        "Gazipur",
        "9000.00",
    )
    refused = api_client.patch(
        f"/v1/centre/staff/{created['staff_id']}",
        json={"kind": "teacher"},
        headers=bearer(owner_session, manager),
    )
    assert refused.status_code == 422, refused.text
    unpaid = api_client.patch(
        f"/v1/centre/staff/{created['staff_id']}",
        json={"pay_basis": "none"},
        headers=bearer(owner_session, manager),
    )
    assert unpaid.status_code == 400, unpaid.text
    assert _code(unpaid) == "STAFF_PAY_RATE_NOT_ALLOWED"


def test_the_list_shows_everyone_with_their_state(
    api_client: TestClient, owner_session: Session
) -> None:
    """Active people first, then those who left."""
    manager = _manager(api_client)
    teacher = _invite_teacher(api_client, owner_session, manager).json()  # type: ignore[attr-defined]
    other = _add_other(api_client, owner_session, manager).json()  # type: ignore[attr-defined]
    api_client.post(
        f"/v1/centre/staff/{teacher['staff_id']}/leave",
        json={},
        headers=bearer(owner_session, manager),
    )
    listed = api_client.get("/v1/centre/staff", headers=bearer(owner_session, manager))
    assert listed.status_code == 200, listed.text
    assert [(row["staff_id"], row["status"]) for row in listed.json()] == [
        (other["staff_id"], "active"),
        (teacher["staff_id"], "left"),
    ]


def test_only_this_centres_manager_reaches_a_record(
    api_client: TestClient, owner_session: Session
) -> None:
    """Another centre's manager, and a solo tutor, are refused."""
    manager = _manager(api_client)
    created = _add_other(api_client, owner_session, manager).json()  # type: ignore[attr-defined]

    other_manager = _manager(api_client)
    for method, path in (
        ("GET", f"/v1/centre/staff/{created['staff_id']}"),
        ("POST", f"/v1/centre/staff/{created['staff_id']}/leave"),
    ):
        response = api_client.request(
            method, path, json={}, headers=bearer(owner_session, other_manager)
        )
        assert response.status_code == 403, (path, response.text)

    tutor = make_teacher(owner_session)
    solo = api_client.get(
        "/v1/centre/staff", headers=bearer(owner_session, tutor.account_id)
    )
    assert solo.status_code == 409, solo.text
    assert _code(solo) == "NOT_A_CENTRE"


def test_an_email_is_checked_for_shape_only(
    api_client: TestClient, owner_session: Session
) -> None:
    """Not an address is refused; nothing is sent to it."""
    manager = _manager(api_client)
    response = _invite_teacher(api_client, owner_session, manager, email="not-an-email")
    assert response.status_code == 422, response.text  # type: ignore[attr-defined]
