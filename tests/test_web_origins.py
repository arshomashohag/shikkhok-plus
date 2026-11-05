"""The web client's CORS allowlist: off by default, exact origins only.

These run without a database. A preflight is answered by the CORS
middleware before the request scope opens a session, which is itself
one of the properties under test: a preflight that reached the database
would make every cross-origin call cost two transactions.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from app.config import ConfigurationError
from app.main import create_app
from app.web_origins import WEB_ORIGINS_ENV, parse_web_origins, register_web_origins

WEB = "https://app.shikkhokplus.example"


def _preflight(client: TestClient, origin: str) -> dict[str, str]:
    """Send a browser's CORS preflight for an authenticated GET.

    :param client: The test client
    :param origin: The Origin header to send
    :return: The response headers, lower-cased keys
    """
    response = client.options(
        "/v1/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    return {k.lower(): v for k, v in response.headers.items()}


def test_unset_means_no_cors_at_all() -> None:
    """With nothing configured, no response names any origin."""
    assert parse_web_origins(None) == ()
    assert parse_web_origins("  ,  ") == ()
    app = FastAPI()
    assert register_web_origins(app, "") == ()
    assert app.user_middleware == []


def test_listed_origin_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The configured origin gets its preflight, with the bearer header allowed."""
    monkeypatch.setenv(WEB_ORIGINS_ENV, WEB)
    headers = _preflight(TestClient(create_app()), WEB)
    assert headers.get("access-control-allow-origin") == WEB
    assert "authorization" in headers.get("access-control-allow-headers", "").lower()
    assert "access-control-allow-credentials" not in headers


def test_other_origin_is_not_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A look-alike origin gets no allow header, so the browser blocks it."""
    monkeypatch.setenv(WEB_ORIGINS_ENV, WEB)
    headers = _preflight(
        TestClient(create_app()), "https://app.shikkhokplus.example.evil.test"
    )
    assert "access-control-allow-origin" not in headers


def test_default_app_installs_no_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the variable, the real application carries no CORS layer.

    Checked on the middleware stack rather than with a request: with no
    CORS layer a preflight falls through to the request scope, which
    needs a database this file deliberately does not have.
    """
    monkeypatch.delenv(WEB_ORIGINS_ENV, raising=False)
    app = create_app()
    assert all(m.cls is not CORSMiddleware for m in app.user_middleware)


@pytest.mark.parametrize(
    "raw",
    [
        "*",
        f"{WEB},*",
        "http://app.shikkhokplus.example",
        f"{WEB}/app",
        f"{WEB}?x=1",
        "app.shikkhokplus.example",
        "https://user:pass@app.shikkhokplus.example",
    ],
)
def test_malformed_allowlist_refuses_to_start(raw: str) -> None:
    """A wildcard, plain http or a path is a deployment error, not ignored."""
    with pytest.raises(ConfigurationError):
        parse_web_origins(raw)


def test_loopback_http_and_normalisation() -> None:
    """Plain http is fine for localhost; entries are trimmed and de-duplicated."""
    assert parse_web_origins(
        " http://localhost:4173 , HTTPS://App.Example.test/ ,https://app.example.test"
    ) == (
        "http://localhost:4173",
        "https://app.example.test",
    )
