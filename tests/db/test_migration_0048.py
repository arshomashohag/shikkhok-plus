"""``0048`` adds a batch listing's seat counts and the view that publishes them.

What the view shows, and to whom, is probed as the hub reader in
``tests/privacy/test_hub_public_batch_seats_view.py``; the counts' rules in
``tests/hub/test_batch_listing.py``. Here: that a listing which exists
before the upgrade shows no seats, and that the downgrade restores
``0047``'s shape.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from typing import Final

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.engine import Connection, Engine

from tests.db.migration_support import _alembic_config, insert_account, stage_at

#: The columns ``0048`` adds to ``batch_listing``.
COLUMNS: Final[tuple[str, ...]] = (
    "seat_capacity",
    "seats_free",
    "seats_updated_at",
    "show_seats",
)

#: The view ``0048`` creates.
VIEW: Final[str] = "hub_public_batch_seats"


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0047``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0047") as engine:
        yield engine


def _staged_batch_listing(connection: Connection) -> uuid.UUID:
    """Arrange a published solo listing with one published batch, by raw SQL.

    :param connection: An open connection to the staged database
    :return: The batch id
    """
    owner_id, batch_id = uuid.uuid4(), uuid.uuid4()
    connection.execute(
        sa.text(
            "INSERT INTO owner (id, account_id, created_at) VALUES (:o, :a, now())"
        ),
        {"o": owner_id, "a": insert_account(connection, "+8801711000480")},
    )
    connection.execute(
        sa.text(
            "INSERT INTO batch (id, owner_id, name, marksheet_visible, active, "
            "created_at) VALUES (:b, :o, 'Class 9', true, true, :n)"
        ),
        {"b": batch_id, "o": owner_id, "n": dt.datetime.now(dt.UTC)},
    )
    connection.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, slug, status, public_name, "
            "published_at) VALUES (:o, 'seat-tutor', 'published', 'Rahim Sir', now())"
        ),
        {"o": owner_id},
    )
    connection.execute(
        sa.text(
            "INSERT INTO batch_listing (batch_id, owner_id, slug, status, "
            "public_title, show_fee, show_schedule, published_at) VALUES "
            "(:b, :o, 'class-9', 'published', 'Class 9 maths', true, true, now())"
        ),
        {"b": batch_id, "o": owner_id},
    )
    return batch_id


def _shape(connection: Connection) -> tuple[list[str], int]:
    """Read which seat columns and how many seat views exist.

    :param connection: An open connection
    :return: The seat columns present, sorted, and the view count
    """
    columns = sorted(
        connection.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'batch_listing' AND column_name = ANY(:c)"
            ),
            {"c": list(COLUMNS)},
        ).scalars()
    )
    views = connection.execute(
        sa.text("SELECT count(*) FROM pg_class WHERE relname = :v AND relkind = 'v'"),
        {"v": VIEW},
    ).scalar_one()
    return columns, views


def test_0048_adds_hidden_seats_and_the_view_and_downgrade_removes_them(
    staged: Engine,
) -> None:
    """An existing listing shows no seats; the downgrade restores ``0047``.

    :param staged: The engine staged at ``0047``
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    with staged.begin() as connection:
        batch_id = _staged_batch_listing(connection)
        assert _shape(connection) == ([], 0)

    command.upgrade(_alembic_config(url), "0048")

    with staged.connect() as connection:
        assert _shape(connection) == (sorted(COLUMNS), 1)
        stored = connection.execute(
            sa.text(
                "SELECT show_seats, seat_capacity, seats_free, seats_updated_at "
                "FROM batch_listing WHERE batch_id = :b"
            ),
            {"b": batch_id},
        ).one()
        rows = connection.execute(
            sa.text(f"SELECT count(*) FROM {VIEW}")  # noqa: S608 -- module constant
        ).scalar_one()
    assert tuple(stored) == (False, None, None, None)
    assert rows == 0

    command.downgrade(_alembic_config(url), "0047")

    with staged.connect() as connection:
        assert _shape(connection) == ([], 0)
