r"""Operator commands that need the database OWNER rather than the API's role.

**One verb today: ``set-app-role-password``** [OPS-5]. A deployed API
connects as the restricted ``shikkhok_app`` role, so row-level security
and the append-only grants of ``0015`` actually bind it. ``0001`` creates
that role with no password, because a migration is committed and a
password in it would be a committed credential. Something has to give
the role its password on each host, and that something must connect as
the owner -- the restricted role cannot alter itself, which is the
point of it.

Run as::

    SHIKKHOKPLUS_MIGRATION_DATABASE_URL=<owner url> \
    SHIKKHOKPLUS_APP_DB_PASSWORD=<password> \
        python -m app.db.commands set-app-role-password

**Both variables are required and neither has a fallback.** Falling
back to ``SHIKKHOKPLUS_DATABASE_URL`` would, once the API's URL names the
restricted role, try to alter that role as itself and fail confusingly;
falling back to a default password would be a hardcoded credential.

**Idempotent**: setting the same password again is a no-op in effect,
so the host's boot script can run this on every boot rather than
tracking whether it already has.

**The password never leaves this process in plain text.** It is
hashed client-side into a SCRAM verifier by libpq (the mechanism
``\password`` in psql uses) and the verifier is what ``ALTER ROLE``
carries. A plain-text ``PASSWORD '...'`` would otherwise be written to
the server log by any ``log_statement`` setting covering DDL, and shown
in ``pg_stat_activity`` while it ran. Nothing printed by this module
carries the password or an unredacted URL.
"""

from __future__ import annotations

import os
import sys
from typing import Final, cast

import psycopg
import sqlalchemy as sa
from psycopg import sql as psycopg_sql

from app.db.roles import APP_ROLE
from app.db.session import MIGRATION_DATABASE_URL_ENV, redact_url

__all__ = ["APP_DB_PASSWORD_ENV", "CommandError", "main", "set_app_role_password"]

#: The environment variable carrying the restricted role's new password.
APP_DB_PASSWORD_ENV: Final = "SHIKKHOKPLUS_APP_DB_PASSWORD"  # noqa: S105  a variable name, not a credential

_VERB: Final = "set-app-role-password"


class CommandError(RuntimeError):
    """A refusal whose message is safe to print as-is."""


def _required(name: str) -> str:
    """Read a required, non-blank environment variable.

    :param name: The variable
    :return: Its value
    :raises CommandError: It is unset or blank
    """
    value = os.environ.get(name, "")
    if not value.strip():
        raise CommandError(f"{name} is required and is not set.")
    return value


def set_app_role_password(owner_url: str, password: str) -> None:
    """Give the restricted role LOGIN and a password, as the owner.

    :param owner_url: A URL connecting as the schema owner
    :param password: The new password, non-blank
    :return: None
    :raises CommandError: The connection or the ALTER failed; the
        message carries the redacted URL and the error class only
    """
    engine = sa.create_engine(owner_url, future=True, poolclass=sa.pool.NullPool)
    try:
        with engine.begin() as connection:
            driver = cast(
                "psycopg.Connection[object]", connection.connection.driver_connection
            )
            # libpq computes the verifier using the SERVER's
            # `password_encryption` setting, so the stored form is what a
            # plain-text ALTER would have produced.
            verifier = driver.pgconn.encrypt_password(
                password.encode(), APP_ROLE.encode()
            )
            # ALTER ROLE is a utility statement and takes no bind
            # parameter, so the literal must be quoted client-side, as
            # tests/conftest.py does. Done by the DRIVER's composition
            # here rather than through `sa.text`, which would read the
            # verifier's `:salt` segment as a bind parameter. Same
            # connection, same transaction.
            statement = psycopg_sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                psycopg_sql.Identifier(APP_ROLE),
                psycopg_sql.Literal(verifier.decode()),
            )
            with driver.cursor() as cursor:
                cursor.execute(statement)
    except (sa.exc.SQLAlchemyError, psycopg.Error) as error:
        # The class name only: a driver message can echo the statement,
        # and the statement carries the verifier.
        cause = getattr(error, "orig", None) or error
        raise CommandError(
            f"could not set the password for {APP_ROLE} via "
            f"{redact_url(owner_url)}: {type(cause).__name__}"
        ) from None
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    """Dispatch the one verb.

    :param argv: The argument vector, or None to read ``sys.argv``
    :return: 0 on success, 1 on a refusal, 2 on a usage error
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if args != [_VERB]:
        print(f"usage: python -m app.db.commands {_VERB}", file=sys.stderr)
        return 2

    try:
        owner_url = _required(MIGRATION_DATABASE_URL_ENV)
        password = _required(APP_DB_PASSWORD_ENV)
        set_app_role_password(owner_url, password)
    except CommandError as refusal:
        print(f"refusing: {refusal}", file=sys.stderr)
        return 1

    print(f"password set for {APP_ROLE} via {redact_url(owner_url)}")
    return 0


if __name__ == "__main__":  # pragma: no cover - a process entry point
    sys.exit(main())
