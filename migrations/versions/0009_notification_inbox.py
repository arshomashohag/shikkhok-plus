"""The in-app notification inbox.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-28

**One table, ``notification``: a message addressed to one account.** The
first producer is the fee reminder, which until now could only be a push
the product never had a token for; the inbox gives a reminder somewhere
to arrive. ``kind`` keeps the table open to the next producer without a
migration.

**Addressed to an ACCOUNT, deliberately, and that is the revisit trigger
0006 named.** ``account_id`` identifies the READER directly, which is
the property 0006 said would make a table a candidate for a row-level
policy. It gets none here, for the same reason ``refresh_token`` has
none: every read is ``WHERE account_id = :caller`` from the
authenticated account, with no lens to resolve and no path that takes an
account id from a request. A test asserts one account's inbox never
shows another's.

``amount`` is ``NUMERIC(12,2)`` and nullable: a reminder carries what is
owed, and a later kind may carry no money at all.

Forward-only and backward-compatible: this migration only creates.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.roles import APP_ROLE

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the notification table, its index and its grant.

    :return: None
    """
    op.create_table(
        "notification",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "enrollment_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("enrollment.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("batch_name", sa.Text(), nullable=False),
        sa.Column("period", sa.String(7), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notification_account_created",
        "notification",
        ["account_id", "created_at"],
    )
    op.execute(
        sa.text(
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON "notification" TO {APP_ROLE}'  # noqa: S608  fixed module constant
        )
    )


def downgrade() -> None:
    """Drop the notification table.

    :return: None
    """
    op.drop_table("notification")
