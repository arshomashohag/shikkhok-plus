r"""Operator commands that need the database OWNER rather than the API's role.

Two verbs: ``set-app-role-password`` and ``migrate-if-behind``.

``set-app-role-password`` [OPS-5]. A deployed API
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

``migrate-if-behind`` [C-12] is what the host's boot runs in place of a
bare ``alembic upgrade head``::

    SHIKKHOKPLUS_MIGRATION_DATABASE_URL=<owner url> \\
        python -m app.db.commands migrate-if-behind

**Why a bare upgrade broke rollback.** Every boot migrates with the
image it is booting. After a release that added a migration, rolling
back re-points the host at the PREVIOUS image, whose Alembic has never
heard of the database's revision: ``upgrade head`` fails with "Can't
locate revision", the boot exits non-zero, the replacement host is
abandoned, and the failed release keeps serving. Every later self-heal
of that group boots the old image and fails the same way.

So this command upgrades when the database is at a revision the image
knows (or at none), and **skips** the upgrade when the database is
AHEAD of the image -- which is safe only because migrations are
forward-only and backward-compatible with the previous release
[team.md Deployment]. "Ahead" cannot be read from the image's own
scripts, which by definition do not contain the newer revision, so it
is decided from the revision ids: this project numbers revisions as a
single linear sequence of zero-padded integers, so a database revision
the image does not know and whose number is greater than the image's
head is a later revision on the same line. ``tests/gates/
test_migration_numbering.py`` asserts that numbering, because this
decision is only sound while it holds.

**Anything else refuses**: an unknown revision numbered at or below the
image's head (a branch migration, or a database from another line), a
database with several heads, or an image whose own history branches.
Each of those is a schema the image was not built for, and serving
against it is the failure the boot's exit exists to prevent.
"""

from __future__ import annotations

import enum
import os
import sys
from typing import Final, cast

import psycopg
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from psycopg import sql as psycopg_sql

from app.db.roles import APP_ROLE
from app.db.session import MIGRATION_DATABASE_URL_ENV, redact_url

__all__ = [
    "APP_DB_PASSWORD_ENV",
    "CommandError",
    "MigrationPlan",
    "main",
    "migrate_if_behind",
    "plan_migration",
    "set_app_role_password",
]

#: The environment variable carrying the restricted role's new password.
APP_DB_PASSWORD_ENV: Final = "SHIKKHOKPLUS_APP_DB_PASSWORD"  # noqa: S105  a variable name, not a credential

_VERB: Final = "set-app-role-password"
_MIGRATE_VERB: Final = "migrate-if-behind"

#: The Alembic configuration, relative to the working directory -- the
#: image's ``/srv`` and the repository root alike.
ALEMBIC_INI: Final = "alembic.ini"


class MigrationPlan(enum.Enum):
    """What the boot should do with the schema."""

    #: The database is at a revision this image knows, or at none.
    UPGRADE = "upgrade"
    #: The database is at a later revision than this image's head.
    AHEAD = "ahead"


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


def plan_migration(current: tuple[str, ...], script: ScriptDirectory) -> MigrationPlan:
    """Decide whether this image may upgrade the database it booted against.

    :param current: The revision ids in ``alembic_version``, empty for a
        database never migrated
    :param script: This image's migration scripts
    :return: :attr:`MigrationPlan.UPGRADE` or :attr:`MigrationPlan.AHEAD`
    :raises CommandError: The database is at a revision this image was
        not built for and cannot be shown to be later than its head
    """
    heads = tuple(script.get_heads())
    if len(heads) != 1:
        raise CommandError(
            f"this image's migrations have {len(heads)} heads, not one; "
            "the history branches and no single head can be trusted."
        )
    head = heads[0]

    if not current:
        return MigrationPlan.UPGRADE
    if len(current) > 1:
        raise CommandError(
            f"the database records {len(current)} revisions at once "
            f"({', '.join(sorted(current))}); it is not on a single line."
        )

    revision = current[0]
    # Exact membership, never `get_revision`: Alembic resolves a PREFIX
    # of a revision id, so an unknown id could match a known one.
    known = {script_revision.revision for script_revision in script.walk_revisions()}
    if revision in known:
        return MigrationPlan.UPGRADE

    if revision.isdigit() and head.isdigit() and int(revision) > int(head):
        return MigrationPlan.AHEAD

    raise CommandError(
        f"the database is at revision {revision!r}, which this image does "
        f"not know and which is not numbered after its head {head!r}. "
        "That is a schema from another line of history; refusing to serve "
        "against it."
    )


