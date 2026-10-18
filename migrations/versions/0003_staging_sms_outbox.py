"""The staging SMS outbox.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-18

**A table that must never hold a row in production.** It records
messages the null gateway did not send, so a person can read a code on
a staging host that has no SMS credentials and sign in on a real device.

The table exists in every environment because a migration that branched
on environment would produce two different schemas, and "does the
production schema match staging" is then unanswerable -- which is the
property staging exists to provide. What differs is that nothing ever
WRITES it in production: ``record_outbox`` is a no-op unless the
environment is permitted and the flag is set, the route is not
registered, and the startup check refuses a production process that
forced it on.

The rows are short-lived by design: ``read_outbox`` ignores anything
older than five minutes, which is shorter than the OTP's own expiry, so
the outbox never outlives the thing it exposes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.roles import APP_ROLE

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the outbox table and grant the application role.

    :return: None
    """
    op.create_table(
        "staging_sms_outbox",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        # A STRING, matching the rest of the codebase. Correlation ids
        # are strings everywhere else, and a UUID column here would
        # mean a conversion at the one call site that could raise.
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_staging_sms_outbox"),
    )
    # Reads are by phone, newest first, inside a five-minute window.
    op.create_index(
        "ix_staging_sms_outbox_phone_recorded",
        "staging_sms_outbox",
        ["phone", "recorded_at"],
    )

    # 0001's GRANT ON ALL TABLES covered only what existed then, so each
    # later migration grants its own tables -- the defect B5 found, where
    # a new table was invisible to the application role AND to the
    # governance gates reading information_schema.
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT, DELETE ON staging_sms_outbox "
            f"TO {APP_ROLE}"
        )
    )


def downgrade() -> None:
    """Drop the outbox table.

    Reversible, unlike ``0002``: the table holds nothing anyone needs
    and losing it loses nothing.

    :return: None
    """
    op.drop_index("ix_staging_sms_outbox_phone_recorded", table_name="staging_sms_outbox")
    op.drop_table("staging_sms_outbox")
