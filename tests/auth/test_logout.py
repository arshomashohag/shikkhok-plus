"""Sessions end server-side: logout, sign out everywhere, a family cap.

Before this, sign-out cleared local state only and a refresh family
lived for as long as it kept rotating (audit C-21). A token copied from
a shared phone or a lost device kept access to children's records
indefinitely, and nothing the real owner did could end it.

Written before the implementation, because every assertion here is an
authorization answer: a logout that revoked only the presented token, or
only one family, would pass a happy-path test and leave the copied
token working -- the stolen-token case inverted, exactly as the reuse
detector's docstring warns.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import uuid
from collections.abc import Iterator

import jwt
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import (
    FAMILY_LIFETIME,
    JWT_ACTIVE_KID_ENV,
    JWT_KEYS_ENV,
    REFRESH_TOKEN_LIFETIME,
    issue_pair,
    revoke_all_families,
    revoke_family,
    rotate,
    verify_access_token,
)
from app.db.models import Account
from app.errors import AuthorizationError

CORRELATION = "test-correlation-id"
T0 = dt.datetime(2026, 11, 2, 9, 0, tzinfo=dt.UTC)
SECRET = "logout-suite-secret-padded-to-thirty-two-bytes"  # noqa: S105
HMAC_KEY = "test-only-hmac-key"


@pytest.fixture(autouse=True)
def _secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install the keys every token operation reads.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, HMAC_KEY)
    monkeypatch.setenv(JWT_KEYS_ENV, f"k1:{SECRET}")
    monkeypatch.setenv(JWT_ACTIVE_KID_ENV, "k1")


@pytest.fixture
def client(restricted_engine: Engine) -> Iterator[TestClient]:
    """Build a client whose app uses the restricted test engine.

    :param restricted_engine: The non-superuser engine
    :return: A context manager yielding the client
    """
    from app.main import create_app

    app = create_app()
    app.state.engine = restricted_engine
    with TestClient(app) as test_client:
        yield test_client


def _account(session: Session) -> uuid.UUID:
    """Create one account with a unique number.

    :param session: An arranging session
    :return: The account id
    """
    record = Account(
        phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    session.commit()
    return record.id


def _refresh(client: TestClient, token: str) -> int:
    """Present one refresh token and return the status.

    :param client: The test client
    :param token: The refresh token
    :return: The HTTP status
    """
    return client.post("/v1/auth/refresh", json={"refresh_token": token}).status_code


def _audit_events(session: Session, account_id: uuid.UUID) -> list[str]:
    """Read one account's audit events, oldest first.

    :param session: A session able to read the audit log
    :param account_id: The account
    :return: The event names
    """
    session.expire_all()
    return list(
        session.execute(
            sa.text(
                "SELECT event FROM auth_audit_log WHERE account_id = :id "
                "ORDER BY occurred_at, event"
            ),
            {"id": account_id},
        ).scalars()
    )


# --------------------------------------------------------------------- logout


def test_logout_revokes_the_whole_family(
    client: TestClient, owner_session: Session, restricted_session: Session
) -> None:
    """Every token of the family stops working, not just the one presented.

    :param client: A client against the restricted engine
    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    account_id = _account(owner_session)
    first = issue_pair(restricted_session, account_id, CORRELATION)
    restricted_session.commit()
    rotated = client.post(
        "/v1/auth/refresh", json={"refresh_token": first.refresh_token}
    ).json()

    response = client.post(
        "/v1/auth/logout", json={"refresh_token": first.refresh_token}
    )

    assert response.status_code == 204
    assert response.content == b""
    # The LIVE successor dies too: logging out with an old token still
    # ends the session that token started.
    assert _refresh(client, rotated["refresh_token"]) == 401
    assert "LOGGED_OUT" in _audit_events(owner_session, account_id)


def test_logout_leaves_the_accounts_other_families_alone(
    client: TestClient, owner_session: Session, restricted_session: Session
) -> None:
    """Signing out of one device is not signing out of all of them.

    :param client: A client against the restricted engine
    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    account_id = _account(owner_session)
    phone = issue_pair(restricted_session, account_id, CORRELATION)
    laptop = issue_pair(restricted_session, account_id, CORRELATION)
    restricted_session.commit()

    client.post("/v1/auth/logout", json={"refresh_token": phone.refresh_token})

    assert _refresh(client, phone.refresh_token) == 401
    assert _refresh(client, laptop.refresh_token) == 200


def test_logout_answers_identically_for_any_token(
    client: TestClient, owner_session: Session, restricted_session: Session
) -> None:
    """A logout never says whether the token it was given was real.

    Idempotent too: a second logout with the same token is the same 204,
    so a client retrying a lost response is never shown an error.

    :param client: A client against the restricted engine
    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    account_id = _account(owner_session)
    pair = issue_pair(restricted_session, account_id, CORRELATION)
    restricted_session.commit()

    real = client.post("/v1/auth/logout", json={"refresh_token": pair.refresh_token})
    again = client.post("/v1/auth/logout", json={"refresh_token": pair.refresh_token})
    bogus = client.post(
        "/v1/auth/logout", json={"refresh_token": "never-issued-but-well-formed"}
    )

    assert real.status_code == again.status_code == bogus.status_code == 204
    assert real.content == again.content == bogus.content == b""


