"""Verify-first signup drafts, and refresh families that can end.

Revision ID: 0028
Revises: 0026
Create Date: 2026-11-07

* **``pending_signup``** holds a signup form until the code sent to its
  number is verified [C-07]. Signup used to create the account, profile,
  owner and centre before anyone proved they held the number, and
  answered an existing number with a 409: an existence oracle, and a way
  to squat a stranger's number. One row per number (``UNIQUE (phone)``),
  bound to the one ``otp_request`` row whose code completes it. The
  binding is ``ON DELETE SET NULL`` so the seven-day code purge never
  blocks on a draft, and a draft whose code is gone can no longer be
  completed -- which is the right outcome.
* **``refresh_token.family_started_at``** is when the family's first
  token was issued, carried on every row so the absolute family lifetime
  [C-21] survives the purge of the family's oldest rows. Backfilled from
  the oldest surviving row of each family, which can only start a
  family LATER than it really started -- the lenient direction, so no
  live session is ended early by this migration.
* **``refresh_token.revoked_at``** marks a family ended by logout or by
  "sign out everywhere" [C-21], kept apart from ``reuse_detected_at`` so
  a signed-out device presenting its old token is not reported as an
  attack.

Both columns are **nullable and written by the new code only**, so a
container still running the previous image while this migration runs
keeps issuing tokens: a NOT NULL column would refuse its inserts for
the length of the deploy [team: Deployment, backward-compatible].
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.roles import APP_ROLE

revision: str = "0028"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the signup draft table and the two refresh-family columns.

    :return: None
    """
    op.create_table(
        "pending_signup",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("self_name", sa.String(120), nullable=False),
        sa.Column("address_house", sa.Text(), nullable=False),
        sa.Column("address_road", sa.Text(), nullable=False),
        sa.Column("address_city", sa.Text(), nullable=False),
        sa.Column("address_postcode", sa.String(4), nullable=False),
        sa.Column("centre_name", sa.String(120), nullable=True),
        sa.Column(
            "otp_request_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey(
                "otp_request.id",
                ondelete="SET NULL",
                name="fk_pending_signup_otp_request_id_otp_request",
            ),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_pending_signup"),
        sa.UniqueConstraint("phone", name="uq_pending_signup_phone"),
        sa.CheckConstraint(
            "role IN ('teacher', 'student', 'guardian', 'coaching')",
            name="ck_pending_signup_role",
        ),
    )
    op.create_index(
        "ix_pending_signup_otp_request_id", "pending_signup", ["otp_request_id"]
    )
    op.create_index("ix_pending_signup_created_at", "pending_signup", ["created_at"])
    op.execute(
        sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON pending_signup TO {APP_ROLE}")
    )

    op.add_column(
        "refresh_token",
        sa.Column("family_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "refresh_token",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE refresh_token AS r SET family_started_at = f.started "
            "FROM (SELECT family_id, min(issued_at) AS started "
            "FROM refresh_token GROUP BY family_id) AS f "
            "WHERE r.family_id = f.family_id"
        )
    )
    # Sign out everywhere revokes by account; the family index exists
    # since 0001.
    op.create_index("ix_refresh_token_account_id", "refresh_token", ["account_id"])


def downgrade() -> None:
    """Drop the draft table and the two columns.

    Dropping a draft loses only a form nobody has verified yet, and the
    two columns are re-derivable or advisory, so this downgrade refuses
    nothing.

    :return: None
    """
    op.drop_index("ix_refresh_token_account_id", table_name="refresh_token")
    op.drop_column("refresh_token", "revoked_at")
    op.drop_column("refresh_token", "family_started_at")
    op.drop_index("ix_pending_signup_created_at", table_name="pending_signup")
    op.drop_index("ix_pending_signup_otp_request_id", table_name="pending_signup")
    op.drop_table("pending_signup")
