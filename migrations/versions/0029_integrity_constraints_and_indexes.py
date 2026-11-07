"""Freeze approved salaries in the database; add the missing key, checks and indexes.

Revision ID: 0029
Revises: 0027
Create Date: 2026-11-07

* **``salary_line_frozen``** [audit C-30]. "Approval freezes the line"
  lived in Python alone, while the ledger, expenses and extra fees are
  protected in the database too. A trigger now refuses any change to an
  approved line's amounts, basis, period, staff or approval, and any new,
  changed or removed adjustment on an approved line. A referential
  ``SET NULL`` of ``approved_by_account_id`` -- an approving manager
  deleting their account -- still passes, and a line deleted by a cascade
  takes its adjustments with it.
* **``fk_enrollment_batch_id_batch``** [audit C-26]. The relationship
  every fee, attendance row and mark hangs off had no foreign key; ``0002``
  deferred it to a migration that never landed. Added ``NOT VALID`` so it
  binds every new and changed seat at once, then validated only if no
  existing seat points at a missing batch -- an orphan is reported, not
  allowed to stop the boot.
* **Value checks** [audit C-26], each ``NOT VALID`` and validated the same
  way: a period is ``YYYY-MM`` (the balance fold sorts periods as text and
  relies on the fixed width), a fee is never negative, a timetable slot
  ends after it starts.
* **``student.client_mutation_id``** [audit C-25], unique per teacher where
  set: the retry key that lets a resent "add student" return the student
  the first request created instead of making a duplicate.
* **Indexes** [audit C-27] on the columns hot reads filter by -- the
  signup link by guardian number, a batch's timetable, the unread count,
  duplicate payment references -- and on the foreign keys an account or
  seat deletion fans out through, each of which was a sequential scan
  under row locks.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FROZEN_LINE = """
CREATE FUNCTION salary_line_frozen() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status = 'approved' AND (
        NEW.status IS DISTINCT FROM OLD.status
        OR NEW.period IS DISTINCT FROM OLD.period
        OR NEW.staff_id IS DISTINCT FROM OLD.staff_id
        OR NEW.owner_id IS DISTINCT FROM OLD.owner_id
        OR NEW.basis IS DISTINCT FROM OLD.basis
        OR NEW.rate IS DISTINCT FROM OLD.rate
        OR NEW.classes_held IS DISTINCT FROM OLD.classes_held
        OR NEW.base_amount IS DISTINCT FROM OLD.base_amount
        OR NEW.approved_at IS DISTINCT FROM OLD.approved_at
        OR (NEW.approved_by_account_id IS DISTINCT FROM OLD.approved_by_account_id
            AND NEW.approved_by_account_id IS NOT NULL)
    ) THEN
        RAISE EXCEPTION 'salary_line_frozen: line % is approved', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
