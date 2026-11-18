"""``0044`` adds the four photo acts to the moderation event vocabulary.

The labels are added in an autocommit block, so the test checks that they
land in order after ``0036``'s, that the model's tuple matches, that the
lock timeout ``env.py`` set survives the block, and that the downgrade
rebuilds the type -- refusing while an event records a photo act.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Final

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.engine import Connection, Engine

from app.db.models import HUB_MODERATION_EVENT_VALUES
from tests.db.migration_support import _alembic_config, stage_at

#: ``0036``'s labels, which the downgrade restores.
EARLIER: Final[tuple[str, ...]] = (
    "report_filed",
    "report_upheld",
    "report_dismissed",
    "listing_suspended",
    "listing_unsuspended",
)

#: The labels ``0044`` adds, in order.
MEDIA: Final[tuple[str, ...]] = (
    "media_approved",
    "media_rejected",
    "media_held",
    "media_restored",
)


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0043``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0043") as engine:
        yield engine


def _labels(connection: Connection) -> tuple[str, ...]:
    return tuple(
        connection.execute(
            sa.text(
                "SELECT e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = 'hub_moderation_event_kind' "
                "ORDER BY e.enumsortorder"
            )
        ).scalars()
    )


def test_0044_adds_photo_acts_and_downgrade_removes_them(staged: Engine) -> None:
    """The four labels follow ``0036``'s; the downgrade restores the five.

    :param staged: The engine staged at ``0043``
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    with staged.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO hub_moderation_event (id, event, target_kind, "
                "target_id, correlation_id) VALUES (:i, 'report_filed', "
                "'media', :t, 'test')"
            ),
            {"i": uuid.uuid4(), "t": uuid.uuid4()},
        )

    command.upgrade(_alembic_config(url), "0044")
    with staged.connect() as connection:
        assert _labels(connection) == EARLIER + MEDIA
    assert HUB_MODERATION_EVENT_VALUES == EARLIER + MEDIA

    command.downgrade(_alembic_config(url), "0043")
    with staged.connect() as connection:
        assert _labels(connection) == EARLIER
        kept = connection.execute(
            sa.text("SELECT event::text FROM hub_moderation_event")
        ).scalars()
        assert list(kept) == ["report_filed"]


def test_0044_downgrade_refuses_while_a_photo_act_is_recorded(
    staged: Engine,
) -> None:
    """A recorded hold blocks the downgrade; the moderation record is kept.

    :param staged: The engine staged at ``0043``
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    command.upgrade(_alembic_config(url), "0044")
    with staged.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO hub_moderation_event (id, event, target_kind, "
                "target_id, decision_code, correlation_id) VALUES (:i, "
                "'media_held', 'media', :t, 'child_safety', 'test')"
            ),
            {"i": uuid.uuid4(), "t": uuid.uuid4()},
        )

    with pytest.raises(Exception, match="Cannot downgrade 0044"):
        command.downgrade(_alembic_config(url), "0043")


def test_0044_upgrade_is_rerunnable_after_the_block(staged: Engine) -> None:
    """Labels already present (a run that failed after the block) pass.

    :param staged: The engine staged at ``0043``
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    with staged.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(
            sa.text("ALTER TYPE hub_moderation_event_kind ADD VALUE 'media_approved'")
        )

    command.upgrade(_alembic_config(url), "0044")

    with staged.connect() as connection:
        assert _labels(connection) == EARLIER + MEDIA


def test_0044_keeps_the_lock_timeout_for_what_follows(staged: Engine) -> None:
    """After the autocommit block, statements still run under the 10s timeout.

    The block commits the transaction ``env.py`` set ``lock_timeout`` in
    with ``SET LOCAL``; without the restore the version stamp, and any later
    migration in the same run, could queue for a lock indefinitely
    [audit C-18].

    :param staged: The engine staged at ``0043``
    :return: None
    """
    seen: list[tuple[str, str]] = []

    def record(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        probe = cursor.connection.cursor()  # type: ignore[attr-defined]
        probe.execute("SHOW lock_timeout")
        seen.append((statement, str(probe.fetchone()[0])))
        probe.close()

    url = staged.url.render_as_string(hide_password=False)
    sa.event.listen(Engine, "after_cursor_execute", record)
    try:
        command.upgrade(_alembic_config(url), "0044")
    finally:
        sa.event.remove(Engine, "after_cursor_execute", record)

    labels = [
        i
        for i, (sql, _) in enumerate(seen)
        if "ADD VALUE" in sql and "hub_moderation_event_kind" in sql
    ]
    assert len(labels) == len(MEDIA)
    after = seen[labels[-1] + 1 :]
    assert any("alembic_version" in sql for sql, _ in after)
    assert [(sql, timeout) for sql, timeout in after if timeout != "10s"] == []
