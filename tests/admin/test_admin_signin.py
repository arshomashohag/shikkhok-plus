"""Platform administrator sign-in over HTTP: SMS code, then authenticator.

**Written to the authentication predicate.** Each test states one way a
second factor could be skipped, replayed, guessed or carried off the
admin hostname, and asserts the route refuses it. Codes are computed
from the secret the enrollment step returned, exactly as an
authenticator app would, so nothing here bypasses the path under test.
"""

from __future__ import annotations

import datetime as dt
import time
import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.admin.signin import MAX_FAILED_ATTEMPTS
from app.auth import totp
from app.authz.admin import PLATFORM_ADMIN_PHONES_ENV
from app.gateway.null import NullGateway
from tests.admin.conftest import EDGE, admin_headers
from tests.conftest import bearer
from tests.help.conftest import People, phone_of


@pytest.fixture
def texts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Capture every SMS the null gateway is asked to send.

    :param monkeypatch: The patcher
    :return: ``(number, message)`` per send
    """
    sent: list[tuple[str, str]] = []
    original = NullGateway.send

    def capture(
        self: NullGateway, number: str, message: str, correlation_id: str
    ) -> object:
        sent.append((number, message))
        return original(self, number, message, correlation_id)

    monkeypatch.setattr(NullGateway, "send", capture)
    return sent


@pytest.fixture
def admin_phone(
    owner_session: Session, people: People, monkeypatch: pytest.MonkeyPatch
) -> str:
    """Make the stranger the one administrator.

    :param owner_session: An arranging session
    :param people: The arranged accounts
    :param monkeypatch: The patcher
    :return: Their number
    """
    phone = phone_of(owner_session, people.stranger)
    monkeypatch.setenv(PLATFORM_ADMIN_PHONES_ENV, phone)
    return phone


def _sms_step(client: TestClient, phone: str, texts: list[tuple[str, str]]) -> dict:
    """Ask for a code, read it from the captured SMS, spend it.

    :param client: The HTTP client
    :param phone: The number
    :param texts: The captured sends
    :return: The challenge response body
    """
    assert (
        client.post(
            "/v1/admin/auth/otp", json={"phone": phone}, headers=EDGE
        ).status_code
        == 200
    )
    code = next(part for part in texts[-1][1].split() if part.isdigit())
    verified = client.post(
        "/v1/admin/auth/verify", json={"phone": phone, "code": code}, headers=EDGE
    )
    assert verified.status_code == 200, verified.text
    return verified.json()


def _now_code(secret: str, offset_steps: int = 0) -> str:
    """Compute the code an authenticator app shows now.

    :param secret: The base32 secret
    :param offset_steps: Steps from now
    :return: The code
    """
    return totp.code_at(secret, int(time.time() // 30) + offset_steps)


def _enroll(
    client: TestClient, phone: str, texts: list[tuple[str, str]]
) -> tuple[str, dict]:
    """Complete a first sign-in.

    :param client: The HTTP client
    :param phone: The administrator's number
    :param texts: The captured sends
    :return: The secret and the session body
    """
    challenge = _sms_step(client, phone, texts)
    secret = challenge["enrollment"]["secret"]
    done = client.post(
        "/v1/admin/auth/mfa",
        json={"challenge": challenge["challenge"], "code": _now_code(secret, -1)},
        headers=EDGE,
    )
    assert done.status_code == 200, done.text
    return secret, done.json()


def test_a_first_sign_in_enrolls_then_issues_an_admin_token(
    api_client: TestClient, admin_phone: str, texts: list[tuple[str, str]]
) -> None:
    """SMS, a fresh secret, one code, ten recovery codes, a working token.

    :param api_client: The HTTP client
    :param admin_phone: The administrator's number
    :param texts: The captured sends
    :return: None
    """
    challenge = _sms_step(api_client, admin_phone, texts)
    assert challenge["stage"] == "enroll"
    assert challenge["expires_in"] == 300
    uri = challenge["enrollment"]["otpauth_uri"]
    assert uri.startswith("otpauth://totp/ShikkhokPlus%20Admin%3Aadmin-")
    assert admin_phone not in uri

    secret = challenge["enrollment"]["secret"]
    done = api_client.post(
        "/v1/admin/auth/mfa",
        json={"challenge": challenge["challenge"], "code": _now_code(secret)},
        headers=EDGE,
    )

    assert done.status_code == 200, done.text
    body = done.json()
    assert body["expires_in"] == 3600
    assert len(body["recovery_codes"]) == 10
    overview = api_client.get(
        "/v1/admin/overview",
        headers={**EDGE, "Authorization": f"Bearer {body['access_token']}"},
    )
    assert overview.status_code == 200


def test_a_later_sign_in_asks_for_a_code_and_shows_no_secret(
    api_client: TestClient, admin_phone: str, texts: list[tuple[str, str]]
) -> None:
    """After enrollment the secret is never sent again.

    :param api_client: The HTTP client
    :param admin_phone: The administrator's number
    :param texts: The captured sends
    :return: None
    """
    secret, _ = _enroll(api_client, admin_phone, texts)

    challenge = _sms_step(api_client, admin_phone, texts)

    assert challenge["stage"] == "verify"
    assert challenge["enrollment"] is None
    done = api_client.post(
        "/v1/admin/auth/mfa",
        json={"challenge": challenge["challenge"], "code": _now_code(secret)},
        headers=EDGE,
    )
    assert done.status_code == 200, done.text
    assert done.json()["recovery_codes"] is None


def test_the_secret_is_stored_encrypted(
    api_client: TestClient,
    admin_phone: str,
    texts: list[tuple[str, str]],
    owner_session: Session,
    people: People,
) -> None:
    """The base32 secret appears nowhere in the row.

    :param api_client: The HTTP client
    :param admin_phone: The administrator's number
    :param texts: The captured sends
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :return: None
    """
    secret, _ = _enroll(api_client, admin_phone, texts)
    row = owner_session.execute(
        sa.text("SELECT secret_ciphertext FROM mfa_factor WHERE account_id = :a"),
        {"a": people.stranger},
    ).scalar_one()
    assert secret.encode() not in bytes(row)
    assert len(bytes(row)) > 12 + len(secret)


def test_the_same_code_cannot_be_used_twice(
    api_client: TestClient, admin_phone: str, texts: list[tuple[str, str]]
) -> None:
    """A code seen over a shoulder is spent once it has been used.

    :param api_client: The HTTP client
    :param admin_phone: The administrator's number
    :param texts: The captured sends
    :return: None
    """
    secret, _ = _enroll(api_client, admin_phone, texts)
    code = _now_code(secret)
    first = _sms_step(api_client, admin_phone, texts)
    ok = api_client.post(
        "/v1/admin/auth/mfa",
        json={"challenge": first["challenge"], "code": code},
        headers=EDGE,
    )
    assert ok.status_code == 200

    second = _sms_step(api_client, admin_phone, texts)
    replay = api_client.post(
        "/v1/admin/auth/mfa",
        json={"challenge": second["challenge"], "code": code},
        headers=EDGE,
    )
    assert replay.status_code == 400
    assert replay.json()["error"]["code"] == "ADMIN_MFA_WRONG"


def test_a_recovery_code_works_once(
    api_client: TestClient, admin_phone: str, texts: list[tuple[str, str]]
) -> None:
    """Each recovery code signs in once, typed however the person types it.

    :param api_client: The HTTP client
    :param admin_phone: The administrator's number
    :param texts: The captured sends
    :return: None
    """
    _, enrolled = _enroll(api_client, admin_phone, texts)
    code = enrolled["recovery_codes"][3]

    first = _sms_step(api_client, admin_phone, texts)
    used = api_client.post(
        "/v1/admin/auth/mfa",
        json={
            "challenge": first["challenge"],
            "recovery_code": code.lower().replace("-", ""),
        },
        headers=EDGE,
    )
    assert used.status_code == 200, used.text

    second = _sms_step(api_client, admin_phone, texts)
    again = api_client.post(
        "/v1/admin/auth/mfa",
        json={"challenge": second["challenge"], "recovery_code": code},
        headers=EDGE,
    )
    assert again.status_code == 400


def test_enrollment_does_not_accept_a_recovery_code(
    api_client: TestClient, admin_phone: str, texts: list[tuple[str, str]]
) -> None:
    """A first sign-in must prove the app works; there are no codes yet.

    :param api_client: The HTTP client
    :param admin_phone: The administrator's number
    :param texts: The captured sends
    :return: None
    """
    challenge = _sms_step(api_client, admin_phone, texts)
    response = api_client.post(
        "/v1/admin/auth/mfa",
        json={"challenge": challenge["challenge"], "recovery_code": "ABCDE-FGHJK"},
        headers=EDGE,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ADMIN_MFA_INPUT"


def test_wrong_codes_lock_the_factor_even_against_the_right_one(
    api_client: TestClient,
    admin_phone: str,
    texts: list[tuple[str, str]],
    owner_session: Session,
    people: People,
) -> None:
    """The limit counts across challenges and survives the failed requests.

    :param api_client: The HTTP client
    :param admin_phone: The administrator's number
    :param texts: The captured sends
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :return: None
    """
    secret, _ = _enroll(api_client, admin_phone, texts)
    # Two challenges, the wrong codes split across them: the count is the
    # factor's, so a fresh SMS code does not reset it.
    first = _sms_step(api_client, admin_phone, texts)
    second = _sms_step(api_client, admin_phone, texts)
    for attempt in range(MAX_FAILED_ATTEMPTS):
        challenge = first if attempt < 2 else second
        wrong = api_client.post(
            "/v1/admin/auth/mfa",
            json={"challenge": challenge["challenge"], "code": "000000"},
            headers=EDGE,
        )
        expected = 409 if attempt == MAX_FAILED_ATTEMPTS - 1 else 400
        assert wrong.status_code == expected, attempt

    challenge = second
    right = api_client.post(
        "/v1/admin/auth/mfa",
        json={"challenge": challenge["challenge"], "code": _now_code(secret)},
        headers=EDGE,
    )
    assert right.status_code == 409
    assert right.json()["error"]["code"] == "ADMIN_MFA_LOCKED"
    events = owner_session.execute(
        sa.text(
            "SELECT event, count(*) FROM auth_audit_log WHERE account_id = :a "
            "AND event LIKE 'ADMIN_%' GROUP BY event"
        ),
        {"a": people.stranger},
    ).all()
    counts = dict(events)
    assert counts["ADMIN_MFA_FAILED"] == MAX_FAILED_ATTEMPTS - 1
    assert counts["ADMIN_MFA_LOCKED"] == 1


def test_an_enroll_challenge_cannot_re_enroll_a_confirmed_factor(
    api_client: TestClient, admin_phone: str, texts: list[tuple[str, str]]
) -> None:
    """A challenge minted before confirmation is dead after it.

    Otherwise a stolen SMS code plus an old enroll challenge could set up
    a second authenticator.

    :param api_client: The HTTP client
    :param admin_phone: The administrator's number
    :param texts: The captured sends
    :return: None
    """
    stale = _sms_step(api_client, admin_phone, texts)
    secret = stale["enrollment"]["secret"]
    fresh = _sms_step(api_client, admin_phone, texts)
    new_secret = fresh["enrollment"]["secret"]
    assert new_secret != secret
    ok = api_client.post(
        "/v1/admin/auth/mfa",
        json={"challenge": fresh["challenge"], "code": _now_code(new_secret)},
        headers=EDGE,
    )
    assert ok.status_code == 200

    replayed = api_client.post(
        "/v1/admin/auth/mfa",
        json={"challenge": stale["challenge"], "code": _now_code(new_secret, 1)},
        headers=EDGE,
    )
    assert replayed.status_code == 401
    assert replayed.json()["error"]["code"] == "ADMIN_CHALLENGE_INVALID"


def test_a_challenge_is_not_an_admin_token(
    api_client: TestClient, admin_phone: str, texts: list[tuple[str, str]]
) -> None:
    """The SMS step alone reaches nothing.

    :param api_client: The HTTP client
    :param admin_phone: The administrator's number
    :param texts: The captured sends
    :return: None
    """
    challenge = _sms_step(api_client, admin_phone, texts)
    response = api_client.get(
        "/v1/admin/overview",
        headers={**EDGE, "Authorization": f"Bearer {challenge['challenge']}"},
    )
    assert response.status_code == 401


def test_a_non_admin_is_never_texted_and_gets_the_same_answer(
    api_client: TestClient,
    admin_phone: str,
    texts: list[tuple[str, str]],
    owner_session: Session,
    people: People,
) -> None:
    """The SMS step says nothing about who is an administrator.

    :param api_client: The HTTP client
    :param admin_phone: The administrator's number
    :param texts: The captured sends
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :return: None
    """
    teacher = phone_of(owner_session, people.teacher.account_id)
    unknown = "+8801799999998"
    answers = [
        api_client.post("/v1/admin/auth/otp", json={"phone": n}, headers=EDGE)
        for n in (admin_phone, teacher, unknown)
    ]
    assert {a.status_code for a in answers} == {200}
    assert len({a.content for a in answers}) == 1
    assert [n for n, _ in texts] == [admin_phone]


def test_removing_the_number_ends_a_live_session(
    api_client: TestClient,
    admin_phone: str,
    texts: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The allowlist is checked per request, not when the token was issued.

    :param api_client: The HTTP client
    :param admin_phone: The administrator's number
    :param texts: The captured sends
    :param monkeypatch: The patcher
    :return: None
    """
    _, enrolled = _enroll(api_client, admin_phone, texts)
    headers = {**EDGE, "Authorization": f"Bearer {enrolled['access_token']}"}
    assert api_client.get("/v1/admin/overview", headers=headers).status_code == 200

    monkeypatch.setenv(PLATFORM_ADMIN_PHONES_ENV, "")

    assert api_client.get("/v1/admin/overview", headers=headers).status_code == 403


