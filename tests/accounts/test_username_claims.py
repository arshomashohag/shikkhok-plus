"""Who may take a name, and what a lookup may say about one [U1: BR3, BR5, BR6].

Written FIRST, to the authorization predicate [team: Testing Posture].
Every answer here -- available or not, allowed or refused, which window
and which hold -- is knowable from the rules before the code exists, and
a wrong one hands a name, or the knowledge that it exists, to the wrong
person.

**Time is injected, never slept.** The routes read the clock through
:func:`app.accounts.usernames.utc_now`, so a test steps through the
30-day window by setting the moment it is asked at. The counters keep
the real clock, which is what keeps every ceiling test in one window.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from collections.abc import Iterator
from typing import Any, Final

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.accounts import usernames
from app.auth.client_address import TRUSTED_CLIENT_IP_HEADER_ENV
from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV, issue_pair
from tests.accounts.signup_support import named_account, unique_username

PASSWORD: Final = "a long enough passphrase"  # noqa: S105 -- a test value

#: Not the account's password: what a wrong guess sends.
WRONG: Final = "not-the-passphrase"

#: Sent with a first choice, where it must be ignored [BR5.3].
IGNORED: Final = "ignored-for-a-first-choice"

DAY0: Final = dt.datetime(2026, 11, 1, 9, 0, tzinfo=dt.UTC)


@pytest.fixture
def client(
    restricted_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Build a client whose caller address is a header.

    :param restricted_engine: The non-superuser engine
    :param monkeypatch: The patcher
    :return: A context manager yielding the client
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")
    monkeypatch.setenv(JWT_KEYS_ENV, "k1:test-signing-key-padded-to-thirty-two")
    monkeypatch.setenv(JWT_ACTIVE_KID_ENV, "k1")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_APP_HASH", "AAAAAAAAAAA")
    monkeypatch.setenv(TRUSTED_CLIENT_IP_HEADER_ENV, "X-Client-Address")

    from app.main import create_app

    app = create_app()
    app.state.engine = restricted_engine
    with TestClient(app) as test_client:
        yield test_client


class Clock:
    """The moment the username routes are asked at.

    :ivar moment: What :func:`usernames.utc_now` returns
    """

    def __init__(self, moment: dt.datetime) -> None:
        """Start at one moment.

        :param moment: The first moment
        """
        self.moment = moment

    def at(self, days: float) -> None:
        """Move to a number of days after ``DAY0``.

        :param days: Days after ``DAY0``
        :return: None
        """
        self.moment = DAY0 + dt.timedelta(days=days)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    """Pin the username routes' clock to ``DAY0``.

    :param monkeypatch: The patcher
    :return: The clock, to move
    """
    pinned = Clock(DAY0)
    monkeypatch.setattr(usernames, "utc_now", lambda: pinned.moment)
    return pinned


def _auth(session: Session, account_id: uuid.UUID) -> dict[str, str]:
    """Authorize as an account.

    :param session: A session to write the token family through
    :param account_id: The account
    :return: The header mapping
    """
    pair = issue_pair(session, account_id=account_id, correlation_id=uuid.uuid4())
    session.commit()
    return {"Authorization": f"Bearer {pair.access_token}"}


def _lookup(
    client: TestClient,
    name: str,
    headers: dict[str, str] | None = None,
    ip: str = "198.51.100.7",
) -> httpx.Response:
    """Ask either lookup about a name.

    :param client: The test client
    :param name: The candidate
    :param headers: An Authorization header for the signed-in form, or None
    :param ip: The caller's address
    :return: The response
    """
    path = (
        "/v1/me/username-availability"
        if headers
        else "/v1/accounts/username-availability"
    )
    return client.post(
        path,
        json={"username": name},
        headers={**(headers or {}), "X-Client-Address": ip},
    )


def _put(
    client: TestClient,
    headers: dict[str, str],
    name: str,
    password: str | None = PASSWORD,
    ip: str = "198.51.100.7",
) -> httpx.Response:
    """Choose or change the signed-in account's username.

    :param client: The test client
    :param headers: The Authorization header
    :param name: The candidate
    :param password: The password, or None to send none
    :param ip: The caller's address
    :return: The response
    """
    body: dict[str, Any] = {"username": name}
    if password is not None:
        body["password"] = password
    return client.put(
        "/v1/me/username", json=body, headers={**headers, "X-Client-Address": ip}
    )


def _row(session: Session, account_id: uuid.UUID) -> sa.Row[Any]:
    """Read an account's username columns.

    :param session: A session able to read fixture data
    :param account_id: The account
    :return: The row
    """
    session.expire_all()
    return session.execute(
        sa.text(
            "SELECT username, username_key, username_changed_at, "
            "username_reclaimed_at FROM account WHERE id = :id"
        ),
        {"id": account_id},
    ).one()


def _holds(session: Session) -> dict[str, tuple[dt.datetime, uuid.UUID | None]]:
    """Read every hold, by digest.

    :param session: A session able to read fixture data
    :return: ``{digest: (held_until, releasing_account_id)}``
    """
    session.expire_all()
    return {
        row.key_digest: (row.held_until, row.releasing_account_id)
        for row in session.execute(
            sa.text(
                "SELECT key_digest, held_until, releasing_account_id FROM username_hold"
            )
        )
    }


def _hold(
    session: Session,
    name: str,
    releasing: uuid.UUID | None,
    held_until: dt.datetime,
) -> None:
    """Arrange a hold directly.

    :param session: An arranging session
    :param name: The held name's key
    :param releasing: The releasing account, or None
    :param held_until: Its expiry
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO username_hold (key_digest, held_until, releasing_account_id, "
            "created_at) VALUES (:digest, :until, :releasing, :until)"
        ),
        {
            "digest": usernames.hold_digest(name.lower()),
            "until": held_until,
            "releasing": releasing,
        },
    )
    session.commit()


