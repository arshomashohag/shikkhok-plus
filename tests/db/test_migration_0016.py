"""``0016`` adds the address in four nullable parts.

Staged at ``0015`` with a profile already present, because the point of
nullable columns is what happens to rows that exist: an address typed
before the four parts stays where it was.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from tests.db.migration_support import stage_at, upgrade_to_head

#: Each new column and its bound.
COLUMNS = {
    "address_house": 60,
    "address_road": 120,
    "address_city": 60,
    "address_postcode": 10,
}


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0015``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0015") as engine:
        yield engine


def test_0016_adds_four_nullable_parts_and_keeps_the_old_address(
    staged: Engine,
) -> None:
    """The parts exist, nullable and bounded; an old address survives.

    :param staged: The engine staged at ``0015``
    :return: None
    """
    account_id = uuid.uuid4()
    with staged.begin() as connection:
        connection.execute(sa.text("SET session_replication_role = replica"))
        connection.execute(
            sa.text(
                "INSERT INTO profile (account_id, address) "
                "VALUES (:id, 'House 7, Road 11, Dhaka')"
            ),
            {"id": account_id},
        )

    upgrade_to_head(staged)

    with staged.begin() as connection:
        shapes = {
            name: (nullable, length)
            for name, nullable, length in connection.execute(
                sa.text(
                    "SELECT column_name, is_nullable, character_maximum_length "
                    "FROM information_schema.columns "
                    "WHERE table_name = 'profile' "
                    "AND column_name LIKE 'address_%'"
                )
            )
        }
        row = connection.execute(
            sa.text(
                "SELECT address, address_house, address_postcode "
                "FROM profile WHERE account_id = :id"
            ),
            {"id": account_id},
        ).one()

    assert shapes == {name: ("YES", length) for name, length in COLUMNS.items()}
    assert tuple(row) == ("House 7, Road 11, Dhaka", None, None)
