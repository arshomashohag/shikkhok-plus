"""Email sign-up, password sign-in, and the code flow that sets a password.

**Written to the authentication predicate** [team: Testing Posture]: who
a code or a password signs in is knowable from the inputs alone, and a
wrong answer is an authorization error. Each test names one way the new
surface could let somebody in who should not be, or tell somebody what
they should not learn, and asserts it does not:

* a verified code never yields a session by itself [0032];
* a password sign-in answers an unknown account, an account with no
  password and a wrong password identically;
* a setup token is spent by the password it sets;
* an authenticator factor is not skipped by recovering a password;
* changing a password needs the current one, and ends every session;
* a phone number reaches an email-only account's seats only once proved.
"""

from __future__ import annotations

import base64
import datetime as dt
import os
import time
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import totp
from app.auth.ceilings import PASSWORD_FAILURES_PER_IDENTIFIER_HOURLY
from app.auth.mfa_crypto import MFA_ACTIVE_KID_ENV, MFA_KEYS_ENV
from app.auth.passwords import hash_password
from app.gateway.email import EmailMessage, NullEmailGateway
from app.gateway.null import NullGateway
from tests.accounts.signup_support import submit_signup
from tests.batches.conftest import make_teacher
from tests.conftest import bearer

PASSWORD = "a long enough passphrase"  # noqa: S105 -- a test value


@pytest.fixture(autouse=True)
def keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure the MFA keyring, for the tests that turn a factor on.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(MFA_KEYS_ENV, "k1:" + base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv(MFA_ACTIVE_KID_ENV, "k1")


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple[str, str]]]:
    """Capture every text and email the null gateways are asked to send.

    :param monkeypatch: The patcher
    :return: ``(destination, body)`` per send
    """
    captured: list[tuple[str, str]] = []
    sms = NullGateway.send
    email = NullEmailGateway.send

    def capture_sms(
        self: NullGateway, number: str, message: str, correlation_id: str
    ) -> object:
        captured.append((number, message))
        return sms(self, number, message, correlation_id)

    def capture_email(
        self: NullEmailGateway, address: str, message: EmailMessage, cid: str
    ) -> object:
        captured.append((address, message.text))
        return email(self, address, message, cid)

    monkeypatch.setattr(NullGateway, "send", capture_sms)
    monkeypatch.setattr(NullEmailGateway, "send", capture_email)
    yield captured


def _code_for(sent: list[tuple[str, str]], destination: str) -> str:
    """Read the latest code sent to one destination.

    :param sent: The captured sends
    :param destination: The number or address
    :return: The six-digit code
    """
    body = next(text for to, text in reversed(sent) if to == destination)
    return next(part for part in body.split() if part.isdigit() and len(part) == 6)


def _number() -> str:
    """Return a fresh canonical mobile number.

    :return: ``+88017`` and eight random digits
    """
    return f"+88017{uuid.uuid4().int % 10**8:08d}"


def _address() -> str:
    """Return a fresh email address.

    :return: A unique address
    """
    return f"person-{uuid.uuid4().hex[:10]}@example.com"


def _form(**identifier: str) -> dict[str, str]:
    """Build a signup form for one identifier.

    :param identifier: ``phone=...`` or ``email=...``
    :return: The request body
    """
    return {
        **identifier,
        "role": "teacher",
        "self_name": "Nasrin",
        "address_house": "House 12",
        "address_road": "Road 5",
        "address_city": "Dhaka",
        "address_postcode": "1205",
    }


def _account(
    session: Session, *, phone: str | None = None, password: str | None = None
) -> tuple[uuid.UUID, str]:
    """Arrange an account, with or without a password.

    :param session: An arranging session
    :param phone: Its number, or None for a fresh one
    :param password: Its password, or None for an account that has none
    :return: Its id and its number
    """
    number = phone or _number()
    account_id = uuid.uuid4()
    now = dt.datetime.now(tz=dt.UTC)
    session.execute(
        sa.text(
            "INSERT INTO account (id, phone, password_hash, password_changed_at, "
            "created_at, activated_at) VALUES (:id, :p, :h, :c, :now, :now)"
        ),
        {
            "id": account_id,
            "p": number,
            "h": hash_password(password) if password else None,
            "c": now if password else None,
            "now": now,
        },
    )
    session.commit()
    return account_id, number


