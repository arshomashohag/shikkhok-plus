"""Notes on a class.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-01

``session.notes`` is free text a teacher writes about one class, shown
back on the class calendar. It is a column on a table that already
exists, so the ``app`` role's grants already cover it. It is nullable
because most classes never get a note, and every session recorded
before this revision reads as having none.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable notes column.

    :return: None
    """
    op.add_column("session", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop the notes column.

    :return: None
    """
    op.drop_column("session", "notes")
