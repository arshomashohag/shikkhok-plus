"""``0017`` widens marks to two decimals and adds the publish time.

Staged at ``0016`` with an exam and a whole mark already present: the
mark must read back unchanged, and the existing exam must come out
published, because families could already see it.
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
    """Yield an engine on a throwaway database staged at ``0016``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0016") as engine:
        yield engine


def test_0017_keeps_whole_marks_and_publishes_existing_exams(staged: Engine) -> None:
    """A whole mark reads back the same; an old exam is published.

    :param staged: The engine staged at ``0016``
    :return: None
    """
    exam_id, mark_id = uuid.uuid4(), uuid.uuid4()
    created = dt.datetime(2026, 10, 1, 9, 0, tzinfo=dt.UTC)
    with staged.begin() as connection:
        connection.execute(sa.text("SET session_replication_role = replica"))
        connection.execute(
            sa.text(
                "INSERT INTO exam (id, batch_id, batch_subject_id, title, date, "
                "total_marks, created_at) VALUES (:id, :batch, :subject, 'Test', "
                "'2026-10-01', 50, :created)"
            ),
            {
                "id": exam_id,
                "batch": uuid.uuid4(),
                "subject": uuid.uuid4(),
                "created": created,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO mark (id, exam_id, enrollment_id, result_state, marks, "
                "recorded_at, created_at) VALUES (:id, :exam, :seat, 'marked', 44, "
                ":created, :created)"
            ),
            {"id": mark_id, "exam": exam_id, "seat": uuid.uuid4(), "created": created},
        )

    upgrade_to_head(staged)

    with staged.begin() as connection:
        marks, data_type, scale = connection.execute(
            sa.text(
                "SELECT m.marks, c.data_type, c.numeric_scale FROM mark m, "
                "information_schema.columns c WHERE m.id = :id "
                "AND c.table_name = 'mark' AND c.column_name = 'marks'"
            ),
            {"id": mark_id},
        ).one()
        published = connection.execute(
            sa.text("SELECT published_at FROM exam WHERE id = :id"), {"id": exam_id}
        ).scalar_one()

    assert (data_type, scale) == ("numeric", 2)
    assert float(marks) == 44
    assert published == created
