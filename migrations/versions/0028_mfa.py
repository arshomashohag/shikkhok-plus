"""Authenticator-app MFA: one factor per account, and its recovery codes.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-07

* **``mfa_factor``** holds one account's authenticator secret, encrypted
  with AES-256-GCM under the key ``secret_kid`` names
  (``app/auth/mfa_crypto.py``), never in plaintext. ``confirmed_at`` is
  NULL until the person proves the app works by typing one code, so an
  abandoned enrollment never becomes a factor. ``last_used_step`` stops a
  code being used twice. ``failed_attempts`` and ``locked_until`` bound
  guessing: six digits is a million codes, and a lock after a handful of
  wrong ones makes guessing them hopeless.
* **``mfa_recovery_code``** holds the ten one-time codes issued at
  enrollment, each hashed with scrypt and its own salt.

Required for platform administrators from this revision. The tables are
named for the factor rather than for administrators because the next
change offers the same factor to teachers and, optionally, everyone.
Both cascade from ``account``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.roles import APP_ROLE

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the MFA tables.

    :return: None
    """
    op.create_table(
        "mfa_factor",
        sa.Column(
            "account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("secret_kid", sa.String(16), nullable=False),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_step", sa.BigInteger(), nullable=True),
        sa.Column(
            "failed_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "failed_attempts >= 0", name="ck_mfa_factor_failed_attempts"
        ),
    )
    op.create_table(
        "mfa_recovery_code",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.LargeBinary(), nullable=False),
        sa.Column("salt", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_mfa_recovery_code_account", "mfa_recovery_code", ["account_id"]
    )
    for table in ("mfa_factor", "mfa_recovery_code"):
        op.execute(
            sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        )


def downgrade() -> None:
    """Drop the MFA tables, refusing while any confirmed factor exists.

    :return: None
    """
    factors = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM mfa_factor WHERE confirmed_at IS NOT NULL"))
        .scalar()
    )
    if factors:
        raise RuntimeError(
            f"{factors} confirmed MFA factor(s) exist; downgrading would "
            "silently remove a second factor from those accounts. Refusing."
        )
    op.drop_table("mfa_recovery_code")
    op.drop_table("mfa_factor")
