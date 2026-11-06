"""A centre's teachers and other staff, as its manager records them.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-06

* **``staff``** holds the facts a manager types about a person who works
  at a centre: name, contact, address, role, pay terms, joining and
  leaving. It grants nothing. App access stays on ``owner_member``, the
  lean authorization table, and a teacher's staff record links to its
  membership through ``member_id`` -- the split a student's record and
  seat already follow.
* **The address has its own column names** (``staff_house`` and so on),
  never the profile's, so the schema gate that keeps profile addresses
  out of every teacher-facing response stays exactly as strict.
* **Pay terms are a basis and a rate.** ``monthly`` or ``per_class``
  carry a rate above zero; ``none`` carries no rate. A CHECK holds the
  pairing so no row can say it pays per class without saying how much.
* Only the leaving columns and the editable facts change after insert;
  the row is never deleted by the application.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.roles import APP_ROLE

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS: Final = ("teacher", "other")
BASES: Final = ("monthly", "per_class", "none")

#: Every column a manager may correct after the record is created.
_EDITABLE: Final = (
    "display_name, phone, email, staff_house, staff_road, staff_city, "
    "staff_postcode, role_label, pay_basis, pay_rate, joined_on, left_on"
)


def upgrade() -> None:
    """Create the staff table, its types, indexes and grants.

    :return: None
    """
    postgresql.ENUM(*KINDS, name="staff_kind").create(op.get_bind(), checkfirst=False)
    postgresql.ENUM(*BASES, name="pay_basis").create(op.get_bind(), checkfirst=False)
    op.create_table(
        "staff",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("owner.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kind",
            postgresql.ENUM(name="staff_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("staff_house", sa.String(120), nullable=True),
        sa.Column("staff_road", sa.String(120), nullable=True),
        sa.Column("staff_city", sa.String(80), nullable=True),
        sa.Column("staff_postcode", sa.String(4), nullable=True),
        sa.Column("role_label", sa.String(60), nullable=True),
        sa.Column(
            "member_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("owner_member.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column(
            "pay_basis",
            postgresql.ENUM(name="pay_basis", create_type=False),
            nullable=False,
        ),
        sa.Column("pay_rate", sa.Numeric(12, 2), nullable=True),
        sa.Column("joined_on", sa.Date(), nullable=False),
        sa.Column("left_on", sa.Date(), nullable=True),
        sa.Column(
            "created_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(display_name)) > 0", name="ck_staff_display_name"
        ),
        sa.CheckConstraint(
            "(pay_basis = 'none' AND pay_rate IS NULL) "
            "OR (pay_basis <> 'none' AND pay_rate > 0)",
            name="ck_staff_pay_terms",
        ),
        sa.CheckConstraint(
            "kind = 'teacher' OR member_id IS NULL",
            name="ck_staff_only_teachers_have_access",
        ),
        sa.CheckConstraint(
            "left_on IS NULL OR left_on >= joined_on", name="ck_staff_left_after_joined"
        ),
    )
    op.create_index("ix_staff_owner_id", "staff", ["owner_id"])
    op.execute(sa.text(f"GRANT SELECT, INSERT ON staff TO {APP_ROLE}"))
    op.execute(sa.text(f"GRANT UPDATE ({_EDITABLE}) ON staff TO {APP_ROLE}"))


def downgrade() -> None:
    """Drop the staff table and its types, refusing while a record exists.

    :return: None
    """
    count = op.get_bind().execute(sa.text("SELECT count(*) FROM staff")).scalar()
    if count:
        raise RuntimeError(
            f"{count} staff record(s) exist; downgrading would destroy a "
            "centre's records of who works there. Refusing."
        )
    op.drop_table("staff")
    postgresql.ENUM(name="pay_basis").drop(op.get_bind(), checkfirst=False)
    postgresql.ENUM(name="staff_kind").drop(op.get_bind(), checkfirst=False)
