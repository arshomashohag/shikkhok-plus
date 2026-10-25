"""Migration ``0006`` creates six tables and touches no ``batch`` column.

**``Batch.marksheet_visible`` is already built and already non-null**,
and its own docstring says so. D4 is the unit that makes the existing
column mean something; it adds no column for it and writes no
migration for it [BR5.4, entities.md].

The assertion is on the migration's own source rather than on the
schema, because the schema cannot distinguish "D4 did not touch it"
from "D4 touched it and put it back".
"""

from __future__ import annotations

import importlib.util
import pathlib
from types import ModuleType

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

#: Loaded by PATH rather than imported. Alembic revision modules are
#: not an importable package -- they are loaded by the migration
#: environment from the directory -- so a plain import resolves to
#: nothing and the test errors at collection rather than running.
SOURCE = (
    pathlib.Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "0006_teaching_and_recording.py"
)


def _migration() -> ModuleType:
    """Load the revision module from its file.

    :return: The loaded module
    """
    spec = importlib.util.spec_from_file_location("_migration_0006", SOURCE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration_0006 = _migration()

#: The six tables D4 creates.
EXPECTED_TABLES = frozenset(
    {
        "session",
        "queued_submission",
        "attendance",
        "exam",
        "mark",
        "announcement",
    }
)


def test_the_migration_declares_exactly_the_six_new_tables() -> None:
    assert set(migration_0006.NEW_TABLES) == EXPECTED_TABLES
    assert len(migration_0006.NEW_TABLES) == 6


def test_the_migration_touches_no_column_of_batch() -> None:
    # **The whole point** [BR5.4]. `marksheet_visible` is already
    # built and non-null; a migration adding it again, or adding a
    # default for it, would either fail or silently re-state a
    # decision D2 owns.
    text = SOURCE.read_text(encoding="utf-8")

    for forbidden in (
        'add_column("batch"',
        "add_column('batch'",
        'alter_column("batch"',
        "alter_column('batch'",
        'drop_column("batch"',
        "drop_column('batch'",
    ):
        assert forbidden not in text, (
            f"migration 0006 calls {forbidden}: the marksheet_visible "
            "column is ALREADY BUILT and non-null, so D4 ships no "
            "migration for it [BR5.4, entities.md]"
        )

    # **The OPERATIONS, not a substring of the file.** A bare
    # `"marksheet_visible" not in text` fires on the docstring that
    # explains this very rule, which is a check nobody keeps -- the
    # same mistake the queue_state assertion made before it was
    # narrowed to property names. What matters is that no `op.*`
    # call names the column.
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    operations = [
        line
        for line in code.splitlines()
        if "op." in line and "marksheet_visible" in line
    ]
    assert operations == [], (
        f"migration 0006 operates on marksheet_visible: {operations}"
    )


def test_every_new_table_exists_and_is_readable(
    restricted_session: DbSession,
) -> None:
    # The grant half of a new table's two obligations [§ 6.3]. An
    # ungranted table is INVISIBLE to the restricted role in
    # information_schema, so every governance gate silently stops
    # covering it -- which is how a control is retired rather than
    # failed.
    for table in EXPECTED_TABLES:
        restricted_session.execute(
            sa.text(f'SELECT 1 FROM "{table}" LIMIT 1')  # noqa: S608  fixed set
        )


def test_the_partial_unique_index_on_mark_is_partial(
    restricted_session: DbSession,
) -> None:
    # A FULL unique index would make a second correction impossible,
    # and the partiality is what BR4.5's supersession chain needs.
    definition = restricted_session.execute(
        sa.text(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_mark_live_per_seat'"
        )
    ).scalar_one()

    assert "UNIQUE" in definition
    assert "WHERE (superseded_by_id IS NULL)" in definition


def test_the_sessions_idempotency_constraint_exists(
    restricted_session: DbSession,
) -> None:
    # BR1.3's whole mechanism. Generation inserts with ON CONFLICT DO
    # NOTHING against this constraint by name, so a rename breaks the
    # job loudly rather than silently disabling idempotency.
    found = restricted_session.execute(
        sa.text(
            "SELECT conname FROM pg_constraint "
            "WHERE conname = 'uq_session_batch_date_start'"
        )
    ).scalar_one_or_none()

    assert found == "uq_session_batch_date_start"


def test_both_queued_submission_constraints_exist(
    restricted_session: DbSession,
) -> None:
    # Two INDEPENDENT guarantees [reliability-design § 5]: replay
    # safety on the account-scoped pair, and the version increment on
    # (session_id, kind, resulting_version). The second is what makes
    # the guarantee survive somebody rewriting the conditional update
    # into a read-then-write.
    names = {
        row[0]
        for row in restricted_session.execute(
            sa.text(
                "SELECT conname FROM pg_constraint WHERE conrelid = "
                "'queued_submission'::regclass AND contype = 'u'"
            )
        )
    }

    assert names == {
        "uq_queued_submission_replay",
        "uq_queued_submission_version",
    }


def test_the_version_constraint_is_scoped_by_kind(
    restricted_session: DbSession,
) -> None:
    # **The constraint change's own regression, at the schema level.**
    # Without `kind` in this constraint a topic write reaching topic
    # version N+1 collides with the roster write that reached
    # attendance version N+1 on the same session -- which is why the
    # naive reuse of this table for both paths could not work.
    definition = restricted_session.execute(
        sa.text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'uq_queued_submission_version'"
        )
    ).scalar_one()

    assert definition == "UNIQUE (session_id, kind, resulting_version)", (
        f"the version constraint is {definition!r}: without `kind` the "
        "two version counters share one uniqueness scope and refuse "
        "each other [BR2.1, BR3.4]"
    )


def test_the_replay_constraint_is_not_scoped_by_kind(
    restricted_session: DbSession,
) -> None:
    # The other half, and it is deliberate rather than an omission. A
    # mutation id is unique per ACCOUNT whatever path it arrived on,
    # so the same id on the other path is the same client decision --
    # adding `kind` here would let one id be spent twice.
    definition = restricted_session.execute(
        sa.text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'uq_queued_submission_replay'"
        )
    ).scalar_one()

    assert definition == "UNIQUE (submitted_by_account_id, client_mutation_id)"


def test_the_kind_column_has_no_default(
    restricted_session: DbSession,
) -> None:
    # `session.origin`'s reasoning applied to a second column: a later
    # insert path that does not state the kind is one that forgot to
    # think about it.
    default = restricted_session.execute(
        sa.text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'queued_submission' AND column_name = 'kind'"
        )
    ).scalar_one()

    assert default is None


def test_no_row_level_security_is_enabled_on_the_six_tables(
    restricted_session: DbSession,
) -> None:
    # The recorded decision [NFR14.52], asserted so the absence is
    # deliberate rather than forgotten. None of these tables has a
    # column naming its READER, so a policy would need the lens
    # resolver's three-branch join inside a USING clause -- two
    # implementations of one authorization rule, the second outside
    # app.authz's coverage and its strict mypy island.
    enabled = {
        row[0]
        for row in restricted_session.execute(
            sa.text(
                "SELECT relname FROM pg_class WHERE relrowsecurity "
                "AND relname = ANY(:names)"
            ),
            {"names": sorted(EXPECTED_TABLES)},
        )
    }

    assert enabled == set(), (
        f"row-level security is enabled on {sorted(enabled)}, which D4 "
        "deliberately does not add [NFR14.52]. If a table has gained a "
        "column identifying a reader directly, that is the stated "
        "re-open trigger and this decision should be revisited."
    )
