"""``0019`` adds exam cancellation and forbids it on a published exam.

Staged at ``0018`` with one published exam: it must come through still
on, and the storage layer must refuse marking it cancelled, because
results families have read are corrected and never cancelled away.
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
    """Yield an engine on a throwaway database staged at ``0018``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0018") as engine:
        yield engine


def test_0019_keeps_exams_on_and_refuses_cancelling_a_published_one(
    staged: Engine,
) -> None:
    """An existing exam is not cancelled, and cannot become cancelled.

    :param staged: The engine staged at ``0018``
    :return: None
    """
    exam_id = uuid.uuid4()
    created = dt.datetime(2026, 10, 1, 9, 0, tzinfo=dt.UTC)
    with staged.begin() as connection:
        connection.execute(sa.text("SET session_replication_role = replica"))
        connection.execute(
            sa.text(
                "INSERT INTO exam (id, batch_id, batch_subject_id, title, date, "
                "total_marks, created_at, published_at) VALUES (:id, :batch, "
                ":subject, 'Test', '2026-10-01', 50, :created, :created)"
            ),
            {
                "id": exam_id,
                "batch": uuid.uuid4(),
                "subject": uuid.uuid4(),
                "created": created,
            },
        )

    upgrade_to_head(staged)

    with staged.begin() as connection:
        cancelled, reason = connection.execute(
            sa.text(
                "SELECT cancelled_at, cancellation_reason FROM exam WHERE id = :id"
            ),
            {"id": exam_id},
        ).one()
    assert (cancelled, reason) == (None, None)

    with pytest.raises(sa.exc.IntegrityError), staged.begin() as connection:
        connection.execute(
            sa.text("UPDATE exam SET cancelled_at = now() WHERE id = :id"),
            {"id": exam_id},
        )
