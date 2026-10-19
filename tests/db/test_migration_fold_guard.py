"""Step 1 (RED): the fold guard refuses what it cannot place.

The ``0002`` migration folds each ``role='guardian'`` enrollment into the
student row of the same batch and then deletes it. **That is only safe
when the batch holds exactly one student row.** Zero students and the
guardian's link has nowhere to go; two and the fold would have to pick,
which is a guess wearing a migration's authority.

**The seed script's shape is the zero case**, not a hypothetical: the
B3 checkpoint instructs the operator to run ``seed_skeleton.py``, which
creates one guardian enrollment and no student row at all. A fold that
deletes what it cannot place would destroy that link silently, and the
operator would discover it when a guardian could not sign in.

The guard therefore runs against the **real migration on a real
container**, not against a transcription of its logic. A test that
re-implements the predicate passes whether or not the migration
contains it.
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

    Each case needs its own database: the guard aborts the upgrade, and
    a shared container would carry one case's rows into the next.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at_0001(postgres_url) as engine:
        yield engine


def _batch_with(
    engine: Engine,
    *,
    students: int,
    guardians: int,
) -> uuid.UUID:
    """Create one batch's worth of enrollment rows at the ``0001`` shape.

    :param engine: The staged engine
    :param students: How many ``role='student'`` rows to create
    :param guardians: How many ``role='guardian'`` rows to create
    :return: The batch id the rows share
    """
    batch_id = uuid.uuid4()
    with engine.begin() as connection:
        for index in range(students):
            account_id = insert_account(connection, f"0170000{index:04d}")
            insert_enrollment(
                connection,
                batch_id=batch_id,
                account_id=account_id,
                role="student",
                display_name=f"student-{index}",
            )
        for index in range(guardians):
            account_id = insert_account(connection, f"0180000{index:04d}")
            insert_enrollment(
                connection,
                batch_id=batch_id,
                account_id=account_id,
                role="guardian",
                display_name=f"guardian-{index}",
            )
    return batch_id


def test_a_guardian_row_with_no_student_refuses(staged: Engine) -> None:
    """Zero students: the seed script's shape, and the live risk.

    :param staged: The engine staged at ``0001``
    :return: None
    """
    batch_id = _batch_with(staged, students=0, guardians=1)

    with pytest.raises(MigrationFailed) as caught:
        upgrade_to_head(staged)

    message = str(caught.value)
    # The refusal is the operator's whole user interface here, so the
    # batch and the count it found are part of the requirement.
    assert str(batch_id) in message
    assert "0" in message


def test_a_guardian_row_with_two_students_refuses(staged: Engine) -> None:
    """Two students: the fold would have to guess which one.

    :param staged: The engine staged at ``0001``
    :return: None
    """
    batch_id = _batch_with(staged, students=2, guardians=1)

    with pytest.raises(MigrationFailed) as caught:
        upgrade_to_head(staged)

    assert str(batch_id) in str(caught.value)


def test_a_guardian_row_with_exactly_one_student_folds(staged: Engine) -> None:
    """One student: the only foldable shape, and the link survives.

    Asserting the **value** rather than a row count is the requirement:
    a fold that deleted both rows would leave a count of zero and pass a
    count-based test.

    :param staged: The engine staged at ``0001``
    :return: None
    """
    batch_id = _batch_with(staged, students=1, guardians=1)

    with staged.begin() as connection:
        student_account = connection.execute(
            sa.text(
                "SELECT account_id FROM enrollment "
                "WHERE batch_id = :batch AND role = 'student'"
            ),
            {"batch": batch_id},
        ).scalar_one()
        guardian_account = connection.execute(
            sa.text(
                "SELECT account_id FROM enrollment "
                "WHERE batch_id = :batch AND role = 'guardian'"
            ),
            {"batch": batch_id},
        ).scalar_one()

    upgrade_to_head(staged)

    with staged.begin() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT student_account_id, guardian_account_id "
                "FROM enrollment WHERE batch_id = :batch"
            ),
            {"batch": batch_id},
        ).all()

    assert len(rows) == 1
    assert rows[0][0] == student_account
    assert rows[0][1] == guardian_account


def test_a_batch_with_no_guardian_row_is_untouched(staged: Engine) -> None:
    """The common shape, which must not be collateral damage.

    :param staged: The engine staged at ``0001``
    :return: None
    """
    batch_id = _batch_with(staged, students=1, guardians=0)

    upgrade_to_head(staged)

    with staged.begin() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT student_account_id, guardian_account_id "
                "FROM enrollment WHERE batch_id = :batch"
            ),
            {"batch": batch_id},
        ).all()

    assert len(rows) == 1
    assert rows[0][0] is not None
    assert rows[0][1] is None
