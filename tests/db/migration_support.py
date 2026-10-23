"""Staging helpers for tests that run migrations against a live database.

Two tests need to observe a migration **in flight** rather than its
finished result: the fold guard must be caught refusing, and the
from-head test must seed rows between ``0001`` and head. Both therefore
need a database that is at ``0001`` and not at head, which the session
fixtures deliberately do not provide.

Each helper creates a **throwaway database** inside the running
container. An aborted upgrade leaves its own schema behind, and sharing
one database would carry one case's rows into the next.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

__all__ = [
    "MigrationFailed",
    "insert_account",
    "insert_enrollment",
    "stage_at",
    "stage_at_0001",
    "upgrade_to_head",
]


class MigrationFailed(RuntimeError):
    """Raised when an Alembic upgrade aborts.

    Wrapping the driver's exception keeps the tests from asserting on a
    psycopg type, while the original message is preserved as the string
    value so the refusal's content stays testable.
    """


def _alembic_config(url: str) -> object:
    """Build an Alembic config pointed at one database.

    :param url: The connection URL to migrate
    :return: The configured Alembic config object
    """
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config


@contextmanager
def stage_at(postgres_url: str, revision: str) -> Iterator[Engine]:
    """Create a throwaway database migrated to one revision and yield it.

    **Which revision a test stages at is part of what it asserts.**
    ``0001`` is the right floor for the reshape, whose subject is rows
    written before ``enrollment`` had two links. A test about ``0004``'s
    backfill of a DORMANT seat cannot use it, because ``0001`` makes
    ``account_id`` NOT NULL and dormancy only becomes expressible after
    ``0002`` -- seeding a linked row and nulling it afterwards would be
    arranging through the post-migration schema rather than the one the
    deploy meets.

    :param postgres_url: The owner connection URL of the container
    :param revision: The revision to migrate the new database to
    :return: A context manager yielding an engine on the new database
    """
    from alembic import command

    name = f"stage_{uuid.uuid4().hex[:12]}"
    admin = sa.create_engine(postgres_url, future=True, isolation_level="AUTOCOMMIT")
    with admin.begin() as connection:
        connection.execute(sa.text(f'CREATE DATABASE "{name}"'))

    # ``str()`` on a URL masks the password as ``***``, which Alembic
    # would then present as a literal credential. Render it explicitly.
    staged_url = (
        sa.engine.make_url(postgres_url)
        .set(database=name)
        .render_as_string(hide_password=False)
    )
    engine = sa.create_engine(staged_url, future=True)
    try:
        command.upgrade(_alembic_config(staged_url), revision)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name"
                ),
                {"name": name},
            )
            connection.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


@contextmanager
def stage_at_0001(postgres_url: str) -> Iterator[Engine]:
    """Create a throwaway database migrated to ``0001`` and yield it.

    :param postgres_url: The owner connection URL of the container
    :return: A context manager yielding an engine on the new database
    """
    with stage_at(postgres_url, "0001") as engine:
        yield engine


def upgrade_to_head(engine: Engine) -> None:
    """Upgrade a staged database to head, surfacing a refusal.

    :param engine: The staged engine
    :return: None
    :raises MigrationFailed: If the upgrade aborts for any reason
    """
    from alembic import command

    url = engine.url.render_as_string(hide_password=False)
    try:
        command.upgrade(_alembic_config(url), "head")
    except Exception as error:
        raise MigrationFailed(str(error)) from error


def insert_account(connection: Connection, phone: str) -> uuid.UUID:
    """Insert one account at the ``0001`` shape.

    :param connection: An open connection to the staged database
    :param phone: The account's phone number, unique per account
    :return: The new account's id
    """
    account_id = uuid.uuid4()
    connection.execute(
        sa.text(
            "INSERT INTO account (id, phone, created_at) VALUES (:id, :phone, :now)"
        ),
        {"id": account_id, "phone": phone, "now": dt.datetime.now(dt.UTC)},
    )
    return account_id


def insert_enrollment(
    connection: Connection,
    *,
    batch_id: uuid.UUID,
    account_id: uuid.UUID,
    role: str,
    display_name: str,
) -> uuid.UUID:
    """Insert one enrollment at the ``0001`` shape.

    Written against the pre-migration columns deliberately: the point of
    these tests is what happens to rows that already exist.

    :param connection: An open connection to the staged database
    :param batch_id: The batch the enrollment belongs to
    :param account_id: The enrolled account
    :param role: ``student`` or ``guardian``
    :param display_name: The teacher-typed name
    :return: The new enrollment's id
    """
    enrollment_id = uuid.uuid4()
    connection.execute(
        sa.text(
            "INSERT INTO enrollment "
            "(id, batch_id, account_id, role, display_name, created_at) "
            "VALUES (:id, :batch, :account, :role, :name, :now)"
        ),
        {
            "id": enrollment_id,
            "batch": batch_id,
            "account": account_id,
            "role": role,
            "name": display_name,
            "now": dt.datetime.now(dt.UTC),
        },
    )
    return enrollment_id
