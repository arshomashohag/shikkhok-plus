"""What a teacher or a centre spends: one expense table.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-06

* ``expense`` is one amount an owner spent on a day, with a category, a
  short description and optionally who it was paid to and which batch or
  exam or other fee it was for. It is the owner's own record; no family sees it.
* **Categories are a closed set of keys**, not free text: each client
  renders the key in Bangla or English, which a typed category name
  never could be. ``what`` carries the detail ("Answer sheets, 200").
* **Append-only, like the ledgers.** A mistake is voided -- with who and
  why -- and entered again; the row and its amount are never changed.
  The application role gets ``SELECT`` and ``INSERT`` and ``UPDATE`` on
  the three void columns only, so a compromised credential cannot
  rewrite an amount, and nothing deletes a row but the owner's own
  cascade.
* **A resend is a replay**: ``UNIQUE (recorded_by_account_id,
  client_mutation_id)`` makes a retried record return the first one.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.roles import APP_ROLE

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The replay key the record path inserts against.
REPLAY_CONSTRAINT: Final = "uq_expense_account_mutation"

#: The closed category set, mirrored by ``app.db.models``.
CATEGORIES: Final = (
    "exam_paper",
    "printing",
    "rent",
    "utilities",
    "materials",
    "transport",
    "salary",
    "other",
)


def upgrade() -> None:
    """Create the expense table, its type, indexes and narrowed grants.

    :return: None
    """
    category = postgresql.ENUM(*CATEGORIES, name="expense_category")
    category.create(op.get_bind(), checkfirst=False)
    op.create_table(
        "expense",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("owner.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category",
            postgresql.ENUM(name="expense_category", create_type=False),
            nullable=False,
        ),
        sa.Column("what", sa.String(120), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("spent_on", sa.Date(), nullable=False),
        sa.Column("payee", sa.String(80), nullable=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column(
            "batch_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("batch.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "extra_fee_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("extra_fee.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "recorded_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("client_mutation_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "voided_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("void_reason", sa.String(200), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_expense_amount_positive"),
        sa.CheckConstraint("length(trim(what)) > 0", name="ck_expense_what"),
        sa.CheckConstraint(
            "voided_at IS NOT NULL OR void_reason IS NULL",
            name="ck_expense_void_reason_only_when_voided",
        ),
        sa.UniqueConstraint(
            "recorded_by_account_id", "client_mutation_id", name=REPLAY_CONSTRAINT
        ),
    )
    op.create_index("ix_expense_owner_spent_on", "expense", ["owner_id", "spent_on"])
    op.execute(sa.text(f"GRANT SELECT, INSERT ON expense TO {APP_ROLE}"))
    op.execute(
        sa.text(
            "GRANT UPDATE (voided_at, voided_by_account_id, void_reason) "
            f"ON expense TO {APP_ROLE}"
        )
    )


def downgrade() -> None:
    """Drop the table, refusing while any expense is recorded.

    :return: None
    """
    recorded = op.get_bind().execute(sa.text("SELECT count(*) FROM expense")).scalar()
    if recorded:
        raise RuntimeError(
            f"{recorded} expense(s) are recorded; downgrading would delete "
            "a teacher's record of what they spent. Refusing."
        )
    op.drop_table("expense")
    postgresql.ENUM(name="expense_category").drop(op.get_bind(), checkfirst=False)
