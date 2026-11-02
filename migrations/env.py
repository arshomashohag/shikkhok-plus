"""Alembic environment.

The URL comes from the environment, never from ``alembic.ini``: a URL in
the repository would be a committed credential, and the test container's
URL is assigned per run so it could not be written there anyway.

**Migrations run as the table owner; the API does not** [OPS-5]. The
API's ``SHIKKHOKPLUS_DATABASE_URL`` names the restricted
``shikkhok_app`` role in a deployed environment, and that role can
neither create a table nor grant on one -- by design, since it is also
the role whose privileges ``0015`` narrows. So a deploy supplies the
owner separately as ``SHIKKHOKPLUS_MIGRATION_DATABASE_URL``, read here
first. Unset, the old single-URL behaviour holds, which is what local
Compose and the test suite rely on.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db import models as _models  # noqa: F401  registers the tables
from app.db.base import Base
from app.db.session import DATABASE_URL_ENV, MIGRATION_DATABASE_URL_ENV, build_engine

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    """Resolve the database URL for this migration run.

    Precedence: an explicit ``sqlalchemy.url`` (the test fixtures set
    one per throwaway database), then the owner URL, then the API's.

    :return: The URL
    :raises RuntimeError: The environment names no URL
    """
    configured = config.get_main_option("sqlalchemy.url", None)
    if configured:
        return configured
    owner = os.environ.get(MIGRATION_DATABASE_URL_ENV)
    if owner:
        return owner
    return str(build_engine().url.render_as_string(hide_password=False))


def run_migrations_offline() -> None:
    """Emit SQL to the script output without a live connection.

    :return: None
    """
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection.

    :return: None
    """
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _url()
    connectable = engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()


__all__ = ["DATABASE_URL_ENV", "MIGRATION_DATABASE_URL_ENV"]
