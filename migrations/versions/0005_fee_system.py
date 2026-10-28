"""The fee system: cycles, the ledger, claims, reminders and a heartbeat.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-24

**Five tables, and the shape of two of them is the design.**

``fee_cycle`` carries **no money column of any kind** [BR1.2] -- not
charged, not paid, not outstanding, not a status. Every quantity is
derived by folding ``ledger_entry`` rows. A stored total would be a
second source of truth that drifts from the entries producing it,
silently and in the direction of whichever write path forgot to update
it. The thinness is asserted by a test over the column set rather than
claimed in this docstring.

``fee_cycle``'s **UNIQUE (enrollment_id, period) is the whole idempotency
mechanism** [BR1.3, FR5.4]. Generation inserts with ``ON CONFLICT DO
NOTHING`` and the conflict is the SUCCESS path. This follows a built
precedent rather than inventing a second one: ``rate_limit_counter``'s
unique constraint carries the same reasoning in ``app/db/models.py`` --
"two workers racing on the same window cannot both read a stale count,
because the second one conflicts" -- and D3 is that shape with DO NOTHING
in place of DO UPDATE. An application-level "has this already run?" guard
passes a sequential test and double-charges under two workers, which
Phase 1 has.

``ledger_entry.period`` is a **plain string, not a foreign key** to
``fee_cycle.id``, and the reason is a real case rather than a preference:
a ``carry_forward`` lands on the receiving period, and at the moment a
teacher approves a short payment in January the February cycle row does
not exist yet. Keying the entry to a cycle row would force generation to
run before a carry could be written, inverting the dependency.

``CHECK (amount >= 0)`` on ``ledger_entry`` is not a restatement of the
value type's own refusal [BR3.4]. The fold cannot defend against a row
inserted by a migration or a repair script, which never passes through
``Money``. The sign lives in the kind.

**Every new table is GRANTed explicitly.** ``0001``'s
``GRANT ... ON ALL TABLES`` covered only the tables that existed when it
ran. An ungranted table is not merely unreadable by the application -- it
is invisible to the restricted role in ``information_schema``, so every
governance gate silently stops covering it, which is how a control is
retired rather than failed.

**No row-level security policy here, and that is a decision**
[NFR14.36, security-design § 2]. The built policy is on ``profile``
alone, where ``account_id`` IS the subject so ``account_id =
current_setting(...)`` is a predicate on a column of the row. These
tables have no such column: a fee cycle's authorization is a *path* --
an accepted student link, an accepted guardian link, or ownership of the
batch -- which is the three-branch join ``_LENS_QUERY`` already performs.
Encoding it into a ``USING`` clause would produce two implementations of
one authorization rule, the second outside ``app.authz``'s coverage
measurement and its strict mypy island. The revisit trigger is named:
any of these tables gaining an account-scoped column that identifies a
reader directly.

Forward-only and backward-compatible: this migration only creates. It
alters no existing table and destroys nothing, so the downgrade is a
clean drop of exactly what was added.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.roles import APP_ROLE

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The ledger vocabulary's type name in the database. Shared by upgrade
#: and downgrade so a rename cannot drift between them.
LEDGER_KIND_TYPE = "ledger_entry_kind"

#: The seven kinds, closed [ADR-002]. An eighth is not a data change: it
#: must be assigned a side of the balance identity, and the fold in
#: ``app/money/_kinds.py`` is exhaustive so that adding one without
#: extending the fold fails the type check.
LEDGER_KIND_VALUES = (
    "charge",
    "receipt",
    "carry_forward",
    "carried_out",
    "forgiveness",
    "credit_grant",
    "credit_apply",
)

#: The claim status type's name.
CLAIM_STATUS_TYPE = "payment_claim_status"

#: What the claimant is shown [AC6.4.1, BR6.3]. Server-set at
#: verification, never client-derived.
CLAIM_STATUS_VALUES = ("pending", "approved_full", "approved_partial", "rejected")

#: The shortfall disposition type's name.
DISPOSITION_TYPE = "shortfall_disposition"

#: The teacher's choice on approving less than was CHARGED [BR5.4]. There
#: is deliberately no third "default" value: a default would silently
#: choose for the teacher and the two have opposite consequences for the
#: student.
DISPOSITION_VALUES = ("carried", "waived")

#: The reminder outcome type's name.
REMINDER_OUTCOME_TYPE = "reminder_outcome"

#: A reminder's delivery outcome [BR7.2]. ``pending`` exists because the
#: event is committed BEFORE the push is dispatched
#: [reliability-design § 5]: writing the event after a successful
#: dispatch loses the record of a send that happened if the process dies
#: in between, and the whole reason a reminder is an event rather than a
#: boolean is that a flag cannot express a failed send.
REMINDER_OUTCOME_VALUES = ("pending", "sent", "failed")

#: Every table this migration creates, in dependency order. Used by the
#: grant loop so a table cannot be created and left ungranted.
NEW_TABLES = (
    "fee_cycle",
    "ledger_entry",
    "payment_claim",
    "reminder_event",
    "job_heartbeat",
)


def upgrade() -> None:
    """Create the five tables, their types, indexes and grants.

    Order is load-bearing only in that the enum types must exist before
    the columns that use them, and ``payment_claim`` must exist before
    ``ledger_entry.payment_claim_id`` references it.

    :return: None
    """
    bind = op.get_bind()

    # Created explicitly, ONCE, before any table references them. The
    # column-side references below carry `create_type=False` because
    # `create_table` would otherwise re-emit CREATE TYPE per column and
    # fail on the duplicate -- the same lifecycle split `0004` and the
    # ORM models already use.
    for name, values in (
        (LEDGER_KIND_TYPE, LEDGER_KIND_VALUES),
        (CLAIM_STATUS_TYPE, CLAIM_STATUS_VALUES),
        (DISPOSITION_TYPE, DISPOSITION_VALUES),
        (REMINDER_OUTCOME_TYPE, REMINDER_OUTCOME_VALUES),
    ):
        sa.Enum(*values, name=name).create(bind, checkfirst=False)

    kind = postgresql.ENUM(
        *LEDGER_KIND_VALUES, name=LEDGER_KIND_TYPE, create_type=False
    )
    claim_status = postgresql.ENUM(
        *CLAIM_STATUS_VALUES, name=CLAIM_STATUS_TYPE, create_type=False
    )
    disposition = postgresql.ENUM(
        *DISPOSITION_VALUES, name=DISPOSITION_TYPE, create_type=False
    )
    outcome = postgresql.ENUM(
        *REMINDER_OUTCOME_VALUES, name=REMINDER_OUTCOME_TYPE, create_type=False
    )

    # ----------------------------------------------------------------
    # fee_cycle. Five columns, and the set is the rule [BR1.2].
    # ----------------------------------------------------------------
    op.create_table(
        "fee_cycle",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "enrollment_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("enrollment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "enrollment_id",
            "period",
            name="uq_fee_cycle_enrollment_period",
        ),
    )
    op.create_index("ix_fee_cycle_enrollment_id", "fee_cycle", ["enrollment_id"])

    # ----------------------------------------------------------------
    # payment_claim. Created before ledger_entry, which references it.
    # ----------------------------------------------------------------
    op.create_table(
        "payment_claim",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "enrollment_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("enrollment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("claimed_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        # Nullable REGARDLESS of how OQ-1 is answered, which is what makes
        # this schema answer-agnostic: if the human decides the reference
        # does not survive the claimant's deletion, D6 nulls it in place
        # rather than migrating the table.
        sa.Column("transaction_id", sa.String(64), nullable=True),
        sa.Column(
            "submitted_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", claim_status, nullable=False),
        sa.Column("approved_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("shortfall_disposition", disposition, nullable=True),
        sa.Column(
            "verified_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        # JSONB rather than JSON: the previous decision is read back and
        # compared in tests, and JSONB normalises key order so an equality
        # does not depend on how the driver serialised it.
        sa.Column("previous_decision", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "claimed_amount > 0",
            name="ck_payment_claim_claimed_amount_positive",
        ),
        sa.CheckConstraint(
            "approved_amount IS NULL OR approved_amount >= 0",
            name="ck_payment_claim_approved_amount_non_negative",
        ),
    )
    op.create_index(
        "ix_payment_claim_enrollment_id", "payment_claim", ["enrollment_id"]
    )
    op.create_index("ix_payment_claim_status", "payment_claim", ["status"])

    # ----------------------------------------------------------------
    # ledger_entry. Append-only; the CHECK is the table's own defence.
    # ----------------------------------------------------------------
    op.create_table(
        "ledger_entry",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "enrollment_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("enrollment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("kind", kind, nullable=False),
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
            sa.ForeignKey("ledger_entry.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # [BR3.4] The value type refuses a negative amount already. This
        # is the TABLE's own defence, because the fold never sees a row
        # a repair script inserted.
        sa.CheckConstraint("amount >= 0", name="ck_ledger_entry_amount_non_negative"),
    )
    op.create_index("ix_ledger_entry_enrollment_id", "ledger_entry", ["enrollment_id"])
    # The hot read: every balance is a fold over one enrollment's rows,
    # and the per-period breakdown sorts by period.
    op.create_index(
        "ix_ledger_entry_enrollment_period",
        "ledger_entry",
        ["enrollment_id", "period"],
    )
    op.create_index(
        "ix_ledger_entry_payment_claim_id", "ledger_entry", ["payment_claim_id"]
    )

    # ----------------------------------------------------------------
    # reminder_event. An event, never a flag [BR7.1].
    # ----------------------------------------------------------------
    op.create_table(
        "reminder_event",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "enrollment_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("enrollment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "sent_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("outcome", outcome, nullable=False),
    )
    op.create_index(
        "ix_reminder_event_enrollment_period",
        "reminder_event",
        ["enrollment_id", "period"],
    )

    # ----------------------------------------------------------------
    # job_heartbeat. One row per job name, updated in place
    # [observability-design § 1.1].
    #
    # A TABLE rather than a file or a counter in a worker, because the
    # instance is replaced on every deploy -- the exact event the alert
    # exists to survive. A file on the host or process memory is erased
    # by it.
    #
    # Deliberately outside the privacy boundary: it is the only D3 table
    # that is not enrollment-scoped and carries nothing a person wrote.
    # ----------------------------------------------------------------
    op.create_table(
        "job_heartbeat",
        sa.Column("job_name", sa.Text(), primary_key=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cycles_created", sa.Integer(), nullable=False),
        sa.Column("cycles_skipped", sa.Integer(), nullable=False),
        sa.Column("periods_failed", sa.Integer(), nullable=False),
    )

    # ----------------------------------------------------------------
    # The grants. Looped over the declared table list rather than
    # written out, so a table added to NEW_TABLES cannot be granted by
    # accident and a table created without being added there fails the
    # governance test loudly.
    # ----------------------------------------------------------------
    for table in NEW_TABLES:
        op.execute(
            sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        )


def downgrade() -> None:
    """Drop the five tables and the four enum types.

    Cleanly reversible, because this migration only ever created. The
    data is lost, which is why the deploy runbook takes a ``pg_dump``
    before any production migration regardless.

    :return: None
    """
    op.drop_table("job_heartbeat")
    op.drop_table("reminder_event")
    op.drop_table("ledger_entry")
    op.drop_table("payment_claim")
    op.drop_table("fee_cycle")

    bind = op.get_bind()
    sa.Enum(name=REMINDER_OUTCOME_TYPE).drop(bind, checkfirst=False)
    sa.Enum(name=DISPOSITION_TYPE).drop(bind, checkfirst=False)
    sa.Enum(name=CLAIM_STATUS_TYPE).drop(bind, checkfirst=False)
    sa.Enum(name=LEDGER_KIND_TYPE).drop(bind, checkfirst=False)
