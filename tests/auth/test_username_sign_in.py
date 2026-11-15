"""Signing in with a username, in one field, without an oracle [U1: BR4].

Written FIRST, to the authorization predicate [team: Testing Posture]:
who may sign in, from which network, and whether a refusal says that a
name exists are all knowable from the rules before the code exists, and a
wrong answer is either a lockout or an open door.

**Family D is per network, by design** [NFR2.4, Q1]. A username is
enumerable, so a hard cross-network limit would let anyone lock its owner
out; the per-username-across-networks count instead refuses only a
network that has already failed that name three times once it fills
(this plan's ``>= 3`` rule, replacing ``>= 1``), so an owner who mistyped
once or twice still gets in. The recomputed per-window bound is asserted
below rather than stated.

Addresses arrive in the trusted client header, so each test chooses its
networks: IPv4 ``/24``s where /64 and /48 coincide, and IPv6 where they
must differ.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from typing import Final

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session

from app.accounts.identifier import Channel, Identifier, UsernameSubject, classify_login
from app.auth.ceilings import ScopeKind
from app.auth.client_address import TRUSTED_CLIENT_IP_HEADER_ENV
from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.passwords import hash_password
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV
from app.errors import ValidationError

PASSWORD: Final = "a long enough passphrase"  # noqa: S105 -- a test value
WRONG: Final = "not the passphrase at all"
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


def _name() -> str:
    """Return a fresh valid username.

    :return: A username no other test uses
    """
    return f"u{uuid.uuid4().hex[:12]}"


def _account(
    session: Session,
    *,
    username: str | None = None,
    password: str | None = PASSWORD,
    email: str | None = None,
) -> tuple[uuid.UUID, str]:
    """Arrange an account with a number and, optionally, a username.

    :param session: An arranging session
    :param username: Its display form, or None
    :param password: Its password, or None for an account without one
    :param email: Its address, or None
    :return: The account id and its number
    """
    account_id = uuid.uuid4()
    phone = f"+88017{uuid.uuid4().int % 10**8:08d}"
    now = dt.datetime.now(tz=dt.UTC)
    session.execute(
        sa.text(
            "INSERT INTO account (id, phone, email, password_hash, "
            "password_changed_at, created_at, activated_at, username, username_key) "
            "VALUES (:id, :phone, :email, :hash, :changed, :now, :now, :name, :key)"
        ),
        {
            "id": account_id,
            "phone": phone,
            "email": email,
            "hash": hash_password(password) if password else None,
            "changed": now if password else None,
            "now": now,
            "name": username,
            "key": username.lower() if username else None,
        },
    )
    session.commit()
    return account_id, phone


def _sign_in(
    client: TestClient, login: str, password: str, ip: str = "198.51.100.7"
) -> httpx.Response:
    """Post one password sign-in by the single field.

    :param client: The test client
    :param login: What the person typed
    :param password: The password
    :param ip: The caller's address
    :return: The response
    """
    return client.post(
        "/v1/auth/password",
        json={"login": login, "password": password},
        headers={"X-Client-Address": ip},
    )


def _counts(session: Session) -> dict[str, int]:
    """Read every counter's total, by scope kind.

    :param session: A session able to read the counters
    :return: The sum of counts per scope kind
    """
    session.expire_all()
    return {
        str(kind): int(total)
        for kind, total in session.execute(
            sa.text(
                "SELECT scope_kind, sum(count) FROM rate_limit_counter "
                "GROUP BY scope_kind"
            )
        ).all()
    }


def _preload(session: Session, kind: str, value: str, count: int) -> None:
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
        {"kind": kind, "value": value, "window": start, "count": count},
    )
    session.commit()


def _fail(client: TestClient, login: str, ip: str, times: int) -> None:
    """Fail a username sign-in a number of times from one address.

    :param client: The test client
    :param login: The username
    :param ip: The address
    :param times: How many failures
    :return: None
    """
    for _ in range(times):
        assert _sign_in(client, login, WRONG, ip).status_code == 400


# ------------------------------------------------------- BR4.1, NFR6.1


def test_exactly_one_of_login_phone_and_email(client: TestClient) -> None:
    """None, two or three are refused by the schema [BR4.1, NFR6.1].

    :param client: The test client
    :return: None
    """
    phone = "+8801712345678"
    bodies = [
        {"password": PASSWORD},
        {"login": "rahim_01", "phone": phone, "password": PASSWORD},
        {"login": "rahim_01", "email": "a@example.com", "password": PASSWORD},
        {"phone": phone, "email": "a@example.com", "password": PASSWORD},
        {
            "login": "rahim_01",
            "phone": phone,
            "email": "a@example.com",
            "password": PASSWORD,
        },
    ]
    for body in bodies:
        assert client.post("/v1/auth/password", json=body).status_code == 422, body
    # IdentifierFields itself is not widened (ADR-003).
    assert client.post("/v1/auth/otp", json={}).status_code == 422


def test_a_login_only_body_is_accepted(
    client: TestClient, owner_session: Session
) -> None:
    """``{login, password}`` is a whole request [NFR6.1].

    :param client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    name = _name()
    _account(owner_session, username=name)

    response = _sign_in(client, name, PASSWORD)

    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


