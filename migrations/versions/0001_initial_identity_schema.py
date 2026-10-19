"""The first migration: identity, OTP, tokens, audit, and the shells.

Revision ID: 0001
Revises:
Create Date: 2026-10-18

**From zero, against a real PostgreSQL.** The test container migrates with
Alembic rather than loading a schema dump, which gives the migration path
continuous exercise at no extra cost -- and that matters more than usual
here, because the fee model is known to be changing and there is no
failover.

Four things happen that no autogenerate would produce, and each is the
load-bearing half of a control:

1. ``Owner`` and ``Enrollment`` are created **empty** [BR6.1]. Empty is not
   absent: lens resolution queries them, and a query against a table that
   does not exist fails.
2. Row-level security is **enabled and forced** on ``profile``, with a
   policy keyed on the session's account id [BR3.2].
3. The **restricted application role** is created, owning nothing. This is
   what makes the privacy suite mean anything -- a superuser or table owner
   bypasses RLS entirely, so a suite run as one passes identically whether
   the policy is correct, broken, or absent.
4. ``FORCE ROW LEVEL SECURITY``, because RLS otherwise does not apply to
   the table's own owner, and the migration runs as that owner.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.roles import APP_ROLE, SESSION_ACCOUNT_KEY

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the schema, the policy and the restricted role.

    :return: None
    """
    op.create_table(
        "account",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_account"),
        sa.UniqueConstraint("phone", name="uq_account_phone"),
    )

    op.create_table(
        "profile",
        sa.Column("account_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("self_name", sa.Text(), nullable=True),
        sa.Column("photo_ref", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name="fk_profile_account_id_account",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", name="pk_profile"),
    )

    op.create_table(
        "otp_request",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("otp_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_otp_request"),
    )
    op.create_index(
        "ix_otp_request_phone_issued_at", "otp_request", ["phone", "issued_at"]
    )

    op.create_table(
        "verify_attempt",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("otp_request_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["otp_request_id"],
            ["otp_request.id"],
            name="fk_verify_attempt_otp_request_id_otp_request",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_verify_attempt"),
    )
    op.create_index(
        "ix_verify_attempt_otp_request_id", "verify_attempt", ["otp_request_id"]
    )

    op.create_table(
        "refresh_token",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reuse_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name="fk_refresh_token_account_id_account",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_token"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_token_token_hash"),
    )
    op.create_index("ix_refresh_token_family_id", "refresh_token", ["family_id"])

    op.create_table(
        "rate_limit_counter",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_kind", sa.String(length=16), nullable=False),
        sa.Column("scope_value", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rate_limit_counter"),
        # The constraint the atomic upsert-and-increment conflicts against.
        # Without it, two workers racing on one window both read a stale
        # count and the ceiling silently admits twice what it should.
        sa.UniqueConstraint(
            "scope_kind",
            "scope_value",
            "window_start",
            name="uq_rate_limit_counter_scope_window",
        ),
    )

    op.create_table(
        "auth_audit_log",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        # Nullable BY DESIGN: an OTP issued for an unknown number has no
        # account, and a placeholder would reintroduce the existence oracle
        # the issue path exists to close [BR2.7].
        sa.Column("account_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("event", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name="fk_auth_audit_log_account_id_account",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_audit_log"),
    )
    op.create_index("ix_auth_audit_log_occurred_at", "auth_audit_log", ["occurred_at"])

    # -----------------------------------------------------------------
    # The two shells. [BR6.1]
    #
    # U4 owns their behaviour and will extend their columns. U3 creates
    # the shape because lens resolution reads them, and a query against a
    # table that does not exist fails -- so the skeleton could not run end
    # to end without them. A test asserts this Unit writes neither.
    # -----------------------------------------------------------------
    op.create_table(
        "owner",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name="fk_owner_account_id_account",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_owner"),
    )
    op.create_index("ix_owner_account_id", "owner", ["account_id"])

    op.create_table(
        "enrollment",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name="fk_enrollment_account_id_account",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_enrollment"),
    )
    op.create_index("ix_enrollment_account_id", "enrollment", ["account_id"])

    _create_restricted_role()
    _enable_profile_rls()


def _create_restricted_role() -> None:
    """Create the restricted application role, owning nothing.

    **This is not hygiene; it is what makes the privacy suite mean
    anything.** PostgreSQL documents that superusers and table owners
    bypass row-level security entirely, and the default test-container
    connection is ``postgres``, a superuser. A privacy suite run as one
    passes identically whether the policy is correct, broken, or absent.

    :return: None
    """
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT FROM pg_catalog.pg_roles WHERE rolname = '{APP_ROLE}'
                ) THEN
                    CREATE ROLE {APP_ROLE} NOINHERIT LOGIN;
                END IF;
            END
            $$;
            """
        )
    )
    op.execute(sa.text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
            f"IN SCHEMA public TO {APP_ROLE}"
        )
    )
    op.execute(
        sa.text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    )


def _enable_profile_rls() -> None:
    """Enable and force row-level security on ``profile``.

    ``FORCE`` matters: without it the policy does not apply to the table's
    own owner, and the migration runs as that owner. Enabling without
    forcing produces a policy that looks present in ``pg_policies`` and
    silently does nothing for the one connection most likely to be used by
    mistake.

    :return: None
    """
    op.execute(sa.text("ALTER TABLE profile ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE profile FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"""
            CREATE POLICY profile_owner_only ON profile
                USING (
                    account_id = NULLIF(
                        current_setting('{SESSION_ACCOUNT_KEY}', true), ''
                    )::uuid
                )
                WITH CHECK (
                    account_id = NULLIF(
                        current_setting('{SESSION_ACCOUNT_KEY}', true), ''
                    )::uuid
                );
            """
        )
    )


def downgrade() -> None:
    """Drop everything this revision created.

    :return: None
    """
    op.execute(sa.text("DROP POLICY IF EXISTS profile_owner_only ON profile"))
    op.drop_index("ix_enrollment_account_id", table_name="enrollment")
    op.drop_table("enrollment")
    op.drop_index("ix_owner_account_id", table_name="owner")
    op.drop_table("owner")
    op.drop_index("ix_auth_audit_log_occurred_at", table_name="auth_audit_log")
    op.drop_table("auth_audit_log")
    op.drop_table("rate_limit_counter")
    op.drop_index("ix_refresh_token_family_id", table_name="refresh_token")
    op.drop_table("refresh_token")
    op.drop_index("ix_verify_attempt_otp_request_id", table_name="verify_attempt")
    op.drop_table("verify_attempt")
    op.drop_index("ix_otp_request_phone_issued_at", table_name="otp_request")
    op.drop_table("otp_request")
    op.drop_table("profile")
    op.drop_table("account")
