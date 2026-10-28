"""Fixtures for D1's signup, lookup and decision suites.

The client fixture matches the one U4 built for ``GET /v1/me``: a real
application against the **restricted** engine, so every assertion here
is made through the same non-superuser role the application uses and the
row-level-security policy is in force rather than bypassed [pg-rls].
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
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV, issue_pair
from app.db.models import Account


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


def auth_header(session: Session, account_id: uuid.UUID) -> dict[str, str]:
    """Build an Authorization header for an account.

    :param session: The session to write the token family through
    :param account_id: The account to authenticate as
    :return: The header mapping
    """
    pair = issue_pair(session, account_id=account_id, correlation_id=uuid.uuid4())
    return {"Authorization": f"Bearer {pair.access_token}"}


def make_account(session: Session, phone: str | None = None) -> uuid.UUID:
    """Create one account with a unique number.

    :param session: An arranging session
    :param phone: The number, or None to generate a unique one
    :return: The new account's id
    """
    record = Account(
        phone=phone or f"+88017{uuid.uuid4().int % 10**8:08d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    session.commit()
    return record.id
