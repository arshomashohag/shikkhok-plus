"""Emit the canonical OpenAPI document to stdout.

A module entry point rather than a function call, because the determinism
check needs to run generation in a **separate process**. Python seeds hash
randomization once per process, so two generations inside one process share
an ordering by construction and agree however unstable the serialization
is. A subprocess gets a fresh seed, which is the only arrangement that can
observe a set-derived ordering.

Run as ``python -m app.contract.emit``. This is also what ``make openapi``
calls, so the committed document and the gate's comparison come from the
same code path -- there is no second renderer to drift.
"""

from __future__ import annotations

import sys

from app.contract.serialize import canonical
from app.main import app


def main() -> int:
    """Write the canonical document to stdout.

    :return: The process exit code
    """
    sys.stdout.write(canonical(app.openapi()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
