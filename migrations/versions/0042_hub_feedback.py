"""The teacher demand question and the first-publish anchor.

Revision ID: 0042
Revises: 0041
Create Date: 2026-11-17

The product decides at day 90 whether the public hub is worth continuing,
from publishing owners' answers to "Did the hub bring you a student?". A
daily job asks at day 60 and day 90 after an owner's FIRST publish and
records one ``hub_feedback`` row per ``(owner_id, day)``; the unique
constraint is what keeps overlapping runs from asking twice.

**``owner_listing.first_published_at``.** ``published_at`` is overwritten
by every publish, so an owner who hid and republished their listing would
have their day 60 and day 90 moved. The new column is set by the first
publish only and backfilled here from ``published_at`` -- the best
evidence there is for listings published before this revision.

The application role may read, write and delete the table (a solo owner's
rows go with their account); the hub reader is granted nothing.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.sql.elements import conv

from app.db.roles import APP_ROLE

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the first-publish anchor and the demand-question table.

    :return: None
    """
    op.add_column(
        "owner_listing",
        sa.Column("first_published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE owner_listing SET first_published_at = published_at "
            "WHERE published_at IS NOT NULL"
        )
    )
    op.create_table(
        "hub_feedback",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey(
                "owner.id", ondelete="CASCADE", name=conv("fk_hub_feedback_owner")
            ),
            nullable=False,
        ),
        sa.Column("asked_on", sa.Date(), nullable=False),
        sa.Column("day", sa.SmallInteger(), nullable=False),
        sa.Column("answer", sa.String(10), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "answered_by_account_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey(
                "account.id",
                ondelete="SET NULL",
                name=conv("fk_hub_feedback_answered_by_account_id"),
            ),
            nullable=True,
        ),
        sa.UniqueConstraint("owner_id", "day", name=conv("uq_hub_feedback_owner_day")),
        sa.CheckConstraint("day IN (60, 90)", name=conv("ck_hub_feedback_day")),
        sa.CheckConstraint(
            "answer IN ('yes', 'not_yet', 'not_sure')",
            name=conv("ck_hub_feedback_answer"),
        ),
        sa.CheckConstraint(
            "(answer IS NULL) = (answered_at IS NULL)",
            name=conv("ck_hub_feedback_answered"),
        ),
    )
    op.create_index(
        "ix_hub_feedback_answered_by_account_id",
        "hub_feedback",
        ["answered_by_account_id"],
    )
    op.execute(
        sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON hub_feedback TO {APP_ROLE}")
    )


def downgrade() -> None:
    """Drop the table and the anchor.

    The answers go with the table; ``published_at`` is untouched.

    :return: None
    """
    op.drop_table("hub_feedback")
    op.drop_column("owner_listing", "first_published_at")
