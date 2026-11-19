"""Post-deploy smoke: the API answers, its database is reachable, at head.

Usage::

    python3 deploy/smoke.py <base-url> [--attempts N] [--interval S]
        [--sign-in-phone +8801XXXXXXXXX]
    python3 deploy/smoke.py <site-url> --hub --api-url <api-url>
        [--attempts N] [--interval S]

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

**Given ``--hub``, the public hub instead** [H2]. The base URL is then the
public SITE, and ``--api-url`` names the API. The hub's pages are rendered
by the API but served only through the site's distribution, which answers
a hub 404 -- and a 403 -- with the site's own 404 page. So an
origin-secret mismatch between the two distributions reads as a missing
page, and the first check is the one that cannot be faked by that: ``GET
{site}/hub/en`` answers 200 carrying the hub's own CSP, a canonical link
on the site's origin, and a stylesheet the site serves. Then the sitemap
(200), the ``sort`` key (200: the edge function lets through only the
keys it lists, so this proves the deployed function carries it [H4]; it
answers 200 whether reviews are switched on or not, because a switched-off
page ignores the key), an unknown query key (400, from the edge function),
a teacher no listing can be (404, not a soft 200), and the API host's own
``/hub/en`` (404, from its hub-block function). **Photos** [H3]: two ``/m/`` paths, a
well-formed absent key (reaches the bucket through OAC) and a malformed
one (refused by the viewer function), each 403 or 404 with ``nosniff``. It needs no listing to exist, so it
runs against production as well.
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


#: The public hub page's Content-Security-Policy, verbatim. This script
#: imports nothing from ``app/`` (it runs on a bare runner), so the copy is
#: held to ``app.api.html.HUB_PAGE_CSP`` by tests/gates/test_deploy_workflow.py.
HUB_PAGE_CSP = (
    "default-src 'none'; style-src 'self'; img-src 'self'; font-src 'self'; "
    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)

#: A teacher slug no listing can ever hold: the underscore is outside the
#: slug pattern ``[a-z0-9-]{3,60}``, so this is a 404 in every environment.
ABSENT_SLUG = "no_such_teacher"

#: The hub stylesheet a page links, named by its content.
_STYLESHEET = re.compile(
    r'<link rel="stylesheet" href="(/hub-assets/hub\.[0-9a-f]{12}\.css)"'
)


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Report a redirect as its own status instead of following it."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        """Decline every redirect.

        :param args: Unused
        :param kwargs: Unused
        :return: None, so urllib raises the 3xx as an HTTPError
        """
        return None


_OPENER = urllib.request.build_opener(_NoRedirects)


def _get(url: str) -> tuple[int, dict[str, str], str]:
    """GET one URL and return its answer, whatever the status.

    :param url: The absolute URL
    :return: The status, the headers (names lowercased) and the body
    """
    request = urllib.request.Request(  # noqa: S310 -- the URL is ours, https or localhost
        url, headers={"User-Agent": "shikkhokplus-smoke"}
    )
    try:
        with _OPENER.open(request, timeout=10) as response:
            status = response.status
            headers = response.headers
            body = response.read()
    except urllib.error.HTTPError as exc:
        status, headers, body = exc.code, exc.headers, exc.read()
    return (
        status,
        {name.lower(): value for name, value in headers.items()},
        body.decode("utf-8", "replace"),
    )


def _expect(url: str, status: int, what: str) -> None:
    """Fail unless one URL answers one status.

    :param url: The absolute URL
    :param status: The status it must answer
    :param what: How to name it in the failure
    :raises RuntimeError: It answered anything else
    """
    actual, _, _ = _get(url)
    if actual != status:
        raise RuntimeError(f"{what} answered {actual}, not {status}")


def _check_landing(site: str) -> None:
    """Check ``/hub/en`` is the hub's page, not the site's 404.

    :param site: The site origin, no trailing slash
    :raises RuntimeError: Any part of the page is wrong; the message says which
    """
    url = f"{site}/hub/en"
    status, headers, body = _get(url)
    if status != 200:
        raise RuntimeError(
            f"{url} answered {status}; the site's 404 page here usually means "
            "the site distribution's origin secret no longer matches nginx's"
        )
    csp = headers.get("content-security-policy", "")
    if csp != HUB_PAGE_CSP:
        raise RuntimeError(
            f"{url} carries Content-Security-Policy {csp!r}, not the hub's own"
        )
    canonical = f'<link rel="canonical" href="{url}">'
    if canonical not in body:
        raise RuntimeError(
            f"{url} has no canonical link on {site}; SHIKKHOKPLUS_SITE_URL is "
            "missing or wrong in the API's runtime env"
        )
    stylesheet = _STYLESHEET.search(body)
    if stylesheet is None:
        raise RuntimeError(f"{url} links no hub stylesheet")
    sheet = f"{site}{stylesheet.group(1)}"
    sheet_status, sheet_headers, _ = _get(sheet)
    if sheet_status != 200 or not sheet_headers.get("content-type", "").startswith(
        "text/css"
    ):
        raise RuntimeError(
            f"the stylesheet {sheet} answered {sheet_status} "
            f"({sheet_headers.get('content-type', 'no type')}); the site build "
            "and the API disagree on hub.css"
        )


#: A well-formed key no photo holds (a real one is random), so no object
#: sits under it. It passes the /m/ viewer function, reaches the bucket
#: through Origin Access Control and is refused there (403, or 404 where
#: the caller may list).
ABSENT_MEDIA = "/m/00000000000000000000000000000000/320.webp"

#: A path the viewer function itself refuses: not a 32-hex key.
MALFORMED_MEDIA = "/m/does-not-exist/320.webp"


def _check_media(site: str) -> None:
    """Check ``/m/*`` is routed to the bucket and serves nothing unapproved.

    Each probe must answer 403 or 404 carrying ``X-Content-Type-Options:
    nosniff``. The well-formed absent key proves the routing (it gets past
    the viewer function to the bucket); the malformed one proves the
    function refuses what is not a photo URL.

    :param site: The site origin, no trailing slash
    :raises RuntimeError: Either probe answered otherwise
    """
    for path in (ABSENT_MEDIA, MALFORMED_MEDIA):
        status, headers, _ = _get(f"{site}{path}")
        if status not in (403, 404):
            raise RuntimeError(f"{site}{path} answered {status}, not 403 or 404")
        if headers.get("x-content-type-options", "").lower() != "nosniff":
            raise RuntimeError(
                f"{site}{path} answered {status} without X-Content-Type-Options: "
                "nosniff"
            )


def smoke_hub(site_url: str, api_url: str, *, attempts: int, interval: float) -> str:
    """Check the public hub through the site's and the API's distributions.

    :param site_url: The public site, e.g. ``https://shikkhokplus.com``
    :param api_url: The API, e.g. ``https://api.shikkhokplus.com``
    :param attempts: How many times to try the landing page
    :param interval: Seconds between those tries
    :return: A one-line description of what was verified
    :raises RuntimeError: Any check failed; the message names which
    """
    site = site_url.rstrip("/")
    api = api_url.rstrip("/")
    for attempt in range(1, attempts + 1):
        try:
            _check_landing(site)
            break
        except (RuntimeError, urllib.error.URLError, OSError) as exc:
            if attempt == attempts:
                raise RuntimeError(str(exc)) from None
            print(f"attempt {attempt}/{attempts}: {exc}", file=sys.stderr)
            time.sleep(interval)

    _expect(f"{site}/hub/sitemap.xml", 200, f"{site}/hub/sitemap.xml")
    _expect(f"{site}/hub/en?sort=rating", 200, f"{site}/hub/en?sort=rating")
    _expect(f"{site}/hub/en?utm=x", 400, f"{site}/hub/en?utm=x")
    absent = f"{site}/hub/en/t/{ABSENT_SLUG}"
    _expect(absent, 404, absent)
    _expect(f"{api}/hub/en", 404, f"the API host's {api}/hub/en")
    _check_media(site)
    return (
        f"the hub answers at {site}/hub/en with its own CSP, the sitemap, "
        "the stylesheet, a 200 for the sort key, a 400 for an unknown query "
        "key and a 404 for an unknown teacher, the photo path refusing what "
        "is not approved, and the API host refuses it"
    )


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
    parser.add_argument(
        "--hub",
        action="store_true",
        help="smoke the public hub instead: base_url is the public site",
    )
    parser.add_argument("--api-url", default="", help="with --hub: the API's URL")
    args = parser.parse_args()

    if args.hub:
        if not args.api_url:
            parser.error("--hub needs --api-url")
        try:
            print(
                smoke_hub(
                    args.base_url,
                    args.api_url,
                    attempts=args.attempts,
                    interval=args.interval,
                )
            )
        except (RuntimeError, urllib.error.URLError, OSError) as exc:
            print(f"::error::hub smoke failed: {exc}", file=sys.stderr)
            return 1
        return 0

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
