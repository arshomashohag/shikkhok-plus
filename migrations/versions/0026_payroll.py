"""Payroll: a salary line per staff member per month, adjustments, payments.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-06

* **``salary_line``** is one staff member's pay for one month. It holds
  the basis and the rate as they were when the line was drawn, so a later
  change to the staff record never reprices a month already drawn. It is
  ``draft`` until a manager approves it, and approving freezes
  ``classes_held`` and ``base_amount``: a class edited next month never
  silently changes a salary already approved. One line per person per
  month (``UNIQUE (staff_id, period)``), so drawing the month twice draws
  nothing new, the same rule fee cycles follow.
* **``salary_adjustment``** is a named addition or deduction, its amount
  never negative and its sign carried by its kind -- the ledger's own
  rule. Written only while the line is a draft.
* **``expense.salary_line_id``**: paying a salary records an expense
  against its line, so the month's summary counts it as money out and the
  line shows paid and remaining, both derived, never stored.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.roles import APP_ROLE

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the salary tables and link expenses to them.

    :return: None
    """
    postgresql.ENUM("draft", "approved", name="salary_status").create(
        op.get_bind(), checkfirst=False
    )
    postgresql.ENUM("addition", "deduction", name="adjustment_kind").create(
        op.get_bind(), checkfirst=False
    )
    op.create_table(
        "salary_line",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("owner.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "staff_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("staff.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column(
            "basis",
            postgresql.ENUM(name="pay_basis", create_type=False),
            nullable=False,
        ),
        sa.Column("rate", sa.Numeric(12, 2), nullable=False),
        sa.Column("classes_held", sa.Integer(), nullable=True),
        sa.Column("base_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="salary_status", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "approved_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("staff_id", "period", name="uq_salary_line_staff_period"),
        sa.CheckConstraint(
            "period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'", name="ck_salary_line_period"
        ),
        sa.CheckConstraint("basis <> 'none'", name="ck_salary_line_paid_basis"),
        sa.CheckConstraint("rate > 0", name="ck_salary_line_rate_positive"),
        sa.CheckConstraint(
            "(status = 'draft' AND base_amount IS NULL AND approved_at IS NULL) "
            "OR (status = 'approved' AND base_amount IS NOT NULL "
            "AND base_amount >= 0 AND classes_held >= 0 AND approved_at IS NOT NULL)",
            name="ck_salary_line_frozen_on_approval",
        ),
    )
    op.create_index(
        "ix_salary_line_owner_period", "salary_line", ["owner_id", "period"]
    )
    op.create_table(
        "salary_adjustment",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "salary_line_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("salary_line.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kind",
            postgresql.ENUM(name="adjustment_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_salary_adjustment_amount_positive"),
        sa.CheckConstraint(
            "length(trim(label)) > 0", name="ck_salary_adjustment_label"
        ),
    )
    op.create_index(
        "ix_salary_adjustment_line", "salary_adjustment", ["salary_line_id"]
    )
    op.add_column(
        "expense",
        sa.Column(
            "salary_line_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("salary_line.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_expense_salary_line", "expense", ["salary_line_id"])
    for table in ("salary_line", "salary_adjustment"):
        op.execute(
            sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        )


def downgrade() -> None:
    """Drop payroll, refusing while any salary line exists.

    :return: None
    """
    lines = op.get_bind().execute(sa.text("SELECT count(*) FROM salary_line")).scalar()
    if lines:
        raise RuntimeError(
            f"{lines} salary line(s) exist; downgrading would destroy a "
            "centre's payroll record. Refusing."
        )
    op.drop_index("ix_expense_salary_line", table_name="expense")
    op.drop_column("expense", "salary_line_id")
    op.drop_table("salary_adjustment")
    op.drop_table("salary_line")
    postgresql.ENUM(name="adjustment_kind").drop(op.get_bind(), checkfirst=False)
    postgresql.ENUM(name="salary_status").drop(op.get_bind(), checkfirst=False)
