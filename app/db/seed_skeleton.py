"""The skeleton's verification precondition. NOT application code.

**B3's confidence hypothesis requires rows that BR6.1 forbids U3 from
creating.** The skeleton must demonstrate a teacher lens, and a teacher
lens needs an ``Owner`` row; it must demonstrate a guardian lens, and that
needs an ``Enrollment`` row. U3 may write neither table.

The empty-shell rule solved the *schema* question and left the *data*
question open, and the two are not the same. Without this script the
skeleton can prove the OTP path and the **absence** of a lens, and nothing
else -- so the single most structurally unusual decision in the system
would go undemonstrated at the one checkpoint built to demonstrate it.

**Run it by hand against staging**, as a verification precondition::

    python3 -m app.db.seed_skeleton +8801700000000

The thing an implementer would otherwise reach for is an INSERT inside U3
to make the demo work. That is the ownership transfer BR6.1 forbids,
arriving disguised as a fixture -- which is why this is a script with a
``__main__`` guard rather than a function anything can import.

**Removing this script is a B5 obligation.** It is throwaway by intent: it
exists only until U4 can create a batch for real. A test asserts no
application module imports it.
"""

from __future__ import annotations

import datetime as dt
import sys
import uuid

import sqlalchemy as sa

from app.db.session import build_engine

__all__ = ["main"]

#: The batch this seeded enrollment points at. U4 owns the batch table, so
#: there is nothing to reference yet and no foreign key to satisfy --
#: ``Enrollment.batch_id`` is deliberately unconstrained until then.
SEED_BATCH_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


def main(argv: list[str] | None = None) -> int:
    """Insert one ``Owner`` row and one ``Enrollment`` row for a number.

    The account must already exist -- sign in once through the real OTP
    path first, which is the part of the skeleton this script is not
    standing in for.

    :param argv: Command-line arguments, or None to read ``sys.argv``
    :return: A process exit status
    """
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("usage: python3 -m app.db.seed_skeleton <phone>", file=sys.stderr)
        return 2

    phone = arguments[0]
    now = dt.datetime.now(tz=dt.UTC)
    engine = build_engine()

    with engine.begin() as connection:
        account_id = connection.execute(
            sa.text("SELECT id FROM account WHERE phone = :phone"),
            {"phone": phone},
        ).scalar_one_or_none()

        if account_id is None:
            print(
                "no account for that number -- sign in once first, so the "
                "OTP path is the thing that created it.",
                file=sys.stderr,
            )
            return 1

        connection.execute(
            sa.text(
                "INSERT INTO owner (id, account_id, created_at) "
                "VALUES (:id, :account_id, :created_at)"
            ),
            {"id": uuid.uuid4(), "account_id": account_id, "created_at": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO enrollment "
                "(id, batch_id, account_id, role, display_name, created_at) "
                "VALUES (:id, :batch_id, :account_id, 'guardian', "
                ":display_name, :created_at)"
            ),
            {
                "id": uuid.uuid4(),
                "batch_id": SEED_BATCH_ID,
                "account_id": account_id,
                "display_name": "Skeleton Demo Child",
                "created_at": now,
            },
        )

    print("seeded one owner row and one guardian enrollment.")
    print("Both lenses should now resolve on the NEXT request -- no re-auth.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