"""

_FROZEN_ADJUSTMENT = """
CREATE FUNCTION salary_adjustment_frozen() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    line_id uuid;
BEGIN
    line_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.salary_line_id
                    ELSE NEW.salary_line_id END;
    -- A line deleted by a cascade is already gone when its adjustments
    -- follow it, so this finds nothing and lets them go.
    IF EXISTS (
        SELECT 1 FROM salary_line WHERE id = line_id AND status = 'approved'
    ) THEN
        RAISE EXCEPTION 'salary_line_frozen: line % is approved', line_id
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;
"""

#: ``(name, table, definition)`` for each check, added ``NOT VALID``.
_CHECKS: tuple[tuple[str, str, str], ...] = (
    ("ck_fee_cycle_period_format", "fee_cycle", "period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'"),
    (
        "ck_ledger_entry_period_format",
        "ledger_entry",
        "period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'",
    ),
    (
        "ck_batch_default_fee_non_negative",
        "batch",
        "default_fee IS NULL OR default_fee >= 0",
    ),
    (
        "ck_enrollment_fee_amount_non_negative",
        "enrollment",
        "fee_amount IS NULL OR fee_amount >= 0",
    ),
    ("ck_schedule_slot_ends_after_start", "schedule_slot", "end_time > start_time"),
)

#: ``(name, table, columns, partial predicate or None)``.
_INDEXES: tuple[tuple[str, str, str, str | None], ...] = (
    (
        "ix_enrollment_guardian_phone",
        "enrollment",
        "guardian_phone",
        "guardian_phone IS NOT NULL",
    ),
    ("ix_schedule_slot_batch_id", "schedule_slot", "batch_id", None),
    ("ix_notification_unread", "notification", "account_id", "read_at IS NULL"),
    (
        "ix_payment_submission_batch_transaction",
        "payment_submission",
        "batch_id, transaction_id",
        "transaction_id IS NOT NULL",
    ),
    ("ix_refresh_token_account_id", "refresh_token", "account_id", None),
    (
        "ix_ledger_entry_created_by",
        "ledger_entry",
        "created_by_account_id",
        "created_by_account_id IS NOT NULL",
    ),
    (
        "ix_attendance_recorded_by",
        "attendance",
        "recorded_by_account_id",
        "recorded_by_account_id IS NOT NULL",
    ),
    (
        "ix_mark_recorded_by",
        "mark",
        "recorded_by_account_id",
        "recorded_by_account_id IS NOT NULL",
    ),
    (
        "ix_payment_claim_submitted_by",
        "payment_claim",
        "submitted_by_account_id",
        "submitted_by_account_id IS NOT NULL",
    ),
    (
        "ix_payment_claim_verified_by",
        "payment_claim",
        "verified_by_account_id",
        "verified_by_account_id IS NOT NULL",
    ),
    (
        "ix_extra_fee_entry_superseded_by_id",
        "extra_fee_entry",
        "superseded_by_id",
        "superseded_by_id IS NOT NULL",
    ),
    (
        "ix_notification_enrollment_id",
        "notification",
        "enrollment_id",
        "enrollment_id IS NOT NULL",
    ),
    ("ix_reminder_event_sent_by", "reminder_event", "sent_by_account_id", None),
    (
        "ix_auth_audit_log_account_id",
        "auth_audit_log",
        "account_id",
        "account_id IS NOT NULL",
    ),
    ("ix_hidden_batch_preference_batch_id", "hidden_batch_preference", "batch_id", None),
)


def _validate_if_clean(table: str, constraint: str, violators: str) -> None:
    """Validate a ``NOT VALID`` constraint unless existing rows break it.

    An existing violation is reported and left for a person to resolve;
    failing the migration would stop a host from booting over historical
    data the new constraint already prevents more of.

    :param table: The constrained table
    :param constraint: The constraint's name
    :param violators: A query returning any row that violates it
    :return: None
    """
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS ({violators}) THEN
                RAISE NOTICE '{constraint}: existing rows violate it; left NOT VALID';
            ELSE
                ALTER TABLE {table} VALIDATE CONSTRAINT {constraint};
            END IF;
        END;
        $$;
        """
    )


def upgrade() -> None:
    """Add the triggers, the foreign key, the checks and the indexes.

    :return: None
    """
    op.execute(_FROZEN_LINE)
    op.execute(
        "CREATE TRIGGER salary_line_frozen BEFORE UPDATE ON salary_line "
        "FOR EACH ROW EXECUTE FUNCTION salary_line_frozen()"
    )
    op.execute(_FROZEN_ADJUSTMENT)
    op.execute(
        "CREATE TRIGGER salary_adjustment_frozen "
        "BEFORE INSERT OR UPDATE OR DELETE ON salary_adjustment "
        "FOR EACH ROW EXECUTE FUNCTION salary_adjustment_frozen()"
    )

    op.execute(
        "ALTER TABLE enrollment ADD CONSTRAINT fk_enrollment_batch_id_batch "
        "FOREIGN KEY (batch_id) REFERENCES batch (id) NOT VALID"
    )
    _validate_if_clean(
        "enrollment",
        "fk_enrollment_batch_id_batch",
        "SELECT 1 FROM enrollment e WHERE NOT EXISTS "
        "(SELECT 1 FROM batch b WHERE b.id = e.batch_id)",
    )

    for name, table, condition in _CHECKS:
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID")
        _validate_if_clean(table, name, f"SELECT 1 FROM {table} WHERE NOT ({condition})")

    for name, table, columns, where in _INDEXES:
        predicate = f" WHERE {where}" if where else ""
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns}){predicate}")

    op.execute("ALTER TABLE student ADD COLUMN client_mutation_id uuid")
    op.execute(
        "CREATE UNIQUE INDEX uq_student_owner_mutation ON student "
        "(owner_id, client_mutation_id) WHERE client_mutation_id IS NOT NULL"
    )


def downgrade() -> None:
    """Remove everything this revision added.

    :return: None
    """
    op.execute("DROP INDEX uq_student_owner_mutation")
    op.execute("ALTER TABLE student DROP COLUMN client_mutation_id")
    for name, table, _columns, _where in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
    for name, table, _condition in _CHECKS:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
    op.execute("ALTER TABLE enrollment DROP CONSTRAINT fk_enrollment_batch_id_batch")
    op.execute("DROP TRIGGER salary_adjustment_frozen ON salary_adjustment")
    op.execute("DROP FUNCTION salary_adjustment_frozen()")
    op.execute("DROP TRIGGER salary_line_frozen ON salary_line")
    op.execute("DROP FUNCTION salary_line_frozen()")
