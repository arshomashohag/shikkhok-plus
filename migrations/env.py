"""Alembic environment.

The URL comes from the environment, never from ``alembic.ini``: a URL in
the repository would be a committed credential, and the test container's
URL is assigned per run so it could not be written there anyway.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db import models as _models  # noqa: F401  registers the tables
from app.db.base import Base
from app.db.session import DATABASE_URL_ENV, build_engine

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    """Resolve the database URL for this migration run.

    :return: The URL
    :raises RuntimeError: The environment names no URL
    """
    configured = config.get_main_option("sqlalchemy.url", None)
    if configured:
        return configured
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


__all__ = ["DATABASE_URL_ENV"]