def _alembic_config(owner_url: str) -> Config:
    """Build the Alembic configuration aimed at one database.

    :param owner_url: The owner's URL
    :return: The configuration
    """
    config = Config(ALEMBIC_INI)
    # ConfigParser interpolates `%`, and a percent-encoded password
    # carries one; doubling it is how the value survives unchanged.
    config.set_main_option("sqlalchemy.url", owner_url.replace("%", "%%"))
    return config


def _current_revisions(owner_url: str) -> tuple[str, ...]:
    """Read the database's recorded revisions.

    :param owner_url: The owner's URL
    :return: The revision ids, empty for a database never migrated
    :raises CommandError: The database could not be reached; the message
        carries the redacted URL and the error class only
    """
    engine = sa.create_engine(owner_url, future=True, poolclass=sa.pool.NullPool)
    try:
        with engine.connect() as connection:
            return tuple(MigrationContext.configure(connection).get_current_heads())
    except (sa.exc.SQLAlchemyError, psycopg.Error) as error:
        cause = getattr(error, "orig", None) or error
        raise CommandError(
            f"could not read the schema revision via {redact_url(owner_url)}: "
            f"{type(cause).__name__}"
        ) from None
    finally:
        engine.dispose()


def migrate_if_behind(owner_url: str) -> str:
    """Upgrade the database to this image's head, unless it is already later.

    A failure INSIDE a migration is not caught: it propagates with
    Alembic's own traceback, exactly as ``alembic upgrade head`` reported
    it, because that traceback is what an operator needs to diagnose it.

    :param owner_url: A URL connecting as the schema owner
    :return: A one-line account of what was done, safe to print
    :raises CommandError: The database is at a revision the image was
        not built for, or could not be reached
    """
    config = _alembic_config(owner_url)
    script = ScriptDirectory.from_config(config)
    current = _current_revisions(owner_url)
    plan = plan_migration(current, script)
    head = script.get_current_head()

    if plan is MigrationPlan.AHEAD:
        return (
            f"database is at {current[0]}, later than this image's head {head}: "
            "not upgrading. This is a rollback to an older release; migrations "
            "are forward-only and backward-compatible, so it serves as is."
        )

    alembic_command.upgrade(config, "head")
    before = current[0] if current else "an empty schema"
    return f"upgraded from {before} to {head}"


def main(argv: list[str] | None = None) -> int:
    """Dispatch one of the two verbs.

    :param argv: The argument vector, or None to read ``sys.argv``
    :return: 0 on success, 1 on a refusal, 2 on a usage error
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in ([_VERB], [_MIGRATE_VERB]):
        print(
            f"usage: python -m app.db.commands {{{_VERB}|{_MIGRATE_VERB}}}",
            file=sys.stderr,
        )
        return 2

    try:
        owner_url = _required(MIGRATION_DATABASE_URL_ENV)
        if args == [_MIGRATE_VERB]:
            print(migrate_if_behind(owner_url))
            return 0
        password = _required(APP_DB_PASSWORD_ENV)
        set_app_role_password(owner_url, password)
    except CommandError as refusal:
        print(f"refusing: {refusal}", file=sys.stderr)
        return 1

    print(f"password set for {APP_ROLE} via {redact_url(owner_url)}")
    return 0


if __name__ == "__main__":  # pragma: no cover - a process entry point
    sys.exit(main())
