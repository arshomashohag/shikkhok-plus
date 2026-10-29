"""A teacher's deletion keeps their batches: owner.account_id SET NULL.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-28

**BR1.6 is amended.** It refused a teacher's deletion while they owned a
batch, and nothing in the app could close or hand over a batch, so a
teacher could never delete their account -- which Play requires be
possible. The amended rule follows the O5 board: the teacher's login and
profile go, and every batch stays with its students as read-only
history.

The refusal was what made the ``account -> owner -> batch`` cascade safe:
it was unreachable rather than corrected. With the refusal gone the
cascade must go too, so ``owner.account_id`` becomes nullable and
``SET NULL``. An owner row with no account is a teacher who left: no
lens resolves through it, so nobody can write to those batches again,
while each student and guardian still reaches their own seat.

After this, ``tests/db/test_cascade_contradictions.py`` asserts that NO
retained table is reachable from ``account`` by cascade at all, with no
``owner`` qualifier -- a property of the schema rather than of a refusal.

Order is load-bearing: nullable first, because ``SET NULL`` against a
``NOT NULL`` column is refused.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Named in ``0001`` and never renamed.
CONSTRAINT = "fk_owner_account_id_account"


def upgrade() -> None:
    """Make the owner link nullable and survivable.

    :return: None
    """
    op.alter_column(
        "owner", "account_id", existing_type=sa.UUID(as_uuid=True), nullable=True
    )
    op.drop_constraint(CONSTRAINT, "owner", type_="foreignkey")
    op.create_foreign_key(
        CONSTRAINT, "owner", "account", ["account_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    """Restore the cascade and ``NOT NULL``.

    **Can fail, and failing is correct**: an owner row nulled by a
    teacher's deletion has no account to restore. The deploy runbook
    takes a ``pg_dump`` before any production migration for this class
    of step.

    :return: None
    """
    op.drop_constraint(CONSTRAINT, "owner", type_="foreignkey")
    op.create_foreign_key(
        CONSTRAINT, "owner", "account", ["account_id"], ["id"], ondelete="CASCADE"
    )
    op.alter_column(
        "owner", "account_id", existing_type=sa.UUID(as_uuid=True), nullable=False
    )
