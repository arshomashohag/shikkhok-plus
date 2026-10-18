"""The three auth endpoints, end to end through the real app.

**The byte-identical assertion is made at the HTTP boundary here**, not
at the function boundary. That is where an attacker actually observes
it, and a difference can enter at any layer between the two -- a header,
a status code, a content length.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV
from app.db.models import Account

KNOWN = "+8801711111111"
UNKNOWN = "+8801799999999"


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
def known_account(owner_session: Session) -> uuid.UUID:
    """Create the account the known branch finds.

    :param owner_session: A session able to arrange fixture data
    :return: The account's id
    """
    record = Account(phone=KNOWN, created_at=dt.datetime.now(tz=dt.UTC))
    owner_session.add(record)
    owner_session.commit()
    return record.id


def test_issue_returns_the_same_bytes_for_known_and_unknown(
    client: TestClient, known_account: uuid.UUID
) -> None:
    # THE ASSERTION AT THE BOUNDARY AN ATTACKER OBSERVES. A difference
    # can enter at any layer between the function and the socket.
    known = client.post("/v1/auth/otp", json={"phone": KNOWN})
    unknown = client.post("/v1/auth/otp", json={"phone": UNKNOWN})

    assert known.status_code == unknown.status_code
    assert known.content == unknown.content
    assert known.headers.get("content-length") == unknown.headers.get("content-length")


def test_issue_accepts_a_number_from_the_body_only(client: TestClient) -> None:
    # The number is TYPED BY THE USER and never read from the SIM
    # [AC1.1.6]: there is no device-side source for this field.
    response = client.post("/v1/auth/otp", json={"phone": KNOWN})
    assert response.status_code == 200


def test_issue_rejects_an_unexpected_field(client: TestClient) -> None:
    response = client.post(
        "/v1/auth/otp", json={"phone": KNOWN, "account_exists": True}
    )
    assert response.status_code == 422


def test_the_full_sign_in_path_returns_a_working_token_pair(
    client: TestClient,
    known_account: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # THE SKELETON PATH, end to end over HTTP. The transmitted code
    # cannot be read back from the database -- that is the point of
    # BR2.4 -- so it is captured at the one place it exists in the
    # clear: the gateway call. That is the same seam the real send
    # uses, so nothing here bypasses the path under test.
    sent: list[str] = []

    from app.gateway.null import NullGateway

    original = NullGateway.send

    def capture(
        self: NullGateway, number: str, message: str, correlation_id: str
    ) -> object:
        sent.append(message)
        return original(self, number, message, correlation_id)

    monkeypatch.setattr(NullGateway, "send", capture)

    issued = client.post("/v1/auth/otp", json={"phone": KNOWN})
    assert issued.status_code == 200
    assert sent, "no SMS was dispatched"

    code = next(part for part in sent[0].split() if part.isdigit())

    verified = client.post("/v1/auth/verify", json={"phone": KNOWN, "code": code})
    assert verified.status_code == 200

    pair = verified.json()
    assert pair["access_token"] and pair["refresh_token"]
    assert pair["expires_in"] == 900

    rotated = client.post(
        "/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}
    )
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != pair["refresh_token"]


def test_a_replayed_refresh_token_is_refused_over_http(
    client: TestClient, known_account: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []

    from app.gateway.null import NullGateway

    original = NullGateway.send

    def capture(
        self: NullGateway, number: str, message: str, correlation_id: str
    ) -> object:
        sent.append(message)
        return original(self, number, message, correlation_id)

    monkeypatch.setattr(NullGateway, "send", capture)

    client.post("/v1/auth/otp", json={"phone": KNOWN})
    code = next(part for part in sent[0].split() if part.isdigit())
    pair = client.post("/v1/auth/verify", json={"phone": KNOWN, "code": code}).json()

    client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    replayed = client.post(
        "/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}
    )
    assert replayed.status_code == 401


def test_a_ceiling_breach_returns_409_not_429(
    client: TestClient, known_account: uuid.UUID
) -> None:
    # A ConflictError, never a TransientError: retrying into a cost
    # ceiling is exactly wrong, and 429 carries a retry-after
    # convention that invites it [BR2.2].
    for _ in range(3):
        client.post("/v1/auth/otp", json={"phone": KNOWN})

    refused = client.post("/v1/auth/otp", json={"phone": KNOWN})
    assert refused.status_code == 409


def test_the_breach_message_does_not_say_invalid_number(
    client: TestClient, known_account: uuid.UUID
) -> None:
    for _ in range(3):
        client.post("/v1/auth/otp", json={"phone": KNOWN})

    refused = client.post("/v1/auth/otp", json={"phone": KNOWN})
    body = refused.text.lower()
    assert "invalid" not in body
    assert KNOWN not in refused.text


def test_health_reports_the_migration_revision(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["migration_revision"] == "0003"


def test_health_discloses_nothing_beyond_its_three_fields(
    client: TestClient,
) -> None:
    # It is PUBLIC, so every field added is information disclosed. It
    # must not grow into a diagnostic endpoint.
    assert set(client.get("/health").json()) == {
        "status",
        "database",
        "migration_revision",
    }


def test_a_refresh_with_an_unknown_token_is_401(client: TestClient) -> None:
    response = client.post("/v1/auth/refresh", json={"refresh_token": "x" * 32})
    assert response.status_code == 401


def test_no_response_body_carries_a_phone_number(
    client: TestClient, known_account: uuid.UUID
) -> None:
    for response in (
        client.post("/v1/auth/otp", json={"phone": KNOWN}),
        client.post("/v1/auth/verify", json={"phone": KNOWN, "code": "000000"}),
    ):
        assert KNOWN not in response.text
