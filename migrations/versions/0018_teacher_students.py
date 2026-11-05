"""Students belong to the teacher, and a seat points at one.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-05

Decided by the owner on 2026-11-05: a teacher keeps ONE list of students,
and the same student can sit in any number of that teacher's batches.
Until now a student existed only as a seat (``enrollment``) inside one
batch, so a child in two classes was two unrelated rows.

* **``student``** is the teacher's record of a person: the name and the
  two numbers the teacher typed. It is owned by ``owner``, never by an
  account, so it outlives nobody's sign-in and grants nothing.
* **``enrollment.student_id``** says which student a seat belongs to, and
  ``(batch_id, student_id)`` is unique: one seat per student per batch.

**The seat keeps its copy of the name, numbers, links and decisions.**
Every read that grants a lens, generates a fee or renders a roster reads
those columns on ``enrollment`` today and is unchanged by this revision;
``app.students.service`` is the one writer and keeps every seat of a
student in step with the student in the same transaction.

**Backfill.** Seats of the same owner that share a student number become
one student, which is the case this change exists for. A seat with no
student number becomes a student of its own: a matching name alone is
not proof two seats are the same child. The earliest seat of a group
supplies the student's name and guardian number, and its id is reused as
the student's id so the mapping needs no temporary table. A seat whose
batch row is missing has no owner and keeps a NULL ``student_id``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.roles import APP_ROLE

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``student``, backfill it, and point every seat at one.

    :return: None
    """
    op.create_table(
        "student",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("owner.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("student_phone", sa.String(20), nullable=True),
        sa.Column("guardian_phone", sa.String(20), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_student_owner_id", "student", ["owner_id"])
    # One student per number per teacher [D2]. Partial, because a student
    # with no number is allowed and two of them are not duplicates.
    op.create_index(
        "uq_student_owner_phone",
        "student",
        ["owner_id", "student_phone"],
        unique=True,
        postgresql_where=sa.text("student_phone IS NOT NULL"),
    )
    op.execute(
        sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON student TO {APP_ROLE}")
    )

    op.add_column(
        "enrollment",
        sa.Column(
            "student_id",
            sa.UUID(as_uuid=True),
            # RESTRICT: a student with seats is archived, never deleted,
            # so no seat and none of its fee history can lose its owner.
            sa.ForeignKey("student.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )

    # Seats with a number: one student per (owner, number), from the
    # earliest seat of the group.
    op.execute(
        sa.text(
            """
            INSERT INTO student (id, owner_id, display_name, student_phone,
                                 guardian_phone, created_at)
            SELECT DISTINCT ON (b.owner_id, e.student_phone)
                   e.id, b.owner_id, e.display_name, e.student_phone,
                   e.guardian_phone, e.created_at
            FROM enrollment e
            JOIN batch b ON b.id = e.batch_id
            WHERE e.student_phone IS NOT NULL
            ORDER BY b.owner_id, e.student_phone, e.created_at, e.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE enrollment e
            SET student_id = s.id
            FROM batch b, student s
            WHERE b.id = e.batch_id
              AND s.owner_id = b.owner_id
              AND s.student_phone = e.student_phone
            """
        )
    )
    # Seats without a number: one student each, reusing the seat's id.
    op.execute(
        sa.text(
            """
            INSERT INTO student (id, owner_id, display_name, student_phone,
                                 guardian_phone, created_at)
            SELECT e.id, b.owner_id, e.display_name, NULL,
                   e.guardian_phone, e.created_at
            FROM enrollment e
            JOIN batch b ON b.id = e.batch_id
            WHERE e.student_phone IS NULL
              AND e.student_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            "UPDATE enrollment SET student_id = id "
            "WHERE student_id IS NULL AND id IN (SELECT id FROM student)"
        )
    )

    # Left NULLABLE, and only for one case: a seat whose batch row does
    # not exist has no owner, so no student can be made for it. No
    # application path creates such a seat -- every seat the app writes
    # is created through `app.students.service.seat_for` with its
    # student -- but `enrollment.batch_id` carries no foreign key, so
    # the migration cannot assume there are none.
    op.create_index("ix_enrollment_student_id", "enrollment", ["student_id"])
    op.create_index(
        "uq_enrollment_batch_student_record",
        "enrollment",
        ["batch_id", "student_id"],
        unique=True,
    )


def downgrade() -> None:
    """Drop the link and the table. Seats keep their own copies.

    :return: None
    """
    op.drop_index("uq_enrollment_batch_student_record", table_name="enrollment")
    op.drop_index("ix_enrollment_student_id", table_name="enrollment")
    op.drop_column("enrollment", "student_id")
    op.drop_index("uq_student_owner_phone", table_name="student")
    op.drop_index("ix_student_owner_id", table_name="student")
    op.drop_table("student")
