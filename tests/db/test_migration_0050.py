"""``0050`` adds the hub's page-view counts, and its downgrade removes them.

The counting itself is tested in ``tests/hub/test_page_views.py``. Here:
that the table and its enum arrive and leave cleanly, and that a count of
zero or less is refused, so a row always means at least one view.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from tests.db.migration_support import _alembic_config, stage_at


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0049``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0049") as engine:
        yield engine


def _exists(engine: Engine) -> tuple[bool, bool]:
    """Say whether the table and its enum exist.

    :param engine: The staged engine
    :return: ``(table, enum)``
    """
    with engine.connect() as connection:
        table = connection.execute(
            sa.text("SELECT to_regclass('hub_page_view') IS NOT NULL")
        ).scalar_one()
        enum = connection.execute(
            sa.text("SELECT count(*) FROM pg_type WHERE typname = 'hub_page_kind'")
        ).scalar_one()
    return bool(table), bool(enum)


def test_0050_creates_the_counts_and_the_downgrade_drops_them(
    staged: Engine,
) -> None:
    """Up adds a table that refuses a zero count; down leaves 0049's shape.

    :param staged: The engine staged at ``0049``
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    assert _exists(staged) == (False, False)

    command.upgrade(_alembic_config(url), "0050")

    assert _exists(staged) == (True, True)
    with staged.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO hub_page_view (page_kind, page_id, day, views) "
                "VALUES ('owner', :i, current_date, 1)"
            ),
            {"i": uuid.uuid4()},
        )
    with pytest.raises(IntegrityError), staged.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO hub_page_view (page_kind, page_id, day, views) "
                "VALUES ('batch', :i, current_date, 0)"
            ),
            {"i": uuid.uuid4()},
        )

    command.downgrade(_alembic_config(url), "0049")

    assert _exists(staged) == (False, False)
