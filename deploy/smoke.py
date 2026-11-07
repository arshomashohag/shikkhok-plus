"""Post-deploy smoke: the API answers, its database is reachable, at head.

Usage::

    python3 deploy/smoke.py <base-url> [--attempts N] [--interval S]
        [--sign-in-phone +8801XXXXXXXXX]

Run by the deploy workflow against the PUBLIC URL -- through CloudFront,
the origin's certificate and nginx's origin-secret check, which is the
path a teacher's phone takes -- and by check.yml's image job against a
container on localhost. Standard library only, so it runs on any runner
without installing anything.

**What it asserts.** ``/health`` must answer 200, report ``"database":
"ok"``, and report the migration revision this commit declares as its
head -- derived from ``migrations/versions``, so adding a migration
cannot leave this asserting the previous one.

**And, given ``--sign-in-phone``, the sign-in path end to end** [C-38]:
issue a code for that number, read it back from the staging outbox,
verify it, and resolve ``GET /v1/me`` with the issued token. That is
OTP issue and verify, token signing and per-request lens resolution,
through the public path. It needs a staging host with the outbox on and
the number on its operator allowlist, and an account for the number --
the outbox records only numbers that have one. Each run spends one of
that number's daily OTP issues. **Production runs without it**: the
outbox cannot exist there, and no other way to obtain a code without a
real SMS is safe to build. A fee read, which team.md's smoke set also
names, needs seeded data and is not automated.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "migrations" / "versions"


def migration_head() -> str:
    """Return the one revision no other revision names as its parent.

    :return: The head revision id
    :raises SystemExit: When there is not exactly one head
    """
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in VERSIONS.glob("*.py"):
        text = path.read_text()
        rev = re.search(r'^revision[^=]*=\s*"([^"]+)"', text, re.MULTILINE)
        down = re.search(r'^down_revision[^=]*=\s*"([^"]+)"', text, re.MULTILINE)
        if rev:
            revisions.add(rev.group(1))
        if down:
            parents.add(down.group(1))
    heads = revisions - parents
    if len(heads) != 1:
        raise SystemExit(f"expected exactly one migration head, found {heads}")
    return heads.pop()


def _call(
    base_url: str,
    method: str,
    path: str,
    body: dict[str, str] | None = None,
    token: str | None = None,
) -> dict[str, object]:
    """Make one JSON request and decode the answer.

    :param base_url: e.g. ``https://api.example.com``
    :param method: ``GET`` or ``POST``
    :param path: The path, with any query string
    :param body: A JSON body, or None
    :param token: A bearer token, or None
    :return: The decoded body
    :raises urllib.error.HTTPError: The API answered with an error status
    """
    headers = {"User-Agent": "shikkhokplus-smoke", "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(  # noqa: S310 -- the URL is ours, https or localhost
        base_url.rstrip("/") + path, data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        decoded: dict[str, object] = json.loads(response.read())
        return decoded


def fetch_health(base_url: str) -> dict[str, object]:
    """GET ``<base_url>/health`` and parse it.

    :param base_url: e.g. ``https://api.example.com``
    :return: The decoded body
    """
    return _call(base_url, "GET", "/health")


#: The six-digit code inside the rendered SMS. Bounded by non-alphanumerics
#: so six digits inside the SMS Retriever hash are never taken for it.
_CODE = re.compile(r"(?<![0-9A-Za-z])([0-9]{6})(?![0-9A-Za-z])")


def sign_in(base_url: str, phone: str, *, attempts: int, interval: float) -> str:
    """Sign in through the staging outbox and resolve ``/v1/me``.

    :param base_url: e.g. ``https://api.example.com``
    :param phone: An operator number on the staging allowlist
    :param attempts: How many times to poll the outbox for the code
    :param interval: Seconds between polls
    :return: A one-line description of what was verified
    :raises RuntimeError: Any step failed; the message names which
    """
    try:
        _call(base_url, "POST", "/v1/auth/otp", {"phone": phone})
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"issuing a code answered {exc.code}") from None

    query = "/staging/last-otp?" + urllib.parse.urlencode({"phone": phone})
    code = None
    for _ in range(attempts):
        try:
            message = str(_call(base_url, "GET", query).get("message", ""))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise RuntimeError(
                    "the staging outbox route is absent: the outbox is off, or "
                    "the number is not on SHIKKHOKPLUS_STAGING_OUTBOX_NUMBERS"
                ) from None
            message = ""
        found = _CODE.search(message)
        if found:
            code = found.group(1)
            break
        time.sleep(interval)
    if code is None:
        raise RuntimeError(
            "no code reached the outbox; the number may have no account, or "
            "may not be on the outbox allowlist"
        )

    try:
        tokens = _call(
            base_url, "POST", "/v1/auth/verify", {"phone": phone, "code": code}
        )
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"verifying the code answered {exc.code}") from None
    access = tokens.get("access_token")
    if not isinstance(access, str) or not access:
        raise RuntimeError("verification returned no access token")

    try:
        me = _call(base_url, "GET", "/v1/me", token=access)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"GET /v1/me with the issued token answered {exc.code}"
        ) from None
    lenses = me.get("lenses")
    if not isinstance(lenses, list):
        raise RuntimeError("GET /v1/me returned no lens list")
    return f"signed in through the outbox and resolved {len(lenses)} lens(es)"


def _sign_in_or_skip(base_url: str, phone: str) -> int:
    """Run the sign-in check when a number was given.

    :param base_url: The API's base URL
    :param phone: The operator number, or empty to skip
    :return: The process exit code
    """
    if not phone:
        return 0
    try:
        print(sign_in(base_url, phone, attempts=6, interval=5.0))
    except (RuntimeError, urllib.error.URLError, OSError, ValueError) as exc:
        print(f"::error::sign-in smoke failed: {exc}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    """Poll until healthy at head, or fail.

    :return: The process exit code
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("--attempts", type=int, default=30)
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument(
        "--sign-in-phone",
        default="",
        help="staging only: also sign in through the outbox with this number",
    )
    args = parser.parse_args()

    head = migration_head()
    last = "no response"
    for attempt in range(1, args.attempts + 1):
        try:
            health = fetch_health(args.base_url)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = f"{type(exc).__name__}: {exc}"
        else:
            last = json.dumps(health)
            if (
                health.get("database") == "ok"
                and health.get("migration_revision") == head
            ):
                print(f"healthy at migration head {head} (attempt {attempt})")
                return _sign_in_or_skip(args.base_url, args.sign_in_phone)
        print(f"attempt {attempt}/{args.attempts}: {last}", file=sys.stderr)
        time.sleep(args.interval)

    print(
        f"::error::{args.base_url}/health never reported database ok at "
        f"head {head}. Last: {last}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