def _verify(
    client: TestClient, sent: list[tuple[str, str]], **identifier: str
) -> dict[str, object]:
    """Request a code and verify it, returning the verify body.

    :param client: The HTTP client
    :param sent: The captured sends
    :param identifier: ``phone=...`` or ``email=...``
    :return: The verify response body
    """
    assert client.post("/v1/auth/otp", json=identifier).status_code == 200
    code = _code_for(sent, next(iter(identifier.values())))
    verified = client.post("/v1/auth/verify", json={**identifier, "code": code})
    assert verified.status_code == 200, verified.text
    body: dict[str, object] = verified.json()
    return body


# ---------------------------------------------------------------- email signup


def test_an_email_signup_is_verified_by_email_and_finished_with_a_password(
    api_client: TestClient, owner_session: Session, sent: list[tuple[str, str]]
) -> None:
    """The whole sign-up, by email, as a client makes it.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param sent: The captured sends
    :return: None
    """
    address = _address()
    response, code = submit_signup(api_client, _form(email="  " + address.upper()))
    assert response.status_code == 201, response.text
    assert response.json()["code_sent_to"] == address
    assert code is not None

    verified = api_client.post("/v1/auth/verify", json={"email": address, "code": code})
    assert verified.status_code == 200, verified.text
    grant = verified.json()
    # A code never signs anyone in by itself.
    assert grant["access_token"] is None and grant["refresh_token"] is None
    assert grant["password_setup_token"] and grant["mfa_required"] is False

    pair = api_client.post(
        "/v1/auth/password/setup",
        json={"token": grant["password_setup_token"], "password": PASSWORD},
    )
    assert pair.status_code == 200, pair.text

    me = api_client.get(
        "/v1/me", headers={"Authorization": f"Bearer {pair.json()['access_token']}"}
    ).json()
    assert me["email"] == address
    assert me["phone"] is None
    assert me["has_password"] is True

    signed_in = api_client.post(
        "/v1/auth/password", json={"email": address, "password": PASSWORD}
    )
    assert signed_in.status_code == 200
    assert signed_in.json()["access_token"]


def test_a_signup_naming_both_or_neither_is_refused(api_client: TestClient) -> None:
    """Exactly one of phone and email.

    :param api_client: The HTTP client
    :return: None
    """
    both = api_client.post(
        "/v1/accounts", json=_form(phone=_number(), email=_address())
    )
    neither = api_client.post("/v1/accounts", json=_form())
    assert both.status_code == 422
    assert neither.status_code == 422


def test_a_malformed_email_is_refused_with_its_own_key(api_client: TestClient) -> None:
    """The client shows the remedy under the field.

    :param api_client: The HTTP client
    :return: None
    """
    refused = api_client.post("/v1/auth/otp", json={"email": "not-an-address"})
    assert refused.status_code == 400
    assert refused.json()["error"]["message_key"] == "email.invalid"


# ------------------------------------------------------------ password sign-in


def test_every_failed_sign_in_gets_the_same_answer(
    api_client: TestClient, owner_session: Session
) -> None:
    """Unknown, no password yet, and wrong password are one refusal.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :return: None
    """
    _, without = _account(owner_session)
    _, with_one = _account(owner_session, password=PASSWORD)

    answers = [
        api_client.post("/v1/auth/password", json={"phone": phone, "password": pw})
        for phone, pw in (
            (_number(), PASSWORD),
            (without, PASSWORD),
            (with_one, "the wrong passphrase"),
        )
    ]
    assert {answer.status_code for answer in answers} == {400}
    assert {answer.json()["error"]["message_key"] for answer in answers} == {
        "auth.password.wrong"
    }
    assert len({answer.json()["error"]["code"] for answer in answers}) == 1


def test_a_password_sign_in_with_a_factor_goes_on_to_the_factor(
    api_client: TestClient, owner_session: Session
) -> None:
    """The password is the first step, never the whole of it.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :return: None
    """
    account_id, phone = _account(owner_session, password=PASSWORD)
    secret = _turn_on_factor(api_client, owner_session, account_id)

    first = api_client.post(
        "/v1/auth/password", json={"phone": phone, "password": PASSWORD}
    ).json()
    assert first["access_token"] is None and first["mfa_required"] is True

    second = api_client.post(
        "/v1/auth/mfa",
        json={"challenge": first["mfa_challenge"], "code": _now_code(secret)},
    )
    assert second.status_code == 200, second.text
    assert second.json()["access_token"]


