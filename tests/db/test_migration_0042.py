"""``0042`` adds the demand question's table and the first-publish anchor.

``first_published_at`` is backfilled from ``published_at``: for a listing
published before this revision that is the best evidence of its first
publish there is, and a listing never published keeps it NULL, so the
daily job never asks a draft.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.engine import Engine

from tests.db.migration_support import _alembic_config, insert_account, stage_at

PUBLISHED = dt.datetime(2026, 11, 20, 4, 0, tzinfo=dt.UTC)


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0041``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0041") as engine:
        yield engine


def _owner_with_listing(
    connection: sa.Connection, phone: str, published_at: dt.datetime | None
) -> uuid.UUID:
    """Insert a solo owner and their listing at the ``0041`` shape.

    :param connection: An open connection to the staged database
    :param phone: The owner's account phone
    :param published_at: When the listing was last published, or never
    :return: The owner id
    """
    owner_id = uuid.uuid4()
    connection.execute(
        sa.text(
            "INSERT INTO owner (id, account_id, created_at) VALUES (:o, :a, now())"
        ),
        {"o": owner_id, "a": insert_account(connection, phone)},
    )
    connection.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, slug, status, public_name, "
            "published_at) VALUES (:o, :slug, :status, 'N', :at)"
        ),
        {
            "o": owner_id,
            "slug": f"o-{owner_id.hex[:12]}",
            "status": "draft" if published_at is None else "published",
            "at": published_at,
        },
    )
    return owner_id


def test_0042_backfills_the_anchor_and_downgrades_cleanly(staged: Engine) -> None:
    """A published listing is anchored on its publish; a draft on nothing.

    :param staged: The staged engine
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    with staged.begin() as connection:
        live = _owner_with_listing(connection, "+8801711000001", PUBLISHED)
        draft = _owner_with_listing(connection, "+8801711000002", None)

    command.upgrade(_alembic_config(url), "0042")

    with staged.connect() as connection:
        anchors = dict(
            connection.execute(
                sa.text("SELECT owner_id, first_published_at FROM owner_listing")
            ).all()
        )
        tables = set(
            connection.execute(
                sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )
    assert anchors == {live: PUBLISHED, draft: None}
    assert "hub_feedback" in tables

    command.downgrade(_alembic_config(url), "0041")

    with staged.connect() as connection:
        columns = set(
            connection.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'owner_listing'"
                )
            ).scalars()
        )
        gone = connection.execute(
            sa.text("SELECT to_regclass('hub_feedback') IS NULL")
        ).scalar_one()
    assert "first_published_at" not in columns
    assert "published_at" in columns
    assert gone is True
