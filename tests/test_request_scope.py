"""The request transaction commits a success and nothing else [PA-ARCH-1].

**The defect this pins was invisible from every existing test.** The
taxonomy handler runs INSIDE ``call_next``, so by the time the
middleware saw the response a raised ``ConflictError`` had already
become an ordinary 409 -- and the middleware committed. A service that
flushed a row and then refused left the row behind while telling the
client the request failed. Each such service was individually tested
for its refusal, and none of those tests looked for the row.

The routes here are added to a fresh application instance for this file
only; they never reach the application ``app.main`` exports, so the
route-enumeration gates and the committed contract do not see them.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV
from app.errors import ConflictError, ValidationError


def _insert_account(session: Session, phone: str) -> None:
    """Write one account row through the request's session.

    :param session: The request-scoped session
    :param phone: A phone number unique to the test
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO account (id, phone, created_at) VALUES (:id, :phone, :now)"
        ),
        {"id": uuid.uuid4(), "phone": phone, "now": dt.datetime.now(tz=dt.UTC)},
    )
    session.flush()


@pytest.fixture
def probe(
    restricted_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Build an application carrying the probe routes, on the restricted role.

    :param restricted_engine: The non-superuser engine
    :param monkeypatch: The patcher
    :return: A context manager yielding the client
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")
    monkeypatch.setenv(JWT_KEYS_ENV, "k1:test-signing-key-padded-to-thirty-two")
    monkeypatch.setenv(JWT_ACTIVE_KID_ENV, "k1")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_APP_HASH", "AAAAAAAAAAA")
    from app.main import create_app

    app: FastAPI = create_app()
    app.state.engine = restricted_engine

    def writes_then_conflicts(request: Request, phone: str) -> None:
        """Flush a row, then refuse with a 409.

        :param request: The request carrying the session
        :param phone: The row's phone number
        :raises ConflictError: Always
        """
        _insert_account(request.state.session, phone)
        raise ConflictError(code="PROBE_CONFLICT", message_key="probe.conflict")

    def writes_then_rejects(request: Request, phone: str) -> None:
        """Flush a row, then refuse with a 400.

        :param request: The request carrying the session
        :param phone: The row's phone number
        :raises ValidationError: Always
        """
        _insert_account(request.state.session, phone)
        raise ValidationError(code="PROBE_INVALID", message_key="probe.invalid")

    def commits_then_rejects(request: Request, phone: str) -> None:
        """Commit a row, as the OTP path does, then refuse.

        :param request: The request carrying the session
        :param phone: The row's phone number
        :raises ValidationError: Always
        """
        _insert_account(request.state.session, phone)
        request.state.session.commit()
        raise ValidationError(code="PROBE_INVALID", message_key="probe.invalid")

    def writes_then_succeeds(request: Request, phone: str) -> dict[str, str]:
        """Flush a row and succeed.

        :param request: The request carrying the session
        :param phone: The row's phone number
        :return: An empty acknowledgement
        """
        _insert_account(request.state.session, phone)
        return {}

    def writes_then_crashes(request: Request, phone: str) -> None:
        """Flush a row, then fail with an unhandled error.

        :param request: The request carrying the session
        :param phone: The row's phone number
        :raises RuntimeError: Always
        """
        _insert_account(request.state.session, phone)
        raise RuntimeError("probe crash")

    for path, handler in (
        ("/probe/conflict", writes_then_conflicts),
        ("/probe/reject", writes_then_rejects),
        ("/probe/committed-reject", commits_then_rejects),
        ("/probe/succeed", writes_then_succeeds),
        ("/probe/crash", writes_then_crashes),
    ):
        app.add_api_route(path, handler, methods=["POST"])

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _phone() -> str:
    """Make a phone number no other test uses.

    :return: The number
    """
    return f"+88019{uuid.uuid4().int % 10**8:08d}"


def _stored(session: Session, phone: str) -> int:
    """Count account rows with a phone number.

    :param session: A reading session
    :param phone: The number
    :return: The count
    """
    return int(
        session.execute(
            sa.text("SELECT count(*) FROM account WHERE phone = :phone"),
            {"phone": phone},
        ).scalar_one()
    )


@pytest.mark.parametrize(
    ("path", "status"),
    [("/probe/conflict", 409), ("/probe/reject", 400), ("/probe/crash", 500)],
    ids=["conflict", "validation", "unhandled"],
)
def test_a_refused_request_leaves_no_row(
    probe: TestClient, restricted_session: Session, path: str, status: int
) -> None:
    """A flushed write followed by an error response is rolled back.

    :param probe: The probe client
    :param restricted_session: The application's role, to read with
    :param path: The probe route
    :param status: The status that route answers
    :return: None
    """
    phone = _phone()

    response = probe.post(path, params={"phone": phone})

    assert response.status_code == status
    assert _stored(restricted_session, phone) == 0


def test_a_successful_request_commits(
    probe: TestClient, restricted_session: Session
) -> None:
    """The control: the same write, answered 200, is kept.

    Without it every refusal test above would pass against a probe whose
    write never reached the database at all.

    :param probe: The probe client
    :param restricted_session: The application's role, to read with
    :return: None
    """
    phone = _phone()

    response = probe.post("/probe/succeed", params={"phone": phone})

    assert response.status_code == 200
    assert _stored(restricted_session, phone) == 1


def test_a_write_committed_before_the_refusal_survives_it(
    probe: TestClient, restricted_session: Session
) -> None:
    """A service that commits on purpose before refusing is not undone.

    This is the OTP path's shape: the failed attempt and its audit row
    must persist precisely because the request is refused.

    :param probe: The probe client
    :param restricted_session: The application's role, to read with
    :return: None
    """
    phone = _phone()

    response = probe.post("/probe/committed-reject", params={"phone": phone})

    assert response.status_code == 400
    assert _stored(restricted_session, phone) == 1
