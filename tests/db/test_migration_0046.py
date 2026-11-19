"""``0046`` adds review and reply moderation acts to the event vocabulary.

The same shape as ``0044``: the labels are added in an autocommit block, so
the test checks that they land in order after ``0044``'s, that the model's
tuple matches, that the lock timeout ``env.py`` set survives the block, that
a run which failed after the block can be rerun, and that the downgrade
rebuilds the type -- refusing while an event records a review or reply act.
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

#: The labels in place before ``0046``: ``0036``'s, then ``0044``'s.
EARLIER: Final[tuple[str, ...]] = (
    "report_filed",
    "report_upheld",
    "report_dismissed",
    "listing_suspended",
    "listing_unsuspended",
    "media_approved",
    "media_rejected",
    "media_held",
    "media_restored",
)

#: The labels ``0046`` adds, in order.
REVIEWS: Final[tuple[str, ...]] = (
    "review_approved",
    "review_rejected",
    "review_held",
    "review_restored",
    "review_removed",
    "review_published",
    "reply_approved",
    "reply_rejected",
    "reply_held",
    "reply_restored",
    "reply_removed",
)


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0045``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0045") as engine:
        yield engine


def _labels(connection: Connection) -> tuple[str, ...]:
    """Read the event kind's labels in their sort order.

    :param connection: A connection
    :return: The labels
    """
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


def test_0046_adds_labels(staged: Engine) -> None:
    """The eleven labels follow ``0044``'s; the downgrade restores the nine.

    :param staged: The engine staged at ``0045``
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    with staged.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO hub_moderation_event (id, event, target_kind, "
                "target_id, correlation_id) VALUES (:i, 'media_held', "
                "'media', :t, 'test')"
            ),
            {"i": uuid.uuid4(), "t": uuid.uuid4()},
        )

    command.upgrade(_alembic_config(url), "0046")
    with staged.connect() as connection:
        assert _labels(connection) == EARLIER + REVIEWS
    assert HUB_MODERATION_EVENT_VALUES == EARLIER + REVIEWS

    command.downgrade(_alembic_config(url), "0045")
    with staged.connect() as connection:
        assert _labels(connection) == EARLIER
        kept = connection.execute(
            sa.text("SELECT event::text FROM hub_moderation_event")
        ).scalars()
        assert list(kept) == ["media_held"]


@pytest.mark.parametrize(
    ("event", "kind"), [("review_held", "review"), ("reply_removed", "reply")]
)
def test_0046_downgrade_refuses_while_a_review_act_is_recorded(
    staged: Engine, event: str, kind: str
) -> None:
    """A recorded review or reply act blocks the downgrade.

    :param staged: The engine staged at ``0045``
    :param event: The recorded act
    :param kind: Its target kind
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    command.upgrade(_alembic_config(url), "0046")
    with staged.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO hub_moderation_event (id, event, target_kind, "
                "target_id, decision_code, correlation_id) VALUES (:i, "
                "CAST(:e AS hub_moderation_event_kind), "
                "CAST(:k AS hub_report_target), :t, 'child_safety', 'test')"
            ),
            {"i": uuid.uuid4(), "e": event, "k": kind, "t": uuid.uuid4()},
        )

    with pytest.raises(Exception, match="Cannot downgrade 0046"):
        command.downgrade(_alembic_config(url), "0045")


def test_0046_upgrade_is_rerunnable_after_the_block(staged: Engine) -> None:
    """Labels already present (a run that failed after the block) pass.

    :param staged: The engine staged at ``0045``
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    with staged.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(
            sa.text("ALTER TYPE hub_moderation_event_kind ADD VALUE 'review_approved'")
        )

    command.upgrade(_alembic_config(url), "0046")

    with staged.connect() as connection:
        assert _labels(connection) == EARLIER + REVIEWS


def test_0046_keeps_the_lock_timeout_for_what_follows(staged: Engine) -> None:
    """After the autocommit block, statements still run under the 10s timeout.

    :param staged: The engine staged at ``0045``
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
        command.upgrade(_alembic_config(url), "0046")
    finally:
        sa.event.remove(Engine, "after_cursor_execute", record)

    labels = [
        i
        for i, (sql, _) in enumerate(seen)
        if "ADD VALUE" in sql and "hub_moderation_event_kind" in sql
    ]
    assert len(labels) == len(REVIEWS)
    after = seen[labels[-1] + 1 :]
    assert any("alembic_version" in sql for sql, _ in after)
    assert [(sql, timeout) for sql, timeout in after if timeout != "10s"] == []
