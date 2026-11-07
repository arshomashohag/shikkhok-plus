"""Every failure reaches the client in the one error envelope [audit C-17].

The taxonomy handler covered only raised taxonomy errors. A database
outage, an exhausted pool, a serialization failure or a constraint the
service did not map escaped as Starlette's plain-text ``Internal Server
Error``; FastAPI's own request validation answered ``{"detail": [...]}``.
Both clients read ``retryable`` from the envelope, so a database blip in
the middle of a class showed a teacher a non-retryable error -- the
failure the team's practice calls the one a teacher will not forgive.

And the correlation id [audit C-22]: the header was trusted as sent, so a
value longer than the audit column silently dropped every auth audit row
for that request -- exactly the rows recording a brute-force attempt.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, OperationalError

from app.request_scope import correlation_id_from


class _Body(BaseModel):
    """A body with one required field, to fail validation against.

    :ivar phone: Any string
    """

    phone: str


def _app(api_client: TestClient) -> FastAPI:
    """Return the client's application, typed.

    :param api_client: The test client
    :return: Its FastAPI application
    """
    app = api_client.app
    assert isinstance(app, FastAPI)
    return app


@pytest.fixture
def probing_client(api_client: TestClient) -> TestClient:
    """Build a client whose app carries routes that fail on purpose.

    :param api_client: The test client
    :return: A client that renders server errors instead of raising them
    """
    app = _app(api_client)

    def operational() -> None:
        """Fail as a dropped connection does.

        :return: None
        :raises OperationalError: Always
        """
        raise OperationalError("SELECT 1", {}, Exception("server closed"))

    def integrity() -> None:
        """Fail on a constraint no service mapped.

        :return: None
        :raises IntegrityError: Always
        """
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    def crash() -> None:
        """Fail in a way nothing anticipated.

        :return: None
        :raises RuntimeError: Always
        """
        raise RuntimeError("boom")

    def echo(body: _Body) -> dict[str, str]:
        """Accept a body, to be sent an invalid one.

        :param body: The body
        :return: It, unchanged
        """
        return {"phone": body.phone}

    app.add_api_route("/__probe/operational", operational, methods=["GET"])
    app.add_api_route("/__probe/integrity", integrity, methods=["GET"])
    app.add_api_route("/__probe/crash", crash, methods=["GET"])
    app.add_api_route("/__probe/echo", echo, methods=["POST"])
    return TestClient(app, raise_server_exceptions=False)


def test_a_database_outage_is_a_retryable_503_envelope(
    probing_client: TestClient,
) -> None:
    """The case the clients' retry prompt exists for.

    :param probing_client: A client with failing routes
    :return: None
    """
    response = probing_client.get("/__probe/operational")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["retryable"] is True
    assert error["message_key"] == "error.temporarily_unavailable"
    assert response.headers["X-Correlation-Id"]


def test_an_unmapped_constraint_is_a_409_envelope(
    probing_client: TestClient,
) -> None:
    """A race a service did not catch is a conflict, not a crash.

    :param probing_client: A client with failing routes
    :return: None
    """
    response = probing_client.get("/__probe/integrity")

    assert response.status_code == 409
    assert response.json()["error"]["retryable"] is False


def test_an_unknown_failure_is_a_500_envelope(probing_client: TestClient) -> None:
    """Even the unanticipated failure carries a key the client renders.

    :param probing_client: A client with failing routes
    :return: None
    """
    response = probing_client.get("/__probe/crash")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["message_key"] == "error.unexpected"
    assert error["retryable"] is False
    assert "boom" not in response.text


def test_request_validation_is_an_envelope_that_echoes_no_input(
    probing_client: TestClient,
) -> None:
    """A malformed body gets the envelope, and never its own values back.

    :param probing_client: A client with failing routes
    :return: None
    """
    response = probing_client.post("/__probe/echo", json={"phone": 1, "x": "01712"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "REQUEST_INVALID"
    assert "01712" not in response.text


@pytest.mark.parametrize(
    "sent",
    [
        "x" * 65,
        "has spaces in it",
        "line\nbreak",
        "",
    ],
)
def test_an_unusable_correlation_id_is_replaced(sent: str) -> None:
    """Too long, odd characters or empty: a fresh id is generated.

    :param sent: The header as a client sent it
    :return: None
    """
    chosen = correlation_id_from(sent)

    assert chosen != sent
    assert str(uuid.UUID(chosen)) == chosen


def test_a_well_formed_correlation_id_is_kept() -> None:
    """A client's own id survives, so its logs and ours line up.

    :return: None
    """
    sent = "a1b2c3d4-e5f6-4a5b-8c7d-0e1f2a3b4c5d"
    assert correlation_id_from(sent) == sent


def test_an_oversized_header_no_longer_drops_the_audit_row(
    api_client: TestClient, restricted_engine: sa.Engine
) -> None:
    """The audit row for an OTP issue is written whatever the header.

    :param api_client: The test client
    :param restricted_engine: An engine to read the audit log through
    :return: None
    """
    response = api_client.post(
        "/v1/auth/otp",
        json={"phone": "01712345678"},
        headers={"X-Correlation-Id": "z" * 200},
    )
    assert response.status_code < 500, response.text
    with restricted_engine.connect() as connection:
        written = connection.scalar(
            sa.text("SELECT count(*) FROM auth_audit_log WHERE correlation_id = :cid"),
            {"cid": response.headers["X-Correlation-Id"]},
        )
    assert written and written >= 1