# ----------------------------------------------------------------- BR4.2


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Rahim@Example.com", Identifier(Channel.EMAIL, "rahim@example.com")),
        ("  01712345678 ", Identifier(Channel.PHONE, "+8801712345678")),
        ("+8801712345678", Identifier(Channel.PHONE, "+8801712345678")),
        ("Rahim_01", UsernameSubject("rahim_01")),
        ("ra..him", UsernameSubject("ra..him")),
        # A mistyped number is a username nobody has [BR4.2].
        ("0171234567", UsernameSubject("0171234567")),
        ("x" * 254, UsernameSubject("x" * 254)),
    ],
)
def test_the_login_is_classified_email_then_phone_then_username(
    raw: str, expected: object
) -> None:
    """``@`` means email; a mobile number means phone; else a key [BR4.2].

    :param raw: What was typed
    :param expected: What it is classified as
    :return: None
    """
    assert classify_login(raw) == expected


def test_a_malformed_address_with_an_at_is_refused_as_email() -> None:
    """The one classification answer that is not a sign-in result [BR4.2].

    :return: None
    """
    with pytest.raises(ValidationError) as caught:
        classify_login("rahim@")

    assert caught.value.message_key == "email.invalid"


# ----------------------------------------------------------------- BR4.3


def test_phone_and_email_sign_in_keep_working_for_a_named_account(
    client: TestClient, owner_session: Session
) -> None:
    """Through their own fields and through ``login`` [BR4.3].

    :param client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    email = f"{_name()}@example.com"
    _, phone = _account(owner_session, username=_name(), email=email)

    for body in (
        {"phone": phone, "password": PASSWORD},
        {"email": email, "password": PASSWORD},
        {"login": phone, "password": PASSWORD},
        {"login": email.upper(), "password": PASSWORD},
    ):
        response = client.post("/v1/auth/password", json=body)
        assert response.status_code == 200, (body, response.text)


def test_a_username_signs_in_whatever_its_casing(
    client: TestClient, owner_session: Session
) -> None:
    """The key decides, not the typed casing [BR1.7, BR4.2].

    :param client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    name = "Mixed_" + _name()[:8]
    _account(owner_session, username=name)

    assert _sign_in(client, name.upper(), PASSWORD).status_code == 200
    assert _sign_in(client, name.lower(), PASSWORD).status_code == 200


# ---------------------------------------------------------- BR4.4, NFR1.1


