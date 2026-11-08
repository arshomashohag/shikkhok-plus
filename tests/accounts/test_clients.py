"""Which app an account uses, recorded where tokens are issued.

The headers are the client's own statement; anything that is not one of
the two platforms, or not a plain version string, is dropped rather
than stored, so the table can never become a place a client writes
something identifying [TC-3, D-37].
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.accounts.clients import parse_platform, parse_version, record_client
from app.auth.tokens import issue_pair
from app.db.models import Account

KNOWN = "+8801711111112"
T0 = dt.datetime(2026, 11, 1, 9, 0, tzinfo=dt.UTC)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("android", "android"),
        ("Web", "web"),
        ("  ANDROID ", "android"),
        ("ios", None),
        ("", None),
        (None, None),
    ],
)
def test_platform_is_one_of_two_or_nothing(
    raw: str | None, expected: str | None
) -> None:
    """Only the two platforms are recognised, case-insensitively.

    :param raw: The header value
    :param expected: The recognised platform
    :return: None
    """
    assert parse_platform(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.4.0", "1.4.0"),
        ("0.1.0+build.7", "0.1.0+build.7"),
        ("1.0-rc1", "1.0-rc1"),
        ("Pixel 7 / Android 16", None),
        ("x" * 33, None),
        ("", None),
        (None, None),
    ],
)
def test_version_is_plain_or_dropped(raw: str | None, expected: str | None) -> None:
    """A version with spaces, slashes or excess length is not stored.

    :param raw: The header value
    :param expected: What is stored
    :return: None
    """
    assert parse_version(raw) == expected


def _account(session: Session, phone: str | None = None) -> uuid.UUID:
    """Arrange one account.

    :param session: An arranging session
    :param phone: Its number, or a fresh one
    :return: Its id
    """
    record = Account(
        phone=phone or f"+88017{uuid.uuid4().int % 10**8:08d}",
        created_at=T0,
        activated_at=T0,
    )
    session.add(record)
    session.commit()
    return record.id


def _rows(session: Session, account_id: uuid.UUID) -> list[sa.Row[tuple[object, ...]]]:
    """Read an account's client rows.

    :param session: Any session
    :param account_id: The account
    :return: Its rows, by platform
    """
    return list(
        session.execute(
            sa.text(
                "SELECT platform, app_version, first_seen_at, last_seen_at "
                "FROM account_client WHERE account_id = :a ORDER BY platform"
            ),
            {"a": account_id},
        )
    )


def test_recording_twice_keeps_first_seen_and_moves_last_seen(
    restricted_session: Session, owner_session: Session
) -> None:
    """One row per platform; the second sighting updates it.

    :param restricted_session: The application's role
    :param owner_session: An arranging session
    :return: None
    """
    account = _account(owner_session)
    later = T0 + dt.timedelta(hours=3)

    record_client(restricted_session, account, "android", "1.0.0", now=T0)
    record_client(restricted_session, account, "android", "1.1.0", now=later)
    restricted_session.commit()

    (row,) = _rows(restricted_session, account)
    assert row.platform == "android"
    assert row.app_version == "1.1.0"
    assert row.first_seen_at == T0
    assert row.last_seen_at == later


def test_an_older_sighting_never_moves_last_seen_back(
    restricted_session: Session, owner_session: Session
) -> None:
    """Two refreshes landing out of order keep the later time.

    :param restricted_session: The application's role
    :param owner_session: An arranging session
    :return: None
    """
    account = _account(owner_session)
    later = T0 + dt.timedelta(hours=3)

    record_client(restricted_session, account, "web", None, now=later)
    record_client(restricted_session, account, "web", None, now=T0)
    restricted_session.commit()

    (row,) = _rows(restricted_session, account)
    assert row.last_seen_at == later


def test_a_missing_version_keeps_the_known_one(
    restricted_session: Session, owner_session: Session
) -> None:
    """A sighting without a version does not erase the last reported one.

    :param restricted_session: The application's role
    :param owner_session: An arranging session
    :return: None
    """
    account = _account(owner_session)

    record_client(restricted_session, account, "android", "2.0.0", now=T0)
    record_client(restricted_session, account, "android", None, now=T0)
    restricted_session.commit()

    (row,) = _rows(restricted_session, account)
    assert row.app_version == "2.0.0"


def test_no_header_records_nothing(
    restricted_session: Session, owner_session: Session
) -> None:
    """An older app build that sends no header is not guessed at.

    :param restricted_session: The application's role
    :param owner_session: An arranging session
    :return: None
    """
    account = _account(owner_session)

    assert record_client(restricted_session, account, None, "1.0.0") is None
    assert record_client(restricted_session, account, "ios", "1.0.0") is None
    restricted_session.commit()

    assert _rows(restricted_session, account) == []


def test_sign_in_records_the_app(
    api_client: TestClient,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finishing a sign-in with the headers records the platform.

    Since passwords [0032] a code yields a setup token, and the session
    is issued by ``POST /v1/auth/password/setup`` -- which records it.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param monkeypatch: The patcher
    :return: None
    """
    account = _account(owner_session, phone=KNOWN)
    sent: list[str] = []

    from app.gateway.null import NullGateway

    original = NullGateway.send

    def capture(
        self: NullGateway, number: str, message: str, correlation_id: str
    ) -> object:
        sent.append(message)
        return original(self, number, message, correlation_id)

    monkeypatch.setattr(NullGateway, "send", capture)
    assert api_client.post("/v1/auth/otp", json={"phone": KNOWN}).status_code == 200
    code = next(part for part in sent[0].split() if part.isdigit())

    verified = api_client.post(
        "/v1/auth/verify", json={"phone": KNOWN, "code": code}
    ).json()
    signed_in = api_client.post(
        "/v1/auth/password/setup",
        json={
            "token": verified["password_setup_token"],
            "password": "a long enough passphrase",
        },
        headers={"X-Client-Platform": "web", "X-Client-Version": "0.1.0"},
    )

    assert signed_in.status_code == 200, signed_in.text
    (row,) = _rows(owner_session, account)
    assert (row.platform, row.app_version) == ("web", "0.1.0")


def test_refresh_records_the_app_and_still_rotates(
    api_client: TestClient, owner_session: Session
) -> None:
    """``POST /v1/auth/refresh`` records the platform it was called from.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :return: None
    """
    account = _account(owner_session)
    pair = issue_pair(owner_session, account, correlation_id=str(uuid.uuid4()))
    owner_session.commit()

    rotated = api_client.post(
        "/v1/auth/refresh",
        json={"refresh_token": pair.refresh_token},
        headers={"X-Client-Platform": "android", "X-Client-Version": "1.2.3"},
    )

    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != pair.refresh_token
    (row,) = _rows(owner_session, account)
    assert (row.platform, row.app_version) == ("android", "1.2.3")


def test_refresh_without_the_header_records_nothing(
    api_client: TestClient, owner_session: Session
) -> None:
    """An app build predating the header still renews, unrecorded.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :return: None
    """
    account = _account(owner_session)
    pair = issue_pair(owner_session, account, correlation_id=str(uuid.uuid4()))
    owner_session.commit()

    rotated = api_client.post(
        "/v1/auth/refresh", json={"refresh_token": pair.refresh_token}
    )

    assert rotated.status_code == 200
    assert _rows(owner_session, account) == []
