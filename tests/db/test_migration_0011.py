"""``0011`` adds inbox sources, exam topics and rejection reasons.

Staged at ``0010`` with an exam already present, because the point of a
``NOT NULL DEFAULT '{}'`` column is what happens to rows that exist.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.db.roles import APP_ROLE
from tests.db.migration_support import stage_at, upgrade_to_head

NEW_COLUMNS = {
    ("notification", "source_id"),
    ("notification", "child_name"),
    ("notification", "preview"),
    ("exam", "topics"),
    ("payment_claim", "rejection_reason"),
}


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0010``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0010") as engine:
        yield engine


def _insert_exam(engine: Engine) -> uuid.UUID:
    """Insert one exam at the ``0010`` shape, bypassing foreign keys.

    :param engine: The staged engine
    :return: The exam's id
    """
    exam_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(sa.text("SET session_replication_role = replica"))
        connection.execute(
            sa.text(
                "INSERT INTO exam (id, batch_id, batch_subject_id, title, date, "
                "total_marks, created_at) "
                "VALUES (:id, :batch, :subject, 'Unit test', :day, 50, :now)"
            ),
            {
                "id": exam_id,
                "batch": uuid.uuid4(),
                "subject": uuid.uuid4(),
                "day": dt.date(2026, 10, 1),
                "now": dt.datetime.now(dt.UTC),
            },
        )
    return exam_id


def test_0011_adds_columns_and_defaults_existing_exams_to_no_topics(
    staged: Engine,
) -> None:
    """The columns exist, old exams read no topics, the app role can update.

    :param staged: The engine staged at ``0010``
    :return: None
    """
    exam_id = _insert_exam(staged)

    upgrade_to_head(staged)

    with staged.begin() as connection:
        found = {
            (row.table_name, row.column_name)
            for row in connection.execute(
                sa.text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public'"
                )
            )
        }
        topics = connection.execute(
            sa.text("SELECT topics FROM exam WHERE id = :id"), {"id": exam_id}
        ).scalar_one()
        can_update = connection.execute(
            sa.text("SELECT has_table_privilege(:role, 'notification', 'UPDATE')"),
            {"role": APP_ROLE},
        ).scalar_one()

    assert NEW_COLUMNS <= found
    assert topics == []
    assert can_update is True
