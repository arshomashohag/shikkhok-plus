"""Payment methods, payment submissions and claim links.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-02

``payment_method`` is where an owner keeps the places families may pay,
either a mobile-money number or a bank account. ``payment_submission``
is one payment a family reports, which one or more ``payment_claim``
rows (one per child's share) point back to through the new nullable
``payment_claim.payment_submission_id``. A child's provisional share of
a short multi-child payment can be zero, so the claimed-amount check is
relaxed for a linked claim only.

Every distinct ``(owner, channel, collection number)`` already on a
batch becomes one mobile method. The batch columns are left in place.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.roles import APP_ROLE

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

METHOD_KIND_TYPE = "payment_method_kind"
METHOD_KIND_VALUES = ("mobile", "bank")
SUBMISSION_STATUS_TYPE = "payment_submission_status"
SUBMISSION_STATUS_VALUES = ("pending", "approved", "rejected")
NEW_TABLES = ("payment_method", "payment_submission")


def upgrade() -> None:
    """Create the two tables, the claim link, the checks and the grants.

    :return: None
    """
    bind = op.get_bind()
    for name, values in (
        (METHOD_KIND_TYPE, METHOD_KIND_VALUES),
        (SUBMISSION_STATUS_TYPE, SUBMISSION_STATUS_VALUES),
    ):
        sa.Enum(*values, name=name).create(bind, checkfirst=False)
    method_kind = postgresql.ENUM(
        *METHOD_KIND_VALUES, name=METHOD_KIND_TYPE, create_type=False
    )
    submission_status = postgresql.ENUM(
        *SUBMISSION_STATUS_VALUES, name=SUBMISSION_STATUS_TYPE, create_type=False
    )

    op.create_table(
        "payment_method",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("owner.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", method_kind, nullable=False),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("mobile_number", sa.String(32), nullable=True),
        sa.Column("account_number", sa.String(64), nullable=True),
        sa.Column("account_name", sa.String(128), nullable=True),
        sa.Column("branch_name", sa.String(128), nullable=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind <> 'mobile' OR (mobile_number IS NOT NULL "
            "AND account_number IS NULL AND account_name IS NULL "
            "AND branch_name IS NULL)",
            name="ck_payment_method_mobile_shape",
        ),
        sa.CheckConstraint(
            "kind <> 'bank' OR (account_number IS NOT NULL "
            "AND account_name IS NOT NULL AND provider IS NOT NULL "
            "AND branch_name IS NOT NULL AND mobile_number IS NULL)",
            name="ck_payment_method_bank_shape",
        ),
    )
    op.create_index("ix_payment_method_owner_id", "payment_method", ["owner_id"])

    op.create_table(
        "payment_submission",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "batch_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("batch.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "payment_method_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("payment_method.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("destination_snapshot", sa.JSON(), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("transaction_id", sa.String(64), nullable=True),
        sa.Column("from_account", sa.String(120), nullable=True),
        sa.Column("payer_note", sa.String(500), nullable=True),
        sa.Column(
            "submitted_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", submission_status, nullable=False),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.Column(
            "decided_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_decision", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "total_amount > 0", name="ck_payment_submission_total_positive"
        ),
        sa.CheckConstraint(
            "transaction_id IS NULL OR from_account IS NULL",
            name="ck_payment_submission_one_reference",
        ),
    )
    op.create_index(
        "ix_payment_submission_batch_id_status",
        "payment_submission",
        ["batch_id", "status"],
    )

    op.add_column(
        "payment_claim",
        sa.Column(
            "payment_submission_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("payment_submission.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_payment_claim_payment_submission_id",
        "payment_claim",
        ["payment_submission_id"],
    )
    op.drop_constraint(
        "ck_payment_claim_claimed_amount_positive", "payment_claim", type_="check"
    )
    op.create_check_constraint(
        "ck_payment_claim_claimed_amount_positive",
        "payment_claim",
        "claimed_amount > 0 OR "
        "(payment_submission_id IS NOT NULL AND claimed_amount = 0)",
    )

    op.execute(
        sa.text(
            "INSERT INTO payment_method (id, owner_id, kind, provider, "
            "mobile_number, position, created_at, updated_at) "
            "SELECT gen_random_uuid(), owner_id, 'mobile', channel, number, "
            "(row_number() OVER (PARTITION BY owner_id ORDER BY channel, number)) "
            "- 1, now(), now() FROM ("
            "SELECT DISTINCT owner_id, "
            "COALESCE(collection_channel, 'bKash') AS channel, "
            "collection_number AS number FROM batch "
            "WHERE collection_number IS NOT NULL) AS moved"
        )
    )

    for table in NEW_TABLES:
        op.execute(
            sa.text(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}"  # noqa: S608  fixed module constants
            )
        )


def downgrade() -> None:
    """Restore the original claim check and drop everything added.

    A claim is a retained financial record, so a zero-share linked claim
    is never deleted to make the restored check hold. A payment
    submission is one too: dropping its table would delete what a family
    reported paying and how the teacher decided it, so the downgrade
    refuses while any submission exists. ``0014``'s downgrade has already
    removed the submissions it made to wrap legacy claims.

    :return: None
    :raises RuntimeError: If any payment submission or zero-share claim
        exists
    """
    submissions = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM payment_submission"))
        .scalar_one()
    )
    if submissions:
        raise RuntimeError(
            f"Cannot downgrade 0013: {submissions} payment_submission row(s) "
            "hold reported payments and their decisions. This migration "
            "will not delete a financial record."
        )
    zero_shares = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM payment_claim WHERE claimed_amount = 0"))
        .scalar_one()
    )
    if zero_shares:
        raise RuntimeError(
            f"Cannot downgrade 0013: {zero_shares} payment_claim row(s) carry "
            "a zero share linked to a payment submission. Resolve them "
            "first; this migration will not delete a financial record."
        )
    op.drop_constraint(
        "ck_payment_claim_claimed_amount_positive", "payment_claim", type_="check"
    )
    op.create_check_constraint(
        "ck_payment_claim_claimed_amount_positive",
        "payment_claim",
        "claimed_amount > 0",
    )
    op.drop_index("ix_payment_claim_payment_submission_id", table_name="payment_claim")
    op.drop_column("payment_claim", "payment_submission_id")
    op.drop_table("payment_submission")
    op.drop_table("payment_method")
    bind = op.get_bind()
    sa.Enum(name=SUBMISSION_STATUS_TYPE).drop(bind, checkfirst=False)
    sa.Enum(name=METHOD_KIND_TYPE).drop(bind, checkfirst=False)
