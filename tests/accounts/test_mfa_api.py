"""Two-step verification for app accounts, over HTTP.

**Written to the authentication predicate.** Each test names one way the
second factor could be skipped, replayed, guessed, removed by a stolen
session or bypassed at another door -- sign-in, settings, the public
deletion page -- and asserts it is refused. Codes are computed from the
secret the setup step returned, as an authenticator app would.
"""

from __future__ import annotations

import base64
import datetime as dt
import os
import time
import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import totp
from app.auth.mfa import MAX_FAILED_ATTEMPTS
from app.auth.mfa_crypto import MFA_ACTIVE_KID_ENV, MFA_KEYS_ENV
from app.authz.admin import PLATFORM_ADMIN_PHONES_ENV
from app.gateway.null import NullGateway
from tests.batches.conftest import make_teacher
from tests.conftest import bearer


@pytest.fixture(autouse=True)
def keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure the MFA keyring.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(MFA_KEYS_ENV, "k1:" + base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv(MFA_ACTIVE_KID_ENV, "k1")


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


def _account(session: Session) -> tuple[uuid.UUID, str]:
    """Arrange a signed-up account.

    :param session: An arranging session
    :return: Its id and phone
    """
    phone = f"+88017{uuid.uuid4().int % 10**8:08d}"
    now = dt.datetime.now(tz=dt.UTC)
    account_id = uuid.uuid4()
    session.execute(
        sa.text(
            "INSERT INTO account (id, phone, created_at, activated_at) "
            "VALUES (:id, :p, :now, :now)"
        ),
        {"id": account_id, "p": phone, "now": now},
    )
    session.commit()
    return account_id, phone


def _auth(session: Session, account_id: uuid.UUID) -> dict[str, str]:
    """Mint an app session for an account and release the arranging lock.

    :param session: An arranging session
    :param account_id: The account
    :return: Its headers
    """
    headers = bearer(session, account_id)
    session.commit()
    return headers


def _now_code(secret: str, offset: int = 0) -> str:
    """Compute the code an authenticator app shows now.

    :param secret: The base32 secret
    :param offset: Steps from now
    :return: The code
    """
    return totp.code_at(secret, int(time.time() // 30) + offset)


def _turn_on(client: TestClient, headers: dict[str, str]) -> tuple[str, list[str]]:
    """Turn two-step verification on through the settings routes.

    :param client: The HTTP client
    :param headers: The account's session
    :return: The secret and the recovery codes
    """
    setup = client.post("/v1/me/mfa/setup", headers=headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    confirmed = client.post(
        "/v1/me/mfa/confirm", json={"code": _now_code(secret, -1)}, headers=headers
    )
    assert confirmed.status_code == 200, confirmed.text
    return secret, confirmed.json()["recovery_codes"]


def _sms_verify(client: TestClient, phone: str, texts: list[tuple[str, str]]) -> dict:
    """Sign in by SMS and return the verify response.

    :param client: The HTTP client
    :param phone: The number
    :param texts: The captured sends
    :return: The verify body
    """
    assert client.post("/v1/auth/otp", json={"phone": phone}).status_code == 200
    code = next(part for part in texts[-1][1].split() if part.isdigit())
    verified = client.post("/v1/auth/verify", json={"phone": phone, "code": code})
    assert verified.status_code == 200, verified.text
    return verified.json()


def test_it_is_off_by_default_and_recommended_only_to_teachers(
    api_client: TestClient, owner_session: Session
) -> None:
    """A teacher is told it is recommended; anyone else is not.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    student, _ = _account(owner_session)
    for account, recommended in ((teacher.account_id, True), (student, False)):
        body = api_client.get(
            "/v1/me/mfa", headers=_auth(owner_session, account)
        ).json()
        assert body == {
            "enabled": False,
            "enabled_at": None,
            "recovery_codes_left": 0,
            "recommended": recommended,
            "required": False,
        }


def test_turning_it_on_needs_a_working_code(
    api_client: TestClient, owner_session: Session
) -> None:
    """A wrong first code leaves it off; a right one turns it on.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :return: None
    """
    account, _ = _account(owner_session)
    headers = _auth(owner_session, account)
    setup = api_client.post("/v1/me/mfa/setup", headers=headers).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/ShikkhokPlus%3Aaccount-")

    wrong = api_client.post(
        "/v1/me/mfa/confirm", json={"code": "000000"}, headers=headers
    )
    assert wrong.status_code == 400
    assert wrong.json()["error"]["message_key"] == "mfa.code_wrong"
    assert api_client.get("/v1/me/mfa", headers=headers).json()["enabled"] is False

    right = api_client.post(
        "/v1/me/mfa/confirm", json={"code": _now_code(setup["secret"])}, headers=headers
    )
    assert right.status_code == 200
    assert len(right.json()["recovery_codes"]) == 10
    status = api_client.get("/v1/me/mfa", headers=headers).json()
    assert status["enabled"] is True
    assert status["recovery_codes_left"] == 10

    again = api_client.post("/v1/me/mfa/setup", headers=headers)
    assert again.status_code == 409
    assert again.json()["error"]["message_key"] == "mfa.already_enabled"


def test_confirming_without_setup_is_refused(
    api_client: TestClient, owner_session: Session
) -> None:
    """There is nothing to confirm until setup has run.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :return: None
    """
    account, _ = _account(owner_session)
    response = api_client.post(
        "/v1/me/mfa/confirm",
        json={"code": "123456"},
        headers=_auth(owner_session, account),
    )
    assert response.status_code == 409
    assert response.json()["error"]["message_key"] == "mfa.setup_not_started"


def test_sign_in_without_it_is_unchanged(
    api_client: TestClient, owner_session: Session, texts: list[tuple[str, str]]
) -> None:
    """Accounts that never turned it on get their tokens as before.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param texts: The captured sends
    :return: None
    """
    _, phone = _account(owner_session)
    body = _sms_verify(api_client, phone, texts)
    assert body["mfa_required"] is False
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] == 900


def test_sign_in_with_it_needs_the_second_step(
    api_client: TestClient, owner_session: Session, texts: list[tuple[str, str]]
) -> None:
    """The SMS code yields a challenge, never tokens; the code yields tokens.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param texts: The captured sends
    :return: None
    """
    account, phone = _account(owner_session)
    secret, _ = _turn_on(api_client, _auth(owner_session, account))

    body = _sms_verify(api_client, phone, texts)

    assert body["mfa_required"] is True
    assert body["access_token"] is None and body["refresh_token"] is None
    assert body["mfa_expires_in"] == 300
    challenge_as_token = api_client.get(
        "/v1/me", headers={"Authorization": f"Bearer {body['mfa_challenge']}"}
    )
    assert challenge_as_token.status_code == 401

    done = api_client.post(
        "/v1/auth/mfa",
        json={"challenge": body["mfa_challenge"], "code": _now_code(secret)},
        headers={"X-Client-Platform": "android"},
    )
    assert done.status_code == 200, done.text
    tokens = done.json()
    assert (
        api_client.get(
            "/v1/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        ).status_code
        == 200
    )
    rotated = api_client.post(
        "/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200
    platform = owner_session.execute(
        sa.text("SELECT platform FROM account_client WHERE account_id = :a"),
        {"a": account},
    ).scalar_one()
    assert platform == "android"


def test_a_recovery_code_signs_in_once(
    api_client: TestClient, owner_session: Session, texts: list[tuple[str, str]]
) -> None:
    """For a lost phone: each recovery code works exactly once.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param texts: The captured sends
    :return: None
    """
    account, phone = _account(owner_session)
    _, codes = _turn_on(api_client, _auth(owner_session, account))

    first = _sms_verify(api_client, phone, texts)
    used = api_client.post(
        "/v1/auth/mfa",
        json={"challenge": first["mfa_challenge"], "recovery_code": codes[0]},
    )
    assert used.status_code == 200

    second = _sms_verify(api_client, phone, texts)
    again = api_client.post(
        "/v1/auth/mfa",
        json={"challenge": second["mfa_challenge"], "recovery_code": codes[0]},
    )
    assert again.status_code == 400
    assert again.json()["error"]["message_key"] == "mfa.code_wrong"


def test_a_bad_or_foreign_challenge_restarts_sign_in(
    api_client: TestClient, owner_session: Session
) -> None:
    """Garbage, an app token, or an admin challenge: all 401, restart.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :return: None
    """
    from app.auth.tokens import (
        MFA_CHALLENGE_AUDIENCE,
        MFA_CHALLENGE_LIFETIME,
        issue_scoped_token,
    )

    account, _ = _account(owner_session)
    _turn_on(api_client, _auth(owner_session, account))
    admin_challenge = issue_scoped_token(
        account, MFA_CHALLENGE_AUDIENCE, MFA_CHALLENGE_LIFETIME, {"stage": "verify"}
    )
    app_token = _auth(owner_session, account)["Authorization"].split()[1]
    for challenge in ("not-a-token", app_token, admin_challenge):
        response = api_client.post(
            "/v1/auth/mfa", json={"challenge": challenge, "code": "123456"}
        )
        assert response.status_code == 401, challenge[:20]
        assert response.json()["error"]["message_key"] == "mfa.challenge_expired"


def test_a_challenge_minted_before_turning_it_off_is_dead(
    api_client: TestClient, owner_session: Session, texts: list[tuple[str, str]]
) -> None:
    """Turning it off mid-sign-in ends that sign-in.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param texts: The captured sends
    :return: None
    """
    account, phone = _account(owner_session)
    headers = _auth(owner_session, account)
    secret, _ = _turn_on(api_client, headers)
    pending = _sms_verify(api_client, phone, texts)
    api_client.post(
        "/v1/me/mfa/disable", json={"code": _now_code(secret)}, headers=headers
    )
    response = api_client.post(
        "/v1/auth/mfa",
        json={"challenge": pending["mfa_challenge"], "code": _now_code(secret, 1)},
    )
    assert response.status_code == 401


def test_wrong_codes_lock_sign_in_across_challenges(
    api_client: TestClient, owner_session: Session, texts: list[tuple[str, str]]
) -> None:
    """Five wrong codes lock the factor, even against the right code.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param texts: The captured sends
    :return: None
    """
    account, phone = _account(owner_session)
    secret, _ = _turn_on(api_client, _auth(owner_session, account))
    first = _sms_verify(api_client, phone, texts)["mfa_challenge"]
    second = _sms_verify(api_client, phone, texts)["mfa_challenge"]
    for attempt in range(MAX_FAILED_ATTEMPTS):
        challenge = first if attempt < 2 else second
        wrong = api_client.post(
            "/v1/auth/mfa", json={"challenge": challenge, "code": "000000"}
        )
        expected = 409 if attempt == MAX_FAILED_ATTEMPTS - 1 else 400
        assert wrong.status_code == expected, attempt
    right = api_client.post(
        "/v1/auth/mfa", json={"challenge": second, "code": _now_code(secret)}
    )
    assert right.status_code == 409
    assert right.json()["error"]["message_key"] == "mfa.locked"


def test_the_same_code_cannot_sign_in_twice(
    api_client: TestClient, owner_session: Session, texts: list[tuple[str, str]]
) -> None:
    """A code seen over a shoulder is spent once used.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param texts: The captured sends
    :return: None
    """
    account, phone = _account(owner_session)
    secret, _ = _turn_on(api_client, _auth(owner_session, account))
    code = _now_code(secret)
    first = _sms_verify(api_client, phone, texts)["mfa_challenge"]
    assert (
        api_client.post(
            "/v1/auth/mfa", json={"challenge": first, "code": code}
        ).status_code
        == 200
    )
    second = _sms_verify(api_client, phone, texts)["mfa_challenge"]
    assert (
        api_client.post(
            "/v1/auth/mfa", json={"challenge": second, "code": code}
        ).status_code
        == 400
    )


def test_turning_it_off_needs_the_factor_not_just_the_session(
    api_client: TestClient, owner_session: Session, texts: list[tuple[str, str]]
) -> None:
    """A stolen, signed-in phone cannot remove the second factor.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param texts: The captured sends
    :return: None
    """
    account, phone = _account(owner_session)
    headers = _auth(owner_session, account)
    secret, codes = _turn_on(api_client, headers)

    for body in ({}, {"code": "000000"}, {"code": "1", "recovery_code": "x"}):
        refused = api_client.post("/v1/me/mfa/disable", json=body, headers=headers)
        assert refused.status_code in (400, 422), body
    assert api_client.get("/v1/me/mfa", headers=headers).json()["enabled"] is True

    off = api_client.post(
        "/v1/me/mfa/disable", json={"recovery_code": codes[1]}, headers=headers
    )
    assert off.status_code == 200
    assert off.json()["enabled"] is False
    left = owner_session.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM mfa_factor WHERE account_id = :a), "
            "(SELECT count(*) FROM mfa_recovery_code WHERE account_id = :a)"
        ),
        {"a": account},
    ).one()
    assert tuple(left) == (0, 0)
    assert _sms_verify(api_client, phone, texts)["mfa_required"] is False
    assert secret


def test_an_administrator_cannot_turn_it_off(
    api_client: TestClient,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admin door requires the factor, so the app will not remove it.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param monkeypatch: The patcher
    :return: None
    """
    account, phone = _account(owner_session)
    monkeypatch.setenv(PLATFORM_ADMIN_PHONES_ENV, phone)
    headers = _auth(owner_session, account)
    secret, _ = _turn_on(api_client, headers)
    assert api_client.get("/v1/me/mfa", headers=headers).json()["required"] is True

    response = api_client.post(
        "/v1/me/mfa/disable", json={"code": _now_code(secret)}, headers=headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["message_key"] == "mfa.required_for_admin"


def test_new_recovery_codes_retire_the_old_ones(
    api_client: TestClient, owner_session: Session, texts: list[tuple[str, str]]
) -> None:
    """A fresh set replaces, never adds to, the previous one.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param texts: The captured sends
    :return: None
    """
    account, phone = _account(owner_session)
    headers = _auth(owner_session, account)
    secret, old = _turn_on(api_client, headers)

    renewed = api_client.post(
        "/v1/me/mfa/recovery-codes", json={"code": _now_code(secret)}, headers=headers
    )
    assert renewed.status_code == 200
    new = renewed.json()["recovery_codes"]
    assert not set(new) & set(old)

    challenge = _sms_verify(api_client, phone, texts)["mfa_challenge"]
    stale = api_client.post(
        "/v1/auth/mfa", json={"challenge": challenge, "recovery_code": old[0]}
    )
    assert stale.status_code == 400
    fresh = api_client.post(
        "/v1/auth/mfa", json={"challenge": challenge, "recovery_code": new[0]}
    )
    assert fresh.status_code == 200


def test_settings_routes_need_a_session(api_client: TestClient) -> None:
    """None of them is reachable signed out.

    :param api_client: The HTTP client
    :return: None
    """
    assert api_client.get("/v1/me/mfa").status_code == 401
    for path, body in (
        ("/v1/me/mfa/setup", None),
        ("/v1/me/mfa/confirm", {"code": "123456"}),
        ("/v1/me/mfa/disable", {"code": "123456"}),
        ("/v1/me/mfa/recovery-codes", {"code": "123456"}),
    ):
        assert api_client.post(path, json=body).status_code == 401, path


def _deletion_code(client: TestClient, phone: str, texts: list[tuple[str, str]]) -> str:
    """Ask the public deletion page for a code and read it.

    :param client: The HTTP client
    :param phone: The number
    :param texts: The captured sends
    :return: The code
    """
    assert client.post("/account-deletion", json={"phone": phone}).status_code == 200
    return next(part for part in texts[-1][1].split() if part.isdigit())


def test_the_deletion_page_needs_the_second_factor_too(
    api_client: TestClient, owner_session: Session, texts: list[tuple[str, str]]
) -> None:
    """A SIM swap alone cannot delete an account its owner protected.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param texts: The captured sends
    :return: None
    """
    account, phone = _account(owner_session)
    secret, _ = _turn_on(api_client, _auth(owner_session, account))

    refused = api_client.post(
        "/account-deletion",
        json={"phone": phone, "code": _deletion_code(api_client, phone, texts)},
    )
    assert refused.status_code == 400
    assert refused.json()["error"]["message_key"] == "mfa.code_required"
    wrong = api_client.post(
        "/account-deletion",
        json={
            "phone": phone,
            "code": _deletion_code(api_client, phone, texts),
            "authenticator_code": "000000",
        },
    )
    assert wrong.status_code == 400
    assert wrong.json()["error"]["message_key"] == "mfa.code_wrong"
    still = owner_session.execute(
        sa.text("SELECT count(*) FROM account WHERE id = :a"), {"a": account}
    ).scalar_one()
    assert still == 1

    deleted = api_client.post(
        "/account-deletion",
        json={
            "phone": phone,
            "code": _deletion_code(api_client, phone, texts),
            "authenticator_code": _now_code(secret),
        },
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["status"] == "deleted"
    gone = owner_session.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM account WHERE id = :a), "
            "(SELECT count(*) FROM mfa_factor WHERE account_id = :a)"
        ),
        {"a": account},
    ).one()
    assert tuple(gone) == (0, 0)


def test_the_deletion_form_explains_the_second_factor(
    api_client: TestClient, owner_session: Session, texts: list[tuple[str, str]]
) -> None:
    """The browser form says what to do, in words, without the app.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param texts: The captured sends
    :return: None
    """
    page = api_client.get("/account-deletion")
    assert 'name="authenticator_code"' in page.text

    account, phone = _account(owner_session)
    _turn_on(api_client, _auth(owner_session, account))
    code = _deletion_code(api_client, phone, texts)
    response = api_client.post(
        "/account-deletion",
        content=f"phone={phone.replace('+', '%2B')}&code={code}&authenticator_code=",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 400
    assert "two-step verification on" in response.text


def test_a_recovery_code_works_on_the_deletion_page(
    api_client: TestClient, owner_session: Session, texts: list[tuple[str, str]]
) -> None:
    """Someone who lost the phone with the app can still delete.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param texts: The captured sends
    :return: None
    """
    account, phone = _account(owner_session)
    _, codes = _turn_on(api_client, _auth(owner_session, account))
    response = api_client.post(
        "/account-deletion",
        json={
            "phone": phone,
            "code": _deletion_code(api_client, phone, texts),
            "authenticator_code": codes[2],
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"


def test_the_audit_log_records_each_step(
    api_client: TestClient, owner_session: Session, texts: list[tuple[str, str]]
) -> None:
    """On, a verified sign-in, a failure and off each leave a row.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param texts: The captured sends
    :return: None
    """
    account, phone = _account(owner_session)
    headers = _auth(owner_session, account)
    secret, _ = _turn_on(api_client, headers)
    challenge = _sms_verify(api_client, phone, texts)["mfa_challenge"]
    api_client.post("/v1/auth/mfa", json={"challenge": challenge, "code": "000000"})
    api_client.post(
        "/v1/auth/mfa", json={"challenge": challenge, "code": _now_code(secret)}
    )
    api_client.post(
        "/v1/me/mfa/disable", json={"code": _now_code(secret, 1)}, headers=headers
    )
    events = {
        row[0]
        for row in owner_session.execute(
            sa.text(
                "SELECT event FROM auth_audit_log WHERE account_id = :a "
                "AND event LIKE 'MFA_%'"
            ),
            {"a": account},
        )
    }
    assert events == {"MFA_ENROLLED", "MFA_FAILED", "MFA_VERIFIED", "MFA_DISABLED"}
