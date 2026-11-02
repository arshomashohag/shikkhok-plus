"""``0015`` upgrades over live rows and its downgrade restores what it took.

Staged at ``0014``, because that is the schema a deploy meets: existing
submissions carry no replay key and must keep working, and the
application role still holds the full grants this revision narrows.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.engine import Engine

from app.db.roles import APP_ROLE
from tests.db.migration_support import _alembic_config, stage_at, upgrade_to_head


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0014``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0014") as engine:
        yield engine


def _privileges(engine: Engine) -> dict[str, bool]:
    """Read the application role's write privileges on the two tables.

    :param engine: The staged engine
    :return: Privilege name to whether the role holds it table-wide
    """
    checks = {
        "ledger UPDATE": ("ledger_entry", "UPDATE"),
        "ledger DELETE": ("ledger_entry", "DELETE"),
        "audit UPDATE": ("auth_audit_log", "UPDATE"),
        "audit DELETE": ("auth_audit_log", "DELETE"),
    }
    with engine.begin() as connection:
        return {
            name: bool(
                connection.execute(
                    sa.text("SELECT has_table_privilege(:role, :table, :privilege)"),
                    {"role": APP_ROLE, "table": table, "privilege": privilege},
                ).scalar_one()
            )
            for name, (table, privilege) in checks.items()
        }


def _supersede_column_writable(engine: Engine) -> bool:
    """Say whether the role may update ``ledger_entry.superseded_by_id``.

    :param engine: The staged engine
    :return: True when the column privilege is held
    """
    with engine.begin() as connection:
        return bool(
            connection.execute(
                sa.text(
                    "SELECT has_column_privilege(:role, 'ledger_entry', "
                    "'superseded_by_id', 'UPDATE')"
                ),
                {"role": APP_ROLE},
            ).scalar_one()
        )


def _columns(engine: Engine) -> set[str]:
    """Read ``payment_submission``'s column names.

    :param engine: The staged engine
    :return: The columns
    """
    with engine.begin() as connection:
        return {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'payment_submission'"
                )
            )
        }


def test_the_upgrade_narrows_the_grants(staged: Engine) -> None:
    """From full grants at ``0014`` to supersede-only and delete-only.

    :param staged: The staged engine
    :return: None
    """
    assert all(_privileges(staged).values())

    upgrade_to_head(staged)

    assert _privileges(staged) == {
        "ledger UPDATE": False,
        "ledger DELETE": False,
        "audit UPDATE": False,
        # Kept, for the retention purge; bounded by the trigger instead.
        "audit DELETE": True,
    }
    assert _supersede_column_writable(staged)
    assert "client_mutation_id" in _columns(staged)


def test_the_downgrade_restores_the_grants_and_drops_the_key(staged: Engine) -> None:
    """``0015 -> 0014`` puts back exactly what ``0014`` had.

    :param staged: The staged engine
    :return: None
    """
    upgrade_to_head(staged)
    url = staged.url.render_as_string(hide_password=False)

    command.downgrade(_alembic_config(url), "0014")

    assert all(_privileges(staged).values())
    assert "client_mutation_id" not in _columns(staged)
    with staged.begin() as connection:
        triggers = connection.execute(
            sa.text(
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgname = 'trg_auth_audit_log_retention_floor'"
            )
        ).scalar_one()
    assert triggers == 0