@pytest.fixture(autouse=True)
def _hmac_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the arranging helpers the client's HMAC key.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")


# ---------------------------------------------------------- BR3.1, NFR1.4


def test_the_public_lookup_answers_only_its_four_statuses(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """Available, unavailable, invalid with its key, reserved [BR3.1].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    taken = unique_username()
    named_account(owner_session, taken)

    answers = {
        "free": _lookup(client, unique_username()).json(),
        "taken": _lookup(client, taken.upper()).json(),
        "invalid": _lookup(client, "ra..him").json(),
        "reserved": _lookup(client, "Admin").json(),
    }

    assert answers == {
        "free": {"status": "available", "message_key": None},
        "taken": {"status": "unavailable", "message_key": None},
        "invalid": {"status": "invalid", "message_key": "account.username.bad_dot"},
        "reserved": {"status": "reserved", "message_key": None},
    }


def test_a_held_name_reads_exactly_as_a_taken_one(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """Held for nobody, held for an account and taken: one body [NFR1.4].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    taken, for_nobody, for_someone = (unique_username() for _ in range(3))
    named_account(owner_session, taken)
    releasing, _ = named_account(owner_session, unique_username())
    _hold(owner_session, for_nobody, None, DAY0 + dt.timedelta(days=30))
    _hold(owner_session, for_someone, releasing, DAY0 + dt.timedelta(days=30))

    bodies = {
        _lookup(client, name).content for name in (taken, for_nobody, for_someone)
    }

    assert len(bodies) == 1


# ---------------------------------------------------------- BR3.2, NFR1.5


def test_the_signed_in_lookup_differs_only_for_the_callers_own_holds(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """Held for A: available to A, unavailable to B and to anyone [NFR1.5].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    a_name, held = unique_username(), unique_username()
    a, _ = named_account(owner_session, a_name)
    b, _ = named_account(owner_session, unique_username())
    _hold(owner_session, held, a, DAY0 + dt.timedelta(days=30))

    assert (
        _lookup(client, held, _auth(owner_session, a)).json()["status"] == "available"
    )
    assert (
        _lookup(client, held, _auth(owner_session, b)).json()["status"] == "unavailable"
    )
    assert _lookup(client, held).json()["status"] == "unavailable"
    # The caller's own current key, in another casing, is theirs too.
    own = _lookup(client, a_name.upper(), _auth(owner_session, a))
    assert own.json()["status"] == "available"
    assert _lookup(client, a_name, _auth(owner_session, b)).json()["status"] == (
        "unavailable"
    )


# -------------------------------------------------------- BR3.3, NFR2.1


def test_the_lookup_ceilings_refuse_at_their_limits_and_consume_nothing(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """30 per /64, both forms on one counter; the 31st is 429 [NFR2.1].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    account_id, _ = named_account(owner_session, unique_username())
    headers = _auth(owner_session, account_id)
    ip = "10.20.0.1"
    for index in range(30):
        signed_in = headers if index % 2 else None
        # Counted for every candidate, valid or not, before it is judged.
        name = "ab" if index == 0 else unique_username()
        assert _lookup(client, name, signed_in, ip).status_code == 200

    refused = _lookup(client, unique_username(), None, ip)
    refused_signed_in = _lookup(client, unique_username(), headers, ip)

    assert refused.status_code == refused_signed_in.status_code == 429
    error = refused.json()["error"]
    assert (error["message_key"], error["retryable"]) == ("auth.lookup.too_many", False)
    owner_session.expire_all()
    count = owner_session.execute(
        sa.text(
            "SELECT count FROM rate_limit_counter WHERE scope_kind = 'un_lk_ip_hour'"
        )
    ).scalar_one()
    assert count == 30
    assert _lookup(client, unique_username(), None, "10.21.0.1").status_code == 200


def test_the_per_48_lookup_scope_refuses_at_its_limit(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """``un_lk_ip48_hour`` at 100 refuses a fresh /64 inside it [NFR2.1].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    window = dt.datetime.now(tz=dt.UTC).replace(minute=0, second=0, microsecond=0)
    owner_session.execute(
        sa.text(
            "INSERT INTO rate_limit_counter (id, scope_kind, scope_value, "
            "window_start, count) VALUES (gen_random_uuid(), 'un_lk_ip48_hour', "
            "'2001:db8:5::/48', :window, 100)"
        ),
        {"window": window},
    )
    owner_session.commit()

    refused = _lookup(client, unique_username(), None, "2001:db8:5:1::1")

    assert refused.status_code == 429


def test_the_global_lookup_scope_alerts_once_and_refuses_nothing(
    client: TestClient,
    owner_session: Session,
    clock: Clock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Alert-only, on the request that fills it [NFR2.1].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :param caplog: The log capture
    :return: None
    """
    from app.auth.ceilings import USERNAME_LOOKUPS_GLOBAL_HOURLY

    window = dt.datetime.now(tz=dt.UTC).replace(minute=0, second=0, microsecond=0)
    owner_session.execute(
        sa.text(
            "INSERT INTO rate_limit_counter (id, scope_kind, scope_value, "
            "window_start, count) VALUES (gen_random_uuid(), 'un_lk_global_hr', "
            "'global', :window, :count)"
        ),
        {"window": window, "count": USERNAME_LOOKUPS_GLOBAL_HOURLY - 1},
    )
    owner_session.commit()

    with caplog.at_level(logging.CRITICAL):
        filling = _lookup(client, unique_username(), None, "10.22.0.1")
        past = _lookup(client, unique_username(), None, "10.23.0.1")

    assert filling.status_code == past.status_code == 200
    alerts = [
        r for r in caplog.records if getattr(r, "scope", None) == "un_lk_global_hr"
    ]
    assert len(alerts) == 1


# ------------------------------------------------------------ BR5.1, BR5.3


def test_username_required_is_true_exactly_while_there_is_none(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """Computed from the column, every time [BR5.1].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    account_id, _ = named_account(owner_session)
    headers = _auth(owner_session, account_id)
    name = "First_" + unique_username()[:6]

    before = client.get("/v1/me", headers=headers).json()
    chosen = _put(client, headers, name, password=None)
    after = client.get("/v1/me", headers=headers).json()

    assert (before["username"], before["username_required"]) == (None, True)
    assert chosen.status_code == 200, chosen.text
    assert (after["username"], after["username_required"]) == (name, False)


def test_the_first_choice_needs_no_password_no_limit_and_places_no_hold(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """And it does not start the limit [BR5.3].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    account_id, _ = named_account(owner_session, password=PASSWORD)
    headers = _auth(owner_session, account_id)
    first, second = unique_username(), unique_username()

    chosen = _put(client, headers, first, password=IGNORED)

    assert chosen.status_code == 200, chosen.text
    assert chosen.json() == {"username": first, "next_change_at": None}
    row = _row(owner_session, account_id)
    assert (row.username, row.username_changed_at, row.username_reclaimed_at) == (
        first,
        None,
        None,
    )
    assert _holds(owner_session) == {}
    events = owner_session.execute(
        sa.text("SELECT event FROM auth_audit_log WHERE account_id = :id"),
        {"id": account_id},
    ).scalars()
    assert list(events) == ["USERNAME_SET"]
    # A first choice does not start the limit: a rename is allowed at once.
    assert _put(client, headers, second).status_code == 200


def test_a_sign_up_username_is_a_first_choice_too(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """The first ordinary rename after sign-up is allowed at once [BR5.3].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    account_id, _ = named_account(owner_session, unique_username(), password=PASSWORD)

    renamed = _put(client, _auth(owner_session, account_id), unique_username())

    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["next_change_at"] == "2026-12-01T09:00:00Z"


# ------------------------------------------------------------------ BR6.1


def test_a_rename_needs_the_password(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """None sent, none set, or wrong: refused before anything is locked.

    [BR6.1] A missing password and an account with none answer
    ``password_required``; a wrong one ``current_wrong``. A case-only
    change needs it too.

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    name = unique_username()
    with_password, _ = named_account(owner_session, name, password=PASSWORD)
    without, _ = named_account(owner_session, unique_username())
    headers = _auth(owner_session, with_password)

    none_sent = _put(client, headers, unique_username(), password=None)
    none_set = _put(client, _auth(owner_session, without), unique_username())
    wrong = _put(client, headers, unique_username(), password=WRONG)
    case_only = _put(client, headers, name.upper(), password=None)

    for response in (none_sent, none_set, case_only):
        assert response.status_code == 400, response.text
        error = response.json()["error"]
        assert error["message_key"] == "account.username.password_required"
        assert error["code"] == "USERNAME_PASSWORD_REQUIRED"
    assert wrong.status_code == 400
    assert wrong.json()["error"]["message_key"] == "auth.password.current_wrong"
    assert _row(owner_session, with_password).username == name


# --------------------------------------------- BR6.2, BR6.3, NFR2.8


def test_one_ordinary_rename_per_thirty_days(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """Day 0 allowed, day 20 refused with ``next_change_at``, day 30 allowed.

    [BR6.2, NFR2.8] ``next_change_at`` is an ISO 8601 UTC string with
    seconds and ``Z``, in ``details``, which are strings.

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    account_id, _ = named_account(owner_session, unique_username(), password=PASSWORD)
    headers = _auth(owner_session, account_id)

    day0 = _put(client, headers, unique_username())
    clock.at(20)
    day20 = _put(client, headers, unique_username())
    clock.at(30)
    day30 = _put(client, headers, unique_username())

    assert day0.status_code == 200
    assert day0.json()["next_change_at"] == "2026-12-01T09:00:00Z"
    assert day20.status_code == 409
    error = day20.json()["error"]
    assert error["message_key"] == "account.username.change_too_soon"
    assert error["code"] == "USERNAME_CHANGE_TOO_SOON"
    assert error["details"] == {"next_change_at": "2026-12-01T09:00:00Z"}
    assert day30.status_code == 200, day30.text


def test_a_rename_holds_the_old_name_for_the_account(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """The old key is held 30 days for this account alone [BR6.3].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    old = unique_username()
    account_id, _ = named_account(owner_session, old, password=PASSWORD)
    headers = _auth(owner_session, account_id)
    other, _ = named_account(owner_session, unique_username(), password=PASSWORD)

    _put(client, headers, unique_username())

    assert _holds(owner_session) == {
        usernames.hold_digest(old): (DAY0 + dt.timedelta(days=30), account_id)
    }
    row = _row(owner_session, account_id)
    assert row.username_changed_at == DAY0
    assert _lookup(client, old).json()["status"] == "unavailable"
    assert _lookup(client, old, headers).json()["status"] == "available"
    stranger = _put(client, _auth(owner_session, other), old)
    assert stranger.status_code == 409
    assert stranger.json()["error"]["message_key"] == "account.username.unavailable"


# -------------------------------------------- BR6.4 to BR6.6, R-10


def test_the_worked_check_of_r10(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """Computed step by step, as functional-spec W8 works it [R-10].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    math, short = f"m{uuid.uuid4().hex[:8]}_math", f"m{uuid.uuid4().hex[:8]}_m"
    account_id, _ = named_account(owner_session, math, password=PASSWORD)
    headers = _auth(owner_session, account_id)
    stranger, _ = named_account(owner_session, unique_username(), password=PASSWORD)

    renamed = _put(client, headers, short)
    assert renamed.json() == {
        "username": short,
        "next_change_at": "2026-12-01T09:00:00Z",
    }

    clock.at(3)
    assert _put(client, _auth(owner_session, stranger), math).status_code == 409
    reclaimed = _put(client, headers, math)
    assert reclaimed.status_code == 200, reclaimed.text
    assert reclaimed.json() == {
        "username": math,
        "next_change_at": "2026-12-01T09:00:00Z",
    }
    row = _row(owner_session, account_id)
    assert (row.username_changed_at, row.username_reclaimed_at) == (
        DAY0,
        DAY0 + dt.timedelta(days=3),
    )
    assert _holds(owner_session) == {
        usernames.hold_digest(short): (DAY0 + dt.timedelta(days=33), account_id)
    }

    clock.at(5)
    second = _put(client, headers, short)
    assert second.status_code == 409
    assert second.json()["error"]["details"] == {
        "next_change_at": "2026-12-01T09:00:00Z"
    }

    clock.at(30)
    ordinary = _put(client, headers, short)
    assert ordinary.status_code == 200, ordinary.text
    assert ordinary.json()["next_change_at"] == "2026-12-31T09:00:00Z"
    row = _row(owner_session, account_id)
    # Own-held while the window is open is an ordinary rename [BR6.6]:
    # the window moves, and the reclaim allowance is untouched.
    assert (row.username, row.username_changed_at, row.username_reclaimed_at) == (
        short,
        DAY0 + dt.timedelta(days=30),
        DAY0 + dt.timedelta(days=3),
    )
    assert _holds(owner_session) == {
        usernames.hold_digest(math): (DAY0 + dt.timedelta(days=60), account_id)
    }


# ------------------------------------------------------------------ NFR1.6


def test_a_closed_window_tells_the_caller_nothing_about_other_names(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """Free, taken and held-for-nobody give one answer [NFR1.6 (1), (3)].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    account_id, _ = named_account(owner_session, unique_username(), password=PASSWORD)
    headers = _auth(owner_session, account_id)
    taken, held = unique_username(), unique_username()
    named_account(owner_session, taken)
    _hold(owner_session, held, None, DAY0 + dt.timedelta(days=60))
    _put(client, headers, unique_username())
    clock.at(10)
    before = (_row(owner_session, account_id), _holds(owner_session))

    answers = [_put(client, headers, name) for name in (unique_username(), taken, held)]

    assert {response.status_code for response in answers} == {409}
    assert len({response.content for response in answers}) == 1
    assert (
        answers[0].json()["error"]["message_key"] == "account.username.change_too_soon"
    )
    assert (_row(owner_session, account_id), _holds(owner_session)) == before


def test_the_eleventh_claim_in_an_hour_is_refused_even_for_a_free_name(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """``un_cl_acct_hour`` at 10, before the password check [NFR1.6 (2)].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    account_id, _ = named_account(owner_session, unique_username(), password=PASSWORD)
    headers = _auth(owner_session, account_id)
    for index in range(10):
        # Wrong passwords: each is still a claim, counted first.
        assert _put(
            client, headers, unique_username(), password=WRONG, ip=f"10.30.{index}.1"
        ).status_code in {400, 409}

    refused = _put(client, headers, unique_username(), ip="10.31.0.1")

    assert refused.status_code == 429, refused.text
    assert refused.json()["error"]["message_key"] == "auth.lookup.too_many"


# ------------------------------------------------------------------ NFR2.2


@pytest.mark.parametrize(
    ("kind", "value", "limit", "ip"),
    [
        ("un_cl_ip_hour", "10.40.0.0/24", 30, "10.40.0.9"),
        ("un_cl_ip48_hr", "2001:db8:40::/48", 100, "2001:db8:40:7::1"),
    ],
)
def test_the_per_network_claim_scopes_refuse_at_their_limits(
    client: TestClient,
    owner_session: Session,
    clock: Clock,
    kind: str,
    value: str,
    limit: int,
    ip: str,
) -> None:
    """Each refusing Family B scope at its limit [NFR2.2].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :param kind: The scope kind
    :param value: The caller's prefix
    :param limit: Its limit
    :param ip: An address inside it
    :return: None
    """
    account_id, _ = named_account(owner_session)
    window = dt.datetime.now(tz=dt.UTC).replace(minute=0, second=0, microsecond=0)
    owner_session.execute(
        sa.text(
            "INSERT INTO rate_limit_counter (id, scope_kind, scope_value, "
            "window_start, count) VALUES (gen_random_uuid(), :kind, :value, "
            ":window, :count)"
        ),
        {"kind": kind, "value": value, "window": window, "count": limit},
    )
    owner_session.commit()

    refused = _put(client, _auth(owner_session, account_id), unique_username(), ip=ip)

    assert refused.status_code == 429
    assert _row(owner_session, account_id).username is None


def test_typing_lookups_never_spend_the_claim_budget(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """30 lookups from a /64 do not refuse a claim from it [NFR2.2].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    account_id, _ = named_account(owner_session)
    ip = "10.50.0.1"
    for _ in range(30):
        _lookup(client, unique_username(), None, ip)
    assert _lookup(client, unique_username(), None, ip).status_code == 429

    chosen = _put(client, _auth(owner_session, account_id), unique_username(), ip=ip)

    assert chosen.status_code == 200, chosen.text


# ------------------------------------------------------------------ BR6.9


def test_one_claim_rule_refuses_taken_and_held_and_frees_an_expired_hold(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """At first choice and at rename alike [BR6.9].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    taken, held, expired = (unique_username() for _ in range(3))
    named_account(owner_session, taken)
    _hold(owner_session, held, None, DAY0 + dt.timedelta(days=1))
    _hold(owner_session, expired, None, DAY0)
    first_choice, _ = named_account(owner_session)
    renaming, _ = named_account(owner_session, unique_username(), password=PASSWORD)
    first = _auth(owner_session, first_choice)
    rename = _auth(owner_session, renaming)

    for headers in (first, rename):
        for name in (taken, held.upper()):
            refused = _put(client, headers, name)
            assert refused.status_code == 409, (name, refused.text)
            assert refused.json()["error"]["message_key"] == (
                "account.username.unavailable"
            )

    assert _put(client, first, expired).status_code == 200
    assert usernames.hold_digest(expired) not in _holds(owner_session)


# --------------------------------------------- test-after: BR6.7, BR6.8, BR5.2


def test_a_case_only_change_is_not_a_rename(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """Allowed while the window is closed; no hold; no timestamp moves [BR6.7].

    The identical text is a no-op with no audit row.

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    account_id, _ = named_account(owner_session, unique_username(), password=PASSWORD)
    headers = _auth(owner_session, account_id)
    name = "lower_" + uuid.uuid4().hex[:6]
    _put(client, headers, name)
    clock.at(5)
    holds = _holds(owner_session)

    same = _put(client, headers, name)
    cased = _put(client, headers, name.upper())

    assert same.status_code == cased.status_code == 200, cased.text
    assert same.json() == {"username": name, "next_change_at": "2026-12-01T09:00:00Z"}
    assert cased.json() == {
        "username": name.upper(),
        "next_change_at": "2026-12-01T09:00:00Z",
    }
    row = _row(owner_session, account_id)
    assert (row.username, row.username_key) == (name.upper(), name)
    assert (row.username_changed_at, row.username_reclaimed_at) == (DAY0, None)
    assert _holds(owner_session) == holds
    events = list(
        owner_session.execute(
            sa.text(
                "SELECT event FROM auth_audit_log WHERE account_id = :id "
                "ORDER BY occurred_at"
            ),
            {"id": account_id},
        ).scalars()
    )
    assert events == ["USERNAME_CHANGED", "USERNAME_CHANGED"]


def test_changing_the_username_signs_nobody_out(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """Every session survives a first choice and a rename [BR6.8].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    account_id, _ = named_account(owner_session, password=PASSWORD)
    other_device = issue_pair(owner_session, account_id, correlation_id="other")
    owner_session.commit()
    headers = _auth(owner_session, account_id)

    _put(client, headers, unique_username())
    _put(client, headers, unique_username())
    refreshed = client.post(
        "/v1/auth/refresh",
        json={"refresh_token": other_device.refresh_token},
        headers={"Authorization": f"Bearer {other_device.access_token}"},
    )

    assert refreshed.status_code == 200, refreshed.text
    assert client.get("/v1/me", headers=headers).status_code == 200


def test_an_account_without_a_username_is_refused_nothing_else(
    client: TestClient, owner_session: Session, clock: Clock
) -> None:
    """The flag is the decision; the server enforces no screen [BR5.2].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :return: None
    """
    account_id, _ = named_account(owner_session)
    headers = _auth(owner_session, account_id)

    for method, path, body in (
        ("GET", "/v1/me", None),
        ("PATCH", "/v1/me", {"self_name": "Mitu"}),
        ("GET", "/v1/me/notifications", None),
        ("GET", "/v1/invitations", None),
        ("GET", "/v1/me/deletion-summary", None),
    ):
        response = client.request(method, path, json=body, headers=headers)
        assert response.status_code == 200, (path, response.text)


def test_a_rename_retried_after_a_deadlock_applies_once(
    client: TestClient,
    owner_session: Session,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ``40P01`` after the hold upsert re-runs the unit once [NFR4.3].

    200; the new name; one hold on the old key; ``USERNAME_CHANGED``
    once; the claim counted once, because it is outside the unit.

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :param monkeypatch: The patcher
    :return: None
    """
    old = unique_username()
    account_id, _ = named_account(owner_session, old, password=PASSWORD)
    _deadlock_after_the_hold(monkeypatch, times=1)

    renamed = _put(client, _auth(owner_session, account_id), unique_username())

    assert renamed.status_code == 200, renamed.text
    assert _row(owner_session, account_id).username == renamed.json()["username"]
    assert list(_holds(owner_session)) == [usernames.hold_digest(old)]
    assert _events(owner_session, account_id) == ["USERNAME_CHANGED"]
    assert _claims_counted(owner_session) == 1


def test_a_rename_that_keeps_deadlocking_is_a_retryable_503(
    client: TestClient,
    owner_session: Session,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every attempt failing leaves nothing and says retry [NFR4.3].

    :param client: The test client
    :param owner_session: An arranging session
    :param clock: The username clock
    :param monkeypatch: The patcher
    :return: None
    """
    old = unique_username()
    account_id, _ = named_account(owner_session, old, password=PASSWORD)
    _deadlock_after_the_hold(monkeypatch, times=3)
    monkeypatch.setattr("app.db.retry.time.sleep", lambda _: None)

    refused = _put(client, _auth(owner_session, account_id), unique_username())

    assert refused.status_code == 503
    assert refused.json()["error"]["retryable"] is True
    assert _row(owner_session, account_id).username == old
    assert _holds(owner_session) == {}
    assert _events(owner_session, account_id) == []
    assert _claims_counted(owner_session) == 1


def _deadlock_after_the_hold(monkeypatch: pytest.MonkeyPatch, *, times: int) -> None:
    """Make the next ``times`` hold upserts be followed by a ``40P01``.

    :param monkeypatch: The patcher
    :param times: How many attempts fail
    :return: None
    """
    from sqlalchemy.exc import OperationalError

    original = usernames.place_hold
    remaining = [times]

    class _Deadlock(Exception):
        """Carries the SQLSTATE the retry reads."""

        sqlstate = "40P01"

    def place_then_fail(*args: Any, **kwargs: Any) -> None:
        """Upsert the hold, then fail as a detected deadlock would.

        :param args: The hold's arguments
        :param kwargs: Its keyword arguments
        :return: None
        :raises OperationalError: While failures remain
        """
        original(*args, **kwargs)
        if remaining[0] > 0:
            remaining[0] -= 1
            raise OperationalError("injected", {}, _Deadlock())

    monkeypatch.setattr(usernames, "place_hold", place_then_fail)


def _events(session: Session, account_id: uuid.UUID) -> list[str]:
    """List an account's audit events, oldest first.

    :param session: A reading session
    :param account_id: The account
    :return: The event names
    """
    session.expire_all()
    return list(
        session.execute(
            sa.text(
                "SELECT event FROM auth_audit_log WHERE account_id = :id "
                "ORDER BY occurred_at"
            ),
            {"id": account_id},
        ).scalars()
    )


def _claims_counted(session: Session) -> int:
    """Sum the per-account claim counter.

    :param session: A reading session
    :return: The count
    """
    session.expire_all()
    return int(
        session.execute(
            sa.text(
                "SELECT coalesce(sum(count), 0) FROM rate_limit_counter "
                "WHERE scope_kind = 'un_cl_acct_hour'"
            )
        ).scalar_one()
    )
