"""Inbox sources, exam topics and payment rejection reasons.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-31

Three small additions that the family screens need and that share one
property: each is a column on a table that already exists, so the
``app`` role's table grants already cover them.

``notification`` gains ``source_id``, ``child_name`` and ``preview`` so
one inbox can carry notices, exam results and payment decisions and
point back at the thing that produced each. ``source_id`` has no
foreign key on purpose: its target lives in a different table per
``kind``. ``child_name`` is the seat's display name, copied at send
time like ``batch_name``, for guardian recipients.

``exam.topics`` is ``NOT NULL DEFAULT '{}'`` so every exam recorded
before this revision reads as having no topics rather than NULL.

``payment_claim.rejection_reason`` is nullable: only a rejection has one.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the columns and the source index.

    :return: None
    """
    op.add_column(
        "notification",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("notification", sa.Column("child_name", sa.Text(), nullable=True))
    op.add_column("notification", sa.Column("preview", sa.Text(), nullable=True))
    op.create_index("ix_notification_source", "notification", ["kind", "source_id"])
    op.add_column(
        "exam",
        sa.Column(
            "topics",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "payment_claim", sa.Column("rejection_reason", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    """Drop everything ``upgrade`` added.

    :return: None
    """
    op.drop_column("payment_claim", "rejection_reason")
    op.drop_column("exam", "topics")
    op.drop_index("ix_notification_source", table_name="notification")
    op.drop_column("notification", "preview")
    op.drop_column("notification", "child_name")
    op.drop_column("notification", "source_id")
