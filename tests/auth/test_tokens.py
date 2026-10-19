"""The five-transition state machine, not a happy path.

**A client that refreshes normally behaves identically whether or not the
old token was invalidated.** That is the whole problem: reuse detection
degrades silently into non-rotating refresh tokens, and the happy path
cannot see it. Only a *replayed* token reveals the difference — and that
is the stolen-token case the control exists for.

The five transitions: rotate, replay refused, **family invalidated**,
hashed storage, expiry enforced.
"""

from __future__ import annotations

import datetime as dt
import uuid

import jwt
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import (
    ACCESS_TOKEN_LIFETIME,
    JWT_ACTIVE_KID_ENV,
    JWT_KEYS_ENV,
    issue_pair,
    rotate,
    verify_access_token,
)
from app.db.models import Account
from app.errors import AuthorizationError

CORRELATION = "test-correlation-id"

# RFC 7518 §3.2 sets a 32-byte minimum for HS256, and PyJWT warns below
# it. Short test keys would train that warning to be background noise,
# so the fixtures use realistic lengths -- the warning then still means
# something if a short key ever reaches a real environment.
FIRST_SECRET = "first-secret-padded-to-thirty-two-bytes-min"  # noqa: S105
SECOND_SECRET = "second-secret-padded-to-thirty-two-bytes"  # noqa: S105
ATTACKER_SECRET = "an-attackers-secret-also-long-enough-here"  # noqa: S105


@pytest.fixture(autouse=True)
def _secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install test keys: two valid verification keys, one active.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")
    monkeypatch.setenv(JWT_KEYS_ENV, f"k2:{SECOND_SECRET},k1:{FIRST_SECRET}")
    monkeypatch.setenv(JWT_ACTIVE_KID_ENV, "k2")


