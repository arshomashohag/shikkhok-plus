"""Batches, schedule, and the enrollment reshape.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-18

**The first migration that alters a table holding rows**, which makes it
the first one whose failure modes are interesting.

``0001`` created ``enrollment`` as a shell with ``account_id`` and
``role``, because U3 needed lens resolution to have something to query.
That shape cannot answer "which child is this guardian's", since a
guardian row names the guardian's own account and nothing links it to
the student's row except a shared batch. ``0002`` reshapes it into one
row per seat carrying ``student_account_id`` and ``guardian_account_id``
side by side [BR5.0], and folds the separate guardian rows in.

**The fold is the irreversible part, and it is guarded.** A guardian row
can only be folded into a batch holding exactly one student row. Zero
and there is nowhere to put it; two and the fold would have to guess.
The guard raises in both cases, naming the batch and the count, because
that message is the operator's entire interface to the situation.

**The guard may sit after the DDL** because PostgreSQL has transactional
DDL and Alembic wraps an upgrade in one transaction (``env.py`` sets no
``transactional_ddl=False`` override). A raise therefore rolls the
preceding ``ADD COLUMN`` and ``RENAME COLUMN`` back with it, leaving the
schema byte-identical. On a backend without transactional DDL the same
migration would leave a half-renamed table, and this file would be
wrong.

**``enrollment.batch_id`` gains no foreign key here, and that is a
decision rather than an omission.** ``0001`` created ``enrollment``
before ``batch`` existed and left the column deliberately unconstrained,
so every row surviving from that head points at a batch that does not
exist -- and no batch *can* exist before this migration creates the
table. Adding the constraint would therefore refuse every populated
database and succeed only on empty ones, which is the exact shape of a
check that passes in testing and fails on the one deploy that matters.

**Synthesizing a batch per orphan was considered and rejected**, which
is the obvious alternative and the reason this needs writing down. A
``batch`` row requires an ``owner_id``, and a ``0001`` enrollment
carries no owner link at all -- only ``account_id`` and ``batch_id``.
There is no way to determine which teacher an orphan belongs to, so the
migration would have to INVENT an ownership relationship and then make
it referentially binding. A wrong owner is worse than no constraint:
it is a cross-teacher authorization error written by a migration.

**The constraint is scheduled, not merely postponed**, because a
deferral with no owner is a permanent gap wearing a temporary label.
U5 is the first Unit to migrate against a populated ``batch`` table, so
U5's migration adds::

    op.create_foreign_key(
        "fk_enrollment_batch", "enrollment", "batch", ["batch_id"], ["id"]
    )

It can do so unconditionally: by then every enrollment was written by
``app.batches.service``, which only ever stores a ``batch_id`` it just
read from an owned batch. A test asserts the constraint exists once
that migration lands, so the schedule is checkable rather than a note.

Until then the relationship is enforced by the services alone.

``downgrade()`` **raises**. It could reverse the renames, but it cannot
reconstruct which student a deleted guardian row belonged to -- and a
downgrade that appears to work while silently losing guardian links
would be reached for in exactly the moment when care matters most. The
honest rollback for this revision is a restore from the pre-deploy dump.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.roles import APP_ROLE

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The precision every money column carries [TC-7, D-20]. Never a float,
#: never a bare Numeric, and never declared per-column anywhere else.
MONEY_TYPE = sa.Numeric(precision=12, scale=2)


class UnfoldableGuardianRow(RuntimeError):
    """Raised when a guardian enrollment cannot be folded safely.

    Carries the batch id and the student count so the operator reads the
    remedy rather than a stack trace.
    """


def _reshape_enrollment() -> None:
    """Widen ``enrollment`` to carry both links on one row.

    :return: None
    """
    op.add_column(
        "enrollment",
        sa.Column("guardian_account_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("enrollment", sa.Column("guardian_phone", sa.String(20)))
    op.add_column("enrollment", sa.Column("fee_amount", MONEY_TYPE, nullable=True))
    op.add_column("enrollment", sa.Column("joined_on", sa.Date(), nullable=True))
    op.add_column("enrollment", sa.Column("inactive_from", sa.Date(), nullable=True))
    # Per LINK, not per row [BR6.2]. One flag cannot express the four
    # states: a guardian's erasure would permanently block a student who
    # never claimed that seat and never erased anything.
    op.add_column(
        "enrollment",
        sa.Column(
            "student_relink_blocked_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "enrollment",
        sa.Column(
            "guardian_relink_blocked_at", sa.DateTime(timezone=True), nullable=True
        ),
    )

    # RENAME, not drop-and-add. The distinction is invisible on an empty
    # table and destroys every claimed enrollment on a populated one,
    # which is what the from-head test exists to catch [NFR6.18].
    op.alter_column("enrollment", "account_id", new_column_name="student_account_id")
    # Dormancy is expressed as a NULL student link, so the column that
    # 0001 made NOT NULL has to admit one.
    op.alter_column(
        "enrollment",
        "student_account_id",
        existing_type=sa.UUID(as_uuid=True),
        nullable=True,
    )


def _guard_unfoldable_rows() -> None:
    """Refuse the fold when a guardian row has no single student.

    :return: None
    :raises UnfoldableGuardianRow: A guardian row's batch holds a student
        count other than exactly one
    """
    connection = op.get_bind()
    offenders = connection.execute(
        sa.text(
            """
            SELECT g.batch_id,
                   count(s.id) AS student_count
              FROM enrollment g
              LEFT JOIN enrollment s
                ON s.batch_id = g.batch_id
               AND s.role = 'student'
             WHERE g.role = 'guardian'
             GROUP BY g.batch_id, g.id
            HAVING count(s.id) <> 1
            """
        )
    ).all()

    if not offenders:
        return

    detail = "; ".join(
        f"batch {batch_id} has {count} student rows and a guardian row"
        for batch_id, count in offenders
    )
    raise UnfoldableGuardianRow(
        f"cannot fold guardian enrollments: {detail}. "
        "A guardian row folds only into a batch holding exactly one "
        "student row. If these are the skeleton seed's rows, delete the "
        "seed rows and redeploy; otherwise reconcile them by hand. "
        "Nothing has been altered -- this migration rolled back."
    )


def _fold_guardian_rows() -> None:
    """Move each guardian's account onto its batch's student row.

    Two-sided by construction: the guardian's account lands on the
    student row and the guardian row is then deleted, so no account is
    recorded twice.

    :return: None
    """
    op.execute(
        sa.text(
            """
            UPDATE enrollment s
               SET guardian_account_id = g.student_account_id
              FROM enrollment g
             WHERE g.role = 'guardian'
               AND s.role = 'student'
               AND g.batch_id = s.batch_id
            """
        )
    )
    op.execute(sa.text("DELETE FROM enrollment WHERE role = 'guardian'"))
    op.drop_column("enrollment", "role")


def _create_batch_tables() -> None:
    """Create the four tables this Unit owns.

    :return: None
    """
    op.create_table(
        "batch",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("teacher_display_name", sa.Text(), nullable=True),
        # A teacher-typed payment DESTINATION, not money. It must never
        # acquire a money type [components.md].
        sa.Column("collection_number", sa.String(length=32), nullable=True),
        sa.Column("collection_channel", sa.String(length=32), nullable=True),
        sa.Column("default_fee", MONEY_TYPE, nullable=True),
        sa.Column("fee_due_day", sa.Integer(), nullable=True),
        sa.Column("marksheet_visible", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_batch"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["owner.id"], name="fk_batch_owner", ondelete="CASCADE"
        ),
        # 29, 30 and 31 are legal and clamp at generation time [AC2.1.2].
        # The column must admit them or the clamp never runs.
        sa.CheckConstraint(
            "fee_due_day IS NULL OR (fee_due_day BETWEEN 1 AND 31)",
            name="ck_batch_fee_due_day",
        ),
    )

    op.create_table(
        "batch_subject",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_batch_subject"),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["batch.id"],
            name="fk_batch_subject_batch",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "schedule_slot",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", sa.UUID(as_uuid=True), nullable=False),
        # An INTEGER, not a string: a string admits 'Monday', 'monday'
        # and 'Mon' as three different Mondays.
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_schedule_slot"),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["batch.id"],
            name="fk_schedule_slot_batch",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_schedule_slot_weekday"),
    )

    # A separate table, not a column on enrollment [AC2.6.3]. Hiding is
    # PER VIEWER: a student hiding a batch must not hide it from the
    # guardian or the teacher.
    op.create_table(
        "hidden_batch_preference",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_hidden_batch_preference"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name="fk_hidden_batch_preference_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["batch.id"],
            name="fk_hidden_batch_preference_batch",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "account_id", "batch_id", name="uq_hidden_batch_preference"
        ),
    )


def _create_indexes() -> None:
    """Create the roster, lens and uniqueness indexes.

    :return: None
    """
    op.create_index("ix_batch_owner_id", "batch", ["owner_id"])
    op.create_index("ix_enrollment_batch_id", "enrollment", ["batch_id"])
    op.create_index(
        "ix_enrollment_guardian_account_id", "enrollment", ["guardian_account_id"]
    )
    op.create_index("ix_batch_subject_batch_id", "batch_subject", ["batch_id"])

    # PARTIAL, and the predicate is the point [scalability-design §A].
    # Without it the second dormant seat in a batch is refused, which is
    # the normal state early in a batch's life.
    op.create_index(
        "uq_enrollment_batch_student",
        "enrollment",
        ["batch_id", "student_account_id"],
        unique=True,
        postgresql_where=sa.text("student_account_id IS NOT NULL"),
    )


def _grant_new_tables() -> None:
    """Grant the restricted role access to the tables created here.

    **``0001``'s ``GRANT ... ON ALL TABLES`` covered only the tables that
    existed when it ran.** A table created by a later migration has no
    grant at all, so the application role cannot read it and -- less
    obviously -- cannot even see it in ``information_schema``.

    That second effect is what makes this dangerous rather than merely
    broken: the governance gates read ``information_schema`` as the
    restricted role, so an ungranted table is invisible to the very
    checks meant to police it. The money-column assertion reported only
    ``enrollment.fee_amount`` and silently skipped ``batch.default_fee``
    until this grant existed.

    :return: None
    """
    for table in ("batch", "batch_subject", "schedule_slot", "hidden_batch_preference"):
        op.execute(
            sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        )


def upgrade() -> None:
    """Reshape ``enrollment`` and create this Unit's tables.

    The ordering is load-bearing: the reshape must precede the guard, so
    the guard can read ``student_account_id``, and the guard must precede
    the fold, so nothing is deleted that cannot be placed.

    :return: None
    :raises UnfoldableGuardianRow: A guardian row cannot be folded
    """
    _reshape_enrollment()
    _guard_unfoldable_rows()
    _fold_guardian_rows()

    op.create_foreign_key(
        "fk_enrollment_guardian_account",
        "enrollment",
        "account",
        ["guardian_account_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _create_batch_tables()
    _create_indexes()
    _grant_new_tables()


def downgrade() -> None:
    """Refuse: the fold cannot be reversed.

    :return: None
    :raises NotImplementedError: Always
    """
    raise NotImplementedError(
        "0002 cannot be downgraded. The fold collapses each guardian "
        "enrollment into its batch's student row and deletes it, so the "
        "information about which row a guardian came from is gone. "
        "Restore from the pre-deploy pg_dump instead."
    )