def test_an_admin_token_is_refused_on_app_routes(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    admin_phone: str,
) -> None:
    """It cannot be used as an app session either.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :param admin_phone: The administrator's number
    :return: None
    """
    headers = admin_headers(owner_session, people.stranger)
    assert api_client.get("/v1/me", headers=headers).status_code == 401
    assert api_client.get("/v1/me/help/tickets", headers=headers).status_code == 401


def test_an_unconfirmed_factor_does_not_qualify(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    admin_phone: str,
) -> None:
    """An admin token is worthless once the factor is reset.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :param admin_phone: The administrator's number
    :return: None
    """
    headers = admin_headers(owner_session, people.stranger, confirmed=False)
    assert api_client.get("/v1/admin/overview", headers=headers).status_code == 403


@pytest.mark.parametrize(
    ("dropped", "replaced"),
    [
        ("X-Admin-Edge", None),
        (None, ("X-Admin-Edge", "wrong-secret")),
        ("X-Client-Address", None),
        (None, ("X-Client-Address", "192.0.2.50")),
        (None, ("X-Client-Address", "not-an-ip")),
    ],
)
def test_off_the_admin_hostname_every_admin_route_is_404(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    admin_phone: str,
    dropped: str | None,
    replaced: tuple[str, str] | None,
) -> None:
    """Without the edge secret, or from outside the network: not there.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :param admin_phone: The administrator's number
    :param dropped: A header to remove
    :param replaced: A header to change
    :return: None
    """
    headers = admin_headers(owner_session, people.stranger)
    if dropped:
        headers.pop(dropped)
    if replaced:
        headers[replaced[0]] = replaced[1]
    paths = [
        ("GET", "/v1/admin/overview", None),
        ("POST", "/v1/admin/auth/otp", {"phone": admin_phone}),
        ("POST", "/v1/admin/auth/verify", {"phone": admin_phone, "code": "123456"}),
        ("POST", "/v1/admin/auth/mfa", {"challenge": "x", "code": "123456"}),
    ]
    for method, path, body in paths:
        response = api_client.request(method, path, json=body, headers=headers)
        assert response.status_code == 404, (method, path)


