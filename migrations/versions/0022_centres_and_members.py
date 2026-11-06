"""Coaching centres: an owner may be an organisation with members.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-06

* **``owner.kind``** says what an owner is: ``teacher`` (a solo tutor,
  whose ``account_id`` is the one person behind it, as every owner has
  been until now) or ``organisation`` (a coaching centre, which has no
  ``account_id`` and whose people are its members). Every existing row is
  backfilled ``teacher`` by the column's default, which is KEPT: every
  existing path that creates an owner creates a solo tutor, and the one
  path that creates a centre says so. A CHECK keeps an organisation from
  carrying an account.
* **``owner.name``** is a centre's name, shown to its members and its
  families. NULL for a solo tutor.
* **``owner_member``** is one person's place in a centre: a manager or a
  teacher, invited by phone and holding nothing until they accept --
  the rule a student's seat already follows, because naming a number is
  not that person's agreement. ``revoked_at`` ends a membership without
  deleting the record. A person holds at most one live membership per
  centre, and an invitation to the same number cannot be sent twice
  while one is live.

Nothing about a solo tutor changes: no row moves and no backfill touches
a batch, a seat or a ledger.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.roles import APP_ROLE

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the owner kind and name, and the member table.

    :return: None
    """
    kind = postgresql.ENUM("teacher", "organisation", name="owner_kind")
    kind.create(op.get_bind(), checkfirst=False)
    role = postgresql.ENUM("manager", "teacher", name="member_role")
    role.create(op.get_bind(), checkfirst=False)

    op.add_column(
        "owner",
        sa.Column(
            "kind",
            postgresql.ENUM(name="owner_kind", create_type=False),
            nullable=False,
            server_default="teacher",
        ),
    )
    op.add_column("owner", sa.Column("name", sa.String(120), nullable=True))
    op.create_check_constraint(
        "ck_owner_organisation_has_no_account",
        "owner",
        "kind = 'teacher' OR account_id IS NULL",
    )
    op.create_check_constraint(
        "ck_owner_organisation_is_named",
        "owner",
        "kind = 'teacher' OR length(trim(name)) > 0",
    )

    op.create_table(
        "owner_member",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("owner.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("invited_phone", sa.String(20), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(name="member_role", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "decision",
            postgresql.ENUM(name="enrollment_decision", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "invited_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(trim(display_name)) > 0", name="ck_owner_member_display_name"
        ),
    )
    op.create_index("ix_owner_member_owner_id", "owner_member", ["owner_id"])
    op.create_index("ix_owner_member_account_id", "owner_member", ["account_id"])
    op.create_index("ix_owner_member_invited_phone", "owner_member", ["invited_phone"])
    op.create_index(
        "uq_owner_member_live_phone",
        "owner_member",
        ["owner_id", "invited_phone"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.execute(
        sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON owner_member TO {APP_ROLE}")
    )


def downgrade() -> None:
    """Drop the members and the kind, refusing while a centre exists.

    :return: None
    """
    centres = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM owner WHERE kind = 'organisation'"))
        .scalar()
    )
    if centres:
        raise RuntimeError(
            f"{centres} coaching centre(s) exist; downgrading would orphan "
            "their batches and members. Refusing."
        )
    op.drop_table("owner_member")
    op.drop_constraint("ck_owner_organisation_is_named", "owner", type_="check")
    op.drop_constraint("ck_owner_organisation_has_no_account", "owner", type_="check")
    op.drop_column("owner", "name")
    op.drop_column("owner", "kind")
    postgresql.ENUM(name="member_role").drop(op.get_bind(), checkfirst=False)
    postgresql.ENUM(name="owner_kind").drop(op.get_bind(), checkfirst=False)
