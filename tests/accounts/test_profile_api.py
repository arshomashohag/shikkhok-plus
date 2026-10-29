"""The profile read and write on ``/v1/me``.

**The half that did not exist.** `ProfileUiState.Viewing` needs a name
and an address and `GET /v1/me` returned only `lenses`; there was no
write endpoint at all, so the profile screen could neither show
anything nor save an edit.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Profile
from tests.accounts.conftest import auth_header, make_account


def _profile(
    session: Session,
    account_id: uuid.UUID,
    *,
    self_name: str | None = None,
    address: str | None = None,
) -> None:
    """Give an account a stored profile.

    :param session: An arranging session
    :param account_id: Whose profile
    :param self_name: The stored name, or None
    :param address: The stored address, or None
    :return: None
    """
    session.add(Profile(account_id=account_id, self_name=self_name, address=address))
    session.commit()


def test_me_returns_the_readers_own_name_and_address(
    client: TestClient, owner_session: Session
) -> None:
    """The profile screen's source [ProfileUiState.Viewing].

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    account = make_account(owner_session)
    _profile(owner_session, account, self_name="Rahim", address="Dhaka 1205")

    response = client.get("/v1/me", headers=auth_header(owner_session, account))

    assert response.status_code == 200
    body = response.json()
    assert body["self_name"] == "Rahim"
    assert body["address"] == "Dhaka 1205"


def test_an_account_with_no_profile_reads_nulls_rather_than_failing(
    client: TestClient, owner_session: Session
) -> None:
    """A person may reach the screen before anything wrote a row.

    Signup writes one, but a number a teacher recorded has no profile
    until its holder registers. Null is the honest answer; a 404 would
    make an ordinary first visit look like an error.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    account = make_account(owner_session)

    response = client.get("/v1/me", headers=auth_header(owner_session, account))

    assert response.status_code == 200
    assert response.json()["self_name"] is None
    assert response.json()["address"] is None


def test_a_patch_saves_both_fields(client: TestClient, owner_session: Session) -> None:
    """The write the screen's Save needs.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    account = make_account(owner_session)

    response = client.patch(
        "/v1/me",
        json={"self_name": "Rahim", "address": "Dhaka 1205"},
        headers=auth_header(owner_session, account),
    )

    assert response.status_code == 200
    assert response.json()["self_name"] == "Rahim"
    assert response.json()["address"] == "Dhaka 1205"


def test_an_omitted_field_is_left_alone_rather_than_cleared(
    client: TestClient, owner_session: Session
) -> None:
    """Saving one field must not erase the other.

    The app can send a single edited field, and a handler that wrote
    both unconditionally would clear an address the person never
    touched.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    account = make_account(owner_session)
    _profile(owner_session, account, self_name="Rahim", address="Dhaka 1205")

    response = client.patch(
        "/v1/me",
        json={"self_name": "Rahim Uddin"},
        headers=auth_header(owner_session, account),
    )

    assert response.status_code == 200
    assert response.json()["self_name"] == "Rahim Uddin"
    assert response.json()["address"] == "Dhaka 1205"


def test_a_patch_creates_the_row_when_there_is_none(
    client: TestClient, owner_session: Session
) -> None:
    """A write that refused because nothing existed would confuse.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    account = make_account(owner_session)

    response = client.patch(
        "/v1/me",
        json={"self_name": "Rahim"},
        headers=auth_header(owner_session, account),
    )

    assert response.status_code == 200
    assert response.json()["self_name"] == "Rahim"


def test_a_patch_cannot_name_another_account(
    client: TestClient, owner_session: Session
) -> None:
    """There is no field through which it could.

    The row is keyed on the authenticated account id and the request
    body forbids extra keys, so an `account_id` in the payload is
    rejected rather than honoured. Row-level security is the second
    bound beneath that.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    me = make_account(owner_session)
    someone_else = make_account(owner_session)
    _profile(owner_session, someone_else, self_name="Not mine")

    response = client.patch(
        "/v1/me",
        json={"self_name": "Rahim", "account_id": str(someone_else)},
        headers=auth_header(owner_session, me),
    )

    assert response.status_code == 422

    owner_session.expire_all()
    untouched = owner_session.get(Profile, someone_else)
    assert untouched is not None
    assert untouched.self_name == "Not mine"


def test_a_patch_cannot_set_a_role(client: TestClient, owner_session: Session) -> None:
    """A role is computed per request and has no stored field [TC-11].

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    account = make_account(owner_session)

    response = client.patch(
        "/v1/me",
        json={"self_name": "Rahim", "role": "teacher"},
        headers=auth_header(owner_session, account),
    )

    assert response.status_code == 422


def test_me_returns_the_readers_own_sign_in_number(
    client: TestClient, owner_session: Session
) -> None:
    """The profile shows the login number; deletion asks for it back.

    Through the RESTRICTED engine, deliberately: the account row is read
    under row-level security, and a policy that hid it would return a
    null here rather than fail loudly.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    account = make_account(owner_session, phone="+8801611477203")

    response = client.get("/v1/me", headers=auth_header(owner_session, account))

    assert response.status_code == 200
    assert response.json()["phone"] == "+8801611477203"


def test_a_patch_still_returns_the_number(
    client: TestClient, owner_session: Session
) -> None:
    """The write answers with the same shape as the read.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    account = make_account(owner_session, phone="+8801712345678")

    response = client.patch(
        "/v1/me",
        json={"self_name": "Rahim"},
        headers=auth_header(owner_session, account),
    )

    assert response.status_code == 200
    assert response.json()["phone"] == "+8801712345678"
