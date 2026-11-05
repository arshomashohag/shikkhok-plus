"""Decimal marks, and exams published to families only when the teacher says.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-05

Decided by the owner on 2026-11-05:

* **A mark may be any number, whole or decimal**, such as 19.5. The
  column becomes ``NUMERIC(6,2)``: exact, two places, and every whole
  mark already stored converts to the same value. The two checks on the
  column -- non-negative, and present exactly when the state is
  ``marked`` -- read the same on a numeric column and are untouched.
* **Results go out on a draft, review, publish flow.** ``exam`` gains a
  nullable ``published_at``. A family reads no mark of an exam until it
  is set. Every exam that exists before this revision was already shown
  to families, so each is backfilled as published at its creation time;
  only exams created from here on start as drafts.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Widen the mark to two decimal places and add the publish time.

    :return: None
    """
    op.alter_column(
        "mark",
        "marks",
        type_=sa.Numeric(6, 2),
        existing_type=sa.Integer(),
        existing_nullable=True,
        postgresql_using="marks::numeric(6,2)",
    )
    op.add_column(
        "exam", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(sa.text("UPDATE exam SET published_at = created_at"))


def downgrade() -> None:
    """Drop the publish time and round marks back to whole numbers.

    A decimal mark entered after this revision is rounded half up on the
    way down; nothing else is lost.

    :return: None
    """
    op.drop_column("exam", "published_at")
    op.alter_column(
        "mark",
        "marks",
        type_=sa.Integer(),
        existing_type=sa.Numeric(6, 2),
        existing_nullable=True,
        postgresql_using="round(marks)::integer",
    )
