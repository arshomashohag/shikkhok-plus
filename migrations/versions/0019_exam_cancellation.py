"""A teacher can cancel an exam whose results are not published.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-05

* **``exam.cancelled_at``** is when the teacher called the exam off, or
  NULL for an exam still on. An exam is never deleted for this: marks a
  teacher drafted stay as they were (the mark table is append-only), and
  the families' inbox items point at the row.
* **``exam.cancellation_reason``** is the teacher's short note, if any.
* **A published exam cannot be cancelled**, and the CHECK says so at the
  storage layer as well: families have read its results, and taking
  those back is a correction, not a cancellation.

Notification kinds are a free ``VARCHAR(32)`` with no constraint, so the
new ``exam_cancelled`` kind needs no change here; the published set is
narrowed in ``app/api/notifications.py`` instead.

No backfill: every exam that exists before this revision is still on.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the cancellation time and reason, and forbid it once published.

    :return: None
    """
    op.add_column(
        "exam", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "exam", sa.Column("cancellation_reason", sa.String(200), nullable=True)
    )
    op.create_check_constraint(
        "ck_exam_cancelled_not_published",
        "exam",
        "cancelled_at IS NULL OR published_at IS NULL",
    )


def downgrade() -> None:
    """Drop the cancellation columns; a cancelled exam reads as on again.

    :return: None
    """
    op.drop_constraint("ck_exam_cancelled_not_published", "exam", type_="check")
    op.drop_column("exam", "cancellation_reason")
    op.drop_column("exam", "cancelled_at")