def test_failures_for_one_identifier_stop_after_the_ceiling(
    api_client: TestClient, owner_session: Session
) -> None:
    """A guesser gets the ceiling and no more, known account or not.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :return: None
    """
    _, phone = _account(owner_session, password=PASSWORD)
    unknown = _number()
    for target in (phone, unknown):
        for _ in range(PASSWORD_FAILURES_PER_IDENTIFIER_HOURLY):
            wrong = api_client.post(
                "/v1/auth/password", json={"phone": target, "password": "nope-nope"}
            )
            assert wrong.status_code == 400
        stopped = api_client.post(
            "/v1/auth/password", json={"phone": target, "password": PASSWORD}
        )
        assert stopped.status_code == 409
        assert (
            stopped.json()["error"]["message_key"] == "auth.password.too_many_attempts"
        )


# ------------------------------------------------------------- the code flow


def test_an_existing_account_without_a_password_gets_one_through_a_code(
    api_client: TestClient, owner_session: Session, sent: list[tuple[str, str]]
) -> None:
    """The one-time path every pre-password account takes.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param sent: The captured sends
    :return: None
    """
    _, phone = _account(owner_session)
    grant = _verify(api_client, sent, phone=phone)
    assert grant["access_token"] is None

    set_up = api_client.post(
        "/v1/auth/password/setup",
        json={"token": grant["password_setup_token"], "password": PASSWORD},
    )
    assert set_up.status_code == 200, set_up.text
    assert (
        api_client.post(
            "/v1/auth/password", json={"phone": phone, "password": PASSWORD}
        ).status_code
        == 200
    )


def test_a_setup_token_is_spent_by_the_password_it_sets(
    api_client: TestClient, owner_session: Session, sent: list[tuple[str, str]]
) -> None:
    """Replaying the token cannot set a second password.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param sent: The captured sends
    :return: None
    """
    _, phone = _account(owner_session)
    token = _verify(api_client, sent, phone=phone)["password_setup_token"]
    first = api_client.post(
        "/v1/auth/password/setup", json={"token": token, "password": PASSWORD}
    )
    assert first.status_code == 200, first.text

    again = api_client.post(
        "/v1/auth/password/setup",
        json={"token": token, "password": "a different passphrase"},
    )
    assert again.status_code == 401
    assert again.json()["error"]["message_key"] == "auth.password.setup_expired"


def test_recovering_a_password_signs_out_every_other_session(
    api_client: TestClient, owner_session: Session, sent: list[tuple[str, str]]
) -> None:
    """A recovery is a reason not to trust the sessions before it.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param sent: The captured sends
    :return: None
    """
    _, phone = _account(owner_session, password=PASSWORD)
    old = api_client.post(
        "/v1/auth/password", json={"phone": phone, "password": PASSWORD}
    ).json()

    token = _verify(api_client, sent, phone=phone)["password_setup_token"]
    assert (
        api_client.post(
            "/v1/auth/password/setup",
            json={"token": token, "password": "a brand new passphrase"},
        ).status_code
        == 200
    )

    refreshed = api_client.post(
        "/v1/auth/refresh", json={"refresh_token": old["refresh_token"]}
    )
    assert refreshed.status_code == 401
    assert (
        api_client.post(
            "/v1/auth/password", json={"phone": phone, "password": PASSWORD}
        ).status_code
        == 400
    )


def test_recovering_a_password_does_not_skip_the_factor(
    api_client: TestClient, owner_session: Session, sent: list[tuple[str, str]]
) -> None:
    """Holding the phone alone does not take an account that has a factor.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param sent: The captured sends
    :return: None
    """
    account_id, phone = _account(owner_session, password=PASSWORD)
    secret = _turn_on_factor(api_client, owner_session, account_id)

    grant = _verify(api_client, sent, phone=phone)
    assert grant["mfa_required"] is True
    token = grant["password_setup_token"]

    without = api_client.post(
        "/v1/auth/password/setup", json={"token": token, "password": "new passphrase"}
    )
    assert without.status_code == 400
    assert without.json()["error"]["message_key"] == "mfa.code_required"
    wrong = api_client.post(
        "/v1/auth/password/setup",
        json={"token": token, "password": "new passphrase", "code": "000000"},
    )
    assert wrong.status_code == 400
    # The old password still works: nothing was changed by either refusal.
    assert (
        api_client.post(
            "/v1/auth/password", json={"phone": phone, "password": PASSWORD}
        ).status_code
        == 200
    )

    right = api_client.post(
        "/v1/auth/password/setup",
        json={"token": token, "password": "new passphrase", "code": _now_code(secret)},
    )
    assert right.status_code == 200, right.text