def test_unknown_passwordless_and_wrong_are_one_response(
    client: TestClient, owner_session: Session, restricted_engine: Engine
) -> None:
    """Byte-identical, same statements, one scrypt each [BR4.4, NFR1.1].

    The three username failures are also identical to a failed phone
    sign-in, so the field a person typed into tells nobody anything.

    :param client: The test client
    :param owner_session: An arranging session
    :param restricted_engine: The engine whose statements are captured
    :return: None
    """
    passwordless = _name()
    known = _name()
    _account(owner_session, username=passwordless, password=None)
    _, phone = _account(owner_session, username=known)

    statements: list[str] = []

    def capture(
        conn: object,
        cursor: object,
        statement: str,
        params: object,
        context: object,
        executemany: bool,
    ) -> None:
        """Record each statement text.

        :param conn: Unused
        :param cursor: Unused
        :param statement: The SQL text
        :param params: Unused
        :param context: Unused
        :param executemany: Unused
        :return: None
        """
        statements.append(statement)

    from app.auth import passwords as hashing

    original = hashing._derive
    derived: list[int] = []

    def counting(*args: object) -> bytes:
        """Count one scrypt evaluation, then run it.

        :param args: The scrypt arguments
        :return: The derived key
        """
        derived.append(1)
        return original(*args)  # type: ignore[arg-type]

    responses: list[httpx.Response] = []
    traces: list[list[str]] = []
    costs: list[int] = []
    event.listen(restricted_engine, "before_cursor_execute", capture)
    try:
        for index, login in enumerate((_name(), passwordless, known)):
            statements.clear()
            derived.clear()
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(hashing, "_derive", counting)
                responses.append(
                    _sign_in(client, login, WRONG, f"198.51.{100 + index}.9")
                )
            traces.append(list(statements))
            costs.append(len(derived))
    finally:
        event.remove(restricted_engine, "before_cursor_execute", capture)
    by_phone = client.post(
        "/v1/auth/password",
        json={"phone": phone, "password": WRONG},
        headers={"X-Client-Address": "198.51.110.9"},
    )
    malformed = _sign_in(client, "ra..him", WRONG, "198.51.111.9")

    assert {response.status_code for response in responses} == {400}
    first = responses[0]
    for other in [*responses[1:], by_phone, malformed]:
        assert other.content == first.content
        assert {k: v for k, v in other.headers.items() if k != "x-correlation-id"} == {
            k: v for k, v in first.headers.items() if k != "x-correlation-id"
        }
    error = first.json()["error"]
    assert (error["code"], error["message_key"]) == (
        "PASSWORD_NOT_VALID",
        "auth.password.wrong",
    )
    assert traces[0] == traces[1] == traces[2]
    assert costs == [1, 1, 1]


# ------------------------------------------------- BR4.5, BR4.6, NFR2.4


def test_a_username_failure_counts_only_its_own_scopes(
    client: TestClient, owner_session: Session
) -> None:
    """Family D and the alert-only global; never ``pw_fail_id`` or ``vf_*``.

    [BR4.5 as amended, NFR2.4] A username key and a phone or email key
    never share a counter, and username failures leave the codes' scopes.

    :param client: The test client
    :param owner_session: A session able to read counters back
    :return: None
    """
    name = _name()
    _account(owner_session, username=name)

    assert _sign_in(client, name, WRONG).status_code == 400

    assert _counts(owner_session) == {
        "un_fail_net_hour": 1,
        "un_fail_ip_hour": 1,
        "un_fail_ip48_hr": 1,
        "un_fail_hour": 1,
        "pwf_global_hour": 1,
    }


def test_unknown_and_known_usernames_are_counted_identically(
    client: TestClient, owner_session: Session
) -> None:
    """Test (e): the counters say nothing about who exists [NFR2.4].

    :param client: The test client
    :param owner_session: A session able to read counters back
    :return: None
    """
    known = _name()
    _account(owner_session, username=known)

    _sign_in(client, known, WRONG, "203.0.113.1")
    known_counts = _counts(owner_session)
    owner_session.execute(sa.text("DELETE FROM rate_limit_counter"))
    owner_session.commit()
    _sign_in(client, _name(), WRONG, "203.0.113.1")

    assert _counts(owner_session) == known_counts


def test_a_full_username_ceiling_refuses_in_sign_ins_words(
    client: TestClient, owner_session: Session
) -> None:
    """409 ``too_many_attempts``, audited with no account [BR4.6].

    :param client: The test client
    :param owner_session: A session able to read back
    :return: None
    """
    name = _name()
    _account(owner_session, username=name)
    _fail(client, name, "192.0.2.1", 10)

    refused = _sign_in(client, name, PASSWORD, "192.0.2.1")

    assert refused.status_code == 409
    error = refused.json()["error"]
    assert error["message_key"] == "auth.password.too_many_attempts"
    assert error["code"] == "TEMPORARILY_UNAVAILABLE"
    owner_session.expire_all()
    breached = owner_session.execute(
        sa.text(
            "SELECT account_id FROM auth_audit_log "
            "WHERE event = 'PASSWORD_CEILING_BREACHED'"
        )
    ).all()
    assert [row.account_id for row in breached] == [None]


