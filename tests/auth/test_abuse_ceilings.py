"""The 2026-11-07 abuse ceilings: a signup budget, /48 buckets, verify limits.

Three audit findings, one mechanism (:class:`CeilingChecker`):

* **C-05**: signup spent sign-in's daily SMS budget and an IPv6 caller
  held a fresh per-IP bucket per /64, so one caller with a /56 could
  spend the day's budget and nobody in the country received a sign-in
  code until midnight UTC. Signup now spends its own budget, and every
  per-IP cascade also counts the caller's /48.
* **C-20**: ``/verify`` had no limit wider than one code. A failed
  verify now counts against the caller's prefix and a global hourly
  ceiling, and a number whose codes keep dying is cooled off.
* Both: a code whose SMS was skipped for budget is not left verifiable.

Written before the implementation: each refusal here is an
authorization answer, and the defect each prevents passes a happy-path
test -- a ceiling that counts and never refuses looks exactly like one
that works until the day it is needed.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from collections.abc import Iterator
from typing import Final

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.ceilings import (
    DEAD_CODES_PER_NUMBER_DAILY,
    GLOBAL_DAILY,
    PER_COARSE_IP_HOURLY,
    SIGNUP_GLOBAL_DAILY,
    VERIFY_FAILURES_GLOBAL_HOURLY,
    VERIFY_FAILURES_PER_IP_HOURLY,
    CeilingBreach,
    CeilingChecker,
    ScopeKind,
    SendBudget,
)
from app.auth.client_address import (
    TRUSTED_CLIENT_IP_HEADER_ENV,
    coarse_address_prefix,
)
from app.auth.delivery import send_within_budget
from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV
from app.db.models import Account
from app.gateway.null import NullGateway

KNOWN: Final = "+8801711111111"
UNKNOWN: Final = "+8801799999999"
FIXED_CODE: Final = "246810"


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


def _preload(
    session: Session, kind: ScopeKind, value: str, count: int, window: dt.timedelta
) -> None:
    """Set the current window's counter directly.

    :param session: The session to write through
    :param kind: The scope kind
    :param value: The scope value
    :param count: The value to set
    :param window: The scope's window, hour or day
    :return: None
    """
    now = dt.datetime.now(tz=dt.UTC)
    start = (
        now.replace(hour=0, minute=0, second=0, microsecond=0)
        if window == dt.timedelta(days=1)
        else now.replace(minute=0, second=0, microsecond=0)
    )
    session.execute(
        sa.text(
            "INSERT INTO rate_limit_counter "
            "(id, scope_kind, scope_value, window_start, count) "
            "VALUES (gen_random_uuid(), :kind, :value, :window, :count)"
        ),
        {"kind": kind.value, "value": value, "window": start, "count": count},
    )
    session.commit()


def _verify(client: TestClient, phone: str, code: str, ip: str) -> object:
    """Post one verify from one address.

    :param client: The test client
    :param phone: The number
    :param code: The code
    :param ip: The caller's address
    :return: The response
    """
    return client.post(
        "/v1/auth/verify",
        json={"phone": phone, "code": code},
        headers={"X-Client-Address": ip},
    )


# ------------------------------------------------------------- IPv6 /48


def test_ipv6_is_also_counted_per_slash_48() -> None:
    """A /56 holds 256 /64s; it holds one /48 bucket [C-05].

    :return: None
    """
    assert coarse_address_prefix("2001:db8:1:2::1") == "2001:db8:1::/48"
    assert coarse_address_prefix("2001:db8:1:ff00::1") == "2001:db8:1::/48"
    assert coarse_address_prefix("203.0.113.7") == "203.0.113.0/24"
    assert coarse_address_prefix(None) == "unparsable"


def test_the_coarse_bucket_refuses_a_caller_spread_across_slash_64s(
    restricted_session: Session,
) -> None:
    """Fresh /64s no longer buy a fresh allowance [C-05].

    :param restricted_session: A session as the application role
    :return: None
    """
    checker = CeilingChecker(restricted_session)
    coarse = "2001:db8:7::/48"
    # A fixed moment, so the run cannot straddle an hour boundary and
    # split the counts across two windows.
    moment = dt.datetime(2026, 11, 7, 9, 30, tzinfo=dt.UTC)
    for index in range(PER_COARSE_IP_HOURLY):
        checker.check_and_consume(
            number=f"+88017{index:08d}",
            ip_prefix=f"2001:db8:7:{index:x}::/64",
            now=moment,
            coarse_prefix=coarse,
        )

    with pytest.raises(CeilingBreach) as breach:
        checker.check_and_consume(
            number="+8801700099999",
            ip_prefix="2001:db8:7:ffff::/64",
            now=moment,
            coarse_prefix=coarse,
        )

    assert breach.value.scope is ScopeKind.IP48_HOURLY


# ---------------------------------------------------------- signup budget


def test_signup_has_its_own_daily_budget(restricted_session: Session) -> None:
    """An exhausted signup budget leaves sign-in's untouched [C-05].

    :param restricted_session: A session as the application role
    :return: None
    """
    checker = CeilingChecker(restricted_session)
    _preload(
        restricted_session,
        ScopeKind.SIGNUP_GLOBAL_DAILY,
        "global",
        SIGNUP_GLOBAL_DAILY,
        dt.timedelta(days=1),
    )

    with pytest.raises(CeilingBreach) as breach:
        checker.consume_send(SendBudget.SIGNUP)
    checker.consume_send(SendBudget.SIGN_IN)

    assert breach.value.scope is ScopeKind.SIGNUP_GLOBAL_DAILY
    assert GLOBAL_DAILY != 0


def test_the_signup_budget_alerts_when_it_trips(
    restricted_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    """A drained signup budget reaches a human [C-05].

    :param restricted_session: A session as the application role
    :param caplog: The log capture
    :return: None
    """
    _preload(
        restricted_session,
        ScopeKind.SIGNUP_GLOBAL_DAILY,
        "global",
        SIGNUP_GLOBAL_DAILY,
        dt.timedelta(days=1),
    )
    with (
        caplog.at_level(logging.CRITICAL, logger="app.auth.ceilings"),
        pytest.raises(CeilingBreach),
    ):
        CeilingChecker(restricted_session).consume_send(SendBudget.SIGNUP)

    assert [record.scope for record in caplog.records] == ["su_global_day"]


# ------------------------------------------------ a skipped send is dead


def test_a_code_whose_send_was_skipped_cannot_be_verified(
    client: TestClient, owner_session: Session, known_account: uuid.UUID
) -> None:
    """Budget exhausted: the person gets no SMS, and nobody gets a code.

    The code row used to be kept live, so an attacker who had drained
    the budget still had five guesses at a code nobody could receive
    [C-20].

    :param client: A client with a predictable code
    :param owner_session: A session able to arrange fixture data
    :param known_account: The account the number belongs to
    :return: None
    """
    _preload(
        owner_session,
        ScopeKind.GLOBAL_DAILY,
        "global",
        GLOBAL_DAILY,
        dt.timedelta(days=1),
    )

    issued = client.post(
        "/v1/auth/otp", json={"phone": KNOWN}, headers={"X-Client-Address": "1.2.3.4"}
    )
    verified = _verify(client, KNOWN, FIXED_CODE, "1.2.3.4")

    assert issued.status_code == 200
    assert verified.status_code == 400  # type: ignore[attr-defined]


def test_send_within_budget_kills_the_code_it_could_not_send(
    restricted_engine: Engine, owner_session: Session
) -> None:
    """The kill is the delivery function's, so every caller gets it.

    :param restricted_engine: The engine the send opens its session on
    :param owner_session: A session able to arrange and read fixture data
    :return: None
    """
    row_id = uuid.uuid4()
    now = dt.datetime.now(tz=dt.UTC)
    owner_session.execute(
        sa.text(
            "INSERT INTO otp_request (id, phone, otp_hash, purpose, issued_at, "
            "expires_at) VALUES (:id, :phone, 'x', 'otp', :now, :later)"
        ),
        {
            "id": row_id,
            "phone": KNOWN,
            "now": now,
            "later": now + dt.timedelta(minutes=5),
        },
    )
    owner_session.commit()
    _preload(
        owner_session,
        ScopeKind.SIGNUP_GLOBAL_DAILY,
        "global",
        SIGNUP_GLOBAL_DAILY,
        dt.timedelta(days=1),
    )

    result = send_within_budget(
        restricted_engine,
        NullGateway(),
        KNOWN,
        "body",
        "corr",
        budget=SendBudget.SIGNUP,
        otp_request_id=row_id,
    )

    owner_session.expire_all()
    consumed = owner_session.execute(
        sa.text("SELECT consumed_at FROM otp_request WHERE id = :id"),
        {"id": row_id},
    ).scalar_one()
    assert result is None
    assert consumed is not None


# ------------------------------------------------------ verify ceilings


def test_a_full_per_ip_failure_ceiling_refuses_even_the_right_code(
    client: TestClient, owner_session: Session, known_account: uuid.UUID
) -> None:
    """Past the ceiling the guess is not even checked [C-20].

    :param client: A client with a predictable code
    :param owner_session: A session able to arrange fixture data
    :param known_account: The account the number belongs to
    :return: None
    """
    client.post(
        "/v1/auth/otp", json={"phone": KNOWN}, headers={"X-Client-Address": "5.6.7.8"}
    )
    _preload(
        owner_session,
        ScopeKind.VERIFY_FAIL_IP_HOURLY,
        "5.6.7.0/24",
        VERIFY_FAILURES_PER_IP_HOURLY,
        dt.timedelta(hours=1),
    )

    refused = _verify(client, KNOWN, FIXED_CODE, "5.6.7.9")
    elsewhere = _verify(client, KNOWN, FIXED_CODE, "9.9.9.9")

    assert refused.status_code == 409  # type: ignore[attr-defined]
    error = refused.json()["error"]  # type: ignore[attr-defined]
    assert error["code"] == "TEMPORARILY_UNAVAILABLE"
    assert error["message_key"] == "auth.verify.temporarily_unavailable"
    # The refusal consumed nothing: the code still works from elsewhere.
    assert elsewhere.status_code == 200  # type: ignore[attr-defined]


def test_failed_verifies_are_counted_per_prefix_and_globally(
    client: TestClient, owner_session: Session, known_account: uuid.UUID
) -> None:
    """A wrong code spends the caller's failure allowance [C-20].

    :param client: A client with a predictable code
    :param owner_session: A session able to read counters back
    :param known_account: The account the number belongs to
    :return: None
    """
    client.post(
        "/v1/auth/otp", json={"phone": KNOWN}, headers={"X-Client-Address": "7.7.7.7"}
    )
    _verify(client, KNOWN, "000000", "7.7.7.7")

    owner_session.expire_all()
    counted = dict(
        owner_session.execute(
            sa.text(
                "SELECT scope_kind, sum(count) FROM rate_limit_counter "
                "WHERE scope_kind LIKE 'vf_%' GROUP BY scope_kind"
            )
        ).all()
    )
    assert counted == {"vf_ip_hour": 1, "vf_ip48_hour": 1, "vf_global_hour": 1}


def test_the_global_failure_ceiling_alerts_and_refuses(
    client: TestClient,
    owner_session: Session,
    known_account: uuid.UUID,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A country-wide guessing run reaches a human [C-20].

    :param client: A client with a predictable code
    :param owner_session: A session able to arrange fixture data
    :param known_account: The account the number belongs to
    :param caplog: The log capture
    :return: None
    """
    client.post(
        "/v1/auth/otp", json={"phone": KNOWN}, headers={"X-Client-Address": "8.8.8.8"}
    )
    _preload(
        owner_session,
        ScopeKind.VERIFY_FAIL_GLOBAL_HOURLY,
        "global",
        VERIFY_FAILURES_GLOBAL_HOURLY - 1,
        dt.timedelta(hours=1),
    )

    with caplog.at_level(logging.CRITICAL, logger="app.auth.ceilings"):
        wrong = _verify(client, KNOWN, "000000", "8.8.8.8")
        refused = _verify(client, KNOWN, FIXED_CODE, "8.8.4.4")

    assert wrong.status_code == 400  # type: ignore[attr-defined]
    assert refused.status_code == 409  # type: ignore[attr-defined]
    assert "vf_global_hour" in [getattr(r, "scope", None) for r in caplog.records]


