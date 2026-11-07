"""Sign up over HTTP the way a client does: submit the form, type the code.

Since verify-first signup [C-07], ``POST /v1/accounts`` creates no
account: it holds the form and sends a code, and the account exists once
that code is verified at ``POST /v1/auth/verify``. A suite that needs a
signed-up account therefore makes both calls, exactly as the web and
Android clients do. The code is captured at the gateway, the one place
it exists in the clear, so nothing here bypasses the path under test.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest import mock

from fastapi.testclient import TestClient

from app.gateway.null import NullGateway

__all__ = ["sign_up", "submit_signup"]


def submit_signup(client: TestClient, body: dict[str, Any]) -> tuple[Any, str | None]:
    """Submit the signup form and capture the code it sent.

    :param client: The test client
    :param body: The signup request body
    :return: The response, and the six-digit code sent, if one was
    """
    sent: list[str] = []
    original = NullGateway.send

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

    with mock.patch.object(NullGateway, "send", capture):
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
    verified = client.post(
        "/v1/auth/verify", json={"phone": body["phone"], "code": code}
    )
    assert verified.status_code == 200, verified.text
    return uuid.UUID(response.json()["account_id"])
