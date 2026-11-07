"""Keep a seat's history on removal; index the supersession link.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-07

* **``enrollment_keeps_history``**, a ``BEFORE DELETE`` trigger on
  ``enrollment`` [audit C-02]. Removing a pending seat used to cascade
  away its receipts, credits, claims, attendance and marks: ``0015``
  revoked ``DELETE`` on ``ledger_entry`` from the application role, but a
  referential action runs as the table owner and the revoke never
  applied to it. The service now refuses such a removal with a message
  the teacher can act on; this trigger refuses it in the database too,
  so a path that skips the service fails rather than erasing money.
  A seat whose only rows are generated charges and forgiveness of them
  stays removable -- that is the wrong-number recovery path.

  The rule lives in a function rather than a ``RESTRICT`` foreign key
  because the charge-only seat must still cascade: ``RESTRICT`` would
  refuse it too, and the application role holds no ``DELETE`` on
  ``ledger_entry`` to clear the charges first.
* **``ix_ledger_entry_superseded_by_id``**, partial on non-NULL values
  [audit C-04]. Every ledger read that hides corrected entries runs a
  correlated ``NOT EXISTS`` on this column per row, and without an index
  each probe scanned the whole ledger -- every tenant's. Most rows are
  never superseded, so the partial index stays small.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Kept identical to ``app.batches.service.MONEY_MOVEMENT_KINDS``; a test
#: asserts the two agree.
MONEY_MOVEMENT_KINDS: tuple[str, ...] = (
    "carried_out",
    "carry_forward",
    "credit_apply",
    "credit_grant",
    "receipt",
)

_KINDS_SQL = ", ".join(f"'{kind}'" for kind in MONEY_MOVEMENT_KINDS)

_FUNCTION = f"""
CREATE FUNCTION enrollment_keeps_history() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM ledger_entry
        WHERE enrollment_id = OLD.id AND kind IN ({_KINDS_SQL})
    ) OR EXISTS (
        SELECT 1 FROM payment_claim WHERE enrollment_id = OLD.id
    ) OR EXISTS (
        SELECT 1 FROM extra_fee_entry e
        JOIN extra_fee_charge c ON c.id = e.extra_fee_charge_id
        WHERE c.enrollment_id = OLD.id AND e.kind IN ({_KINDS_SQL})
    ) OR EXISTS (
        SELECT 1 FROM attendance WHERE enrollment_id = OLD.id
    ) OR EXISTS (
        SELECT 1 FROM mark WHERE enrollment_id = OLD.id
    ) THEN
        RAISE EXCEPTION 'enrollment_has_history: seat % holds money or records',
            OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN OLD;
END;
$$;
"""


def upgrade() -> None:
    """Add the history trigger and the supersession index.

    :return: None
    """
    op.execute(_FUNCTION)
    op.execute(
        "CREATE TRIGGER enrollment_keeps_history BEFORE DELETE ON enrollment "
        "FOR EACH ROW EXECUTE FUNCTION enrollment_keeps_history()"
    )
    op.create_index(
        "ix_ledger_entry_superseded_by_id",
        "ledger_entry",
        ["superseded_by_id"],
        postgresql_where="superseded_by_id IS NOT NULL",
    )


def downgrade() -> None:
    """Drop the trigger, its function and the index.

    :return: None
    """
    op.drop_index("ix_ledger_entry_superseded_by_id", table_name="ledger_entry")
    op.execute("DROP TRIGGER enrollment_keeps_history ON enrollment")
    op.execute("DROP FUNCTION enrollment_keeps_history()")
