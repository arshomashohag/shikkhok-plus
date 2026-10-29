"""Phone canonicalisation, observed where it matters: at the HTTP boundary.

The function is unit-tested in ``test_phone.py``. These assert the three
properties it exists for, end to end through the real app -- the place a
schema that forgot ``PhoneField`` would let a raw spelling through.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.ceilings import PER_NUMBER_HOURLY
from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV
from app.db.models import OtpRequest
from tests.accounts.conftest import make_account

#: One number, spelled the ways people type it.
SPELLINGS = ("01722-345678", "+8801722345678", "8801722345678", "০১৭২২৩৪৫৬৭৮")


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


def test_a_malformed_number_is_refused_with_a_message_key(client: TestClient) -> None:
    """The client can translate the refusal.

    FastAPI's own 422 carries no ``message_key``, so a client showing it
    could only say "something went wrong" in a Bangla-first UI.

    :param client: The test client
    :return: None
    """
    response = client.post("/v1/auth/otp", json={"phone": "01211234567"})

    assert response.status_code == 400
    assert response.json()["error"]["message_key"] == "phone.invalid"


def test_a_spelled_number_finds_the_canonically_stored_account(
    client: TestClient, owner_session: Session
) -> None:
    """Typing ``01733-456789`` reaches the account stored as ``+880...``.

    No OTP is stored for a number with no account -- that is the
    anti-enumeration design -- so the account exists first. A code then
    issued against it proves the spelled number was canonicalised
    before the lookup, rather than missing the account and silently
    sending nothing.

    :param client: The test client
    :param owner_session: A session able to arrange and read rows
    :return: None
    """
    make_account(owner_session, phone="+8801733456789")

    response = client.post("/v1/auth/otp", json={"phone": "01733-456789"})
    assert response.status_code == 200

    stored = owner_session.scalars(
        sa.select(OtpRequest.phone).where(OtpRequest.phone.like("%733456789"))
    ).all()

    assert stored == ["+8801733456789"]


def test_the_per_number_ceiling_counts_every_spelling_together(
    client: TestClient,
) -> None:
    """Three spellings of one phone are one number, not three allowances.

    **The cost control this restores** [D-33]. Counting the raw string
    gave each spelling its own hourly allowance, so one phone could be
    sent several times the ceiling's worth of SMS.

    :param client: The test client
    :return: None
    """
    statuses = [
        client.post(
            "/v1/auth/otp", json={"phone": SPELLINGS[index % len(SPELLINGS)]}
        ).status_code
        for index in range(PER_NUMBER_HOURLY + 1)
    ]

    assert statuses[:PER_NUMBER_HOURLY] == [200] * PER_NUMBER_HOURLY
    assert statuses[PER_NUMBER_HOURLY] != 200, (
        "a different spelling must not reset the per-number ceiling"
    )