def test_b_eleven_from_one_network_is_refused_and_another_network_succeeds(
    client: TestClient, owner_session: Session
) -> None:
    """Test (b): ``un_fail_net_hour`` is per network [NFR2.4].

    :param client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    name = _name()
    _account(owner_session, username=name)
    _fail(client, name, "192.0.2.1", 10)

    assert _sign_in(client, name, PASSWORD, "192.0.2.1").status_code == 409
    assert _sign_in(client, name, PASSWORD, "192.0.3.1").status_code == 200


def test_a_a_stranger_filling_the_cross_network_count_does_not_lock_out(
    client: TestClient, owner_session: Session
) -> None:
    """Test (a): 7 + 7 + 6 from three networks; a fourth still gets in.

    [NFR2.4, R-02] The 21st failure, from one of the three, is refused:
    each of them has failed the name at least three times.

    :param client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    name = _name()
    _account(owner_session, username=name)
    for ip, times in (("10.1.1.1", 7), ("10.1.2.1", 7), ("10.1.3.1", 6)):
        _fail(client, name, ip, times)

    assert _sign_in(client, name, PASSWORD, "10.1.4.1").status_code == 200
    assert _sign_in(client, name, WRONG, "10.1.3.1").status_code == 409


def test_the_owner_with_two_own_failures_still_signs_in_after_the_fill(
    client: TestClient, owner_session: Session
) -> None:
    """The ``>= 3`` rule: an owner's own typos are not a lockout [plan].

    The owner mistypes twice on their own network; a stranger then fills
    ``un_fail_hour`` from three others: 2 + 7 + 7 + 4 = 20, computed so
    the fill lands on the stranger's last failure. The owner's right
    password, from the owner's network, signs in; the stranger's networks
    stay refused, and a third failure from the owner's network is the
    last it gets.

    :param client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    name = _name()
    _account(owner_session, username=name)
    home = "10.2.0.1"
    _fail(client, name, home, 2)
    for ip, times in (("10.2.1.1", 7), ("10.2.2.1", 7), ("10.2.3.1", 4)):
        _fail(client, name, ip, times)

    assert _sign_in(client, name, PASSWORD, home).status_code == 200
    assert _sign_in(client, name, PASSWORD, "10.2.1.1").status_code == 409
    assert _sign_in(client, name, WRONG, home).status_code == 400
    assert _sign_in(client, name, PASSWORD, home).status_code == 409


def test_c_twenty_failures_on_any_names_refuse_username_sign_in_only(
    client: TestClient, owner_session: Session
) -> None:
    """Test (c): ``un_fail_ip_hour`` refuses usernames, never codes or phones.

    :param client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    name = _name()
    _, phone = _account(owner_session, username=name)
    ip = "10.3.0.1"
    for _ in range(20):
        assert _sign_in(client, _name(), WRONG, ip).status_code == 400

    by_name = _sign_in(client, name, PASSWORD, ip)
    by_phone = client.post(
        "/v1/auth/password",
        json={"phone": phone, "password": PASSWORD},
        headers={"X-Client-Address": ip},
    )
    client.post("/v1/auth/otp", json={"phone": phone}, headers={"X-Client-Address": ip})
    by_code = client.post(
        "/v1/auth/verify",
        json={"phone": phone, "code": FIXED_CODE},
        headers={"X-Client-Address": ip},
    )

    assert by_name.status_code == 409
    assert by_phone.status_code == 200, by_phone.text
    assert by_code.status_code == 200, by_code.text


def test_d_a_full_verify_count_does_not_refuse_a_username_sign_in(
    client: TestClient, owner_session: Session
) -> None:
    """Test (d): Family D never reads ``vf_*`` [NFR2.4].

    :param client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    name = _name()
    _account(owner_session, username=name)
    ip = "10.4.0.1"
    _preload(owner_session, ScopeKind.VERIFY_FAIL_IP_HOURLY.value, "10.4.0.0/24", 500)
    _preload(owner_session, ScopeKind.VERIFY_FAIL_IP48_HOURLY.value, "10.4.0.0/24", 500)

    assert _sign_in(client, name, PASSWORD, ip).status_code == 200


def test_full_username_counters_never_refuse_phone_email_or_code(
    client: TestClient, owner_session: Session
) -> None:
    """The same account's other doors stay open [BR4.7, NFR2.4 (2)].

    :param client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    name = _name()
    email = f"{_name()}@example.com"
    _, phone = _account(owner_session, username=name, email=email)
    ip = "10.5.0.1"
    _fail(client, name, ip, 10)
    assert _sign_in(client, name, PASSWORD, ip).status_code == 409

    by_phone = _sign_in(client, phone, PASSWORD, ip)
    by_email = _sign_in(client, email, PASSWORD, ip)
    client.post("/v1/auth/otp", json={"phone": phone}, headers={"X-Client-Address": ip})
    by_code = client.post(
        "/v1/auth/verify",
        json={"phone": phone, "code": FIXED_CODE},
        headers={"X-Client-Address": ip},
    )

    assert by_phone.status_code == 200, by_phone.text
    assert by_email.status_code == 200, by_email.text
    assert by_code.status_code == 200, by_code.text