def test_a_revoked_token_is_not_reported_as_reuse(
    client: TestClient, owner_session: Session, restricted_session: Session
) -> None:
    """Presenting a logged-out token is refused, and is not an attack.

    Logged as reuse it would page the operator every time a signed-out
    phone woke up and tried its old token.

    :param client: A client against the restricted engine
    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    account_id = _account(owner_session)
    pair = issue_pair(restricted_session, account_id, CORRELATION)
    restricted_session.commit()
    client.post("/v1/auth/logout", json={"refresh_token": pair.refresh_token})

    assert _refresh(client, pair.refresh_token) == 401
    assert "REFRESH_REUSE_DETECTED" not in _audit_events(owner_session, account_id)


# ----------------------------------------------------------------- logout-all


def test_logout_all_revokes_every_family_of_the_caller_only(
    client: TestClient, owner_session: Session, restricted_session: Session
) -> None:
    """Sign out everywhere ends this account's sessions and nobody else's.

    :param client: A client against the restricted engine
    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    mine = _account(owner_session)
    theirs = _account(owner_session)
    phone = issue_pair(restricted_session, mine, CORRELATION)
    laptop = issue_pair(restricted_session, mine, CORRELATION)
    other = issue_pair(restricted_session, theirs, CORRELATION)
    restricted_session.commit()

    response = client.post(
        "/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {phone.access_token}"},
    )

    assert response.status_code == 204
    assert _refresh(client, phone.refresh_token) == 401
    assert _refresh(client, laptop.refresh_token) == 401
    assert _refresh(client, other.refresh_token) == 200
    assert "LOGGED_OUT_EVERYWHERE" in _audit_events(owner_session, mine)


def test_logout_all_requires_an_access_token(client: TestClient) -> None:
    """No token, no sign-out-everywhere: it names whose sessions end.

    :param client: A client against the restricted engine
    :return: None
    """
    assert client.post("/v1/auth/logout-all").status_code == 401


def test_the_service_functions_revoke_and_commit(
    owner_session: Session, restricted_session: Session
) -> None:
    """Both revocations work below the route, in their own transaction.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    account_id = _account(owner_session)
    one = issue_pair(restricted_session, account_id, CORRELATION, now=T0)
    two = issue_pair(restricted_session, account_id, CORRELATION, now=T0)
    restricted_session.commit()

    revoke_family(restricted_session, one.refresh_token, CORRELATION, now=T0)
    with pytest.raises(AuthorizationError):
        rotate(restricted_session, one.refresh_token, CORRELATION, now=T0)
    restricted_session.rollback()
    rotate(restricted_session, two.refresh_token, CORRELATION, now=T0)

    revoke_all_families(restricted_session, account_id, CORRELATION, now=T0)
    owner_session.expire_all()
    live = owner_session.execute(
        sa.text(
            "SELECT count(*) FROM refresh_token "
            "WHERE account_id = :id AND revoked_at IS NULL"
        ),
        {"id": account_id},
    ).scalar_one()
    assert live == 0


# ------------------------------------------------------------ family lifetime


def test_rotation_cannot_extend_a_family_past_its_absolute_lifetime(
    owner_session: Session, restricted_session: Session
) -> None:
    """A family ends a fixed time after it began, however often it rotates.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    account_id = _account(owner_session)
    pair = issue_pair(restricted_session, account_id, CORRELATION, now=T0)
    restricted_session.commit()

    moment = T0
    step = REFRESH_TOKEN_LIFETIME - dt.timedelta(days=1)
    while moment + step < T0 + FAMILY_LIFETIME:
        moment += step
        pair = rotate(restricted_session, pair.refresh_token, CORRELATION, now=moment)

    owner_session.expire_all()
    latest = owner_session.execute(
        sa.text("SELECT max(expires_at) FROM refresh_token WHERE family_id = :family"),
        {"family": pair.family_id},
    ).scalar_one()
    assert latest == T0 + FAMILY_LIFETIME

    with pytest.raises(AuthorizationError):
        rotate(
            restricted_session,
            pair.refresh_token,
            CORRELATION,
            now=T0 + FAMILY_LIFETIME,
        )


