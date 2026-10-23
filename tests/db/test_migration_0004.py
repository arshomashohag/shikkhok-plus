"""The conditional backfill, asserted against rows that already exist.

**A from-zero migration cannot see this defect.** Migrating an empty
database and then reading the column list passes identically whether
``0004`` backfills conditionally or attaches ``DEFAULT 'pending'`` --
both end with the same schema and both leave zero rows. The difference
is only visible on a database that already has seats, which is the
database the deploy actually meets [ADR-013, NFR19.2].

So these tests seed a linked seat and an unlinked seat at ``0003``,
upgrade, and read the two decision columns back. The linked seat must be
``accepted`` because under the superseded model its holder was signed in
and holding a working lens; the unlinked one must be ``pending`` because
nobody was ever named on it.

**``0003`` and not ``0001``** [migration_support]. ``0003`` is the
revision the staging deploy actually upgrades FROM, and it is the first
at which a dormant seat is expressible at all: ``0001`` makes
``enrollment.account_id`` NOT NULL and the nullable two-link shape
arrives with ``0002``. Staging at ``0001`` would force the dormant case
to be arranged through the post-migration schema, which is arranging the
answer.

The two structural assertions -- ``NOT NULL`` and **no server default**
-- are separate tests rather than extra lines, because they fail for
different reasons and a reader needs to know which.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from tests.db.migration_support import (
    insert_account,
    stage_at,
    upgrade_to_head,
)


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0003``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0003") as engine:
        yield engine


def _insert_seat(
    connection: Connection,
    *,
    batch_id: uuid.UUID,
    display_name: str,
    student_account_id: uuid.UUID | None = None,
    guardian_account_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert one seat at the ``0003`` shape, before decisions exist.

    Written against the pre-migration columns deliberately, and with no
    decision column named at all: what happens to rows that already
    exist is the whole point, and those rows were written by code that
    had never heard of a decision.

    :param connection: An open connection to the staged database
    :param batch_id: The batch the seat belongs to
    :param display_name: The teacher-typed name
    :param student_account_id: The student link, or None for dormant
    :param guardian_account_id: The guardian link, or None
    :return: The new enrollment's id
    """
    enrollment_id = uuid.uuid4()
    connection.execute(
        sa.text(
            "INSERT INTO enrollment "
            "(id, batch_id, student_account_id, guardian_account_id, "
            "display_name, created_at) "
            "VALUES (:id, :batch, :student, :guardian, :name, :now)"
        ),
        {
            "id": enrollment_id,
            "batch": batch_id,
            "student": student_account_id,
            "guardian": guardian_account_id,
            "name": display_name,
            "now": dt.datetime.now(dt.UTC),
        },
    )
    return enrollment_id


def test_a_seat_naming_an_account_backfills_to_accepted(staged: Engine) -> None:
    """A student already signed in keeps their working lens [ADR-013].

    The alternative a plain default would produce: this row reads
    ``pending`` and the person opens the app to find their batches gone.

    :param staged: The engine staged at ``0003``
    :return: None
    """
    batch_id = uuid.uuid4()
    with staged.begin() as connection:
        account_id = insert_account(connection, "01799000401")
        enrollment_id = _insert_seat(
            connection,
            batch_id=batch_id,
            student_account_id=account_id,
            display_name="Signed in already",
        )

    upgrade_to_head(staged)

    with staged.begin() as connection:
        row = connection.execute(
            sa.text(
                "SELECT student_decision, student_account_id "
                "FROM enrollment WHERE id = :id"
            ),
            {"id": enrollment_id},
        ).one()

    assert row[1] == account_id
    assert row[0] == "accepted"


