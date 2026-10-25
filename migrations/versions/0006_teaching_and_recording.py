"""Teaching and recording: sessions, attendance, exams, marks, notes.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-25

**Six tables, and this is the unit where the product's children's data
arrives.** Until now the privacy boundary protected a self-chosen name,
a photo reference, an address and a fee balance. These tables store
attendance and marks: a record of where a named child was on a given
afternoon and how they performed.

``session`` carries the product's **first optimistic-concurrency
version**. ``UNIQUE (batch_id, date, start_time)`` is the idempotency
mechanism for generation [BR1.3] -- inserts are ``ON CONFLICT DO
NOTHING`` and the conflict is the SUCCESS path, the same shape
``uq_fee_cycle_enrollment_period`` and ``rate_limit_counter`` already
use.

``queued_submission`` is **a table rather than a column**, and the
reason is the one defect D3 shipped that is most likely to recur here.
§ B.7 requires a replayed ``client_mutation_id`` to return the ORIGINAL
stored result and never write twice; a roster is MANY ``attendance``
rows sharing ONE mutation id, so a unique constraint on that column
cannot live there. **That is precisely the shape of D3's
double-crediting race: a write with no natural key to conflict on.**
The submission row is the natural key, and it converts BOTH guarantees
into database constraints -- replay safety on ``(submitted_by_account_id,
client_mutation_id)`` and the version increment on ``(session_id,
kind, resulting_version)``.

**It serves BOTH queued paths, which is what ``kind`` is for.** BR2.1
puts the topic log on the same device queue under the same rules, so it
needs the same replay store; and ``security-design.md`` § 413 named this
table for both. Reusing it unchanged could not work: ``UNIQUE
(session_id, resulting_version)`` is ATTENDANCE-versioned, so a topic
write producing topic version N+1 would collide with the roster write
that produced attendance version N+1 for the same session. ``kind``
enters the version constraint and resolves that; it deliberately stays
OUT of the replay constraint, because a mutation id is unique per
account whatever path it arrived on -- the same id on a different path
is still the same client decision.

``kind`` has **no default**, on ``session.origin``'s reasoning: a later
insert path that does not state the kind is one that forgot to think
about it.

``mark``'s ``CHECK ((result_state = 'marked') = (marks IS NOT NULL))``
is the biconditional FR4.3 reduces to, as a constraint rather than a
validator because a validator is bypassed by every write path that
forgets it. The ``marks <= exam.total_marks`` bound spans a foreign key
and so **cannot** be a single-table CHECK in PostgreSQL; it is enforced
in the write path and asserted by a test [BR4.2].

``mark``'s partial unique index keeps exactly one live row per
``(exam_id, enrollment_id)``. Without it a correction that fails to set
the old row's pointer leaves two live marks and the marksheet counts one
student twice, inflating the batch size, shifting every rank and skewing
the average with nothing on screen to indicate it [BR4.5].

``announcement`` carries **no expiry column**, stated as an absence
because the obvious implementation adds one [AC3.3.4].

**NO COLUMN ON ``batch``.** ``marksheet_visible`` is already built and
already non-null [``app/db/models.py``]; this unit is the one that gives
it an effect, through exactly one route. A test asserts this migration
touches no ``batch`` column [BR5.4].

**Every new table is GRANTed explicitly**, looping over ``NEW_TABLES``.
``0001``'s ``GRANT ... ON ALL TABLES`` covered only what existed then,
and there is no ``ALTER DEFAULT PRIVILEGES`` anywhere in the migration
history. An ungranted table is not merely unreadable by the application
-- it is **invisible to the restricted role in ``information_schema``**,
so every governance gate silently stops covering it, which is how a
control is retired rather than failed [security-design § 1.2].

**No row-level security policy here, and that is a decision**
[NFR14.52, security-design § 3]. The built policy is on ``profile``
alone, where ``account_id`` IS the subject. None of these six tables has
a column naming its READER: ``attendance`` is keyed by ``(session_id,
enrollment_id)``, and reaching the reader from a row requires joining
enrollment to account and branching on which of three lenses is asking
-- which is the lens resolver's job and not a policy predicate's.
``queued_submission.submitted_by_account_id`` is **not a
counter-example**: it names the WRITER, and no read is ever scoped by
it. The revisit trigger is named: any of these tables gaining a column
identifying a reader directly.

Forward-only and backward-compatible: this migration only creates. It
alters no existing table and destroys nothing, so the downgrade is a
clean drop of exactly what was added.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.roles import APP_ROLE

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The session status type's name, shared by upgrade and downgrade so a
#: rename cannot drift between them.
SESSION_STATUS_TYPE = "session_status"

#: FR3.3's three states. ``cancelled`` is terminal for WRITES and not
#: for reads [BR1.6].
SESSION_STATUS_VALUES = ("scheduled", "held", "cancelled")

#: The session origin type's name.
SESSION_ORIGIN_TYPE = "session_origin"

#: Whether generation produced the row or a teacher did [AC3.0.3].
#: There is deliberately no default on the column: a later insert path
#: that does not state the origin is a path that forgot to think about
#: it, and generation must never re-create or delete an ad-hoc session.
SESSION_ORIGIN_VALUES = ("recurrence", "ad_hoc")

#: The queued-write kind type's name.
SUBMISSION_KIND_TYPE = "queued_submission_kind"

#: Which queued path produced the submission [BR2.1, § B.7]. There is
#: deliberately no default on the column, on ``origin``'s reasoning: a
#: later insert path that does not state the kind is a path that forgot
#: to think about it.
SUBMISSION_KIND_VALUES = ("attendance", "topic")

#: The mark result-state type's name.
RESULT_STATE_TYPE = "mark_result_state"

#: FR4.3's four states. A zero is a ``marked`` result with ``marks`` 0
#: and is never conflated with ``absent``; ``not_entered`` and
#: ``joined_after`` are DERIVED from facts rather than typed by the
#: teacher [BR4.3].
RESULT_STATE_VALUES = ("marked", "absent", "not_entered", "joined_after")

#: Every table this migration creates, in dependency order. Used by the
#: grant loop so a table cannot be created and left ungranted, which is
#: ``0005``'s shape and is chosen because a table added to the list
#: cannot then be missed and one created without being added fails the
#: governance test loudly.
NEW_TABLES = (
    "session",
    "queued_submission",
    "attendance",
    "exam",
    "mark",
    "announcement",
)


def upgrade() -> None:
    """Create the six tables, their types, indexes and grants.

    Order is load-bearing in two places: the enum types must exist
    before the columns that use them, and ``queued_submission`` must
    exist before ``attendance.submission_id`` references it.

    :return: None
    """
    bind = op.get_bind()

    # Created explicitly, ONCE, before any table references them. The
    # column-side references below carry `create_type=False` because
    # `create_table` would otherwise re-emit CREATE TYPE per referencing
    # column and fail on the duplicate -- the same lifecycle split
    # `0004`, `0005` and the ORM models already use.
    for name, values in (
        (SESSION_STATUS_TYPE, SESSION_STATUS_VALUES),
        (SESSION_ORIGIN_TYPE, SESSION_ORIGIN_VALUES),
        (SUBMISSION_KIND_TYPE, SUBMISSION_KIND_VALUES),
        (RESULT_STATE_TYPE, RESULT_STATE_VALUES),
    ):
        sa.Enum(*values, name=name).create(bind, checkfirst=False)

    session_status = postgresql.ENUM(
        *SESSION_STATUS_VALUES, name=SESSION_STATUS_TYPE, create_type=False
    )
    session_origin = postgresql.ENUM(
        *SESSION_ORIGIN_VALUES, name=SESSION_ORIGIN_TYPE, create_type=False
    )
    submission_kind = postgresql.ENUM(
        *SUBMISSION_KIND_VALUES, name=SUBMISSION_KIND_TYPE, create_type=False
    )
    result_state = postgresql.ENUM(
        *RESULT_STATE_VALUES, name=RESULT_STATE_TYPE, create_type=False
    )

    # ----------------------------------------------------------------
    # session. Materialised rows, not a view [BR1.2], and the carrier
    # of the two optimistic-concurrency versions.
    # ----------------------------------------------------------------
    op.create_table(
        "session",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "batch_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("batch.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "batch_subject_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("batch_subject.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("topic", sa.String(2000), nullable=True),
        sa.Column("status", session_status, nullable=False),
        sa.Column("origin", session_origin, nullable=False),
        sa.Column("attendance_version", sa.Integer(), nullable=False),
        sa.Column("topic_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # THE idempotency mechanism [BR1.3]. AC3.0.1 identifies a
        # session by its date and start time, so two rows for one
        # occurrence is the duplicate this prevents -- and it is what
        # makes generation re-runnable at all.
        sa.UniqueConstraint(
            "batch_id",
            "date",
            "start_time",
            name="uq_session_batch_date_start",
        ),
        sa.CheckConstraint(
            "attendance_version >= 0",
            name="ck_session_attendance_version_non_negative",
        ),
        sa.CheckConstraint(
            "topic_version >= 0",
            name="ck_session_topic_version_non_negative",
        ),
    )
    op.create_index("ix_session_batch_id", "session", ["batch_id"])
    # The hot read: a batch's sessions in a date window.
    op.create_index("ix_session_batch_date", "session", ["batch_id", "date"])

    # ----------------------------------------------------------------
    # queued_submission. Created BEFORE attendance, which references
    # it. One row per accepted QUEUED write -- roster or topic --
    # carrying both guarantees as constraints [reliability-design § 5].
    # ----------------------------------------------------------------
    op.create_table(
        "queued_submission",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "submitted_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # NO DEFAULT, on `origin`'s reasoning: a later insert path that
        # does not state the kind is one that forgot to think about it.
        sa.Column("kind", submission_kind, nullable=False),
        sa.Column("client_mutation_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("resulting_version", sa.Integer(), nullable=False),
        # Client-reported and used in NO decision [NFR24.20]. A device
        # clock in a conflict rule would let a wrong phone time
        # silently reorder two teachers' writes.
        sa.Column("composed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # Scoped per ACCOUNT [§ B.7], and deliberately NOT by `kind`.
        # Account B presenting account A's id is NOT a duplicate -- the
        # lookup must be scoped by the authenticated account, and one
        # on client_mutation_id alone would find A's row and return it,
        # which ships as a silent success [security-design § 5.2]. A
        # mutation id is unique per account whatever path it arrived
        # on, so the same id on the other path is still the same client
        # decision and is still a replay.
        sa.UniqueConstraint(
            "submitted_by_account_id",
            "client_mutation_id",
            name="uq_queued_submission_replay",
        ),
        # The second, INDEPENDENT guarantee of the version increment
        # [BR3.4]: two writes of one KIND cannot both produce version
        # N+1. This is what makes the guarantee survive somebody later
        # rewriting the conditional update into a read-then-write.
        #
        # `kind` is in this constraint because the two counters are
        # separate: without it a topic write reaching topic version N+1
        # would collide with the roster write that reached attendance
        # version N+1 on the same session -- a refusal describing
        # nothing the teacher did.
        sa.UniqueConstraint(
            "session_id",
            "kind",
            "resulting_version",
            name="uq_queued_submission_version",
        ),
        sa.CheckConstraint(
            "base_version >= 0",
            name="ck_queued_submission_base_version_non_negative",
        ),
        sa.CheckConstraint(
            "resulting_version >= 1",
            name="ck_queued_submission_resulting_version_positive",
        ),
    )
    op.create_index(
        "ix_queued_submission_session_id",
        "queued_submission",
        ["session_id"],
    )

    # ----------------------------------------------------------------
    # attendance. One row per seat per session; a re-submission
    # REPLACES rather than appends [BR3.5].
    # ----------------------------------------------------------------
    op.create_table(
        "attendance",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "enrollment_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("enrollment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # No third value. AC3.1.4 defaults every seat to present and the
        # teacher marks only exceptions, so an unsubmitted roster is an
        # ABSENT row rather than a null column.
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "submission_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("queued_submission.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "session_id",
            "enrollment_id",
            name="uq_attendance_session_enrollment",
        ),
    )
    op.create_index("ix_attendance_enrollment_id", "attendance", ["enrollment_id"])
    op.create_index("ix_attendance_submission_fk", "attendance", ["submission_id"])

    # ----------------------------------------------------------------
    # exam. `total_marks` is an INTEGER COUNT and not money.
    # ----------------------------------------------------------------
    op.create_table(
        "exam",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "batch_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("batch.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # RESTRICT rather than CASCADE or SET NULL: deleting a subject
        # must not silently destroy the exams and marks recorded under
        # it, and an exam with no subject cannot satisfy AC4.1.1.
        sa.Column(
            "batch_subject_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("batch_subject.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("total_marks", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("total_marks >= 1", name="ck_exam_total_marks_positive"),
    )
    op.create_index("ix_exam_batch_id", "exam", ["batch_id"])
    op.create_index("ix_exam_batch_subject_id", "exam", ["batch_subject_id"])

    # ----------------------------------------------------------------
    # mark. Append-only with a supersession chain, the same shape
    # ledger_entry uses [BR4.4].
    # ----------------------------------------------------------------
    op.create_table(
        "mark",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "exam_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("exam.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "enrollment_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("enrollment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("result_state", result_state, nullable=False),
        sa.Column("marks", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "superseded_by_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("mark.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # The biconditional FR4.3 reduces to. A zero stored as `absent`
        # tells a guardian their child missed an exam they sat and
        # failed; the reverse tells them the child scored nothing when
        # they were ill [BR4.2].
        sa.CheckConstraint(
            "(result_state = 'marked') = (marks IS NOT NULL)",
            name="ck_mark_state_marks_biconditional",
        ),
        sa.CheckConstraint(
            "marks IS NULL OR marks >= 0",
            name="ck_mark_marks_non_negative",
        ),
    )
    # The partial unique index, the same shape as the built
    # uq_enrollment_batch_student. The UPPER bound on `marks` is NOT
    # here: `marks <= exam.total_marks` spans a foreign key and cannot
    # be a single-table CHECK in PostgreSQL, so it is enforced in the
    # write path and asserted by a test [BR4.2, entities.md].
    op.create_index(
        "uq_mark_live_per_seat",
        "mark",
        ["exam_id", "enrollment_id"],
        unique=True,
        postgresql_where=sa.text("superseded_by_id IS NULL"),
    )
    op.create_index("ix_mark_exam_id", "mark", ["exam_id"])
    op.create_index("ix_mark_enrollment_id", "mark", ["enrollment_id"])

    # ----------------------------------------------------------------
    # announcement. Soft-deleted, and with NO expiry column [AC3.3.4].
    # ----------------------------------------------------------------
    op.create_table(
        "announcement",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "batch_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("batch.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("body", sa.String(4000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "posted_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_announcement_batch_id", "announcement", ["batch_id"])

    # ----------------------------------------------------------------
    # The grants. Looped over the declared table list rather than
    # written out six times.
    # ----------------------------------------------------------------
    for table in NEW_TABLES:
        op.execute(
            sa.text(
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table}" TO {APP_ROLE}'  # noqa: S608  fixed module constants
            )
        )


def downgrade() -> None:
    """Drop the six tables and the four enum types.

    Cleanly reversible, because this migration only ever created. The
    data is lost, which is why the deploy runbook takes a ``pg_dump``
    before any production migration regardless.

    :return: None
    """
    op.drop_table("announcement")
    op.drop_table("mark")
    op.drop_table("exam")
    op.drop_table("attendance")
    op.drop_table("queued_submission")
    op.drop_table("session")

    bind = op.get_bind()
    sa.Enum(name=RESULT_STATE_TYPE).drop(bind, checkfirst=False)
    sa.Enum(name=SUBMISSION_KIND_TYPE).drop(bind, checkfirst=False)
    sa.Enum(name=SESSION_ORIGIN_TYPE).drop(bind, checkfirst=False)
    sa.Enum(name=SESSION_STATUS_TYPE).drop(bind, checkfirst=False)
