"""No username reaches a log line, an audit row, a counter, a hold or a stranger.

[U1: BR8.4, NFR3.4, NFR3.3; FR9.3] Written FIRST: whether a child's
username leaves its owner is an authorization answer. A distinctive
sentinel name, in several casings, is driven through every username
path -- sign-up and its refusal (W1), the verify race and its
replacement (W2), sign-in by username, right, wrong and unknown (W3),
both lookups (W4, W5), a first choice and its refusal (W7), a rename,
its refusal and a case-only change (W8, W8a), deletion (W9) and the
purge (W10) -- with logging captured at DEBUG. Afterwards the sentinel,
in any casing, appears in no captured record (message or ``extra``), no
audit row, no counter row, no hold row, no text or email sent, and no
response body other than the owner's own ``MeResponse`` and
``UsernameChangeResponse``.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.logging_setup import STRUCTURED_FIELDS
from tests.accounts.conftest import auth_header, make_account
from tests.accounts.signup_support import submit_signup

PASSWORD = "a long enough passphrase"  # noqa: S105 -- a test value

#: The sentinel's stem; every name below contains it.
SENTINEL = "zq_sentinel"


def _body(phone: str, username: str) -> dict[str, Any]:
    """Build a signup body.

    :param phone: The number
    :param username: The username
    :return: The body
    """
    return {
        "phone": phone,
        "role": "student",
        "self_name": "Mitu",
        "address_house": "House 12",
        "address_road": "Road 5",
        "address_city": "Dhaka",
        "address_postcode": "1205",
        "username": username,
    }


def test_no_structured_log_field_carries_a_subject() -> None:
    """Neither ``username`` nor ``login`` is a log field [NFR3.4].

    :return: None
    """
    assert "username" not in STRUCTURED_FIELDS
    assert "login" not in STRUCTURED_FIELDS


def test_no_sentinel_username_leaves_its_owner(
    client: TestClient,
    owner_session: Session,
    outbound: list[tuple[str, str]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every username path, one run, nothing leaks [BR8.4, NFR3.4].

    :param client: A client against the restricted engine
    :param owner_session: An arranging session, and the reader
    :param outbound: The captured sends
    :param caplog: The log capture
    :return: None
    """
    caplog.set_level("DEBUG")
    strangers: list[str] = []
    owners: list[str] = []

    def keep(response: httpx.Response, *, owner: bool = False) -> httpx.Response:
        """File a response body as the owner's own, or as anyone's.

        :param response: The response
        :param owner: Whether it is the owner's own successful read
        :return: The response
        """
        (owners if owner and response.status_code == 200 else strangers).append(
            response.text
        )
        return response

    first, second = "+8801711990077", "+8801711990078"

    # W1: a refusal, then two drafts on one name (drafts reserve nothing).
    keep(submit_signup(client, _body(first, "zq_sentinel_77."))[0])
    draft_one, code_one = submit_signup(client, _body(first, "Zq_Sentinel_77"))
    draft_two, code_two = submit_signup(client, _body(second, "ZQ_SENTINEL_77"))
    keep(draft_one)
    keep(draft_two)

    # W2: the first verify takes it; the second loses, then replaces it.
    keep(client.post("/v1/auth/verify", json={"phone": first, "code": code_one}))
    keep(client.post("/v1/auth/verify", json={"phone": second, "code": code_two}))
    keep(
        client.post(
            "/v1/auth/verify",
            json={"phone": second, "code": code_two, "username": "zq_sentinel_78"},
        )
    )
    owner_session.expire_all()
    holder = owner_session.execute(
        sa.text("SELECT id FROM account WHERE phone = :p"), {"p": first}
    ).scalar_one()
    owner_session.execute(
        sa.text("UPDATE account SET password_hash = :h WHERE id = :id"),
        {"h": hash_password(PASSWORD), "id": holder},
    )
    owner_session.commit()

    # W4, W5: both lookups, every answer.
    for name in ("zq_sentinel_77", "zq_sentinel_77.", "zq_sentinel_99"):
        keep(client.post("/v1/accounts/username-availability", json={"username": name}))
    headers = auth_header(owner_session, holder)
    owner_session.commit()
    keep(
        client.post(
            "/v1/me/username-availability",
            json={"username": "zq_sentinel_78"},
            headers=headers,
        )
    )

    # W3: right, wrong and unknown.
    for login, password in (
        ("ZQ_SENTINEL_77", PASSWORD),
        ("zq_sentinel_77", "wrong-wrong-wrong"),
        ("zq_sentinel_79", PASSWORD),
    ):
        keep(
            client.post(
                "/v1/auth/password", json={"login": login, "password": password}
            )
        )

    # W8, its refusal, W8a; the owner's reads.
    keep(
        client.put(
            "/v1/me/username",
            json={"username": "zq_sentinel_80", "password": PASSWORD},
            headers=headers,
        ),
        owner=True,
    )
    keep(
        client.put(
            "/v1/me/username",
            json={"username": "zq_sentinel_81", "password": PASSWORD},
            headers=headers,
        )
    )
    keep(
        client.put(
            "/v1/me/username",
            json={"username": "ZQ_SENTINEL_80", "password": PASSWORD},
            headers=headers,
        ),
        owner=True,
    )
    keep(client.get("/v1/me", headers=headers), owner=True)

    # W7 and its refusal.
    chooser = make_account(owner_session)
    chooser_headers = auth_header(owner_session, chooser)
    owner_session.commit()
    keep(
        client.put(
            "/v1/me/username",
            json={"username": "zq_sentinel_78"},
            headers=chooser_headers,
        )
    )
    keep(
        client.put(
            "/v1/me/username",
            json={"username": "zq_sentinel_82"},
            headers=chooser_headers,
        ),
        owner=True,
    )

    # W9: the holder deletes itself.
    keep(client.request("DELETE", "/v1/me", headers=headers))

    owner_session.expire_all()
    tables = {
        table: " ".join(
            str(tuple(row))
            for row in owner_session.execute(
                sa.text(f"SELECT * FROM {table}")  # noqa: S608 -- literal names
            ).all()
        ).lower()
        for table in ("auth_audit_log", "rate_limit_counter", "username_hold")
    }
    holds_before_purge = tables["username_hold"]

    # W10: the purge, far in the future, leaves nothing to read.
    from app.governance.commands import purge_expired

    purge_expired(owner_session, now=dt.datetime.now(tz=dt.UTC) + dt.timedelta(days=90))
    remaining = owner_session.execute(
        sa.text("SELECT count(*) FROM username_hold")
    ).scalar_one()

    server_records = [r for r in caplog.records if not r.name.startswith("httpx")]
    logged = "".join(r.getMessage() + str(vars(r)) for r in server_records).lower()
    sent = " ".join(body for _, body in outbound).lower()

    assert holds_before_purge, "the run must have placed holds"
    assert remaining == 0
    assert strangers and owners
    assert SENTINEL not in logged
    assert SENTINEL not in sent
    for table, text in tables.items():
        assert SENTINEL not in text, table
    for body in strangers:
        assert SENTINEL not in body.lower(), body
    # The owner's own reads are the one place it may appear.
    assert any(SENTINEL in body.lower() for body in owners)
    # Counter values are keyed: not even the unkeyed hash of a key is there.
    for key in ("zq_sentinel_77", "zq_sentinel_79"):
        unkeyed = hashlib.sha256(key.encode()).hexdigest()[:62]
        assert unkeyed not in tables["rate_limit_counter"], key
