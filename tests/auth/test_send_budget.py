"""Only a real SMS spends a daily send budget [PA-SEC-2].

Test-first under the ordering predicate: whether a request spends the
budget is knowable from the requirement, and a wrong answer is the
sign-in denial of service the finding describes -- anyone could drain
the day's budget with numbers nobody owns, because every unknown number
was charged for an SMS that was never sent.

**The shape that keeps this from becoming an existence oracle** is the
second half of the file: the budget is spent inside the deferred send,
after a response that was already identical for both numbers, so an
exhausted budget changes nothing a caller can observe -- the send is
skipped and the operator is told at CRITICAL instead.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Final

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.ceilings import (
    DEL_GLOBAL_DAILY,
    GLOBAL_DAILY,
    PER_NUMBER_HOURLY,
    ScopeKind,
    SendBudget,
)
from app.auth.client_address import TRUSTED_CLIENT_IP_HEADER_ENV
from app.auth.delivery import send_within_budget
from app.db.models import Account
from app.gateway.null import NullGateway

KNOWN: Final = "+8801711111111"
UNKNOWN: Final = "+8801799999999"

#: The two public routes that text a code, each with its own budget.
ROUTES: Final = [
    pytest.param("/v1/auth/otp", ScopeKind.GLOBAL_DAILY, GLOBAL_DAILY, id="sign-in"),
    pytest.param(
        "/account-deletion",
        ScopeKind.DEL_GLOBAL_DAILY,
        DEL_GLOBAL_DAILY,
        id="deletion",
    ),
]


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


@pytest.fixture
def sends(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record the number of every SMS the null gateway is asked to send.

    :param monkeypatch: The patcher
    :return: The list each send appends its number to
    """
    numbers: list[str] = []
    original = NullGateway.send

    def capture(
        self: NullGateway, number: str, message: str, correlation_id: str
    ) -> object:
        numbers.append(number)
        return original(self, number, message, correlation_id)

    monkeypatch.setattr(NullGateway, "send", capture)
    return numbers


def _budget(session: Session, kind: ScopeKind) -> int:
    """Read one daily budget's spend across every window.

    :param session: The session to read through
    :param kind: The global scope kind
    :return: The units spent
    """
    session.expire_all()
    return int(
        session.execute(
            sa.text(
                "SELECT coalesce(sum(count), 0) FROM rate_limit_counter "
                "WHERE scope_kind = :kind AND scope_value = 'global'"
            ),
            {"kind": kind.value},
        ).scalar_one()
    )


