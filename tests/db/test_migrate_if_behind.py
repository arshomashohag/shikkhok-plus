"""``python -m app.db.commands migrate-if-behind`` [C-12].

The boot's migration step, which must let a ROLLBACK boot: an image
older than the database it meets skips the upgrade instead of failing
with "Can't locate revision" and abandoning the host.

The decision is tested against this repository's real migration
scripts, so a change to the numbering scheme that the decision relies
on fails here as well as in ``tests/gates/test_migration_numbering.py``.
The end-to-end cases run against the real container, because what is
under test is what Alembic does to a real ``alembic_version`` row.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.db.commands import (
    ALEMBIC_INI,
    CommandError,
    MigrationPlan,
    main,
    migrate_if_behind,
    plan_migration,
)
from app.db.session import MIGRATION_DATABASE_URL_ENV
from tests.db.migration_support import stage_at


@pytest.fixture(scope="module")
def script() -> ScriptDirectory:
    """Load this repository's migration scripts.

    :return: The script directory ``alembic.ini`` names
    """
    return ScriptDirectory.from_config(Config(ALEMBIC_INI))


def _head(script: ScriptDirectory) -> str:
    """Return the single head.

    :param script: The scripts
    :return: The head revision id
    """
    head = script.get_current_head()
    assert head is not None
    return head


def _after(revision: str) -> str:
    """Return the next number in the zero-padded sequence.

    :param revision: A numbered revision id
    :return: The id one later, padded the same way
    """
    return str(int(revision) + 1).zfill(len(revision))


def test_a_fresh_database_is_upgraded(script: ScriptDirectory) -> None:
    assert plan_migration((), script) is MigrationPlan.UPGRADE


def test_a_database_at_the_head_is_upgraded_which_is_a_no_op(
    script: ScriptDirectory,
) -> None:
    assert plan_migration((_head(script),), script) is MigrationPlan.UPGRADE


def test_a_database_behind_the_head_is_upgraded(script: ScriptDirectory) -> None:
    assert plan_migration(("0001",), script) is MigrationPlan.UPGRADE


def test_a_database_ahead_of_the_image_is_left_alone(
    script: ScriptDirectory,
) -> None:
    # THE ROLLBACK CASE. The previous image meets the revision the
    # failed release added, which it has never heard of.
    later = _after(_head(script))

    assert plan_migration((later,), script) is MigrationPlan.AHEAD


@pytest.mark.parametrize(
    "revision",
    [
        # A branch revision with a name rather than a number.
        "a1b2c3d4e5f6",
        # Numbered, unknown, and NOT after the head: another line.
        "0000",
        # A prefix of every known id. Alembic would resolve it as a
        # partial identifier; the decision must not.
        "00",
    ],
)
def test_an_unknown_revision_not_after_the_head_refuses(
    script: ScriptDirectory, revision: str
) -> None:
    with pytest.raises(CommandError, match="another line"):
        plan_migration((revision,), script)


def test_a_database_with_two_heads_refuses(script: ScriptDirectory) -> None:
    with pytest.raises(CommandError, match="single line"):
        plan_migration(("0001", "0002"), script)


@dataclass(frozen=True)
class _BranchedScripts:
    """Stands in for a script directory whose history has two heads."""

    def get_heads(self) -> list[str]:
        """Two heads.

        :return: The heads
        """
        return ["0002", "0003"]


def test_an_image_whose_history_branches_refuses() -> None:
    branched = _BranchedScripts()

    with pytest.raises(CommandError, match="2 heads"):
        plan_migration(("0001",), branched)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Against the real container.
# ---------------------------------------------------------------------------


@pytest.fixture
def staged_at_head(postgres_url: str, script: ScriptDirectory) -> Iterator[str]:
    """Yield the owner URL of a throwaway database migrated to head.

    :param postgres_url: The container's owner URL
    :param script: The scripts
    :return: A context manager yielding the URL
    """
    with stage_at(postgres_url, _head(script)) as engine:
        yield engine.url.render_as_string(hide_password=False)


def _version(url: str) -> str:
    """Read the recorded revision.

    :param url: The database URL
    :return: The single revision id
    """
    engine = sa.create_engine(url, poolclass=sa.pool.NullPool)
    try:
        with engine.connect() as connection:
            return str(
                connection.execute(
                    sa.text("SELECT version_num FROM alembic_version")
                ).scalar_one()
            )
    finally:
        engine.dispose()


def _stamp(url: str, revision: str) -> None:
    """Record a revision without running anything, as a newer image would.

    :param url: The database URL
    :param revision: The revision to record
    :return: None
    """
    engine = sa.create_engine(url, poolclass=sa.pool.NullPool)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text("UPDATE alembic_version SET version_num = :revision"),
                {"revision": revision},
            )
    finally:
        engine.dispose()


def test_an_older_image_boots_against_a_newer_database(
    staged_at_head: str, script: ScriptDirectory
) -> None:
    later = _after(_head(script))
    _stamp(staged_at_head, later)

    outcome = migrate_if_behind(staged_at_head)

    assert "not upgrading" in outcome
    assert _version(staged_at_head) == later, "the newer revision was rewritten"


def test_a_database_behind_the_image_is_brought_to_head(
    postgres_url: str, script: ScriptDirectory
) -> None:
    # Guards the test above: a command that never upgraded anything
    # would pass it.
    previous = script.get_revision(_head(script)).down_revision
    assert isinstance(previous, str)

    with stage_at(postgres_url, previous) as engine:
        url = engine.url.render_as_string(hide_password=False)
        outcome = migrate_if_behind(url)

        assert outcome == f"upgraded from {previous} to {_head(script)}"
        assert _version(url) == _head(script)


def test_the_verb_refuses_a_foreign_revision_with_a_non_zero_exit(
    staged_at_head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stamp(staged_at_head, "0000")
    monkeypatch.setenv(MIGRATION_DATABASE_URL_ENV, staged_at_head)

    assert main(["migrate-if-behind"]) == 1
    assert _version(staged_at_head) == "0000"


def test_the_verb_needs_the_owner_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(MIGRATION_DATABASE_URL_ENV, raising=False)

    assert main(["migrate-if-behind"]) == 1


def test_an_unreachable_database_is_a_refusal_not_a_traceback() -> None:
    with pytest.raises(CommandError, match="could not read the schema revision"):
        migrate_if_behind(
            "postgresql+psycopg://nobody:secret@127.0.0.1:1/nowhere?connect_timeout=2"
        )
