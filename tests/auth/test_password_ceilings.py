"""Password failures alert globally and never refuse globally [SEC-1].

Password failures used to fill the product-wide failed-verify ceiling,
and that ceiling refuses every verify once full. A few hundred wrong
passwords from a handful of prefixes, or an evening of real typos,
then refused every sign-in in the product until the hour turned.

Written to the authorization predicate [team: Testing Posture]: who may
sign in is knowable from the inputs, and a wrong answer here is an
outage or an open door. Each test names one half of the split:

* a full product-wide password count refuses neither a correct
  password nor a code verify, and it alerts;
* a password failure no longer fills the codes' global ceiling;
* the per-identifier and per-prefix refusals still fire.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from collections.abc import Iterator
from typing import Final

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.ceilings import (
    PASSWORD_FAILURES_GLOBAL_HOURLY,
    PASSWORD_FAILURES_PER_IDENTIFIER_HOURLY,
    VERIFY_FAILURES_GLOBAL_HOURLY,
    VERIFY_FAILURES_PER_IP_HOURLY,
    ScopeKind,
)
from app.auth.client_address import TRUSTED_CLIENT_IP_HEADER_ENV
from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.passwords import hash_password
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV

PASSWORD: Final = "a long enough passphrase"  # noqa: S105 -- a test value
FIXED_CODE: Final = "246810"

#: Well past the old shared limit, so a refusal could not hide behind
#: an off-by-one at the boundary.
BEYOND_THE_OLD_LIMIT: Final = VERIFY_FAILURES_GLOBAL_HOURLY + 100


@pytest.fixture
def client(
    restricted_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Build a client whose codes are predictable and whose IP is a header.

    :param restricted_engine: The non-superuser engine
    :param monkeypatch: The patcher
    :return: A context manager yielding the client
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")
    monkeypatch.setenv(JWT_KEYS_ENV, "k1:test-signing-key-padded-to-thirty-two")
    monkeypatch.setenv(JWT_ACTIVE_KID_ENV, "k1")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_APP_HASH", "AAAAAAAAAAA")
    monkeypatch.setenv(TRUSTED_CLIENT_IP_HEADER_ENV, "X-Client-Address")
    monkeypatch.setattr("app.auth.otp.generate_code", lambda: FIXED_CODE)

    from app.main import create_app

    app = create_app()
    app.state.engine = restricted_engine
    with TestClient(app) as test_client:
        yield test_client


def _number() -> str:
    """Return a fresh canonical mobile number.

    :return: ``+88017`` and eight random digits
    """
    return f"+88017{uuid.uuid4().int % 10**8:08d}"


def _account(session: Session) -> str:
    """Arrange an account with a password.

    :param session: An arranging session
    :return: Its number
    """
    number = _number()
    now = dt.datetime.now(tz=dt.UTC)
    session.execute(
        sa.text(
            "INSERT INTO account (id, phone, password_hash, password_changed_at, "
            "created_at, activated_at) VALUES (:id, :p, :h, :now, :now, :now)"
        ),
        {"id": uuid.uuid4(), "p": number, "h": hash_password(PASSWORD), "now": now},
    )
    session.commit()
    return number


def _preload(session: Session, kind: ScopeKind, value: str, count: int) -> None:
    """Set the current hour's counter for one scope directly.

    :param session: The session to write through
    :param kind: The scope kind
    :param value: The scope value
    :param count: The value to set
    :return: None
    """
    start = dt.datetime.now(tz=dt.UTC).replace(minute=0, second=0, microsecond=0)
    session.execute(
        sa.text(
            "INSERT INTO rate_limit_counter "
            "(id, scope_kind, scope_value, window_start, count) "
            "VALUES (gen_random_uuid(), :kind, :value, :window, :count)"
        ),
        {"kind": kind.value, "value": value, "window": start, "count": count},
    )
    session.commit()


def _counts(session: Session) -> dict[str, int]:
    """Read every counter's total, by scope kind.

    :param session: A session able to read the counters
    :return: The sum of counts per scope kind
    """
    session.expire_all()
    return {
        kind: int(total)
        for kind, total in session.execute(
            sa.text(
                "SELECT scope_kind, sum(count) FROM rate_limit_counter "
                "GROUP BY scope_kind"
            )
        ).all()
    }


def _password(client: TestClient, phone: str, password: str, ip: str) -> httpx.Response:
    """Post one password sign-in from one address.

    :param client: The test client
    :param phone: The number
    :param password: The password typed
    :param ip: The caller's address
    :return: The response
    """
    return client.post(
        "/v1/auth/password",
        json={"phone": phone, "password": password},
        headers={"X-Client-Address": ip},
    )


def test_a_full_global_password_count_refuses_no_sign_in(
    client: TestClient, owner_session: Session
) -> None:
    """Past the old shared limit, a correct password and a code still work.

    :param client: A client with a predictable code
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    phone = _account(owner_session)
    _preload(
        owner_session,
        ScopeKind.PASSWORD_FAIL_GLOBAL_HOURLY,
        "global",
        BEYOND_THE_OLD_LIMIT,
    )

    by_password = _password(client, phone, PASSWORD, "11.12.13.14")
    client.post(
        "/v1/auth/otp", json={"phone": phone}, headers={"X-Client-Address": "11.0.0.1"}
    )
    by_code = client.post(
        "/v1/auth/verify",
        json={"phone": phone, "code": FIXED_CODE},
        headers={"X-Client-Address": "11.0.0.1"},
    )

    assert by_password.status_code == 200, by_password.text
    assert by_code.status_code == 200, by_code.text


