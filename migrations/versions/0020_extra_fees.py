"""Exam and other fees, and what a payment is for.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-06

**Three new tables, and the third is the design.**

* ``extra_fee`` is one fee a teacher raised on a batch: an exam fee or
  another fee, with the name families see, a per-student default amount
  and a due date. The amount is configuration, like ``batch.default_fee``;
  what each student owes is never stored here.
* ``extra_fee_charge`` is one student's place under that fee. Like
  ``fee_cycle`` it carries **no money column**: what the student was
  charged, paid and still owes is folded from the entries below.
  ``UNIQUE (extra_fee_id, enrollment_id)`` is the whole idempotency
  mechanism for raising a fee, exactly as ``uq_fee_cycle_enrollment_period``
  is for a month.
* ``extra_fee_entry`` is the append-only ledger of those charges, and it
  is **a separate table from ``ledger_entry`` on purpose**. Every reader
  of ``ledger_entry`` treats a period as a calendar month: it sorts
  periods to settle the oldest first, measures lateness from a month's
  due date and lists months owed. An exam fee placed in that table would
  be swept into each of those silently -- a monthly payment settling an
  exam fee, an exam fee making a student "late" on a month -- and the
  only guard would be a filter every one of those queries had to
  remember. In its own table no monthly reader can reach it. Only three
  kinds ever appear (``charge``, ``receipt``, ``forgiveness``), checked
  at the storage layer; there is no carry and no credit.

``extra_fee_entry`` is append-only for the application role from its
first row, the narrowing ``0015`` applied to ``ledger_entry``: ``SELECT``
and ``INSERT``, and ``UPDATE`` on ``superseded_by_id`` alone.

**What a payment is for** is recorded twice on ``payment_submission``:
``requested_purpose`` is what the family chose and never changes;
``purpose`` is what the teacher applied it to, which may differ, and the
family is shown both. Each ``payment_claim`` carries the purpose it was
settled under and, for an extra fee, the student's charge. Every existing
row is backfilled ``monthly``, which is what it was. The backfill uses a
temporary server default that is dropped straight after, so no insert
path can skip stating a purpose [ADR-013].

Each CHECK ties a purpose to its target: ``extra`` exactly when a fee (or
a charge) is named, so a half-written purpose is unrepresentable.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.roles import APP_ROLE

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The replay key raising a fee inserts against.
RAISE_REPLAY_CONSTRAINT: Final = "uq_extra_fee_account_mutation"

#: The idempotency constraint the fan-out inserts against.
CHARGE_CONSTRAINT: Final = "uq_extra_fee_charge_fee_enrollment"

#: Granted in full: configuration and the per-student index.
FULL_TABLES: Final = ("extra_fee", "extra_fee_charge")


def upgrade() -> None:
    """Create the three tables and the purpose columns.

    :return: None
    """
    fee_purpose = postgresql.ENUM("exam", "other", name="extra_fee_purpose")
    fee_purpose.create(op.get_bind(), checkfirst=False)
    payment_purpose = postgresql.ENUM("monthly", "extra", name="payment_purpose")
    payment_purpose.create(op.get_bind(), checkfirst=False)
    fee_purpose_col = postgresql.ENUM(name="extra_fee_purpose", create_type=False)
    purpose_col = postgresql.ENUM(name="payment_purpose", create_type=False)
    kind_col = postgresql.ENUM(name="ledger_entry_kind", create_type=False)

    op.create_table(
        "extra_fee",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "batch_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("batch.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("purpose", fee_purpose_col, nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column(
            "exam_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("exam.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column(
            "created_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("client_mutation_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_extra_fee_amount_non_negative"),
        sa.CheckConstraint("length(trim(label)) > 0", name="ck_extra_fee_label"),
        sa.CheckConstraint(
            "purpose = 'exam' OR exam_id IS NULL", name="ck_extra_fee_exam_only"
        ),
        sa.UniqueConstraint(
            "created_by_account_id",
            "client_mutation_id",
            name=RAISE_REPLAY_CONSTRAINT,
        ),
    )
    op.create_index("ix_extra_fee_batch_id", "extra_fee", ["batch_id"])

    op.create_table(
        "extra_fee_charge",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "extra_fee_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("extra_fee.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "enrollment_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("enrollment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("extra_fee_id", "enrollment_id", name=CHARGE_CONSTRAINT),
    )
    op.create_index(
        "ix_extra_fee_charge_enrollment_id", "extra_fee_charge", ["enrollment_id"]
    )

    op.create_table(
        "extra_fee_entry",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "extra_fee_charge_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("extra_fee_charge.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", kind_col, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "payment_claim_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("payment_claim.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "superseded_by_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("extra_fee_entry.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "amount >= 0", name="ck_extra_fee_entry_amount_non_negative"
        ),
        sa.CheckConstraint(
            "kind IN ('charge', 'receipt', 'forgiveness')",
            name="ck_extra_fee_entry_kind",
        ),
    )
    op.create_index(
        "ix_extra_fee_entry_charge_id", "extra_fee_entry", ["extra_fee_charge_id"]
    )
    op.create_index(
        "ix_extra_fee_entry_payment_claim_id", "extra_fee_entry", ["payment_claim_id"]
    )

    for column in ("purpose", "requested_purpose"):
        op.add_column(
            "payment_submission",
            sa.Column(column, purpose_col, nullable=False, server_default="monthly"),
        )
        op.alter_column("payment_submission", column, server_default=None)
    for column in ("extra_fee_id", "requested_extra_fee_id"):
        op.add_column(
            "payment_submission",
            sa.Column(
                column,
                sa.UUID(as_uuid=True),
                sa.ForeignKey("extra_fee.id"),
                nullable=True,
            ),
        )
    op.create_check_constraint(
        "ck_payment_submission_purpose_target",
        "payment_submission",
        "(purpose = 'extra') = (extra_fee_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_payment_submission_requested_target",
        "payment_submission",
        "(requested_purpose = 'extra') = (requested_extra_fee_id IS NOT NULL)",
    )

    op.add_column(
        "payment_claim",
        sa.Column("purpose", purpose_col, nullable=False, server_default="monthly"),
    )
    op.alter_column("payment_claim", "purpose", server_default=None)
    op.add_column(
        "payment_claim",
        sa.Column(
            "extra_fee_charge_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("extra_fee_charge.id"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_payment_claim_purpose_target",
        "payment_claim",
        "(purpose = 'extra') = (extra_fee_charge_id IS NOT NULL)",
    )
    op.create_index(
        "ix_payment_claim_extra_fee_charge_id",
        "payment_claim",
        ["extra_fee_charge_id"],
    )

    for table in FULL_TABLES:
        op.execute(
            sa.text(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}"  # noqa: S608  fixed module constants
            )
        )
    op.execute(sa.text(f"GRANT SELECT, INSERT ON extra_fee_entry TO {APP_ROLE}"))
    op.execute(
        sa.text(f"GRANT UPDATE (superseded_by_id) ON extra_fee_entry TO {APP_ROLE}")
    )


def downgrade() -> None:
    """Drop everything added, refusing while any fee was raised.

    A raised fee is a financial record: dropping its tables would delete
    what families were charged and paid. The refusal comes before any
    change, so a refused downgrade alters nothing.

    :return: None
    """
    raised = op.get_bind().execute(sa.text("SELECT count(*) FROM extra_fee")).scalar()
    if raised:
        raise RuntimeError(
            f"{raised} extra fee(s) exist; downgrading would delete what "
            "families were charged and paid. Refusing."
        )
    op.drop_index("ix_payment_claim_extra_fee_charge_id", table_name="payment_claim")
    op.drop_constraint(
        "ck_payment_claim_purpose_target", "payment_claim", type_="check"
    )
    op.drop_column("payment_claim", "extra_fee_charge_id")
    op.drop_column("payment_claim", "purpose")
    for name in (
        "ck_payment_submission_requested_target",
        "ck_payment_submission_purpose_target",
    ):
        op.drop_constraint(name, "payment_submission", type_="check")
    for column in (
        "requested_extra_fee_id",
        "extra_fee_id",
        "requested_purpose",
        "purpose",
    ):
        op.drop_column("payment_submission", column)
    op.drop_table("extra_fee_entry")
    op.drop_table("extra_fee_charge")
    op.drop_table("extra_fee")
    postgresql.ENUM(name="payment_purpose").drop(op.get_bind(), checkfirst=False)
    postgresql.ENUM(name="extra_fee_purpose").drop(op.get_bind(), checkfirst=False)
