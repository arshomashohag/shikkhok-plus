"""A replay key on payment submissions; the audit log and ledger made append-only.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-02

**Two unrelated changes in one revision, sectioned below**, because the
brief that produced them allotted one revision and two would only add a
head to move. Neither depends on the other.

**A. ``payment_submission.client_mutation_id``** [PA-DB-1]. A payment
whose response was lost after the commit -- a timeout on a flaky mobile
connection -- is retried by the app, and before this column the retry
recorded a second pending claim for money sent once. The app now sends
an optional UUID per payment draft, and ``UNIQUE (submitted_by_account_id,
client_mutation_id)`` is **the guarantee**, not a lookup: the service
inserts ``ON CONFLICT DO NOTHING`` against it and reads the winner back.
NULLs are distinct in a PostgreSQL unique constraint, so an app build
that sends no id keeps working exactly as before. Scoped by account for
the reason ``queued_submission`` is: another account presenting the same
UUID is not a duplicate at all.

**B. ``ledger_entry`` and ``auth_audit_log`` made append-only for the
application role** [PA-SEC-3]. Both tables were append-only by rule and
by code review only: ``0005`` and ``0001`` granted ``shikkhok_app`` full
``UPDATE`` and ``DELETE``, so a compromised application credential could
rewrite an amount or erase the sign-in trail, which is exactly the
record those tables exist to keep. What the application genuinely does
to each table was established by reading every write path, and the
grants below give back that and nothing more:

- ``ledger_entry``: the ONLY post-insert write is ``supersede`` in
  ``app/fees/ledger_writer.py``, which sets ``superseded_by_id``. So
  ``UPDATE`` comes back on that one column, and ``DELETE`` does not
  come back at all. No application path deletes a ledger row; the two
  that remove one -- an enrollment's ``ON DELETE CASCADE`` and the
  self-referencing ``ON DELETE SET NULL`` -- are referential actions,
  which PostgreSQL runs as the **table owner**, not as the role whose
  statement fired them, so revoking the privilege does not touch them.
  The governance deletion suite runs as the restricted role and is what
  proves that rather than this paragraph.
- ``auth_audit_log``: no application path updates a row; the
  ``account_id`` that becomes NULL on account deletion is again a
  referential action run as the owner. So ``UPDATE`` does not come back.
  ``DELETE`` must, because the retention purge (``app/governance/
  commands.py``) deletes rows past their twelve-month window and runs as
  the application role. **Keeping ``DELETE`` and bounding it was chosen
  over a ``SECURITY DEFINER`` purge function** because it is the smaller
  change -- no application code moves, and the purge stays one generic
  loop over every finite-retention table -- while giving the same
  guarantee: a ``BEFORE DELETE`` trigger refuses, for the application
  role, any row younger than :data:`AUDIT_DELETE_FLOOR`. A compromised
  credential can then delete only what the purge would have deleted
  anyway.

The floor is **one day short of the purge's twelve-month window**, not
equal to it, because the purge computes its cutoff from the application
host's clock and the trigger reads the database's: equal windows would
let a few seconds of skew make the purge's boundary row raise and fail
the whole run. One day of tolerance costs at most one day of the
retention guarantee and never a failed purge. The coupling to the purge
window is asserted behaviourally in ``tests/db/test_append_only.py``: a
purge run at the real clock as the application role must succeed, so a
retention window shortened below the floor fails that test rather than
the 03:00 job.

The floor binds **only** ``shikkhok_app``. The owner is the role that
runs migrations and arranges test fixtures with a fixed clock, and it
can drop the trigger anyway, so binding it would protect nothing while
making the purge suite depend on the date it runs.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op

from app.db.roles import APP_ROLE

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The replay key's unique constraint. The service names it in its
#: ``ON CONFLICT`` clause, so a rename here is an error there.
REPLAY_CONSTRAINT: Final = "uq_payment_submission_account_mutation"

#: How young an audit row the application role may never delete.
AUDIT_DELETE_FLOOR: Final = "364 days"

_GUARD_FUNCTION: Final = "auth_audit_log_retention_floor"
_GUARD_TRIGGER: Final = "trg_auth_audit_log_retention_floor"


def upgrade() -> None:
    """Add the replay key, then narrow the two append-only tables.

    :return: None
    """
    # --- A. payment_submission replay key [PA-DB-1] ---------------------
    op.add_column(
        "payment_submission",
        sa.Column("client_mutation_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_unique_constraint(
        REPLAY_CONSTRAINT,
        "payment_submission",
        ["submitted_by_account_id", "client_mutation_id"],
    )

    # --- B1. ledger_entry: insert, read, and supersede only -------------
    # Revoking the table-level privilege also revokes every column-level
    # one, so the narrower grant is re-added after, not before.
    op.execute(sa.text(f"REVOKE UPDATE, DELETE ON ledger_entry FROM {APP_ROLE}"))
    op.execute(
        sa.text(f"GRANT UPDATE (superseded_by_id) ON ledger_entry TO {APP_ROLE}")
    )

    # --- B2. auth_audit_log: no update; delete only past the floor ------
    op.execute(sa.text(f"REVOKE UPDATE ON auth_audit_log FROM {APP_ROLE}"))
    # Both identifiers and the interval are fixed module constants.
    op.execute(
        sa.text(
            f"CREATE FUNCTION {_GUARD_FUNCTION}() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ "
            "BEGIN "
            f"  IF current_user = '{APP_ROLE}' "
            f"     AND OLD.occurred_at >= now() - interval '{AUDIT_DELETE_FLOOR}' "
            "  THEN "
            "    RAISE EXCEPTION 'auth_audit_log row % is inside its retention "
            "window and cannot be deleted', OLD.id "
            "      USING ERRCODE = 'insufficient_privilege'; "
            "  END IF; "
            "  RETURN OLD; "
            "END $$"
        )
    )
    op.execute(
        sa.text(
            f"CREATE TRIGGER {_GUARD_TRIGGER} BEFORE DELETE ON auth_audit_log "
            f"FOR EACH ROW EXECUTE FUNCTION {_GUARD_FUNCTION}()"
        )
    )


def downgrade() -> None:
    """Restore the full grants and drop the replay key.

    Dropping ``client_mutation_id`` loses no financial record: it is a
    retry key, and the submissions it deduplicated stay.

    :return: None
    """
    op.execute(sa.text(f"DROP TRIGGER {_GUARD_TRIGGER} ON auth_audit_log"))
    op.execute(sa.text(f"DROP FUNCTION {_GUARD_FUNCTION}()"))
    op.execute(sa.text(f"GRANT UPDATE ON auth_audit_log TO {APP_ROLE}"))

    op.execute(
        sa.text(f"REVOKE UPDATE (superseded_by_id) ON ledger_entry FROM {APP_ROLE}")
    )
    op.execute(sa.text(f"GRANT UPDATE, DELETE ON ledger_entry TO {APP_ROLE}"))

    op.drop_constraint(REPLAY_CONSTRAINT, "payment_submission", type_="unique")
    op.drop_column("payment_submission", "client_mutation_id")
