"""When a class change tells families, the item says which class and when.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-11

Cancelling or rescheduling a session now puts a ``class_cancelled`` or
``class_rescheduled`` item in each accepted family member's inbox
[PO-1]. Notification kinds are a free ``VARCHAR(32)`` with no
constraint (see ``0019``), so the kinds need no change here. What the
item must carry is new:

* **``notification.class_date``** and **``class_time``**: the day and
  start time the class is on now, or was on when it was cancelled.
* **``notification.moved_from_date``** and **``moved_from_time``**: for
  a reschedule, where it was before.

**Typed columns, not text in ``preview``.** A date written into the
preview is English-shaped and cannot be localized; a client formats a
date column in the reader's language. And they are **copied at send
time** like ``batch_name``, because the item is a record of what was
said: the session row holds only where the class is now, and a
reschedule's old time exists nowhere else.

All four are NULL for every other kind and for every row before this
revision. No backfill.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The four columns, in the order they are added.
_COLUMNS = (
    ("class_date", sa.Date),
    ("class_time", sa.Time),
    ("moved_from_date", sa.Date),
    ("moved_from_time", sa.Time),
)


def upgrade() -> None:
    """Add the class date and time columns.

    :return: None
    """
    for name, kind in _COLUMNS:
        op.add_column("notification", sa.Column(name, kind(), nullable=True))


def downgrade() -> None:
    """Drop them, refusing while any class-change item exists.

    :return: None
    """
    held = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM notification "
                "WHERE kind IN ('class_cancelled', 'class_rescheduled')"
            )
        )
        .scalar()
    )
    if held:
        raise RuntimeError(
            f"{held} class-change notification(s) exist; downgrading would "
            "leave them naming no class. Refusing."
        )
    for name, _ in reversed(_COLUMNS):
        op.drop_column("notification", name)