def test_a_second_allowed_network_is_admitted(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    admin_phone: str,
) -> None:
    """Every configured network counts, including a single /32.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :param admin_phone: The administrator's number
    :return: None
    """
    headers = {
        **admin_headers(owner_session, people.stranger),
        "X-Client-Address": "198.51.100.10",
    }
    assert api_client.get("/v1/admin/overview", headers=headers).status_code == 200
    headers["X-Client-Address"] = "198.51.100.11"
    assert api_client.get("/v1/admin/overview", headers=headers).status_code == 404


def test_an_app_sms_code_cannot_start_an_admin_sign_in(
    api_client: TestClient,
    admin_phone: str,
    texts: list[tuple[str, str]],
) -> None:
    """Codes are purpose-bound: app sign-in codes do not cross over.

    :param api_client: The HTTP client
    :param admin_phone: The administrator's number
    :param texts: The captured sends
    :return: None
    """
    api_client.post("/v1/auth/otp", json={"phone": admin_phone})
    app_code = next(part for part in texts[-1][1].split() if part.isdigit())
    crossed = api_client.post(
        "/v1/admin/auth/verify",
        json={"phone": admin_phone, "code": app_code},
        headers=EDGE,
    )
    assert crossed.status_code != 200


def test_an_app_token_carries_no_audience(
    api_client: TestClient, owner_session: Session, people: People
) -> None:
    """Guard the distinction itself: app tokens stay audience-free.

    :param api_client: Configures the signing environment
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :return: None
    """
    import jwt

    token = bearer(owner_session, people.stranger)["Authorization"].split()[1]
    owner_session.commit()
    assert "aud" not in jwt.decode(token, options={"verify_signature": False})


def test_the_sign_in_routes_need_no_lens_but_record_who_signed_in(
    api_client: TestClient,
    admin_phone: str,
    texts: list[tuple[str, str]],
    owner_session: Session,
    people: People,
) -> None:
    """Enrollment and sign-in each leave an audit row.

    :param api_client: The HTTP client
    :param admin_phone: The administrator's number
    :param texts: The captured sends
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :return: None
    """
    _enroll(api_client, admin_phone, texts)
    events = {
        row[0]
        for row in owner_session.execute(
            sa.text("SELECT event FROM auth_audit_log WHERE account_id = :a"),
            {"a": people.stranger},
        )
    }
    assert {"ADMIN_MFA_ENROLLED", "ADMIN_SIGNED_IN"} <= events
    assert dt.datetime.now(tz=dt.UTC) > dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    assert uuid.UUID(str(people.stranger))