@pytest.mark.parametrize(
    ("password", "key"),
    [
        ("short", "auth.password.too_short"),
        ("x" * 129, "auth.password.too_long"),
        ("password123", "auth.password.too_common"),
        ("aaaaaaaaaaaa", "auth.password.too_common"),
    ],
)
def test_the_policy_refuses_with_its_own_message(
    api_client: TestClient,
    owner_session: Session,
    sent: list[tuple[str, str]],
    password: str,
    key: str,
) -> None:
    """Each refusal names its remedy, and the token survives it.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param sent: The captured sends
    :param password: The refused password
    :param key: The message key it must carry
    :return: None
    """
    _, phone = _account(owner_session)
    token = _verify(api_client, sent, phone=phone)["password_setup_token"]
    refused = api_client.post(
        "/v1/auth/password/setup", json={"token": token, "password": password}
    )
    assert refused.status_code == 400
    assert refused.json()["error"]["message_key"] == key
    assert (
        api_client.post(
            "/v1/auth/password/setup", json={"token": token, "password": PASSWORD}
        ).status_code
        == 200
    )


# ------------------------------------------------------- signed-in settings


def test_changing_a_password_needs_the_current_one(
    api_client: TestClient, owner_session: Session
) -> None:
    """A phone left signed in is not a way to take the account for good.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :return: None
    """
    account_id, phone = _account(owner_session, password=PASSWORD)
    headers = bearer(owner_session, account_id)
    owner_session.commit()

    missing = api_client.post(
        "/v1/me/password", json={"new_password": "another passphrase"}, headers=headers
    )
    wrong = api_client.post(
        "/v1/me/password",
        json={"current_password": "not it at all", "new_password": "x" * 20},
        headers=headers,
    )
    assert missing.status_code == wrong.status_code == 400
    assert wrong.json()["error"]["message_key"] == "auth.password.current_wrong"

    changed = api_client.post(
        "/v1/me/password",
        json={"current_password": PASSWORD, "new_password": "another passphrase"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["access_token"]
    assert (
        api_client.post(
            "/v1/auth/password",
            json={"phone": phone, "password": "another passphrase"},
        ).status_code
        == 200
    )


def test_a_signed_in_account_without_a_password_sets_its_first(
    api_client: TestClient, owner_session: Session
) -> None:
    """No current password to give, and /v1/me says so beforehand.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :return: None
    """
    account_id, _ = _account(owner_session)
    headers = bearer(owner_session, account_id)
    owner_session.commit()
    assert api_client.get("/v1/me", headers=headers).json()["has_password"] is False

    set_first = api_client.post(
        "/v1/me/password", json={"new_password": PASSWORD}, headers=headers
    )
    assert set_first.status_code == 200, set_first.text
    fresh = {"Authorization": f"Bearer {set_first.json()['access_token']}"}
    assert api_client.get("/v1/me", headers=fresh).json()["has_password"] is True


def test_an_email_only_account_reaches_its_seats_once_it_proves_a_phone(
    api_client: TestClient, owner_session: Session, sent: list[tuple[str, str]]
) -> None:
    """Teachers record students by number; proving it brings the seat.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param sent: The captured sends
    :return: None
    """
    teacher = make_teacher(owner_session, name="Chemistry")
    phone = _number()
    added = api_client.post(
        f"/v1/batches/{teacher.batch_id}/enrollments",
        json={"display_name": "Rahim", "student_phone": phone},
        headers=bearer(owner_session, teacher.account_id),
    )
    owner_session.commit()
    assert added.status_code in (200, 201), added.text
    seat_id = uuid.UUID(added.json()["enrollment_id"])

    address = _address()
    response, code = submit_signup(api_client, _form(email=address))
    grant = api_client.post(
        "/v1/auth/verify", json={"email": address, "code": code}
    ).json()
    tokens = api_client.post(
        "/v1/auth/password/setup",
        json={"token": grant["password_setup_token"], "password": PASSWORD},
    ).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    account_id = uuid.UUID(response.json()["account_id"])

    def linked() -> uuid.UUID | None:
        owner_session.expire_all()
        value: uuid.UUID | None = owner_session.execute(
            sa.text("SELECT student_account_id FROM enrollment WHERE id = :e"),
            {"e": seat_id},
        ).scalar_one()
        return value

    assert linked() is None
    asked = api_client.post("/v1/me/contact", json={"phone": phone}, headers=headers)
    assert asked.status_code == 200, asked.text
    # Asking does not attach; only the code does.
    assert linked() is None

    wrong = api_client.post(
        "/v1/me/contact/verify",
        json={"phone": phone, "code": "000000"},
        headers=headers,
    )
    assert wrong.status_code == 400
    assert linked() is None

    proved = api_client.post(
        "/v1/me/contact/verify",
        json={"phone": phone, "code": _code_for(sent, phone)},
        headers=headers,
    )
    assert proved.status_code == 200, proved.text
    assert proved.json()["phone"] == phone
    assert linked() == account_id

    # A second number is a REPLACEMENT since U2 [FR8, BR5.2], and a
    # replacement without the password is refused before any code is sent.
    again = api_client.post(
        "/v1/me/contact", json={"phone": _number()}, headers=headers
    )
    assert again.status_code == 400
    assert again.json()["error"]["message_key"] == "account.contact.password_required"


def test_a_destination_another_account_holds_is_refused_only_after_its_code(
    api_client: TestClient, owner_session: Session, sent: list[tuple[str, str]]
) -> None:
    """Asking is answered alike; only the code's holder learns it is taken.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param sent: The captured sends
    :return: None
    """
    _, taken = _account(owner_session)
    address = _address()
    owner_session.execute(
        sa.text("INSERT INTO account (id, email, created_at) VALUES (:id, :e, :now)"),
        {"id": uuid.uuid4(), "e": address, "now": dt.datetime.now(tz=dt.UTC)},
    )
    owner_session.commit()
    account_id = uuid.UUID(
        str(
            owner_session.execute(
                sa.text("SELECT id FROM account WHERE email = :e"), {"e": address}
            ).scalar_one()
        )
    )
    headers = bearer(owner_session, account_id)
    owner_session.commit()

    asked = api_client.post("/v1/me/contact", json={"phone": taken}, headers=headers)
    assert asked.status_code == 200

    refused = api_client.post(
        "/v1/me/contact/verify",
        json={"phone": taken, "code": _code_for(sent, taken)},
        headers=headers,
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["message_key"] == "account.contact.taken"


def test_a_sign_in_code_cannot_attach_a_destination(
    api_client: TestClient, owner_session: Session, sent: list[tuple[str, str]]
) -> None:
    """Each purpose's code is spent only for that purpose.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param sent: The captured sends
    :return: None
    """
    account_id, _ = _account(owner_session)
    owner_session.execute(
        sa.text("UPDATE account SET phone = NULL, email = :e WHERE id = :a"),
        {"e": _address(), "a": account_id},
    )
    owner_session.commit()
    headers = bearer(owner_session, account_id)
    owner_session.commit()
    stranger = _number()
    # A sign-in code for an unknown number exists (and is never sent);
    # one sent to a pending signup for it is.
    submit_signup(api_client, _form(phone=stranger))
    code = _code_for(sent, stranger)
    refused = api_client.post(
        "/v1/me/contact/verify",
        json={"phone": stranger, "code": code},
        headers=headers,
    )
    assert refused.status_code == 400


# ------------------------------------------------------------------- deletion


def test_an_email_only_account_can_delete_itself_from_the_web_page(
    api_client: TestClient, owner_session: Session, sent: list[tuple[str, str]]
) -> None:
    """Play's external deletion path works without a phone number.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param sent: The captured sends
    :return: None
    """
    address = _address()
    _, code = submit_signup(api_client, _form(email=address))
    api_client.post("/v1/auth/verify", json={"email": address, "code": code})

    asked = api_client.post("/account-deletion", json={"email": address})
    assert asked.status_code == 200, asked.text
    deleted = api_client.post(
        "/account-deletion",
        json={"email": address, "code": _code_for(sent, address)},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["status"] == "deleted"
    owner_session.expire_all()
    assert (
        owner_session.execute(
            sa.text("SELECT count(*) FROM account WHERE email = :e"), {"e": address}
        ).scalar_one()
        == 0
    )
    assert (
        owner_session.execute(
            sa.text("SELECT count(*) FROM otp_request WHERE email = :e"),
            {"e": address},
        ).scalar_one()
        == 0
    )


# -------------------------------------------------------------------- helpers


def _now_code(secret: str) -> str:
    """Compute the code an authenticator app shows now.

    :param secret: The base32 secret
    :return: The code
    """
    return totp.code_at(secret, int(time.time() // 30))


def _turn_on_factor(client: TestClient, session: Session, account_id: uuid.UUID) -> str:
    """Turn an authenticator factor on through the settings routes.

    :param client: The HTTP client
    :param session: An arranging session
    :param account_id: The account
    :return: The secret
    """
    headers = bearer(session, account_id)
    session.commit()
    secret: str = client.post("/v1/me/mfa/setup", headers=headers).json()["secret"]
    confirmed = client.post(
        "/v1/me/mfa/confirm",
        json={"code": totp.code_at(secret, int(time.time() // 30) - 1)},
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    return secret