def test_the_per_window_guessing_bound_is_three_per_network_once_full(
    client: TestClient, owner_session: Session
) -> None:
    """The recomputed NFR2.5 bound, counted rather than stated [plan].

    25 distinct /64s inside 3 /48s try one name round-robin until a whole
    round is refused. ``un_fail_hour`` fills at 20, after which each /64
    may go on only until it has failed the name 3 times, counting its
    earlier failures. Round-robin keeps every /64 at or under 3 before the
    fill, so exactly 3 x 25 = 75 failures are counted and every later
    attempt is refused. (The ``>= 1`` rule this plan replaced allowed
    20 + 5 = 25 here.)

    :param client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    name = _name()
    _account(owner_session, username=name)
    networks = [
        f"2001:db8:{group}:{index:x}::1" for group in (1, 2, 3) for index in range(9)
    ][:25]

    failures = 0
    while True:
        round_failures = 0
        for ip in networks:
            status = _sign_in(client, name, WRONG, ip).status_code
            assert status in {400, 409}, status
            round_failures += status == 400
        failures += round_failures
        if round_failures == 0:
            break

    assert failures == 75
    assert _counts(owner_session)["un_fail_hour"] == 75


# ------------------------------------------ NFR2.6, NFR2.7 (test-after)

#: Every username scope and the refusal it must give: Families A, B and C
#: the lookup's 429, Family D sign-in's 409. A member missing here fails.
USERNAME_SCOPE_REFUSALS: Final = {
    "un_lk_ip_hour": (429, "auth.lookup.too_many"),
    "un_lk_ip48_hour": (429, "auth.lookup.too_many"),
    "un_lk_global_hr": (429, "auth.lookup.too_many"),
    "un_cl_acct_hour": (429, "auth.lookup.too_many"),
    "un_cl_ip_hour": (429, "auth.lookup.too_many"),
    "un_cl_ip48_hr": (429, "auth.lookup.too_many"),
    "un_rp_dest_hour": (429, "auth.lookup.too_many"),
    "un_rp_ip_hour": (429, "auth.lookup.too_many"),
    "un_fail_net_hour": (409, "auth.password.too_many_attempts"),
    "un_fail_ip_hour": (409, "auth.password.too_many_attempts"),
    "un_fail_ip48_hr": (409, "auth.password.too_many_attempts"),
    "un_fail_hour": (409, "auth.password.too_many_attempts"),
}


@pytest.mark.parametrize(
    "kind", [kind for kind in ScopeKind if kind.value.startswith("un_")]
)
def test_every_username_scope_refuses_in_its_own_words(kind: ScopeKind) -> None:
    """No ``un_`` scope falls through to the OTP path's text [NFR2.6].

    :param kind: A username scope
    :return: None
    """
    from app.auth.ceilings import CeilingBreach
    from app.errors import ConflictError, TransientError

    breach = CeilingBreach(kind)

    assert kind.value in USERNAME_SCOPE_REFUSALS, f"{kind} has no stated refusal"
    assert (breach.status, breach.message_key) == USERNAME_SCOPE_REFUSALS[kind.value]
    # Retryability is the class's: a conflict, never a transient error.
    assert isinstance(breach, ConflictError)
    assert not isinstance(breach, TransientError)


def test_the_twelve_username_scopes_are_exactly_the_listed_ones() -> None:
    """The NFR2 table has twelve rows, and so does the enum [NFR2].

    :return: None
    """
    kinds = {kind.value for kind in ScopeKind if kind.value.startswith("un_")}
    assert kinds == set(USERNAME_SCOPE_REFUSALS)
    assert len(kinds) == 12


def test_every_username_scope_fits_its_columns(
    owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kinds in ``String(16)``, keyed values in 64 [NFR2.7, NFR3.3].

    :param owner_session: A writing session
    :param monkeypatch: The patcher
    :return: None
    """
    from app.accounts.usernames import counter_value

    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")
    value = counter_value("x" * 254, "2001:db8:ffff:ffff::/64")
    assert len(value) == 64
    for kind in USERNAME_SCOPE_REFUSALS:
        _preload(owner_session, kind, value, 1)

    assert len(_counts(owner_session)) == len(USERNAME_SCOPE_REFUSALS)
