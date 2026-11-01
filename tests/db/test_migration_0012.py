"""``0012`` adds the nullable ``session.notes`` column.

Staged at ``0011`` with a session already present, because the point of
a nullable column is what happens to rows that exist.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from tests.db.migration_support import stage_at, upgrade_to_head


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0011``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0011") as engine:
        yield engine


def _insert_session(engine: Engine) -> uuid.UUID:
    """Insert one session at the ``0011`` shape, bypassing foreign keys.

    :param engine: The staged engine
    :return: The session's id
    """
    session_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(sa.text("SET session_replication_role = replica"))
        connection.execute(
            sa.text(
                "INSERT INTO session (id, batch_id, date, start_time, status, "
                "origin, attendance_version, topic_version, created_at) "
                "VALUES (:id, :batch, :day, '16:00', 'scheduled', 'ad_hoc', "
                "0, 0, :now)"
            ),
            {
                "id": session_id,
                "batch": uuid.uuid4(),
                "day": dt.date(2026, 10, 1),
                "now": dt.datetime.now(dt.UTC),
            },
        )
    return session_id


def test_0012_adds_nullable_notes(staged: Engine) -> None:
    """The column exists, is nullable, bounded at 2000, and old rows read ``None``.

    :param staged: The engine staged at ``0011``
    :return: None
    """
    session_id = _insert_session(staged)

    upgrade_to_head(staged)

    with staged.begin() as connection:
        nullable, data_type, length = connection.execute(
            sa.text(
                "SELECT is_nullable, data_type, character_maximum_length "
                "FROM information_schema.columns "
                "WHERE table_name = 'session' AND column_name = 'notes'"
            )
        ).one()
        notes = connection.execute(
            sa.text("SELECT notes FROM session WHERE id = :id"), {"id": session_id}
        ).scalar_one()

    assert nullable == "YES"
    assert (data_type, length) == ("character varying", 2000)
    assert notes is None
