"""The deletion route's code step has sign-in's guessing controls [SEC-6].

``POST /account-deletion`` with a code used to call ``otp.verify``
bare: no /64, /48 or global failed-verify ceiling and no dead-code
cool-off, so the route that destroys data had the weakest guessing
controls in the product. It now goes through ``check_verify_allowed``,
``record_verify_failure`` and ``record_dead_code`` as
``POST /v1/auth/verify`` does.

Written to the authorization predicate [team: Testing Posture]: whether
a guess is even checked is knowable from the counters alone, and a
wrong answer lets a guesser at the one irreversible action.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from typing import Final

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.ceilings import (
    DEAD_CODES_PER_NUMBER_DAILY,
    DEL_PER_NUMBER_HOURLY,
    VERIFY_FAILURES_PER_IP_HOURLY,
    ScopeKind,
)
from app.auth.client_address import TRUSTED_CLIENT_IP_HEADER_ENV
from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.otp import ATTEMPT_CEILING
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV
from app.config import ENVIRONMENT_ENV
from app.gateway.outbox import OUTBOX_FORCE_ENV
from tests.governance.conftest import PopulatedSeat

HEADER: Final = "X-Client-Address"


@pytest.fixture
def client(
    restricted_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Build a client whose caller address is a header and codes are readable.

    :param restricted_engine: The non-superuser engine
    :param monkeypatch: The patcher
    :return: A context manager yielding the client
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")
    monkeypatch.setenv(JWT_KEYS_ENV, "k1:test-signing-key-padded-to-thirty-two")
    monkeypatch.setenv(JWT_ACTIVE_KID_ENV, "k1")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_APP_HASH", "AAAAAAAAAAA")
    monkeypatch.setenv(ENVIRONMENT_ENV, "test")
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "1")
    monkeypatch.setenv(TRUSTED_CLIENT_IP_HEADER_ENV, HEADER)

    from app.main import create_app

    app = create_app()
    app.state.engine = restricted_engine
    with TestClient(app) as test_client:
        yield test_client


def _current_code(session: Session, phone: str) -> str:
    """Read back the latest code issued for a number, from the outbox.

    :param session: The session to read through
    :param phone: The number a code was sent to
    :return: The six-digit code
    """
    message = session.execute(
        sa.text(
            "SELECT message FROM staging_sms_outbox WHERE phone = :phone "
            "ORDER BY recorded_at DESC LIMIT 1"
        ),
        {"phone": phone},
    ).scalar_one()
    return next(part for part in str(message).split() if part.isdigit())


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


def _account_exists(session: Session, phone: str) -> bool:
    """Say whether an account still holds a number.

    :param session: A session able to read accounts
    :param phone: The number
    :return: True while the account is there
    """
    session.expire_all()
    return bool(
        session.execute(
            sa.text("SELECT count(*) FROM account WHERE phone = :p"), {"p": phone}
        ).scalar_one()
    )


def _preload_per_ip(session: Session, prefix: str, count: int) -> None:
    """Fill one /24's failed-verify counter for the current hour.

    :param session: The session to write through
    :param prefix: The /24, as the counter stores it
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
        {
            "kind": ScopeKind.VERIFY_FAIL_IP_HOURLY.value,
            "value": prefix,
            "window": start,
            "count": count,
        },
    )
    session.commit()


