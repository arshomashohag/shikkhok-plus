"""Create a teacher account on a staging host, for a device check.

**Deliberately NOT the thing B5 deleted.** ``seed_skeleton.py`` wrote
``owner`` and ``enrollment`` with raw SQL, which made it a second,
untested write path into tables the application also writes — and its
rows were exactly what ``0002``'s fold guard refused.

This creates the **one row the API cannot create for itself** and
nothing more:

* an ``account``, because the issue path is deliberately silent for an
  unknown number and there is no public sign-up;
* an ``owner``, because a teacher lens resolves from it and no endpoint
  creates one yet — that belongs to the subscription surface, which no
  Unit has built.

**Everything else goes through the real API.** Batches, enrollments and
rosters are created by signing in and calling the endpoints, which is
the point of the device check: a seeded batch would prove the seeding
works, not that the product does.

Refuses to run against production, for the same reason the staging
outbox does: a script that creates accounts is a script that creates
accounts.

Run as::

    python -m app.db.seed_staging +8801711111111
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import uuid

import sqlalchemy as sa

from app.config import ENVIRONMENT_ENV
from app.db.session import build_engine

#: Environments this may run against. Production is absent and no
#: value adds it.
PERMITTED_ENVIRONMENTS = frozenset({"staging", "development", "test"})


def main(argv: list[str] | None = None) -> int:
    """Create an account and an owner row for one phone number.

    Idempotent: running it twice for the same number is a no-op rather
    than an error, so an operator who is unsure whether it ran can run
    it again.

    :param argv: The argument vector, or None to read ``sys.argv``
    :return: A process exit code
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print(
            "usage: python -m app.db.seed_staging <phone>\n"
            "  e.g. python -m app.db.seed_staging +8801711111111",
            file=sys.stderr,
        )
        return 2

    environment = os.environ.get(ENVIRONMENT_ENV, "development")
    if environment not in PERMITTED_ENVIRONMENTS:
        print(
            f"refusing to run: {ENVIRONMENT_ENV} is '{environment}'. "
            "This creates an account that can sign in, which is not "
            "something a script should do to a production database.",
            file=sys.stderr,
        )
        return 1

    phone = args[0]
    if not phone.startswith("+"):
        print(
            f"phone must be in international form, got '{phone}'. "
            "The issue endpoint matches on the stored value exactly, so "
            "a mismatched format seeds an account nobody can sign in to.",
            file=sys.stderr,
        )
        return 2

    engine = build_engine()
    now = dt.datetime.now(tz=dt.UTC)

    with engine.begin() as connection:
        account_id = connection.execute(
            sa.text("SELECT id FROM account WHERE phone = :phone"),
            {"phone": phone},
        ).scalar_one_or_none()

        if account_id is None:
            account_id = uuid.uuid4()
            connection.execute(
                sa.text(
                    "INSERT INTO account (id, phone, created_at) "
                    "VALUES (:id, :phone, :now)"
                ),
                {"id": account_id, "phone": phone, "now": now},
            )
            print(f"created account for {phone}")
        else:
            print(f"account for {phone} already exists")

        owner_id = connection.execute(
            sa.text("SELECT id FROM owner WHERE account_id = :account"),
            {"account": account_id},
        ).scalar_one_or_none()

        if owner_id is None:
            connection.execute(
                sa.text(
                    "INSERT INTO owner (id, account_id, created_at) "
                    "VALUES (:id, :account, :now)"
                ),
                {"id": uuid.uuid4(), "account": account_id, "now": now},
            )
            print("created owner row: the teacher lens will now resolve")
        else:
            print("owner row already exists")

    print()
    print("Next, on the device or with curl:")
    print(f'  1. POST /v1/auth/otp     {{"phone": "{phone}"}}')
    print(f"  2. GET  /staging/last-otp?phone={phone.replace('+', '%2B')}")
    print("  3. POST /v1/auth/verify  with the code from step 2")
    print("  4. POST /v1/batches      to create a batch THROUGH THE API")
    return 0


if __name__ == "__main__":  # pragma: no cover - a manual entry point
    raise SystemExit(main())
