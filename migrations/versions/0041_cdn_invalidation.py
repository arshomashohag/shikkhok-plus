"""The CloudFront invalidation outbox.

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-17

Public owner and batch pages are cached at the edge for up to ten minutes,
so a takedown that only changes a row leaves the page served from the cache.
Every takedown -- a suspension, an unpublish, a retired batch, a withdrawn
name consent, a solo owner's account deletion, a slug change -- therefore
writes the paths to evict into ``cdn_invalidation`` **in its own
transaction**, and the rows are sent to CloudFront after commit: by the
request itself, best-effort, and by a ten-minute cron as the backstop.

**Shapes, not code.** A path starts with ``/`` and carries ``*`` only as its
last character, because CloudFront rejects a wildcard anywhere else and a
row it rejects would fail every batch it rode in. Unsent rows are what the
drain reads, so they carry a partial index.

The table holds only public slugs and timestamps. The application role may
read, write and delete it (the retention purge removes rows after seven
days); the hub reader is granted nothing.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import conv

from app.db.roles import APP_ROLE

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the outbox, its unsent index and the application role's grant.

    :return: None
    """
    op.create_table(
        "cdn_invalidation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("path", sa.String(300), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("aws_id", sa.String(64), nullable=True),
        sa.Column(
            "attempts",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.CheckConstraint(
            "left(path, 1) = '/' AND strpos(left(path, -1), '*') = 0",
            name=conv("ck_cdn_invalidation_path"),
        ),
    )
    op.create_index(
        "ix_cdn_invalidation_unsent",
        "cdn_invalidation",
        ["requested_at"],
        postgresql_where=sa.text("sent_at IS NULL"),
    )
    op.execute(
        sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON cdn_invalidation TO {APP_ROLE}")
    )


def downgrade() -> None:
    """Drop the outbox.

    Nothing in it outlives its purpose: an unsent row is at most a page the
    edge serves until its own TTL ends.

    :return: None
    """
    op.drop_table("cdn_invalidation")
