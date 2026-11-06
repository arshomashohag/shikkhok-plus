"""Run the seeder as an AWS Lambda function, from the backend image.

**Why a runtime loop here rather than a Lambda base image.** The
function runs the SAME image the API runs, pulled from the same ECR
repository at the same commit SHA: the same lockfile, the same
``--require-hashes`` install, the same code against the same schema. A
separate Lambda image would be a second dependency set to keep in step
with the first, and a seeder one migration behind the database writes
rows the current code would not.

AWS's runtime interface client is the usual way to make an image a
Lambda, and it is a dependency the lockfile does not carry. The Lambda
Runtime API it wraps is three HTTP calls -- fetch the next event, post
its response, post an error -- documented at
https://docs.aws.amazon.com/lambda/latest/dg/runtimes-api.html, so this
module makes them with the standard library.

The image's command is overridden in the function's configuration::

    python -m app.seed.lambda_runtime

Run locally it refuses to start, because ``AWS_LAMBDA_RUNTIME_API`` is
only set by Lambda.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
import urllib.request
from typing import Final

from sqlalchemy import Engine

from app.db.session import build_engine
from app.seed.handler import handle
from app.seed.scenario import SeedRefused

__all__ = ["main", "serve_one"]

log = logging.getLogger(__name__)

#: Set by Lambda to the runtime API's host and port.
RUNTIME_API_ENV: Final = "AWS_LAMBDA_RUNTIME_API"

#: The runtime API's version prefix.
API_VERSION: Final = "2018-06-01"


def _call(url: str, body: bytes | None = None, error_type: str | None = None) -> bytes:
    """Make one runtime API request.

    The runtime API is plain HTTP on a link-local address Lambda sets;
    nothing user-supplied reaches the URL.

    :param url: The endpoint
    :param body: A POST body, or None for GET
    :param error_type: The ``Lambda-Runtime-Function-Error-Type`` header
    :return: The response body
    """
    request = urllib.request.Request(url, data=body)  # noqa: S310  Lambda's own endpoint
    if body is not None:
        request.add_header("Content-Type", "application/json")
    if error_type is not None:
        request.add_header("Lambda-Runtime-Function-Error-Type", error_type)
    with urllib.request.urlopen(request) as response:  # noqa: S310  as above
        return bytes(response.read())


def _error_body(error: BaseException) -> bytes:
    """Describe a failure the way the runtime API expects.

    A refusal is the invoker's to fix and carries only its message; an
    unexpected failure carries its traceback too, which reaches the
    invoker and the function's log -- neither ever a phone number,
    because no message here is built from one.

    :param error: What went wrong
    :return: The JSON body
    """
    payload: dict[str, object] = {
        "errorType": type(error).__name__,
        "errorMessage": str(error),
    }
    if not isinstance(error, SeedRefused):
        payload["stackTrace"] = traceback.format_exception(error)
    return json.dumps(payload).encode()


def serve_one(base: str, engine: Engine) -> None:
    """Fetch one event, seed, and post the result or the error.

    :param base: ``http://<runtime api>/2018-06-01``
    :param engine: The engine, built once per container
    :return: None
    """
    url = f"{base}/runtime/invocation/next"
    request = urllib.request.Request(url)  # noqa: S310  Lambda's own endpoint
    with urllib.request.urlopen(request) as response:  # noqa: S310  as above
        request_id = response.headers["Lambda-Runtime-Aws-Request-Id"]
        raw = response.read()
    reply = f"{base}/runtime/invocation/{request_id}"
    try:
        event = json.loads(raw or b"{}")
        result = handle(engine, event)
    except SeedRefused as refused:
        log.warning("seed refused: %s", refused)
        _call(f"{reply}/error", _error_body(refused), "SeedRefused")
        return
    # The one place a failure of any kind must be REPORTED rather than
    # raised: an uncaught exception here ends the container without
    # telling Lambda, and the invoker sees a timeout instead of the error.
    except Exception as error:
        log.exception("seed failed")
        _call(f"{reply}/error", _error_body(error), type(error).__name__)
        return
    _call(f"{reply}/response", json.dumps(result).encode())


def main() -> int:
    """Serve events until Lambda freezes or ends the container.

    :return: 1 when not running inside Lambda; never returns otherwise
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    api = os.environ.get(RUNTIME_API_ENV)
    if not api:
        print(
            f"{RUNTIME_API_ENV} is not set: this runs only inside Lambda. "
            "Locally, use: python -m app.seed <phone>",
            file=sys.stderr,
        )
        return 1
    base = f"http://{api}/{API_VERSION}"
    try:
        engine = build_engine()
    except Exception as error:  # noqa: BLE001  reported to Lambda, as above
        _call(f"{base}/runtime/init/error", _error_body(error), type(error).__name__)
        return 1
    while True:
        serve_one(base, engine)


if __name__ == "__main__":  # pragma: no cover - the container's entry point
    raise SystemExit(main())
