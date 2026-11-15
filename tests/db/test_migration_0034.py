"""``0034``'s downgrade removes the role's reach here, or refuses loudly.

Staged in a throwaway database at ``0034``. Roles are cluster-wide, so
the role itself may legitimately survive while another database depends
on it; what must hold in THIS database is that the application role is no
longer a member and the role holds nothing.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.engine import Engine

from app.db.roles import APP_ROLE, HUB_READER_ROLE
from tests.db.migration_support import _alembic_config, stage_at


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0034``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0034") as engine:
        yield engine


def _downgrade(engine: Engine) -> None:
    """Downgrade the staged database one step, to ``0033``.

    :param engine: The staged engine
    :return: None
    """
    url = engine.url.render_as_string(hide_password=False)
    command.downgrade(_alembic_config(url), "0033")


def _is_member(engine: Engine) -> bool:
    """Whether the application role is a member of the hub reader.

    :param engine: The staged engine
    :return: True while the membership exists
    """
    with engine.connect() as connection:
        return bool(
            connection.execute(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM pg_auth_members m "
                    "JOIN pg_roles r ON r.oid = m.roleid "
                    "JOIN pg_roles u ON u.oid = m.member "
                    "WHERE r.rolname = :role AND u.rolname = :member)"
                ),
                {"role": HUB_READER_ROLE, "member": APP_ROLE},
            ).scalar_one()
        )


def _local_dependencies(engine: Engine) -> int:
    """Count the objects in this database the hub reader holds privileges on.

    :param engine: The staged engine
    :return: The number of dependency rows in the current database
    """
    with engine.connect() as connection:
        return int(
            connection.execute(
                sa.text(
                    "SELECT count(*) FROM pg_shdepend d "
                    "JOIN pg_roles r ON r.oid = d.refobjid "
                    "WHERE r.rolname = :role AND d.dbid = ("
                    "SELECT oid FROM pg_database WHERE datname = current_database())"
                ),
                {"role": HUB_READER_ROLE},
            ).scalar_one()
        )


def test_downgrade_removes_membership_and_local_privileges(staged: Engine) -> None:
    """After ``0034`` -> ``0033`` the role reaches nothing in this database.

    :param staged: A database at ``0034``
    :return: None
    """
    assert _is_member(staged)
    assert _local_dependencies(staged) > 0  # USAGE on the schema

    _downgrade(staged)

    assert not _is_member(staged)
    assert _local_dependencies(staged) == 0


def test_a_leftover_local_grant_fails_the_downgrade_loudly(staged: Engine) -> None:
    """A grant a later revision failed to revert is not swallowed.

    :param staged: A database at ``0034``
    :return: None
    """
    with staged.begin() as connection:
        connection.execute(sa.text(f"GRANT SELECT ON account TO {HUB_READER_ROLE}"))

    with pytest.raises(Exception, match="revert their grants before downgrading"):
        _downgrade(staged)

    assert _local_dependencies(staged) > 0
