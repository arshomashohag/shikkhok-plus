"""The runtime loop speaks the Lambda Runtime API correctly.

Against a stand-in runtime API on a local port, so the three calls --
fetch the next event, post its response, post an error -- are checked
for their paths, headers and bodies without AWS. The seed itself is
replaced; what is under test is the transport and that every outcome,
including an unexpected crash, is REPORTED rather than lost.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.seed import lambda_runtime
from app.seed.scenario import SeedRefused

REQUEST_ID = "8476a536-e9f4-11e8-9739-2dfe598c3fcd"


class _FakeRuntime(BaseHTTPRequestHandler):
    """Serve one event and record what the runtime posts back."""

    event = b'{"phone": "+8801711111111"}'
    posted: list[tuple[str, dict[str, str], dict[str, object]]] = []  # noqa: RUF012

    def do_GET(self) -> None:
        assert self.path == "/2018-06-01/runtime/invocation/next"
        self.send_response(200)
        self.send_header("Lambda-Runtime-Aws-Request-Id", REQUEST_ID)
        self.send_header("Content-Length", str(len(self.event)))
        self.end_headers()
        self.wfile.write(self.event)

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        self.posted.append((self.path, dict(self.headers), body))
        self.send_response(202)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_: object) -> None:
        """Keep the test output quiet."""


@pytest.fixture
def runtime() -> Iterator[str]:
    _FakeRuntime.posted = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeRuntime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/2018-06-01"
    server.shutdown()


def test_a_report_is_posted_as_the_invocations_response(
    runtime: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[object] = []

    def fake_handle(_engine: object, event: object) -> dict[str, object]:
        seen.append(event)
        return {"counts": {"batches": 3}}

    monkeypatch.setattr(lambda_runtime, "handle", fake_handle)
    lambda_runtime.serve_one(runtime, engine=None)  # type: ignore[arg-type]

    assert seen == [{"phone": "+8801711111111"}]
    [(path, _headers, body)] = _FakeRuntime.posted
    assert path == f"/2018-06-01/runtime/invocation/{REQUEST_ID}/response"
    assert body == {"counts": {"batches": 3}}


def test_a_refusal_is_posted_as_an_error_without_a_traceback(
    runtime: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(_engine: object, _event: object) -> dict[str, object]:
        raise SeedRefused("this account already has the seeded batches")

    monkeypatch.setattr(lambda_runtime, "handle", refuse)
    lambda_runtime.serve_one(runtime, engine=None)  # type: ignore[arg-type]

    [(path, headers, body)] = _FakeRuntime.posted
    assert path == f"/2018-06-01/runtime/invocation/{REQUEST_ID}/error"
    assert headers["Lambda-Runtime-Function-Error-Type"] == "SeedRefused"
    assert body == {
        "errorType": "SeedRefused",
        "errorMessage": "this account already has the seeded batches",
    }


def test_an_unexpected_crash_is_reported_not_lost(
    runtime: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(_engine: object, _event: object) -> dict[str, object]:
        raise KeyError("boom")

    monkeypatch.setattr(lambda_runtime, "handle", crash)
    lambda_runtime.serve_one(runtime, engine=None)  # type: ignore[arg-type]

    [(path, headers, body)] = _FakeRuntime.posted
    assert path.endswith("/error")
    assert headers["Lambda-Runtime-Function-Error-Type"] == "KeyError"
    assert body["errorType"] == "KeyError"
    assert body["stackTrace"]


def test_outside_lambda_it_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(lambda_runtime.RUNTIME_API_ENV, raising=False)
    assert lambda_runtime.main() == 1
    assert "python -m app.seed" in capsys.readouterr().err
