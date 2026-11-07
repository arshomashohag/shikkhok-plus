"""The address in four parts, required at sign-up (decided 2026-11-05).

Three things are asserted here. Sign-up refuses a body missing any part
or carrying a postcode that is not four digits, and stores the four
parts on the person's own profile; Bangla digits in a postcode are the
same postcode. The owner reads the parts back from ``/v1/me``. And a
part can be corrected but never blanked, because the address is
required.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.contract.privacy import OWNER_PRIVATE_FIELDS
from app.db.models import Account, Profile
from tests.accounts.conftest import auth_header, make_account
from tests.accounts.signup_support import submit_signup

#: A complete sign-up body, less the number.
ADDRESS = {
    "address_house": "House 12",
    "address_road": "Road 5, Dhanmondi",
    "address_city": "Dhaka",
    "address_postcode": "1205",
}

PARTS = tuple(ADDRESS)


def _phone() -> str:
    """Generate a unique number for one test.

    :return: A number in international form
    """
    return f"+88017{uuid.uuid4().int % 10**8:08d}"


def _signup(client: TestClient, **changes: str | None) -> tuple[str, int]:
    """Sign up a student with the address, as changed.

    :param client: A client against the restricted engine
    :param changes: Parts to replace; None leaves a part out
    :return: The number used and the response status
    """
    phone = _phone()
    body: dict[str, str] = {"phone": phone, "role": "student", "self_name": "Rahim"}
    for name, value in {**ADDRESS, **changes}.items():
        if value is not None:
            body[name] = value
    # Submitted and, when accepted, verified: the profile is written
    # when the code is typed, not when the form is sent [C-07].
    response, code = submit_signup(client, body)
    if response.status_code == 201 and code is not None:
        verified = client.post("/v1/auth/verify", json={"phone": phone, "code": code})
        assert verified.status_code == 200, verified.text
    return phone, response.status_code


def _profile_of(session: Session, phone: str) -> Profile:
    """Read the profile a sign-up created.

    :param session: A session able to read fixture data
    :param phone: The number signed up with
    :return: The profile
    """
    session.expire_all()
    account = session.query(Account).filter(Account.phone == phone).one()
    profile = session.get(Profile, account.id)
    assert profile is not None
    return profile


def test_sign_up_stores_the_four_parts(
    client: TestClient, owner_session: Session
) -> None:
    """A complete body creates the account with the address on its profile.

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data
    :return: None
    """
    phone, status = _signup(client)

    assert status == 201
    profile = _profile_of(owner_session, phone)
    stored = (
        profile.address_house,
        profile.address_road,
        profile.address_city,
        profile.address_postcode,
    )
    assert stored == ("House 12", "Road 5, Dhanmondi", "Dhaka", "1205")


@pytest.mark.parametrize("missing", PARTS)
def test_sign_up_refuses_a_missing_part(
    client: TestClient, owner_session: Session, missing: str
) -> None:
    """Every part is required, on every path, so no account is created.

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data
    :param missing: The part left out
    :return: None
    """
    phone, status = _signup(client, **{missing: None})

    assert status == 422
    owner_session.expire_all()
    assert owner_session.query(Account).filter(Account.phone == phone).count() == 0


@pytest.mark.parametrize("blank", PARTS)
def test_sign_up_refuses_a_blank_part(client: TestClient, blank: str) -> None:
    """Spaces are not an address.

    :param client: A client against the restricted engine
    :param blank: The part sent as spaces
    :return: None
    """
    _phone_used, status = _signup(client, **{blank: "   "})

    assert status == 422


@pytest.mark.parametrize("postcode", ["120", "12055", "12a5", "Dhaka"])
def test_sign_up_refuses_a_postcode_that_is_not_four_digits(
    client: TestClient, postcode: str
) -> None:
    """A Bangladeshi postcode is four digits.

    :param client: A client against the restricted engine
    :param postcode: The malformed postcode
    :return: None
    """
    _phone_used, status = _signup(client, address_postcode=postcode)

    assert status == 422


def test_a_postcode_in_bangla_digits_is_stored_in_latin(
    client: TestClient, owner_session: Session
) -> None:
    """১২০৫ and 1205 are one postcode.

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data
    :return: None
    """
    phone, status = _signup(client, address_postcode="১২০৫")

    assert status == 201
    assert _profile_of(owner_session, phone).address_postcode == "1205"


def test_the_owner_reads_and_corrects_the_parts(
    client: TestClient, owner_session: Session
) -> None:
    """``/v1/me`` returns the parts; a patch changes one and keeps the rest.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    account = make_account(owner_session)
    headers = auth_header(owner_session, account)
    assert client.patch("/v1/me", json=ADDRESS, headers=headers).status_code == 200

    response = client.patch("/v1/me", json={"address_road": "Road 7"}, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["address_house"] == "House 12"
    assert body["address_road"] == "Road 7"
    read = client.get("/v1/me", headers=headers).json()
    assert read["address_city"] == "Dhaka"
    assert read["address_postcode"] == "1205"


@pytest.mark.parametrize("blank", PARTS)
def test_a_part_can_be_corrected_but_not_blanked(
    client: TestClient, owner_session: Session, blank: str
) -> None:
    """The address is required, so an edit cannot empty a part.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :param blank: The part sent as an empty string
    :return: None
    """
    account = make_account(owner_session)

    response = client.patch(
        "/v1/me", json={blank: ""}, headers=auth_header(owner_session, account)
    )

    assert response.status_code == 422


def test_every_part_is_owner_private() -> None:
    """No teacher-lens response may carry any part [BR3.4, TC-13].

    :return: None
    """
    assert set(PARTS) <= OWNER_PRIVATE_FIELDS
