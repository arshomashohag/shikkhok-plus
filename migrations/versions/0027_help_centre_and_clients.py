"""Help centre tickets, and which app each account signs in from.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-07

* **``account_client``** is one row per account per app (Android or
  web): when that account was first and last seen on it, and the app
  version it reported. Written at sign-in and at token refresh, never on
  every request, so it costs one upsert per fifteen-minute access token
  rather than one per call. It holds no device identifier of any kind
  [TC-3, D-37] -- the platform is a two-value enum the client states
  about itself, and the version is the app's own version string.
* **``help_ticket``** is a question one account asked ShikkhokPlus
  support. ``requester_ref`` is an opaque, stable label derived from the
  account id, so a platform administrator can group one person's tickets
  without being shown who a student or guardian is [TC-14, D-6].
* **``help_message``** is one message in a ticket's thread, written by
  the requester or by support.

All three cascade from ``account``: the help centre is the account's own
correspondence, and nobody else has a claim on it once the account goes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.roles import APP_ROLE

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the client and help centre tables.

    :return: None
    """
    bind = op.get_bind()
    postgresql.ENUM("android", "web", name="client_platform").create(
        bind, checkfirst=False
    )
    postgresql.ENUM("open", "answered", "closed", name="help_ticket_status").create(
        bind, checkfirst=False
    )
    postgresql.ENUM("requester", "support", name="help_author").create(
        bind, checkfirst=False
    )

    op.create_table(
        "account_client",
        sa.Column(
            "account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "platform",
            postgresql.ENUM(name="client_platform", create_type=False),
            nullable=False,
        ),
        sa.Column("app_version", sa.String(32), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("account_id", "platform"),
        sa.CheckConstraint(
            "last_seen_at >= first_seen_at", name="ck_account_client_seen_order"
        ),
    )
    op.create_index(
        "ix_account_client_platform_seen",
        "account_client",
        ["platform", "last_seen_at"],
    )

    op.create_table(
        "help_ticket",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "requester_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requester_ref", sa.String(16), nullable=False),
        sa.Column("subject", sa.String(120), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="help_ticket_status", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "platform",
            postgresql.ENUM(name="client_platform", create_type=False),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("support_replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requester_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(trim(subject)) > 0", name="ck_help_ticket_subject"),
        sa.CheckConstraint(
            "(status = 'closed') = (closed_at IS NOT NULL)",
            name="ck_help_ticket_closed_at",
        ),
    )
    op.create_index(
        "ix_help_ticket_requester_updated",
        "help_ticket",
        ["requester_account_id", "updated_at"],
    )
    op.create_index(
        "ix_help_ticket_status_updated", "help_ticket", ["status", "updated_at"]
    )
    op.create_index("ix_help_ticket_requester_ref", "help_ticket", ["requester_ref"])

    op.create_table(
        "help_message",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("help_ticket.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author",
            postgresql.ENUM(name="help_author", create_type=False),
            nullable=False,
        ),
        # Which administrator wrote a support reply, for the record.
        # Never shown to the requester, who sees "ShikkhokPlus support".
        sa.Column(
            "author_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(body)) > 0 AND length(body) <= 4000",
            name="ck_help_message_body",
        ),
    )
    op.create_index(
        "ix_help_message_ticket_created", "help_message", ["ticket_id", "created_at"]
    )

    for table in ("account_client", "help_ticket", "help_message"):
        op.execute(
            sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        )


def downgrade() -> None:
    """Drop the help centre, refusing while any ticket exists.

    :return: None
    """
    tickets = (
        op.get_bind().execute(sa.text("SELECT count(*) FROM help_ticket")).scalar()
    )
    if tickets:
        raise RuntimeError(
            f"{tickets} help ticket(s) exist; downgrading would destroy "
            "what people asked support. Refusing."
        )
    op.drop_table("help_message")
    op.drop_table("help_ticket")
    op.drop_table("account_client")
    bind = op.get_bind()
    postgresql.ENUM(name="help_author").drop(bind, checkfirst=False)
    postgresql.ENUM(name="help_ticket_status").drop(bind, checkfirst=False)
    postgresql.ENUM(name="client_platform").drop(bind, checkfirst=False)
