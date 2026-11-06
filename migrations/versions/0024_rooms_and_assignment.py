"""Rooms, and a teacher and a room on every class.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-06

* **``room``** is one of a centre's rooms: a name, and an archive mark so
  a room no longer used stays on the classes that met in it.
* **``schedule_slot`` and ``session`` gain ``teacher_member_id`` and
  ``room_id``**, both optional: a solo tutor's classes carry neither,
  exactly as before. Generation copies a slot's teacher and room into
  each new class.
* **``session.assignment_source``** says whether a class follows its
  slot (``slot``) or a manager set it alone (``override``). Changing a
  slot's teacher or room moves its future, not-yet-held classes that
  follow the slot, and nothing else [BR1.2, amended 2026-11-06].
* **Double-booking is refused by the database.** Two exclusion
  constraints on ``session`` -- one per teacher, one per room -- refuse
  any two classes that are not cancelled and overlap in time. They are
  ``DEFERRABLE`` so that exchanging the teachers of two overlapping
  classes, which passes through a moment where both are the same
  person's, can complete inside one transaction. The same two rules sit
  on ``schedule_slot`` by weekday, so a weekly timetable cannot be saved
  with a clash in it.

``btree_gist`` supplies the equality operator class a GiST exclusion
needs for a uuid; it is a trusted extension, available on RDS.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.roles import APP_ROLE

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: A class's span. A class with no end occupies its first minute, so it
#: still clashes with another starting at the same moment.
_SESSION_SPAN: Final = (
    "tsrange(date + start_time, "
    "date + coalesce(end_time, start_time + interval '1 minute'))"
)

#: A weekly slot's span, on a fixed date so only the times are compared.
_SLOT_SPAN: Final = (
    "tsrange(DATE '2000-01-03' + start_time, DATE '2000-01-03' + end_time)"
)


def upgrade() -> None:
    """Create rooms, add assignment columns, and refuse double-booking.

    :return: None
    """
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
    postgresql.ENUM("slot", "override", name="assignment_source").create(
        op.get_bind(), checkfirst=False
    )

    op.create_table(
        "room",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("owner.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_room_name"),
    )
    op.create_index("ix_room_owner_id", "room", ["owner_id"])
    op.create_index(
        "uq_room_live_name",
        "room",
        ["owner_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.execute(sa.text(f"GRANT SELECT, INSERT ON room TO {APP_ROLE}"))
    op.execute(sa.text(f"GRANT UPDATE (name, archived_at) ON room TO {APP_ROLE}"))

    for table in ("schedule_slot", "session"):
        op.add_column(
            table,
            sa.Column(
                "teacher_member_id",
                sa.UUID(as_uuid=True),
                sa.ForeignKey("owner_member.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "room_id",
                sa.UUID(as_uuid=True),
                sa.ForeignKey("room.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index(f"ix_{table}_teacher_member_id", table, ["teacher_member_id"])

    op.add_column(
        "session",
        sa.Column(
            "assignment_source",
            postgresql.ENUM(name="assignment_source", create_type=False),
            nullable=False,
            server_default="slot",
        ),
    )

    for column, name in (("teacher_member_id", "teacher"), ("room_id", "room")):
        op.execute(
            sa.text(
                f"ALTER TABLE session ADD CONSTRAINT ex_session_{name}_overlap "
                f"EXCLUDE USING gist ({column} WITH =, {_SESSION_SPAN} WITH &&) "
                f"WHERE (status <> 'cancelled' AND {column} IS NOT NULL) "
                "DEFERRABLE INITIALLY IMMEDIATE"
            )
        )
        op.execute(
            sa.text(
                f"ALTER TABLE schedule_slot ADD CONSTRAINT ex_slot_{name}_overlap "
                f"EXCLUDE USING gist ({column} WITH =, weekday WITH =, "
                f"{_SLOT_SPAN} WITH &&) WHERE ({column} IS NOT NULL) "
                "DEFERRABLE INITIALLY IMMEDIATE"
            )
        )

    # The application already writes these tables; it now also writes
    # the new columns, which the existing grants on both cover.


def downgrade() -> None:
    """Drop the constraints, columns and rooms, refusing once any is used.

    :return: None
    """
    used = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT (SELECT count(*) FROM room) + "
                "(SELECT count(*) FROM session WHERE teacher_member_id IS NOT NULL)"
            )
        )
        .scalar()
    )
    if used:
        raise RuntimeError(
            "rooms or class assignments exist; downgrading would discard "
            "a centre's timetable. Refusing."
        )
    for name in ("teacher", "room"):
        op.drop_constraint(f"ex_session_{name}_overlap", "session")
        op.drop_constraint(f"ex_slot_{name}_overlap", "schedule_slot")
    op.drop_column("session", "assignment_source")
    for table in ("schedule_slot", "session"):
        op.drop_index(f"ix_{table}_teacher_member_id", table_name=table)
        op.drop_column(table, "room_id")
        op.drop_column(table, "teacher_member_id")
    op.drop_table("room")
    postgresql.ENUM(name="assignment_source").drop(op.get_bind(), checkfirst=False)
