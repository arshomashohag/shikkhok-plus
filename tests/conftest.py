"""The database fixtures every integration test in this Bolt depends on.

**The restricted session is the load-bearing fixture.** Connecting as
``postgres`` would silently void the entire privacy suite: superusers and
table owners bypass row-level security, so every probe would pass against
a missing policy. The meta-test in ``tests/privacy`` runs first precisely
because this fixture is easy to get wrong in a way nothing else detects.

The container migrates with **Alembic from zero** rather than loading a
schema dump, which gives the migration path continuous exercise at no
extra cost.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.roles import APP_ROLE

#: The password the restricted role connects with inside the test
#: container. A test-only value for a container that is destroyed with the
#: session; it is not a deployment credential.
RESTRICTED_PASSWORD = "test-only-restricted"  # noqa: S105


def _require_docker() -> None:
    """Skip the integration suite when no Docker daemon is reachable.

    :return: None
    """
    import shutil
    import subprocess

    if shutil.which("docker") is None:
        pytest.skip("integration tests need a Docker daemon", allow_module_level=True)
    probe = subprocess.run(
        ["docker", "info"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        pytest.skip("integration tests need a Docker daemon", allow_module_level=True)


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Start a PostgreSQL 16 container and yield its owner URL.

    A real PostgreSQL rather than SQLite, because row-level security,
    ``NUMERIC(12,2)``, ``ON CONFLICT DO NOTHING`` and partial indexes are
    the behaviours under test and SQLite emulates none of them faithfully.

    :return: A context manager yielding the owner connection URL
    """
    _require_docker()
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> str:
    """Migrate the container from zero with Alembic.

    :param postgres_url: The owner connection URL
    :return: The same URL, with the schema applied
    """
    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", postgres_url)
    os.environ.setdefault("SHIKKHOKPLUS_DATABASE_URL", postgres_url)
    command.upgrade(config, "head")

    owner = sa.create_engine(postgres_url, future=True)
    with owner.begin() as connection:
        # ALTER ROLE is a utility statement and cannot take a bind
        # parameter, so the literal is quoted by the driver instead. Both
        # the role name and the password are fixed module constants, never
        # request input.
        quoted = sa.String().literal_processor(dialect=connection.dialect)(
            RESTRICTED_PASSWORD
        )
        connection.execute(sa.text(f"ALTER ROLE {APP_ROLE} WITH PASSWORD {quoted}"))
    owner.dispose()
    return postgres_url


@pytest.fixture(scope="session")
def restricted_url(migrated_url: str) -> str:
    """Build the URL the restricted role connects with.

    :param migrated_url: The migrated owner URL
    :return: The same database, reached as the restricted role
    """
    url = sa.engine.make_url(migrated_url)
    return str(
        url.set(username=APP_ROLE, password=RESTRICTED_PASSWORD).render_as_string(
            hide_password=False
        )
    )


@pytest.fixture(scope="session")
def restricted_engine(restricted_url: str) -> Iterator[Engine]:
    """Yield an engine connected as the **restricted** role.

    :param restricted_url: The restricted-role URL
    :return: A context manager yielding the engine
    """
    engine = sa.create_engine(restricted_url, future=True, poolclass=sa.pool.NullPool)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def owner_engine(migrated_url: str) -> Iterator[Engine]:
    """Yield an engine connected as the table **owner**.

    Used only to arrange fixture data that the restricted role's policy
    would otherwise deny, and never to make an assertion -- an assertion
    made as the owner proves nothing about the policy.

    :param migrated_url: The migrated owner URL
    :return: A context manager yielding the engine
    """
    engine = sa.create_engine(migrated_url, future=True, poolclass=sa.pool.NullPool)
    yield engine
    engine.dispose()


@pytest.fixture
def restricted_session(restricted_engine: Engine) -> Iterator[Session]:
    """Yield a session connected as the RESTRICTED role, not postgres.

    :param restricted_engine: The restricted-role engine
    :return: A context manager yielding the session
    """
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def owner_session(owner_engine: Engine) -> Iterator[Session]:
    """Yield a session connected as the table owner, for arrangement only.

    :param owner_engine: The owner engine
    :return: A context manager yielding the session
    """
    factory = sessionmaker(bind=owner_engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def _clean_tables(request: pytest.FixtureRequest) -> Iterator[None]:
    """Truncate the owned tables between integration tests.

    Only for tests that actually took a database fixture, so the pure unit
    suites pay nothing for it.

    :param request: The pytest request, used to detect database fixtures
    :return: A context manager
    """
    database_fixtures = {
        "restricted_session",
        "owner_session",
        "restricted_engine",
        "owner_engine",
    }
    if not database_fixtures & set(request.fixturenames):
        yield
        return

    yield

    engine = request.getfixturevalue("owner_engine")
    with engine.begin() as connection:
        # The table list is DERIVED from the schema, not maintained by
        # hand. A hand-kept list silently stops truncating a table a
        # later migration adds, and the leak shows up as a test that
        # passes alone and fails in sequence -- which is how
        # staging_sms_outbox was found leaking between tests.
        #
        # Deriving it is also strictly more correct: every table the
        # schema has is one a test can write.
        tables = [
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' "
                    "AND tablename <> 'alembic_version'"
                )
            )
        ]
        if tables:
            connection.execute(
                sa.text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")
            )