def test_a_family_from_before_the_cap_starts_at_its_oldest_token(
    owner_session: Session, restricted_session: Session
) -> None:
    """A row written before ``family_started_at`` existed is still capped.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    account_id = _account(owner_session)
    pair = issue_pair(restricted_session, account_id, CORRELATION, now=T0)
    restricted_session.commit()
    owner_session.execute(
        sa.text(
            "UPDATE refresh_token SET family_started_at = NULL "
            "WHERE family_id = :family"
        ),
        {"family": pair.family_id},
    )
    owner_session.commit()

    late = T0 + FAMILY_LIFETIME - dt.timedelta(days=1)
    owner_session.execute(
        sa.text(
            "UPDATE refresh_token SET expires_at = :late WHERE family_id = :family"
        ),
        {"late": late + dt.timedelta(days=5), "family": pair.family_id},
    )
    owner_session.commit()

    successor = rotate(restricted_session, pair.refresh_token, CORRELATION, now=late)

    owner_session.expire_all()
    expires = owner_session.execute(
        sa.text(
            "SELECT expires_at FROM refresh_token WHERE family_id = :f "
            "ORDER BY issued_at DESC LIMIT 1"
        ),
        {"f": successor.family_id},
    ).scalar_one()
    assert expires == T0 + FAMILY_LIFETIME


# ------------------------------------------------------------- L-02 hashing


def test_new_refresh_tokens_are_stored_under_a_keyless_digest(
    owner_session: Session, restricted_session: Session
) -> None:
    """Rotating the OTP key no longer logs everyone out [L-02].

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    account_id = _account(owner_session)
    pair = issue_pair(restricted_session, account_id, CORRELATION, now=T0)
    restricted_session.commit()

    owner_session.expire_all()
    stored = owner_session.execute(
        sa.text("SELECT token_hash FROM refresh_token WHERE family_id = :f"),
        {"f": pair.family_id},
    ).scalar_one()
    assert stored == hashlib.sha256(pair.refresh_token.encode()).hexdigest()


def test_a_token_stored_under_the_old_digest_still_rotates(
    owner_session: Session, restricted_session: Session
) -> None:
    """Nobody is logged out by the digest change [L-02].

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    account_id = _account(owner_session)
    pair = issue_pair(restricted_session, account_id, CORRELATION, now=T0)
    restricted_session.commit()
    legacy = hmac.new(
        HMAC_KEY.encode(), pair.refresh_token.encode(), hashlib.sha256
    ).hexdigest()
    owner_session.execute(
        sa.text("UPDATE refresh_token SET token_hash = :h WHERE family_id = :f"),
        {"h": legacy, "f": pair.family_id},
    )
    owner_session.commit()

    successor = rotate(
        restricted_session,
        pair.refresh_token,
        CORRELATION,
        now=T0 + dt.timedelta(minutes=1),
    )

    assert successor.family_id == pair.family_id


# ------------------------------------------------------------- L-03 claims


def test_an_access_token_carries_issuer_and_audience(
    owner_session: Session, restricted_session: Session
) -> None:
    """``iss`` is bound to the environment and ``aud`` to this API [L-03].

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    account_id = _account(owner_session)
    pair = issue_pair(restricted_session, account_id, CORRELATION)

    claims = jwt.decode(pair.access_token, options={"verify_signature": False})

    assert claims["aud"] == "shikkhokplus-api"
    assert claims["iss"].startswith("shikkhokplus-")
    assert verify_access_token(pair.access_token) == account_id


def test_a_token_minted_for_another_environment_is_refused(
    owner_session: Session,
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A staging token does not open production, even under one key.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :param monkeypatch: The patcher
    :return: None
    """
    account_id = _account(owner_session)
    monkeypatch.setenv("SHIKKHOKPLUS_ENVIRONMENT", "staging")
    pair = issue_pair(restricted_session, account_id, CORRELATION)
    monkeypatch.setenv("SHIKKHOKPLUS_ENVIRONMENT", "production")

    with pytest.raises(AuthorizationError):
        verify_access_token(pair.access_token)


def test_a_token_without_issuer_or_audience_is_still_accepted() -> None:
    """Tokens signed before the claims existed survive the deploy [L-03].

    :return: None
    """
    account_id = uuid.uuid4()
    now = dt.datetime.now(tz=dt.UTC)
    token = jwt.encode(
        {
            "sub": str(account_id),
            "iat": int(now.timestamp()),
            "exp": int((now + dt.timedelta(minutes=5)).timestamp()),
        },
        SECRET,
        algorithm="HS256",
        headers={"kid": "k1"},
    )

    assert verify_access_token(token) == account_id


def test_a_wrong_audience_is_refused() -> None:
    """A token for another audience under our key is not ours [L-03].

    :return: None
    """
    now = dt.datetime.now(tz=dt.UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": "someone-else",
            "iat": int(now.timestamp()),
            "exp": int((now + dt.timedelta(minutes=5)).timestamp()),
        },
        SECRET,
        algorithm="HS256",
        headers={"kid": "k1"},
    )

    with pytest.raises(AuthorizationError):
        verify_access_token(token)


def test_a_short_signing_key_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """HS256 below 32 bytes is refused outright [L-03, RFC 7518 3.2].

    :param monkeypatch: The patcher
    :return: None
    """
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": 0},
        SECRET,
        algorithm="HS256",
        headers={"kid": "k1"},
    )
    monkeypatch.setenv(JWT_KEYS_ENV, "k1:too-short")

    with pytest.raises(RuntimeError, match="32"):
        verify_access_token(token)
