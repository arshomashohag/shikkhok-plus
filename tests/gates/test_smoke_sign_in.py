"""The deploy smoke's sign-in path, against a stand-in API.

``deploy/smoke.py`` runs only in a workflow, against a real deployment,
so its sign-in sequence [C-38] is exercised here against a local HTTP
server that answers the four calls the way the API does. What is
asserted is the sequence and its refusals: a code read from the outbox
is the one verified, the issued token is the one presented to
``/v1/me``, and each broken step fails the smoke rather than passing it.
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import pathlib
import threading
import urllib.parse
from collections.abc import Iterator
from types import ModuleType

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PHONE = "+8801711111111"
CODE = "482913"
TOKEN = "access-token-for-the-smoke"  # noqa: S105 -- a stand-in value


def _load_smoke() -> ModuleType:
    """Import ``deploy/smoke.py``, which is a script rather than a package.

    :return: The module
    """
    spec = importlib.util.spec_from_file_location("smoke", ROOT / "deploy" / "smoke.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


smoke = _load_smoke()


class _Api(http.server.BaseHTTPRequestHandler):
    """Answers the sign-in calls; ``server.behaviour`` breaks one of them."""

    def log_message(self, format: str, *args: object) -> None:
        """Stay quiet.

        :param format: Unused
        :param args: Unused
        :return: None
        """

    def _send(self, status: int, body: dict[str, object]) -> None:
        """Write a JSON answer.

        :param status: The HTTP status
        :param body: The body
        :return: None
        """
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        """Answer the outbox read and ``/v1/me``.

        :return: None
        """
        behaviour = self.server.behaviour  # type: ignore[attr-defined]
        url = urllib.parse.urlparse(self.path)
        if url.path == "/staging/last-otp":
            if behaviour == "no-outbox":
                self._send(404, {"code": "NOT_FOUND"})
                return
            phone = urllib.parse.parse_qs(url.query)["phone"][0]
            # The hash carries six digits too, as a real one can.
            message = f"<#> {CODE} is your ShikkhokPlus code. 123456ABCDE"
            self._send(200, {"phone": phone, "message": message})
        elif url.path == "/v1/me":
            if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                self._send(401, {"code": "UNAUTHENTICATED"})
                return
            self._send(200, {"lenses": [{"lens": "teacher"}]})
        else:
            self._send(404, {"code": "NOT_FOUND"})

    def do_POST(self) -> None:
        """Answer the issue and verify calls.

        :return: None
        """
        behaviour = self.server.behaviour  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        if self.path == "/v1/auth/otp":
            self._send(200, {"status": "requested"})
        elif self.path == "/v1/auth/verify":
            if body.get("code") != CODE or behaviour == "wrong-code":
                self._send(400, {"code": "INVALID_CODE"})
                return
            self._send(200, {"access_token": TOKEN, "refresh_token": "r"})
        else:
            self._send(404, {"code": "NOT_FOUND"})


@pytest.fixture
def api(request: pytest.FixtureRequest) -> Iterator[str]:
    """Serve the stand-in API on a free local port.

    :param request: Carries the behaviour to break, via indirect params
    :return: A context manager yielding the base URL
    """
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Api)
    server.behaviour = getattr(request, "param", "ok")  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_the_code_from_the_outbox_signs_in_and_resolves_lenses(api: str) -> None:
    outcome = smoke.sign_in(api, PHONE, attempts=1, interval=0)

    assert outcome == "signed in through the outbox and resolved 1 lens(es)"


@pytest.mark.parametrize(
    ("api", "reason"),
    [("no-outbox", "outbox route is absent"), ("wrong-code", "verifying")],
    indirect=["api"],
)
def test_a_broken_step_fails_the_smoke(api: str, reason: str) -> None:
    with pytest.raises(RuntimeError, match=reason):
        smoke.sign_in(api, PHONE, attempts=1, interval=0)


def test_no_number_means_health_only() -> None:
    # Production passes no number; the sign-in step must not run there.
    assert smoke._sign_in_or_skip("http://127.0.0.1:9", "") == 0
