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

import logging
import uuid
from typing import Final

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.exc import DataError, IntegrityError, OperationalError

from app.db.session import build_engine
from app.request_scope import CLIENT_INPUT_SQLSTATES, correlation_id_from

#: A value past int4, bound into a statement that casts it to one.
OVERFLOW = 3_000_000_000


#: One statement per SQLSTATE, each failing on its bound value alone.
_DATA_ERRORS: Final[dict[str, tuple[str, object]]] = {
    # An explicit cast truncates silently; only an assignment raises.
    "22001": ("INSERT INTO _probe_narrow (v) VALUES (:v)", "abc"),
    "22003": ("SELECT CAST(:v AS integer)", OVERFLOW),
    "22P02": ("SELECT CAST(:v AS integer)", "not-a-number"),
    "22007": ("SELECT CAST(:v AS date)", "not-a-date"),
    "22008": ("SELECT CAST(:v AS date)", "2026-13-45"),
    "22012": ("SELECT 1 / CAST(:v AS integer)", 0),
}


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

    def overflow() -> None:
        """Fail as a value too large for its column does, in PostgreSQL.

        :return: None
        :raises DataError: Always
        """
        engine = app.state.engine
        with engine.connect() as connection:
            connection.execute(sa.text("SELECT CAST(:v AS integer)"), {"v": OVERFLOW})

    def data_error(state: str) -> None:
        """Fail with a chosen class-22 SQLSTATE, in PostgreSQL.

        :param state: Which statement to fail, keyed by its SQLSTATE
        :return: None
        :raises DataError: Always
        """
        statement, value = _DATA_ERRORS[state]
        with app.state.engine.connect() as connection:
            connection.execute(
                sa.text("CREATE TEMP TABLE _probe_narrow (v varchar(2))")
            )
            connection.execute(sa.text(statement), {"v": value})

    app.add_api_route("/__probe/data/{state}", data_error, methods=["GET"])
    app.add_api_route("/__probe/operational", operational, methods=["GET"])
    app.add_api_route("/__probe/overflow", overflow, methods=["GET"])
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


def test_a_value_the_column_cannot_hold_is_a_400_envelope(
    probing_client: TestClient,
) -> None:
    """An int4 overflow is the caller's input, not a server fault [SEC-3].

    :param probing_client: A client with failing routes
    :return: None
    """
    response = probing_client.get("/__probe/overflow")

    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["code"] == "REQUEST_INVALID"
    assert error["retryable"] is False
    assert str(OVERFLOW) not in response.text


def test_the_application_engine_hides_bound_parameters(restricted_url: str) -> None:
    """A failing statement's values never reach the exception's text [SEC-3].

    The unexpected-failure handler logs ``exc_info``; with parameters
    shown, that traceback carries whatever the statement was bound with.

    :param restricted_url: A URL the application role connects with
    :return: None
    """
    engine = build_engine(restricted_url)
    try:
        with (
            pytest.raises(DataError) as raised,
            engine.connect() as connection,
        ):
            connection.execute(sa.text("SELECT CAST(:v AS integer)"), {"v": OVERFLOW})
    finally:
        engine.dispose()

    assert str(OVERFLOW) not in str(raised.value)
    assert "hidden due to hide_parameters" in str(raised.value)


@pytest.mark.parametrize("state", sorted(CLIENT_INPUT_SQLSTATES))
def test_each_bad_input_sqlstate_is_a_400_logged_by_state_only(
    probing_client: TestClient, state: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Only the input-shaped SQLSTATEs are the caller's fault [SEC-3].

    :param probing_client: A client with failing routes
    :param state: The SQLSTATE the probe raises
    :param caplog: The log capture
    :return: None
    """
    with caplog.at_level(logging.WARNING, logger="app.request_scope"):
        response = probing_client.get(f"/__probe/data/{state}")

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "REQUEST_INVALID"
    logged = [r for r in caplog.records if r.name == "app.request_scope"]
    assert [getattr(r, "sqlstate", None) for r in logged] == [state]
    assert all(r.exc_info is None for r in logged)


def test_a_data_error_that_is_not_bad_input_is_a_500(
    probing_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """A division by zero is a defect in a statement, not in a request.

    It must not tell the client to fix its input, and its traceback must
    be logged so the defect is found.

    :param probing_client: A client with failing routes
    :param caplog: The log capture
    :return: None
    """
    assert "22012" not in CLIENT_INPUT_SQLSTATES
    with caplog.at_level(logging.WARNING, logger="app.request_scope"):
        response = probing_client.get("/__probe/data/22012")

    assert response.status_code == 500, response.text
    error = response.json()["error"]
    assert error["code"] == "INTERNAL"
    assert error["message_key"] == "error.unexpected"
    unhandled = [r for r in caplog.records if r.getMessage() == "unhandled failure"]
    assert len(unhandled) == 1
    assert unhandled[0].exc_info is not None
