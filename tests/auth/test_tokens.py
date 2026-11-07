"""The five-transition state machine, not a happy path.

**A client that refreshes normally behaves identically whether or not the
old token was invalidated.** That is the whole problem: reuse detection
degrades silently into non-rotating refresh tokens, and the happy path
cannot see it. Only a *replayed* token reveals the difference — and that
is the stolen-token case the control exists for.

The five transitions: rotate, replay refused, **family invalidated**,
hashed storage, expiry enforced.

**And one exception to replay, bounded on every side** [PA-SEC-4]: the
immediately previous token, re-presented within the grace window while
its successor is unused, is a retry after a lost response rather than a
replay. Every replay test below therefore replays OUTSIDE that window,
and the grace section asserts each edge of it.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
import uuid

import jwt
import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import (
    ACCESS_TOKEN_LIFETIME,
    JWT_ACTIVE_KID_ENV,
    JWT_AUDIENCE,
    JWT_KEYS_ENV,
    REFRESH_GRACE_WINDOW,
    TokenPair,
    issue_pair,
    rotate,
    verify_access_token,
)
from app.db.models import Account
from app.errors import AuthorizationError

CORRELATION = "test-correlation-id"

#: The moment every timed test in this file starts from.
T0 = dt.datetime(2026, 11, 2, 9, 0, tzinfo=dt.UTC)

#: When the first token of a family is rotated in the timed tests.
ROTATED = T0 + dt.timedelta(seconds=1)

#: Comfortably past the grace window, so a re-presentation is a replay.
LATER = ROTATED + REFRESH_GRACE_WINDOW + dt.timedelta(seconds=1)

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
        phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
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
    first = issue_pair(restricted_session, account, CORRELATION, now=T0)
    restricted_session.commit()
    rotate(restricted_session, first.refresh_token, CORRELATION, now=ROTATED)

    with pytest.raises(AuthorizationError):
        rotate(restricted_session, first.refresh_token, CORRELATION, now=LATER)


def test_replay_invalidates_the_whole_family_not_one_token(
    restricted_session: Session, account: uuid.UUID
) -> None:
    # THE TRANSITION THAT CARRIES THE RULE. Invalidating only the
    # presented token leaves the THIEF's token working and logs out the
    # victim, which inverts the control [BR4.1].
    first = issue_pair(restricted_session, account, CORRELATION, now=T0)
    restricted_session.commit()
    second = rotate(restricted_session, first.refresh_token, CORRELATION, now=ROTATED)

    # The attacker replays the stolen, already-rotated token.
    with pytest.raises(AuthorizationError):
        rotate(restricted_session, first.refresh_token, CORRELATION, now=LATER)

    # The victim's CURRENT token must now be dead too.
    with pytest.raises(AuthorizationError):
        rotate(restricted_session, second.refresh_token, CORRELATION, now=LATER)


def test_reuse_detection_is_recorded(
    restricted_session: Session, account: uuid.UUID
) -> None:
    first = issue_pair(restricted_session, account, CORRELATION, now=T0)
    restricted_session.commit()
    rotate(restricted_session, first.refresh_token, CORRELATION, now=ROTATED)
    with pytest.raises(AuthorizationError):
        rotate(restricted_session, first.refresh_token, CORRELATION, now=LATER)

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
# THE GRACE WINDOW. [PA-SEC-4]
#
# On a flaky mobile network the server can commit a rotation whose
# response never arrives; the client retries with the token it still
# holds. Without a window that retry IS a replay, and the person is
# logged out of a working session by their own network. Test-first:
# every edge is knowable from the requirement, and a wrong answer is an
# authorization error in one direction or the other.
# ---------------------------------------------------------------------------


def _family(session: Session, family_id: uuid.UUID) -> list[sa.Row[tuple[object, ...]]]:
    """Read every row of one token family, oldest first.

    :param session: The session to read through
    :param family_id: The family
    :return: The rows
    """
    session.expire_all()
    return list(
        session.execute(
            sa.text(
                "SELECT id, issued_at, expires_at, rotated_at, reuse_detected_at "
                "FROM refresh_token WHERE family_id = :family ORDER BY issued_at"
            ),
            {"family": family_id},
        ).all()
    )


def _live(session: Session, family_id: uuid.UUID, at: dt.datetime) -> int:
    """Count the family's tokens that a refresh could still spend.

    :param session: The session to read through
    :param family_id: The family
    :param at: The moment to judge expiry against
    :return: How many are live
    """
    return sum(
        1
        for row in _family(session, family_id)
        if row.rotated_at is None and row.expires_at > at
    )


def _events(session: Session) -> list[str]:
    """Read every audit event.

    :param session: The session to read through
    :return: The event names
    """
    return [
        row[0] for row in session.execute(sa.text("SELECT event FROM auth_audit_log"))
    ]


def _rotated_once(session: Session, account: uuid.UUID) -> tuple[TokenPair, TokenPair]:
    """Issue a pair at T0 and rotate it at ROTATED.

    :param session: The session to work through
    :param account: The account
    :return: The original pair and the pair its rotation issued
    """
    first = issue_pair(session, account, CORRELATION, now=T0)
    session.commit()
    second = rotate(session, first.refresh_token, CORRELATION, now=ROTATED)
    return first, second


def test_the_grace_window_is_sixty_seconds() -> None:
    # The requirement's number, pinned: widening it widens what a stolen
    # previous token can do, so it moves only by a deliberate edit here.
    assert dt.timedelta(seconds=60) == REFRESH_GRACE_WINDOW


def test_a_retry_within_the_window_succeeds_and_kills_the_unreceived_successor(
    restricted_session: Session, account: uuid.UUID
) -> None:
    first, second = _rotated_once(restricted_session, account)
    retry_at = ROTATED + dt.timedelta(seconds=30)

    third = rotate(restricted_session, first.refresh_token, CORRELATION, now=retry_at)

    # A FRESH pair in the SAME family: the original pair cannot be
    # returned, because only its hash was stored.
    assert third.family_id == first.family_id
    assert third.refresh_token not in {first.refresh_token, second.refresh_token}

    # Exactly one live branch, and it is the new one.
    rows = _family(restricted_session, first.family_id)
    assert [row.rotated_at is None for row in rows] == [False, False, True]
    assert _live(restricted_session, first.family_id, retry_at) == 1
    assert all(row.reuse_detected_at is None for row in rows)

    # The new token works like any other.
    rotate(
        restricted_session,
        third.refresh_token,
        CORRELATION,
        now=retry_at + dt.timedelta(seconds=5),
    )


def test_a_grace_retry_is_audited_as_its_own_event(
    restricted_session: Session, account: uuid.UUID
) -> None:
    first, _ = _rotated_once(restricted_session, account)

    rotate(
        restricted_session,
        first.refresh_token,
        CORRELATION,
        now=ROTATED + dt.timedelta(seconds=10),
    )

    events = _events(restricted_session)
    assert events.count("REFRESH_GRACE_REISSUED") == 1
    assert "REFRESH_REUSE_DETECTED" not in events


def test_a_retry_exactly_at_the_window_edge_still_succeeds(
    restricted_session: Session, account: uuid.UUID
) -> None:
    first, _ = _rotated_once(restricted_session, account)

    rotate(
        restricted_session,
        first.refresh_token,
        CORRELATION,
        now=ROTATED + REFRESH_GRACE_WINDOW,
    )


def test_a_retry_outside_the_window_revokes_the_family(
    restricted_session: Session, account: uuid.UUID
) -> None:
    first, second = _rotated_once(restricted_session, account)
    late = ROTATED + REFRESH_GRACE_WINDOW + dt.timedelta(microseconds=1)

    with pytest.raises(AuthorizationError):
        rotate(restricted_session, first.refresh_token, CORRELATION, now=late)

    assert _live(restricted_session, first.family_id, late) == 0
    assert "REFRESH_REUSE_DETECTED" in _events(restricted_session)
    with pytest.raises(AuthorizationError):
        rotate(restricted_session, second.refresh_token, CORRELATION, now=late)


def test_a_retry_after_the_successor_was_used_revokes_the_family(
    restricted_session: Session, account: uuid.UUID
) -> None:
    # The successor WAS received -- it has been spent -- so the old
    # token reappearing is not a lost response. It is the stolen-token
    # case, inside the window, and the window must not cover it.
    first, second = _rotated_once(restricted_session, account)
    third = rotate(
        restricted_session,
        second.refresh_token,
        CORRELATION,
        now=ROTATED + dt.timedelta(seconds=5),
    )
    replay_at = ROTATED + dt.timedelta(seconds=10)

    with pytest.raises(AuthorizationError):
        rotate(restricted_session, first.refresh_token, CORRELATION, now=replay_at)

    assert _live(restricted_session, first.family_id, replay_at) == 0
    with pytest.raises(AuthorizationError):
        rotate(restricted_session, third.refresh_token, CORRELATION, now=replay_at)


def test_a_token_older_than_the_previous_one_revokes_the_family(
    restricted_session: Session, account: uuid.UUID
) -> None:
    # Two rotations inside one window: the first token is now two
    # behind, never the immediately previous one.
    first, second = _rotated_once(restricted_session, account)
    rotate(
        restricted_session,
        second.refresh_token,
        CORRELATION,
        now=ROTATED + dt.timedelta(seconds=1),
    )
    replay_at = ROTATED + dt.timedelta(seconds=2)

    with pytest.raises(AuthorizationError):
        rotate(restricted_session, first.refresh_token, CORRELATION, now=replay_at)

    assert _live(restricted_session, first.family_id, replay_at) == 0


def test_a_second_retry_of_the_same_old_token_revokes_the_family(
    restricted_session: Session, account: uuid.UUID
) -> None:
    # THE DESIGN CHOICE, stated: one grace per rotation. After a grace
    # the old token is no longer the immediately previous one -- the
    # family's live token was issued by the grace -- so presenting it
    # again is a replay, even inside the window. Two lost responses in
    # a row cost a sign-in; letting one old token mint pairs repeatedly
    # for a minute would hand a thief the same.
    first, _ = _rotated_once(restricted_session, account)
    graced = rotate(
        restricted_session,
        first.refresh_token,
        CORRELATION,
        now=ROTATED + dt.timedelta(seconds=10),
    )
    again = ROTATED + dt.timedelta(seconds=20)

    with pytest.raises(AuthorizationError):
        rotate(restricted_session, first.refresh_token, CORRELATION, now=again)

    assert _live(restricted_session, first.family_id, again) == 0
    with pytest.raises(AuthorizationError):
        rotate(restricted_session, graced.refresh_token, CORRELATION, now=again)


def test_the_revoked_successor_earns_no_grace_of_its_own(
    restricted_session: Session, account: uuid.UUID
) -> None:
    # The successor a grace revoked was never received by the client
    # that retried. If it turns up anyway, someone else had it: reuse,
    # not a second window opened from the grace.
    first, second = _rotated_once(restricted_session, account)
    graced = rotate(
        restricted_session,
        first.refresh_token,
        CORRELATION,
        now=ROTATED + dt.timedelta(seconds=10),
    )
    presented_at = ROTATED + dt.timedelta(seconds=15)

    with pytest.raises(AuthorizationError):
        rotate(restricted_session, second.refresh_token, CORRELATION, now=presented_at)

    assert _live(restricted_session, first.family_id, presented_at) == 0
    with pytest.raises(AuthorizationError):
        rotate(restricted_session, graced.refresh_token, CORRELATION, now=presented_at)


def test_a_grace_never_revives_a_revoked_family(
    restricted_session: Session, account: uuid.UUID
) -> None:
    first, second = _rotated_once(restricted_session, account)
    # Revoke the family by replaying outside the window.
    with pytest.raises(AuthorizationError):
        rotate(restricted_session, first.refresh_token, CORRELATION, now=LATER)

    # Every token's rotated_at is set now, so no successor is unused;
    # the grace path must not find one and must not issue anything.
    with pytest.raises(AuthorizationError):
        rotate(
            restricted_session,
            second.refresh_token,
            CORRELATION,
            now=LATER + dt.timedelta(seconds=1),
        )
    assert len(_family(restricted_session, first.family_id)) == 2


def test_two_concurrent_retries_cannot_both_open_a_live_branch(
    restricted_engine: Engine, owner_engine: Engine, account: uuid.UUID
) -> None:
    # REAL CONNECTIONS racing on one token, forced to genuinely overlap:
    # a third connection holds the presented token's row lock until
    # BOTH workers are observed waiting on it, then lets go. Without
    # FOR UPDATE each worker would read the successor unused, revoke it,
    # and issue its own pair -- two live branches from one token.
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    with factory() as setup:
        first, _ = _rotated_once(setup, account)

    retry_at = ROTATED + dt.timedelta(seconds=10)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt() -> None:
        """Retry once with the old token, recording the outcome.

        :return: None
        """
        with factory() as session:
            try:
                rotate(session, first.refresh_token, CORRELATION, now=retry_at)
                result = "issued"
            except AuthorizationError:
                result = "refused"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    gate = factory()
    try:
        gate.execute(
            sa.text(
                "SELECT id FROM refresh_token WHERE family_id = :family "
                "AND rotated_at IS NOT NULL FOR UPDATE"
            ),
            {"family": first.family_id},
        )
        for thread in threads:
            thread.start()

        waiting = 0
        deadline = time.monotonic() + 30
        with owner_engine.connect() as observer:
            while waiting < 2 and time.monotonic() < deadline:
                time.sleep(0.05)
                waiting = observer.execute(
                    sa.text("SELECT count(*) FROM pg_locks WHERE NOT granted")
                ).scalar_one()
        assert waiting >= 2, "the two retries never overlapped"
    finally:
        gate.commit()
        gate.close()

    for thread in threads:
        thread.join(timeout=60)

    assert sorted(outcomes) == ["issued", "refused"]
    with factory() as session:
        # Per the stated design the loser is a second retry of the same
        # old token, so the family is revoked -- and in no case is there
        # more than one live branch.
        assert _live(session, first.family_id, retry_at) == 0


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
    claims = jwt.decode(
        pair.access_token,
        SECOND_SECRET,
        algorithms=["HS256"],
        audience=JWT_AUDIENCE,
    )
    assert not {"role", "lens", "lenses", "is_teacher"} & set(claims)


def test_the_access_token_carries_only_the_subject_times_and_binding(
    restricted_session: Session, account: uuid.UUID
) -> None:
    # `iss` and `aud` since L-03: they bind the token to an environment
    # and to this API, and say nothing about what the subject may do.
    pair = issue_pair(restricted_session, account, CORRELATION)
    claims = jwt.decode(
        pair.access_token,
        SECOND_SECRET,
        algorithms=["HS256"],
        audience=JWT_AUDIENCE,
    )
    assert set(claims) == {"sub", "iat", "exp", "iss", "aud"}


def test_a_tampered_token_is_refused(
    restricted_session: Session, account: uuid.UUID
) -> None:
    pair = issue_pair(restricted_session, account, CORRELATION)
    tampered = pair.access_token[:-4] + "AAAA"
    with pytest.raises(AuthorizationError):
        verify_access_token(tampered)