@pytest.fixture
def account(owner_session: Session) -> uuid.UUID:
    """Create an account to issue tokens for.

    :param owner_session: A session able to arrange fixture data
    :return: The account's id
    """
    record = Account(
        phone=f"+8801{uuid.uuid4().int % 10**9:09d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(record)
    owner_session.commit()
    return record.id


# ---------------------------------------------------------------------------
# THE STATE MACHINE. [BR4.1]
# ---------------------------------------------------------------------------


def test_a_refresh_rotates_and_issues_a_new_pair(
    restricted_session: Session, account: uuid.UUID
) -> None:
    first = issue_pair(restricted_session, account, CORRELATION)
    restricted_session.commit()

    second = rotate(restricted_session, first.refresh_token, CORRELATION)
    assert second.refresh_token != first.refresh_token
    assert second.family_id == first.family_id


def test_replaying_a_rotated_token_is_refused(
    restricted_session: Session, account: uuid.UUID
) -> None:
    first = issue_pair(restricted_session, account, CORRELATION)
    restricted_session.commit()
    rotate(restricted_session, first.refresh_token, CORRELATION)

    with pytest.raises(AuthorizationError):
        rotate(restricted_session, first.refresh_token, CORRELATION)


def test_replay_invalidates_the_whole_family_not_one_token(
    restricted_session: Session, account: uuid.UUID
) -> None:
    # THE TRANSITION THAT CARRIES THE RULE. Invalidating only the
    # presented token leaves the THIEF's token working and logs out the
    # victim, which inverts the control [BR4.1].
    first = issue_pair(restricted_session, account, CORRELATION)
    restricted_session.commit()
    second = rotate(restricted_session, first.refresh_token, CORRELATION)

    # The attacker replays the stolen, already-rotated token.
    with pytest.raises(AuthorizationError):
        rotate(restricted_session, first.refresh_token, CORRELATION)

    # The victim's CURRENT token must now be dead too.
    with pytest.raises(AuthorizationError):
        rotate(restricted_session, second.refresh_token, CORRELATION)


def test_reuse_detection_is_recorded(
    restricted_session: Session, account: uuid.UUID
) -> None:
    first = issue_pair(restricted_session, account, CORRELATION)
    restricted_session.commit()
    rotate(restricted_session, first.refresh_token, CORRELATION)
    with pytest.raises(AuthorizationError):
        rotate(restricted_session, first.refresh_token, CORRELATION)

    detected = restricted_session.execute(
        sa.text(
            "SELECT count(*) FROM refresh_token WHERE reuse_detected_at IS NOT NULL"
        )
    ).scalar_one()
    assert detected > 0

    events = {
        row[0]
        for row in restricted_session.execute(
            sa.text("SELECT event FROM auth_audit_log")
        )
    }
    assert "REFRESH_REUSE_DETECTED" in events


def test_refresh_tokens_are_stored_hashed(
    restricted_session: Session, account: uuid.UUID
) -> None:
    pair = issue_pair(restricted_session, account, CORRELATION)
    restricted_session.commit()

    stored = restricted_session.execute(
        sa.text("SELECT token_hash FROM refresh_token")
    ).scalar_one()
    assert stored != pair.refresh_token


def test_an_expired_refresh_token_is_refused(
    restricted_session: Session, account: uuid.UUID
) -> None:
    now = dt.datetime.now(tz=dt.UTC)
    pair = issue_pair(restricted_session, account, CORRELATION, now=now)
    restricted_session.commit()

    much_later = now + dt.timedelta(days=31)
    with pytest.raises(AuthorizationError):
        rotate(restricted_session, pair.refresh_token, CORRELATION, now=much_later)


def test_an_unknown_refresh_token_is_refused(
    restricted_session: Session,
) -> None:
    with pytest.raises(AuthorizationError):
        rotate(restricted_session, "not-a-real-token", CORRELATION)


# ---------------------------------------------------------------------------
# The access token. [BR4.2, BR4.3]
# ---------------------------------------------------------------------------


def test_an_access_token_verifies(
    restricted_session: Session, account: uuid.UUID
) -> None:
    pair = issue_pair(restricted_session, account, CORRELATION)
    assert verify_access_token(pair.access_token) == account


def test_a_fifteen_minute_expired_token_is_refused(
    restricted_session: Session, account: uuid.UUID
) -> None:
    now = dt.datetime.now(tz=dt.UTC)
    pair = issue_pair(restricted_session, account, CORRELATION, now=now)

    late = now + ACCESS_TOKEN_LIFETIME + dt.timedelta(seconds=1)
    with pytest.raises(AuthorizationError) as raised:
        verify_access_token(pair.access_token, now=late)
    assert raised.value.code == "ACCESS_TOKEN_EXPIRED"
    assert raised.value.status == 401


def test_the_token_carries_a_kid_header(
    restricted_session: Session, account: uuid.UUID
) -> None:
    pair = issue_pair(restricted_session, account, CORRELATION)
    assert jwt.get_unverified_header(pair.access_token)["kid"] == "k2"


def test_a_token_signed_under_the_other_key_still_verifies(
    restricted_session: Session, account: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    # THE POINT OF kid. Rotating the signing key without two valid
    # verification keys force-logs-out every holder of a 30-day refresh
    # token, at exactly the moment rotation is needed [BR4.3].
    monkeypatch.setenv(JWT_ACTIVE_KID_ENV, "k1")
    old = issue_pair(restricted_session, account, CORRELATION)

    monkeypatch.setenv(JWT_ACTIVE_KID_ENV, "k2")
    new = issue_pair(restricted_session, account, CORRELATION)

    assert verify_access_token(old.access_token) == account
    assert verify_access_token(new.access_token) == account


def test_a_token_signed_under_an_unknown_key_is_refused(
    restricted_session: Session, account: uuid.UUID
) -> None:
    forged = jwt.encode(
        {
            "sub": str(account),
            "exp": int(
                (dt.datetime.now(tz=dt.UTC) + dt.timedelta(hours=1)).timestamp()
            ),
        },
        ATTACKER_SECRET,
        algorithm="HS256",
        headers={"kid": "k9"},
    )
    with pytest.raises(AuthorizationError):
        verify_access_token(forged)


def test_the_access_token_carries_no_role_claim(
    restricted_session: Session, account: uuid.UUID
) -> None:
    # A lens or role baked into a 15-minute token is a CACHED ROLE by
    # another name, surviving an ownership change for its lifetime --
    # which is exactly what BR1.2 and BR1.3 forbid.
    pair = issue_pair(restricted_session, account, CORRELATION)
    claims = jwt.decode(pair.access_token, SECOND_SECRET, algorithms=["HS256"])
    assert not {"role", "lens", "lenses", "is_teacher"} & set(claims)


def test_the_access_token_carries_only_the_subject_and_times(
    restricted_session: Session, account: uuid.UUID
) -> None:
    pair = issue_pair(restricted_session, account, CORRELATION)
    claims = jwt.decode(pair.access_token, SECOND_SECRET, algorithms=["HS256"])
    assert set(claims) == {"sub", "iat", "exp"}


def test_a_tampered_token_is_refused(
    restricted_session: Session, account: uuid.UUID
) -> None:
    pair = issue_pair(restricted_session, account, CORRELATION)
    tampered = pair.access_token[:-4] + "AAAA"
    with pytest.raises(AuthorizationError):
        verify_access_token(tampered)
