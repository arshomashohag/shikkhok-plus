"""``0049`` makes an interest a second kind of join request.

The kinds' rules are tested in ``tests/enquiries/test_interest.py``. Here:
that a request sent before the upgrade is a ``join`` after it, and that the
downgrade restores ``0048``'s shape -- and refuses while an interest exists,
since it would have to delete a number a family chose to share.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.engine import Connection, Engine

from tests.db.migration_support import _alembic_config, insert_account, stage_at


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0048``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0048") as engine:
        yield engine


def _owner(connection: Connection) -> uuid.UUID:
    """Arrange a published owner listing, by raw SQL.

    :param connection: An open connection to the staged database
    :return: The owner id
    """
    owner_id = uuid.uuid4()
    connection.execute(
        sa.text(
            "INSERT INTO owner (id, account_id, created_at) VALUES (:o, :a, now())"
        ),
        {"o": owner_id, "a": insert_account(connection, "+8801711000490")},
    )
    connection.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, slug, status, public_name, "
            "published_at) VALUES (:o, 'kind-tutor', 'published', 'Rahim Sir', now())"
        ),
        {"o": owner_id},
    )
    return owner_id


def _kind_exists(connection: Connection) -> bool:
    """Say whether ``listing_enquiry.kind`` exists.

    :param connection: An open connection
    :return: Whether the column exists
    """
    return bool(
        connection.execute(
            sa.text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'listing_enquiry' AND column_name = 'kind'"
            )
        ).scalar_one()
    )


def test_0049_keeps_requests_as_join_and_the_downgrade_guards_interests(
    staged: Engine,
) -> None:
    """A request becomes a ``join``; an interest blocks the downgrade until gone.

    :param staged: The engine staged at ``0048``
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    with staged.begin() as connection:
        owner_id = _owner(connection)
        family = insert_account(connection, "+8801711000491")
        connection.execute(
            sa.text(
                "INSERT INTO listing_enquiry (owner_id, enquirer_account_id, "
                "student_name, class_level, share_contact) "
                "VALUES (:o, :a, 'Nadia', 'class_8', true)"
            ),
            {"o": owner_id, "a": family},
        )

    command.upgrade(_alembic_config(url), "0049")

    with staged.begin() as connection:
        kinds = list(
            connection.execute(
                sa.text("SELECT kind::text FROM listing_enquiry")
            ).scalars()
        )
        assert kinds == ["join"]
        interest_id = connection.execute(
            sa.text(
                "INSERT INTO listing_enquiry (owner_id, enquirer_account_id, kind, "
                "share_contact) VALUES (:o, :a, 'interest', true) RETURNING id"
            ),
            {"o": owner_id, "a": family},
        ).scalar_one()

    with pytest.raises(Exception, match="Cannot downgrade 0049"):
        command.downgrade(_alembic_config(url), "0048")

    with staged.begin() as connection:
        assert _kind_exists(connection)
        connection.execute(
            sa.text("DELETE FROM listing_enquiry WHERE id = :i"), {"i": interest_id}
        )

    command.downgrade(_alembic_config(url), "0048")

    with staged.connect() as connection:
        assert not _kind_exists(connection)
        enums = connection.execute(
            sa.text("SELECT count(*) FROM pg_type WHERE typname = 'hub_enquiry_kind'")
        ).scalar_one()
        assert enums == 0
