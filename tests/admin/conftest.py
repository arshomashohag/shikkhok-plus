"""Fixtures for the administration suite.

People are re-exported from the help suite rather than rebuilt: the
administrator reads the same people and tickets the help centre creates.

**Every test here runs as though it came through the admin hostname**:
the edge secret and the admin network are configured, and the helpers
send the header and the address the admin distribution would. Tests that
exercise the gate itself drop one or the other.
"""

from __future__ import annotations

import base64
import datetime as dt
import os
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.auth.client_address import TRUSTED_CLIENT_IP_HEADER_ENV
from app.auth.mfa_crypto import MFA_ACTIVE_KID_ENV, MFA_KEYS_ENV, encrypt_secret
from app.auth.tokens import ADMIN_AUDIENCE, ADMIN_TOKEN_LIFETIME, issue_scoped_token
from app.authz.admin import ADMIN_ALLOWED_CIDRS_ENV, ADMIN_EDGE_SECRET_ENV
from tests.help.conftest import account_factory, people

__all__ = [
    "ADMIN_NETWORK_ADDRESS",
    "EDGE",
    "EDGE_SECRET",
    "account_factory",
    "admin_edge",
    "admin_headers",
    "people",
]

#: What the admin distribution sends as ``X-Admin-Edge``.
EDGE_SECRET = "test-edge-secret-" + "x" * 31

#: An address inside the allowed network (TEST-NET-3).
ADMIN_NETWORK_ADDRESS = "203.0.113.7"

#: The two headers a request through the admin hostname arrives with.
EDGE = {"X-Admin-Edge": EDGE_SECRET, "X-Client-Address": ADMIN_NETWORK_ADDRESS}


@pytest.fixture(autouse=True)
def admin_edge(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Configure the edge secret, the admin network and the MFA keys.

    :param monkeypatch: The patcher
    :return: A context manager
    """
    monkeypatch.setenv(ADMIN_EDGE_SECRET_ENV, EDGE_SECRET)
    monkeypatch.setenv(ADMIN_ALLOWED_CIDRS_ENV, "203.0.113.0/24, 198.51.100.10/32")
    monkeypatch.setenv(TRUSTED_CLIENT_IP_HEADER_ENV, "X-Client-Address")
    monkeypatch.setenv(MFA_KEYS_ENV, "k1:" + base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv(MFA_ACTIVE_KID_ENV, "k1")
    yield


def admin_headers(
    session: Session, account_id: uuid.UUID, *, confirmed: bool = True
) -> dict[str, str]:
    """Give an account a confirmed factor and an admin token.

    Arranged directly rather than through the sign-in, which has its own
    suite: these tests are about what an administrator can read.

    :param session: An arranging session
    :param account_id: The account
    :param confirmed: Whether the factor is confirmed
    :return: Headers for a request through the admin hostname
    """
    now = dt.datetime.now(tz=dt.UTC)
    sealed = encrypt_secret("JBSWY3DPEHPK3PXP", account_id)
    session.execute(
        sa.text(
            "INSERT INTO mfa_factor (account_id, secret_kid, secret_ciphertext, "
            "created_at, confirmed_at) VALUES (:a, :k, :c, :now, :confirmed) "
            "ON CONFLICT (account_id) DO NOTHING"
        ),
        {
            "a": account_id,
            "k": sealed.kid,
            "c": sealed.ciphertext,
            "now": now,
            "confirmed": now if confirmed else None,
        },
    )
    session.commit()
    token = issue_scoped_token(account_id, ADMIN_AUDIENCE, ADMIN_TOKEN_LIFETIME)
    return {**EDGE, "Authorization": f"Bearer {token}"}