def test_a_wrong_password_counts_toward_its_own_global_scope_not_the_codes(
    client: TestClient, owner_session: Session
) -> None:
    """The codes' outage switch is not filled by password typos.

    :param client: A client with a predictable code
    :param owner_session: A session able to read counters back
    :return: None
    """
    phone = _account(owner_session)

    wrong = _password(client, phone, "nope-nope", "21.22.23.24")

    assert wrong.status_code == 400
    counted = _counts(owner_session)
    assert counted.get("pwf_global_hour") == 1
    assert counted.get("pw_fail_id_hour") == 1
    assert counted.get("vf_ip_hour") == 1
    assert counted.get("vf_ip48_hour") == 1
    assert "vf_global_hour" not in counted


def test_the_global_password_scope_alerts_when_it_fills(
    client: TestClient,
    owner_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The failure that fills the scope reaches a human, and is not refused.

    :param client: A client with a predictable code
    :param owner_session: A session able to arrange fixture data
    :param caplog: The log capture
    :return: None
    """
    phone = _account(owner_session)
    _preload(
        owner_session,
        ScopeKind.PASSWORD_FAIL_GLOBAL_HOURLY,
        "global",
        PASSWORD_FAILURES_GLOBAL_HOURLY - 1,
    )

    with caplog.at_level(logging.CRITICAL, logger="app.auth.ceilings"):
        wrong = _password(client, phone, "nope-nope", "31.32.33.34")
        right = _password(client, phone, PASSWORD, "31.32.33.34")

    assert wrong.status_code == 400
    assert right.status_code == 200
    assert "pwf_global_hour" in [getattr(r, "scope", None) for r in caplog.records]


def test_a_full_codes_global_ceiling_does_not_refuse_a_password(
    client: TestClient, owner_session: Session
) -> None:
    """The codes' outage switch refuses codes, and only codes.

    :param client: A client with a predictable code
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    phone = _account(owner_session)
    _preload(
        owner_session,
        ScopeKind.VERIFY_FAIL_GLOBAL_HOURLY,
        "global",
        VERIFY_FAILURES_GLOBAL_HOURLY,
    )

    right = _password(client, phone, PASSWORD, "41.42.43.44")

    assert right.status_code == 200


def test_the_per_identifier_refusal_still_fires(
    client: TestClient, owner_session: Session
) -> None:
    """A guesser at one identifier gets the ceiling and no more.

    :param client: A client with a predictable code
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    phone = _account(owner_session)
    for attempt in range(PASSWORD_FAILURES_PER_IDENTIFIER_HOURLY):
        # A fresh /24 each time, so only the identifier scope can fill.
        wrong = _password(client, phone, "nope-nope", f"51.{attempt}.0.1")
        assert wrong.status_code == 400

    stopped = _password(client, phone, PASSWORD, "52.0.0.1")

    assert stopped.status_code == 409
    error = stopped.json()["error"]
    assert error["message_key"] == "auth.password.too_many_attempts"


def test_the_per_prefix_refusal_still_fires(
    client: TestClient, owner_session: Session
) -> None:
    """A full /24 refuses even the right password from inside it.

    :param client: A client with a predictable code
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    phone = _account(owner_session)
    _preload(
        owner_session,
        ScopeKind.VERIFY_FAIL_IP_HOURLY,
        "61.62.63.0/24",
        VERIFY_FAILURES_PER_IP_HOURLY,
    )

    refused = _password(client, phone, PASSWORD, "61.62.63.64")
    elsewhere = _password(client, phone, PASSWORD, "71.72.73.74")

    assert refused.status_code == 409
    assert elsewhere.status_code == 200