# ------------------------------------------------------------ dead codes


def test_a_number_whose_codes_keep_dying_is_cooled_off(
    client: TestClient, owner_session: Session, known_account: uuid.UUID
) -> None:
    """At most so many codes per number per day may be guessed to death.

    Each dead code is five wrong guesses at a six-digit code, so the
    cap bounds the guesses one number can take in a day [C-20].

    :param client: A client with a predictable code
    :param owner_session: A session able to arrange fixture data
    :param known_account: The account the number belongs to
    :return: None
    """
    for _ in range(DEAD_CODES_PER_NUMBER_DAILY):
        client.post(
            "/v1/auth/otp",
            json={"phone": KNOWN},
            headers={"X-Client-Address": "10.0.0.1"},
        )
        for _attempt in range(5):
            _verify(client, KNOWN, "000000", "10.0.0.1")

    refused = client.post(
        "/v1/auth/otp", json={"phone": KNOWN}, headers={"X-Client-Address": "10.9.0.1"}
    )

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "TEMPORARILY_UNAVAILABLE"


def test_the_cool_off_answers_a_known_and_an_unknown_number_alike(
    client: TestClient, owner_session: Session, known_account: uuid.UUID
) -> None:
    """The cool-off is not an existence oracle [BR2.7].

    :param client: A client with a predictable code
    :param owner_session: A session able to arrange fixture data
    :param known_account: The account the number belongs to
    :return: None
    """
    for phone in (KNOWN, UNKNOWN):
        _preload(
            owner_session,
            ScopeKind.DEAD_CODE_NUMBER_DAILY,
            phone,
            DEAD_CODES_PER_NUMBER_DAILY,
            dt.timedelta(days=1),
        )

    known = client.post("/v1/auth/otp", json={"phone": KNOWN})
    unknown = client.post("/v1/auth/otp", json={"phone": UNKNOWN})

    assert known.status_code == unknown.status_code == 409
    assert known.content == unknown.content


def test_every_new_scope_kind_is_distinct_and_alerting_is_deliberate() -> None:
    """The new members are new counters, and only the globals alert.

    :return: None
    """
    from app.auth.ceilings import _ALERTING_SCOPES

    assert len({kind.value for kind in ScopeKind}) == len(list(ScopeKind))
    assert _ALERTING_SCOPES == {
        ScopeKind.GLOBAL_DAILY,
        ScopeKind.DEL_GLOBAL_DAILY,
        ScopeKind.SIGNUP_GLOBAL_DAILY,
        ScopeKind.VERIFY_FAIL_GLOBAL_HOURLY,
        ScopeKind.EMAIL_GLOBAL_DAILY,
    }