def _preload(session: Session, kind: ScopeKind, count: int) -> None:
    """Set today's budget spend directly, without issuing sends.

    :param session: The session to write through
    :param kind: The global scope kind
    :param count: The value to set
    :return: None
    """
    window = dt.datetime.now(tz=dt.UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    session.execute(
        sa.text(
            "INSERT INTO rate_limit_counter "
            "(id, scope_kind, scope_value, window_start, count) "
            "VALUES (gen_random_uuid(), :kind, 'global', :window, :count)"
        ),
        {"kind": kind.value, "window": window, "count": count},
    )
    session.commit()


# ---------------------------------------------------------------------------
# Who spends the budget.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("path", "kind", "limit"), ROUTES)
def test_unknown_numbers_spend_none_of_the_budget(
    api_client: TestClient,
    owner_session: Session,
    sends: list[str],
    path: str,
    kind: ScopeKind,
    limit: int,
) -> None:
    # The attack, at small scale: distinct unknown numbers, each
    # admitted by its own per-number scope. Before the fix every one
    # cost a unit of a budget only real SMS should cost.
    for index in range(PER_NUMBER_HOURLY + 2):
        response = api_client.post(path, json={"phone": f"+88017999{index:05d}"})
        assert response.status_code == 200

    assert sends == []
    assert _budget(owner_session, kind) == 0


@pytest.mark.parametrize(("path", "kind", "limit"), ROUTES)
def test_a_known_number_spends_one_unit_per_send(
    api_client: TestClient,
    owner_session: Session,
    known_account: uuid.UUID,
    sends: list[str],
    path: str,
    kind: ScopeKind,
    limit: int,
) -> None:
    # The other half: without it the test above passes against a
    # route that never spends the budget at all.
    api_client.post(path, json={"phone": KNOWN})
    api_client.post(path, json={"phone": KNOWN})

    assert sends == [KNOWN, KNOWN]
    assert _budget(owner_session, kind) == 2


def test_a_deletion_send_does_not_spend_the_sign_in_budget(
    api_client: TestClient,
    owner_session: Session,
    known_account: uuid.UUID,
) -> None:
    # NFR14.102's separation survives the move to send time.
    api_client.post("/account-deletion", json={"phone": KNOWN})

    assert _budget(owner_session, ScopeKind.GLOBAL_DAILY) == 0
    assert _budget(owner_session, ScopeKind.DEL_GLOBAL_DAILY) == 1


def test_signups_sms_spends_the_signup_budget_and_not_sign_ins(
    api_client: TestClient, owner_session: Session, sends: list[str]
) -> None:
    # Signup's cascade carries no request-path global scope because its
    # SMS spends a daily send budget at the send. Before PA-SEC-2 it
    # called the gateway directly and spent no budget at all; until
    # C-05 it spent SIGN-IN's, so a stranger signing up numbers could
    # lock every existing account out for the day.
    phone = "+8801733333333"
    response = api_client.post(
        "/v1/accounts",
        json={
            "phone": phone,
            "role": "student",
            "self_name": "Rahim",
            "address_house": "House 12",
            "address_road": "Road 5",
            "address_city": "Dhaka",
            "address_postcode": "1205",
        },
    )

    assert response.status_code == 201
    assert sends == [phone]
    assert _budget(owner_session, ScopeKind.SIGNUP_GLOBAL_DAILY) == 1
    assert _budget(owner_session, ScopeKind.GLOBAL_DAILY) == 0


# ---------------------------------------------------------------------------
# An exhausted budget: identical responses, a skipped send, an alert.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("path", "kind", "limit"), ROUTES)
def test_an_exhausted_budget_changes_no_response_and_skips_the_send(
    api_client: TestClient,
    owner_session: Session,
    known_account: uuid.UUID,
    sends: list[str],
    caplog: pytest.LogCaptureFixture,
    path: str,
    kind: ScopeKind,
    limit: int,
) -> None:
    _preload(owner_session, kind, limit)

    with caplog.at_level(logging.CRITICAL, logger="app.auth.delivery"):
        known = api_client.post(path, json={"phone": KNOWN})
        unknown = api_client.post(path, json={"phone": UNKNOWN})

    # Byte-identical, status and body: the budget's state is not an
    # existence oracle, because it is consulted after the response.
    assert known.status_code == unknown.status_code == 200
    assert known.content == unknown.content

    assert sends == [], "the send went out past an exhausted budget"
    skipped = [
        record
        for record in caplog.records
        if record.name == "app.auth.delivery" and record.levelno == logging.CRITICAL
    ]
    assert len(skipped) == 1
    assert skipped[0].scope == kind.value
    assert _budget(owner_session, kind) == limit, "a refused send kept its unit"

    # No log line anywhere carries either number.
    for record in caplog.records:
        rendered = record.getMessage() + repr(record.__dict__)
        assert KNOWN not in rendered
        assert UNKNOWN not in rendered


def test_send_within_budget_sends_while_the_budget_holds(
    restricted_engine: Engine, owner_session: Session, sends: list[str]
) -> None:
    result = send_within_budget(
        restricted_engine,
        NullGateway(),
        KNOWN,
        "body",
        "corr-1",
        budget=SendBudget.SIGN_IN,
    )

    assert result is not None
    assert sends == [KNOWN]
    assert _budget(owner_session, ScopeKind.GLOBAL_DAILY) == 1


def test_send_within_budget_skips_and_returns_none_when_exhausted(
    restricted_engine: Engine, owner_session: Session, sends: list[str]
) -> None:
    _preload(owner_session, ScopeKind.DEL_GLOBAL_DAILY, DEL_GLOBAL_DAILY)

    result = send_within_budget(
        restricted_engine,
        NullGateway(),
        KNOWN,
        "body",
        "corr-2",
        budget=SendBudget.DELETION,
    )

    assert result is None
    assert sends == []


# ---------------------------------------------------------------------------
# The per-IP bucket, end to end through the real app.
# ---------------------------------------------------------------------------


def test_the_trusted_header_chooses_the_ip_bucket_over_the_wire(
    api_client: TestClient,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TRUSTED_CLIENT_IP_HEADER_ENV, "X-Client-Address")

    for index, spoof in enumerate(["192.0.2.1", "192.0.2.2", "198.18.0.1"]):
        api_client.post(
            "/v1/auth/otp",
            json={"phone": f"+88017888{index:05d}"},
            headers={
                "X-Client-Address": f"203.0.113.{10 + index}",
                "X-Forwarded-For": spoof,
            },
        )

    owner_session.expire_all()
    rows = owner_session.execute(
        sa.text(
            "SELECT scope_value, count FROM rate_limit_counter WHERE scope_kind = :kind"
        ),
        {"kind": ScopeKind.IP_HOURLY.value},
    ).all()
    assert [(row.scope_value, row.count) for row in rows] == [("203.0.113.0/24", 3)]