def test_a_wrong_deletion_code_counts_against_the_network_ceilings(
    client: TestClient, owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """A guess here spends the same allowance a sign-in guess does.

    :param client: The test client
    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    phone = populated_seat.student_phone
    client.post("/account-deletion", json={"phone": phone}, headers={HEADER: "9.1.1.1"})

    wrong = client.post(
        "/account-deletion",
        json={"phone": phone, "code": "000000"},
        headers={HEADER: "9.1.1.1"},
    )

    assert wrong.status_code == 400
    counted = _counts(owner_session)
    assert counted.get("vf_ip_hour") == 1
    assert counted.get("vf_ip48_hour") == 1
    assert counted.get("vf_global_hour") == 1


def test_a_full_failure_ceiling_refuses_even_the_right_code(
    client: TestClient, owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """Past the ceiling the code is not checked, and nothing is deleted.

    :param client: The test client
    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    phone = populated_seat.student_phone
    client.post("/account-deletion", json={"phone": phone}, headers={HEADER: "9.2.2.2"})
    code = _current_code(owner_session, phone)
    _preload_per_ip(owner_session, "9.2.2.0/24", VERIFY_FAILURES_PER_IP_HOURLY)

    refused = client.post(
        "/account-deletion",
        json={"phone": phone, "code": code},
        headers={HEADER: "9.2.2.3"},
    )

    assert refused.status_code == 409
    error = refused.json()["error"]
    assert error["code"] == "TEMPORARILY_UNAVAILABLE"
    assert error["message_key"] == "auth.verify.temporarily_unavailable"
    assert _account_exists(owner_session, phone)

    # The refusal consumed nothing: the code still works elsewhere.
    elsewhere = client.post(
        "/account-deletion",
        json={"phone": phone, "code": code},
        headers={HEADER: "9.3.3.3"},
    )
    assert elsewhere.status_code == 200, elsewhere.text
    assert not _account_exists(owner_session, phone)


def test_the_form_shows_the_ceiling_in_words(
    client: TestClient, owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """The page explains a ceiling refusal rather than calling it invalid.

    :param client: The test client
    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    phone = populated_seat.student_phone
    _preload_per_ip(owner_session, "9.4.4.0/24", VERIFY_FAILURES_PER_IP_HOURLY)

    page = client.post(
        "/account-deletion",
        data={"phone": phone, "code": "123456"},
        headers={HEADER: "9.4.4.4"},
    )

    assert page.status_code == 409
    assert "Too many wrong codes" in page.text
    assert _account_exists(owner_session, phone)


def test_a_deletion_code_guessed_to_death_counts_toward_the_cool_off(
    client: TestClient, owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """A dead deletion code counts against its number like a sign-in one.

    :param client: The test client
    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    phone = populated_seat.student_phone
    client.post("/account-deletion", json={"phone": phone}, headers={HEADER: "9.5.5.5"})
    for _ in range(ATTEMPT_CEILING):
        client.post(
            "/account-deletion",
            json={"phone": phone, "code": "000000"},
            headers={HEADER: "9.5.5.5"},
        )

    assert _counts(owner_session).get("dead_number_day") == 1


def _guess_codes_to_death(
    client: TestClient, phone: str, rounds: int, address: str
) -> None:
    """Request a deletion code and guess it to death, ``rounds`` times.

    :param client: The test client
    :param phone: The number codes are requested for
    :param rounds: How many codes to kill
    :param address: The caller address every request comes from
    :return: None
    """
    for _ in range(rounds):
        requested = client.post(
            "/account-deletion", json={"phone": phone}, headers={HEADER: address}
        )
        assert requested.status_code == 200, requested.text
        for _attempt in range(ATTEMPT_CEILING):
            client.post(
                "/account-deletion",
                json={"phone": phone, "code": "000000"},
                headers={HEADER: address},
            )


def test_a_number_whose_deletion_codes_died_is_refused_a_new_one(
    client: TestClient, owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """The cool-off refuses a deletion code, alike for known and unknown.

    Recording dead codes without ever reading the count on this route let
    a guesser keep taking fresh codes at the one irreversible action
    [C-20, SEC-6]. The refusal must also say nothing about whether the
    number holds an account [BR2.7], and it must come from the cool-off
    rather than from deletion's own per-number cascade, which still has
    room for another code this hour -- so the refused request consumes
    no deletion allowance.

    :param client: The test client
    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    known = populated_seat.student_phone
    unknown = "+8801799999999"
    for index, phone in enumerate((known, unknown)):
        _guess_codes_to_death(
            client, phone, DEAD_CODES_PER_NUMBER_DAILY, f"9.6.{index}.1"
        )
    # Deletion's own per-number cascade would still allow this request,
    # so a refusal can only be the cool-off's.
    assert DEAD_CODES_PER_NUMBER_DAILY < DEL_PER_NUMBER_HOURLY
    before = _counts(owner_session)

    refusals = [
        client.post(
            "/account-deletion", json={"phone": phone}, headers={HEADER: "9.7.7.7"}
        )
        for phone in (known, unknown)
    ]

    for refused in refusals:
        assert refused.status_code == 409
        assert refused.json()["error"]["message_key"] == (
            "auth.otp.temporarily_unavailable"
        )
    assert refusals[0].content == refusals[1].content
    after = _counts(owner_session)
    assert after.get("del_number_hour") == before.get("del_number_hour")
    assert after.get("del_ip_hour") == before.get("del_ip_hour")
    assert _account_exists(owner_session, known)
