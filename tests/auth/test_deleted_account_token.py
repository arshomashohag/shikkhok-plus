"""A deleted account's access token stops working at once.

**The defect this pins.** An access token is a signed claim with a
fifteen-minute lifetime, and it was verified by signature and expiry
alone. After ``DELETE /v1/me`` the account row is gone but the token is
still validly signed, so for the rest of its lifetime it authenticated a
person who no longer exists: reads answered 200 with every field null,
and ``PATCH /v1/me`` raised an unhandled 500 trying to update a row that
was not there. Nothing leaked -- every read was empty -- but an
authenticated request for an account that does not exist is not a
request the server should be answering at all.

**The rule now**: authentication is the signature AND an account row.
A token naming a deleted account gets the same 401 an expired token
gets, so a client does what it already does for an expired session --
it tries to refresh, the refresh tokens went with the account, and it
signs out.

**One deliberate exception**, kept and asserted: ``DELETE /v1/me`` itself
stays idempotent for a token whose account is already gone, so a double
tap on "Delete" reports the deletion rather than an error [BR1.4].
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Account
from tests.conftest import bearer


def _account(session: Session) -> uuid.UUID:
    """Create one account with a unique number.

    :param session: An arranging session
    :return: The new account's id
    """
    record = Account(
        phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    session.commit()
    return record.id


@pytest.fixture
def deleted(api_client: TestClient, owner_session: Session) -> dict[str, str]:
    """Delete an account in-app and return the token it was deleted with.

    :param api_client: The test client
    :param owner_session: A session able to arrange fixture data
    :return: The still-unexpired bearer header of the deleted account
    """
    headers = bearer(owner_session, _account(owner_session))
    owner_session.commit()
    response = api_client.request("DELETE", "/v1/me", headers=headers)
    assert response.status_code == 200, response.text
    return headers


def _is_session_ended(response_status: int, body: dict[str, object]) -> bool:
    """Whether a response is the ordinary "your session has ended" 401.

    :param response_status: The HTTP status
    :param body: The decoded JSON body
    :return: True for a 401 naming ``auth.token.not_valid``
    """
    error = body.get("error")
    return (
        response_status == 401
        and isinstance(error, dict)
        and error.get("message_key") == "auth.token.not_valid"
    )


def test_a_deleted_accounts_token_cannot_read_me(
    api_client: TestClient, deleted: dict[str, str]
) -> None:
    """``GET /v1/me`` no longer answers 200 with every field null.

    :param api_client: The test client
    :param deleted: The deleted account's bearer header
    :return: None
    """
    response = api_client.get("/v1/me", headers=deleted)

    assert _is_session_ended(response.status_code, response.json()), response.text


def test_a_deleted_accounts_token_cannot_write_me(
    api_client: TestClient, deleted: dict[str, str]
) -> None:
    """``PATCH /v1/me`` is a 401, not the unhandled 500 it was.

    :param api_client: The test client
    :param deleted: The deleted account's bearer header
    :return: None
    """
    response = api_client.patch(
        "/v1/me", headers=deleted, json={"self_name": "Still here?"}
    )

    assert _is_session_ended(response.status_code, response.json()), response.text


@pytest.mark.parametrize(
    "path",
    ["/v1/batches", "/v1/me/enrollments", "/v1/me/notifications", "/v1/invitations"],
)
def test_a_deleted_accounts_token_cannot_reach_any_lens(
    api_client: TestClient, deleted: dict[str, str], path: str
) -> None:
    """Every lensed or lens-exempt read refuses it the same way.

    :param api_client: The test client
    :param deleted: The deleted account's bearer header
    :param path: A route behind authentication
    :return: None
    """
    response = api_client.get(path, headers=deleted)

    assert _is_session_ended(response.status_code, response.json()), response.text


def test_deleting_twice_still_reports_the_deletion(
    api_client: TestClient, deleted: dict[str, str]
) -> None:
    """A double tap on Delete is not an error [BR1.4].

    The account is gone, which is what was asked for; the second request
    says so rather than telling the person their session ended.

    :param api_client: The test client
    :param deleted: The deleted account's bearer header
    :return: None
    """
    response = api_client.request("DELETE", "/v1/me", headers=deleted)

    assert response.status_code == 200, response.text


def test_a_live_accounts_token_still_works(
    api_client: TestClient, owner_session: Session
) -> None:
    """The control: the check refuses only accounts that are gone.

    :param api_client: The test client
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    headers = bearer(owner_session, _account(owner_session))
    owner_session.commit()

    response = api_client.get("/v1/me", headers=headers)

    assert response.status_code == 200, response.text
