"""Wrap every claim made before submissions in a one-child submission.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-02

Payments are now decided per submission, so a claim made before ``0013``
had no route to a decision and its seat could not be settled. Each such
claim, whatever its status, becomes the only claim of a new
``payment_submission``: the status maps across (``approved_full`` and
``approved_partial`` to ``approved``), the claimed amount is the total,
the payment date is the day it was submitted in Bangladesh, and the
claim's decision columns become the submission's.

The snapshot is ``{"kind": "legacy", "channel": <claim channel>}``,
which both records that no method was shown and marks the rows this
migration created, so the downgrade removes exactly those.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_KIND = "legacy"

STATUS_MAP = {
    "pending": "pending",
    "approved_full": "approved",
    "approved_partial": "approved",
    "rejected": "rejected",
}


def upgrade() -> None:
    """Give every unlinked claim a submission of its own.

    :return: None
    """
    bind = op.get_bind()
    claims = bind.execute(
        sa.text(
            "SELECT c.id, e.batch_id, c.claimed_amount, c.channel, "
            "c.transaction_id, c.submitted_by_account_id, c.submitted_at, "
            "c.status, c.rejection_reason, c.verified_by_account_id, "
            "c.verified_at, "
            "(c.submitted_at AT TIME ZONE 'Asia/Dhaka')::date AS paid_on "
            "FROM payment_claim c JOIN enrollment e ON e.id = c.enrollment_id "
            "WHERE c.payment_submission_id IS NULL"
        )
    ).mappings()
    for claim in list(claims):
        submission_id = uuid.uuid4()
        bind.execute(
            sa.text(
                "INSERT INTO payment_submission (id, batch_id, "
                "destination_snapshot, total_amount, paid_on, transaction_id, "
                "submitted_by_account_id, submitted_at, status, decision_note, "
                "decided_by_account_id, decided_at) VALUES (:id, :batch, "
                "CAST(:snapshot AS json), :total, :paid_on, :transaction_id, "
                ":submitted_by, :submitted_at, "
                "CAST(:status AS payment_submission_status), :note, "
                ":decided_by, :decided_at)"
            ),
            {
                "id": submission_id,
                "batch": claim["batch_id"],
                "snapshot": json.dumps(
                    {"kind": LEGACY_KIND, "channel": claim["channel"]}
                ),
                "total": claim["claimed_amount"],
                "paid_on": claim["paid_on"],
                "transaction_id": claim["transaction_id"],
                "submitted_by": claim["submitted_by_account_id"],
                "submitted_at": claim["submitted_at"],
                "status": STATUS_MAP[claim["status"]],
                "note": claim["rejection_reason"],
                "decided_by": claim["verified_by_account_id"],
                "decided_at": claim["verified_at"],
            },
        )
        bind.execute(
            sa.text(
                "UPDATE payment_claim SET payment_submission_id = :submission "
                "WHERE id = :claim"
            ),
            {"submission": submission_id, "claim": claim["id"]},
        )


def downgrade() -> None:
    """Unlink the wrapped claims and delete only the submissions made here.

    :return: None
    """
    op.execute(
        sa.text(
            "UPDATE payment_claim SET payment_submission_id = NULL "
            "WHERE payment_submission_id IN (SELECT id FROM payment_submission "
            "WHERE destination_snapshot->>'kind' = :kind)"
        ).bindparams(kind=LEGACY_KIND)
    )
    op.execute(
        sa.text(
            "DELETE FROM payment_submission WHERE destination_snapshot->>'kind' = :kind"
        ).bindparams(kind=LEGACY_KIND)
    )
