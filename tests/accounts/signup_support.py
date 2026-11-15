"""Sign up over HTTP the way a client does: submit the form, type the code.

Since verify-first signup [C-07], ``POST /v1/accounts`` creates no
account: it holds the form and sends a code, and the account exists once
that code is verified at ``POST /v1/auth/verify``. A suite that needs a
signed-up account therefore makes both calls, exactly as the web and
Android clients do. The code is captured at the gateway, the one place
it exists in the clear, so nothing here bypasses the path under test.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any
from unittest import mock

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.gateway.email import EmailMessage, NullEmailGateway
from app.gateway.null import NullGateway

__all__ = ["named_account", "sign_up", "submit_signup", "unique_username"]


def named_account(
    session: Session,
    username: str | None = None,
    *,
    password: str | None = None,
    changed_at: dt.datetime | None = None,
) -> tuple[uuid.UUID, str]:
    """Arrange an account with a number and, optionally, a username.

    Written as the table owner, for arrangement only: the assertions are
    made through the application's routes and role.

    :param session: An arranging session
    :param username: Its display form, or None for an account with none
    :param password: Its password, or None for an account without one
    :param changed_at: Its last ordinary rename, or None
    :return: The account id and its number
    """
    account_id = uuid.uuid4()
    phone = f"+88017{uuid.uuid4().int % 10**8:08d}"
    now = dt.datetime.now(tz=dt.UTC)
    session.execute(
        sa.text(
            "INSERT INTO account (id, phone, password_hash, password_changed_at, "
            "created_at, activated_at, username, username_key, username_changed_at) "
            "VALUES (:id, :phone, :hash, :pw_at, :now, :now, :name, :key, :changed)"
        ),
        {
            "id": account_id,
            "phone": phone,
            "hash": hash_password(password) if password else None,
            "pw_at": now if password else None,
            "now": now,
            "name": username,
            "key": username.lower() if username else None,
            "changed": changed_at,
        },
    )
    session.commit()
    return account_id, phone


def unique_username() -> str:
    """Return a username no other test uses [U1: FR2.1].

    Starts with a letter and is 13 characters, so it passes FR1.

    :return: A fresh, valid username
    """
    return f"u{uuid.uuid4().hex[:12]}"


def with_username(body: dict[str, Any]) -> dict[str, Any]:
    """Give a signup body a unique username unless it names one.

    Sign-up requires a username since U1 [BR2.1]; a suite that is not
    about usernames gets a fresh one, so two of its signups never collide.
    A body that sets ``username`` -- even to None, to test its absence --
    is sent as written.

    :param body: The signup request body
    :return: The body, with a username
    """
    if "username" not in body:
        return {**body, "username": unique_username()}
    if body["username"] is None:
        return {key: value for key, value in body.items() if key != "username"}
    return body


def submit_signup(client: TestClient, body: dict[str, Any]) -> tuple[Any, str | None]:
    """Submit the signup form and capture the code it sent.

    :param client: The test client
    :param body: The signup request body; given a unique username when it
        names none (:func:`with_username`)
    :return: The response, and the six-digit code sent, if one was
    """
    body = with_username(body)
    sent: list[str] = []
    original = NullGateway.send
    original_email = NullEmailGateway.send

    def capture(
        self: NullGateway, number: str, message: str, correlation_id: str
    ) -> object:
        """Record the message, then send as the null gateway would.

        :param self: The gateway
        :param number: The destination
        :param message: The rendered message
        :param correlation_id: The request's correlation id
        :return: The null gateway's result
        """
        sent.append(message)
        return original(self, number, message, correlation_id)

    def capture_email(
        self: NullEmailGateway,
        address: str,
        message: EmailMessage,
        correlation_id: str,
    ) -> object:
        """Record the email body, then send as the null gateway would.

        :param self: The gateway
        :param address: The destination
        :param message: The rendered email
        :param correlation_id: The request's correlation id
        :return: The null gateway's result
        """
        sent.append(message.text)
        return original_email(self, address, message, correlation_id)

    with (
        mock.patch.object(NullGateway, "send", capture),
        mock.patch.object(NullEmailGateway, "send", capture_email),
    ):
        response = client.post("/v1/accounts", json=body)
    code = next(
        (
            part
            for message in sent
            for part in message.split()
            if part.isdigit() and len(part) == 6
        ),
        None,
    )
    return response, code


def sign_up(client: TestClient, body: dict[str, Any]) -> uuid.UUID:
    """Sign up and verify, returning the account the code created.

    :param client: The test client
    :param body: The signup request body
    :return: The new account's id
    """
    response, code = submit_signup(client, body)
    assert response.status_code == 201, response.text
    assert code is not None, "signup sent no code"
    destination = (
        {"phone": body["phone"]} if body.get("phone") else {"email": body["email"]}
    )
    verified = client.post("/v1/auth/verify", json={**destination, "code": code})
    assert verified.status_code == 200, verified.text
    return uuid.UUID(response.json()["account_id"])
