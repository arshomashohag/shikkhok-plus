"""The guard's refusal leaves the schema byte-identical.

**This is the property the deploy ordering rests on**, and it is not the
migration's own doing: the guard runs AFTER ``ADD COLUMN`` and ``RENAME
COLUMN``, so at the moment it raises the table is already half-changed.
PostgreSQL's transactional DDL and Alembic's one-transaction-per-revision
default are what roll it back.

Asserting it here rather than trusting the reasoning is the point. A
change to ``migrations/env.py`` that disabled per-migration transactions
would falsify the claim silently, and this test is what would notice.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from tests.db.migration_support import (
    MigrationFailed,
    insert_account,
    insert_enrollment,
    stage_at_0001,
    upgrade_to_head,
)


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0001``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at_0001(postgres_url) as engine:
        yield engine


def _enrollment_columns(engine: Engine) -> set[str]:
    """Read the enrollment table's column names.

    :param engine: The engine to read through
    :return: The column names present
    """
    with engine.begin() as connection:
        return {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'enrollment'"
                )
            )
        }


def test_a_refused_migration_alters_nothing(staged: Engine) -> None:
    """The column list is identical before and after the refusal.

    :param staged: The engine staged at ``0001``
    :return: None
    """
    batch_id = uuid.uuid4()
    with staged.begin() as connection:
        account_id = insert_account(connection, "01799000050")
        insert_enrollment(
            connection,
            batch_id=batch_id,
            account_id=account_id,
            role="guardian",
            display_name="unplaceable",
        )

    before = _enrollment_columns(staged)

    with pytest.raises(MigrationFailed):
        upgrade_to_head(staged)

    after = _enrollment_columns(staged)

    # The rename and the seven added columns are all rolled back.
    assert after == before
    assert "account_id" in after
    assert "student_account_id" not in after
    assert "role" in after


def test_the_revision_pointer_did_not_advance(staged: Engine) -> None:
    """A refused upgrade leaves the recorded revision at ``0001``.

    :param staged: The engine staged at ``0001``
    :return: None
    """
    batch_id = uuid.uuid4()
    with staged.begin() as connection:
        account_id = insert_account(connection, "01799000051")
        insert_enrollment(
            connection,
            batch_id=batch_id,
            account_id=account_id,
            role="guardian",
            display_name="unplaceable",
        )

    with pytest.raises(MigrationFailed):
        upgrade_to_head(staged)

    with staged.begin() as connection:
        revision = connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()

    assert revision == "0001"
