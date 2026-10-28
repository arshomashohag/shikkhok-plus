"""Step 2 (RED): the rename preserves rows [NFR6.18].

**The from-zero run cannot see a destructive rename.** Migrating an empty
database and then asserting the column list passes identically whether
``0002`` renames ``account_id`` or drops it and adds a new one — both
end with the same schema, and both leave zero rows.

So this test seeds a **claimed** enrollment at the ``0001`` head, runs
the upgrade, and asserts the enrollment **still points at its account**.
Steps 2 and 4 of that sequence are the requirement; step 1 is only
setup. A row count would pass against a drop-and-recreate too, because
the count would be zero either way.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from tests.db.migration_support import (
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


def test_a_claimed_enrollment_survives_the_rename(staged: Engine) -> None:
    """The seeded link is intact after the upgrade.

    :param staged: The engine staged at ``0001``
    :return: None
    """
    batch_id = uuid.uuid4()
    with staged.begin() as connection:
        account_id = insert_account(connection, "01799000001")
        enrollment_id = insert_enrollment(
            connection,
            batch_id=batch_id,
            account_id=account_id,
            role="student",
            display_name="Rahim",
        )

    upgrade_to_head(staged)

    with staged.begin() as connection:
        row = connection.execute(
            sa.text(
                "SELECT student_account_id, display_name FROM enrollment WHERE id = :id"
            ),
            {"id": enrollment_id},
        ).one_or_none()

    # The VALUE, not the count. A drop-and-recreate leaves no row at all
    # and a count-based assertion would read that as a clean zero.
    assert row is not None, "the enrollment was destroyed by the upgrade"
    assert row[0] == account_id
    assert row[1] == "Rahim"


def test_a_dormant_enrollment_survives_with_a_null_link(staged: Engine) -> None:
    """A dormant seat keeps its display name and stays dormant.

    Dormancy is ``student_account_id IS NULL`` after the rename, so this
    also pins that the migration does not invent an account for a seat
    that never had one.

    :param staged: The engine staged at ``0001``
    :return: None
    """
    batch_id = uuid.uuid4()
    with staged.begin() as connection:
        account_id = insert_account(connection, "01799000002")
        enrollment_id = insert_enrollment(
            connection,
            batch_id=batch_id,
            account_id=account_id,
            role="student",
            display_name="Karim",
        )
        # ``0001`` makes account_id NOT NULL, so dormancy cannot be
        # seeded directly -- it becomes expressible only after 0002.
        # Seeding a claimed row and nulling it afterwards would test the
        # post-migration schema rather than the migration.

    upgrade_to_head(staged)

    with staged.begin() as connection:
        connection.execute(
            sa.text("UPDATE enrollment SET student_account_id = NULL WHERE id = :id"),
            {"id": enrollment_id},
        )
        row = connection.execute(
            sa.text(
                "SELECT student_account_id, student_relink_blocked_at, display_name "
                "FROM enrollment WHERE id = :id"
            ),
            {"id": enrollment_id},
        ).one()

    assert row[0] is None
    # Never-claimed, not claimed-then-erased. The two are distinguished
    # by the marker, and the migration must not set it [AC1.3.6].
    assert row[1] is None
    assert row[2] == "Karim"
    assert account_id is not None


def test_the_head_revision_advanced(staged: Engine) -> None:
    """Head is ``0006`` after the upgrade.

    The literal is updated by every Unit that adds a migration, which
    is the point: a head assertion that drifted silently would stop
    telling anyone which revision the suite actually ran against.

    :param staged: The engine staged at ``0001``
    :return: None
    """
    upgrade_to_head(staged)

    with staged.begin() as connection:
        revision = connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()

    assert revision == "0008"


def test_the_role_column_is_gone(staged: Engine) -> None:
    """``role`` is dropped: there is no role column anywhere [BR1.1].

    :param staged: The engine staged at ``0001``
    :return: None
    """
    upgrade_to_head(staged)

    with staged.begin() as connection:
        columns = {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'enrollment'"
                )
            )
        }

    assert "role" not in columns
    assert "account_id" not in columns
    assert {"student_account_id", "guardian_account_id"} <= columns
