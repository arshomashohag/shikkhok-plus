"""Seed from the command line, against the configured database.

For local development and the docker-compose stack::

    python -m app.seed +8801711111111
    python -m app.seed 01711111111 --months 2 --seed 7

The account must exist and be a teacher's -- sign up in the app first,
or create one with ``python -m app.db.seed_staging``. Connects with
``SHIKKHOKPLUS_DATABASE_URL``, the restricted role, and refuses to run
when ``SHIKKHOKPLUS_ENVIRONMENT`` is production.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.db.session import build_engine
from app.seed.handler import handle
from app.seed.scenario import SeedRefused, SeedRequest


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, seed, print the report.

    :param argv: The argument vector, or None for ``sys.argv``
    :return: A process exit code
    """
    defaults = SeedRequest(phone="")
    parser = argparse.ArgumentParser(prog="python -m app.seed")
    parser.add_argument("phone", help="the teacher's number")
    parser.add_argument("--months", type=int, default=defaults.months)
    parser.add_argument("--seed", type=int, default=defaults.seed)
    args = parser.parse_args(argv)
    try:
        report = handle(
            build_engine(),
            {"phone": args.phone, "months": args.months, "seed": args.seed},
        )
    except SeedRefused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - a manual entry point
    raise SystemExit(main())
