"""Post-deploy smoke: the API answers, its database is reachable, at head.

Usage: ``python3 deploy/smoke.py <base-url> [--attempts N] [--interval S]``

Run by the deploy workflow against the PUBLIC URL -- through CloudFront,
the origin's certificate and nginx's origin-secret check, which is the
path a teacher's phone takes -- and by check.yml's image job against a
container on localhost. Standard library only, so it runs on any runner
without installing anything.

**What it asserts, and what it does not.** ``/health`` must answer 200,
report ``"database": "ok"``, and report the migration revision this
commit declares as its head -- derived from ``migrations/versions``, so
adding a migration cannot leave this asserting the previous one. It does
NOT exercise OTP, lens resolution or a fee read, which team.md's smoke
set also names; those need a test identity in the deployed environment
and are not automated yet. A green run here means the deployed image is
serving against a migrated database through the public path, and no
more.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
import urllib.error
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


def fetch_health(base_url: str) -> dict[str, object]:
    """GET ``<base_url>/health`` and parse it.

    :param base_url: e.g. ``https://api.example.com``
    :return: The decoded body
    """
    request = urllib.request.Request(  # noqa: S310 -- the URL is ours, https or localhost
        base_url.rstrip("/") + "/health",
        headers={"User-Agent": "shikkhokplus-smoke"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        body: dict[str, object] = json.loads(response.read())
        return body


def main() -> int:
    """Poll until healthy at head, or fail.

    :return: The process exit code
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("--attempts", type=int, default=30)
    parser.add_argument("--interval", type=float, default=10.0)
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
                return 0
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