def test_a_seat_naming_nobody_backfills_to_pending(staged: Engine) -> None:
    """A dormant seat was never answered, so it is pending [ADR-013].

    :param staged: The engine staged at ``0003``
    :return: None
    """
    batch_id = uuid.uuid4()
    with staged.begin() as connection:
        enrollment_id = _insert_seat(
            connection, batch_id=batch_id, display_name="Never signed in"
        )

    upgrade_to_head(staged)

    with staged.begin() as connection:
        row = connection.execute(
            sa.text(
                "SELECT student_decision, guardian_decision "
                "FROM enrollment WHERE id = :id"
            ),
            {"id": enrollment_id},
        ).one()

    assert row[0] == "pending"
    assert row[1] == "pending"


def test_the_guardian_column_backfills_from_its_own_link(staged: Engine) -> None:
    """Each column reads its OWN link, never the other's [BR5.2].

    A single backfill keyed on either link alone would grant the other
    link's holder a lens they never had -- the exact harm acceptance
    exists to prevent, written by the migration itself.

    The seat carries a student link and NO guardian link, which is the
    asymmetric case that catches it: a backfill reading
    ``student_account_id`` for both columns would write ``accepted``
    into ``guardian_decision`` for a seat that names no guardian at all.

    :param staged: The engine staged at ``0003``
    :return: None
    """
    batch_id = uuid.uuid4()
    with staged.begin() as connection:
        student_id = insert_account(connection, "01799000402")
        enrollment_id = _insert_seat(
            connection,
            batch_id=batch_id,
            student_account_id=student_id,
            guardian_account_id=None,
            display_name="Rahim",
        )

    upgrade_to_head(staged)

    with staged.begin() as connection:
        row = connection.execute(
            sa.text(
                "SELECT student_account_id, guardian_account_id, "
                "student_decision, guardian_decision "
                "FROM enrollment WHERE id = :id"
            ),
            {"id": enrollment_id},
        ).one()

    assert (row[0], row[1]) == (student_id, None)
    assert (row[2], row[3]) == ("accepted", "pending")


def test_both_decision_columns_are_not_null_with_no_server_default(
    staged: Engine,
) -> None:
    """The structural half: required, and never defaulted [ADR-013].

    A default lets a future insert path skip the decision silently, and
    the seat's initial state is exactly the thing every insert must
    state. Asserted against ``information_schema`` rather than by
    reading the migration, because the migration is what is under test.

    :param staged: The engine staged at ``0003``
    :return: None
    """
    upgrade_to_head(staged)

    with staged.begin() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT column_name, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_name = 'enrollment' "
                "AND column_name IN ('student_decision', 'guardian_decision') "
                "ORDER BY column_name"
            )
        ).all()

    assert [row[0] for row in rows] == ["guardian_decision", "student_decision"]
    for row in rows:
        assert row[1] == "NO", f"{row[0]} is nullable"
        assert row[2] is None, f"{row[0]} carries a server default: {row[2]!r}"


def test_the_address_column_is_added_nullable(staged: Engine) -> None:
    """``profile.address`` arrives nullable [FR1.17, entities.md].

    Nullable because the already-added path reaches signup with the
    name pre-filled and no address yet.

    :param staged: The engine staged at ``0003``
    :return: None
    """
    upgrade_to_head(staged)

    with staged.begin() as connection:
        row = connection.execute(
            sa.text(
                "SELECT data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'profile' AND column_name = 'address'"
            )
        ).one_or_none()

    assert row is not None, "profile.address was not added"
    assert row[0] == "text"
    assert row[1] == "YES"


def test_the_decision_enum_admits_exactly_three_values(staged: Engine) -> None:
    """Three representable decisions, and no fourth [entities.md].

    The design fixes that the three values are the only representable
    ones. A check-constrained string would satisfy that equally; what a
    native type adds is that widening the set is a visible migration
    rather than an edit to a constraint nobody reads.

    :param staged: The engine staged at ``0003``
    :return: None
    """
    upgrade_to_head(staged)

    with staged.begin() as connection:
        values = {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT e.enumlabel FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = 'enrollment_decision'"
                )
            )
        }

    assert values == {"pending", "accepted", "declined"}
