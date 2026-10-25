"""Three cascades that would destroy retained records become SET NULL.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-25

**This migration exists because a `CASCADE` to `account.id` is wrong
exactly when its table's disposition is `RETAIN_WITH_BASIS`** [BR1.2].
The manifest already says the row must survive account deletion, and a
cascade deletes it -- so the two documents contradicted each other and
the database was the one that would have won.

Three references contradicted, found by enumerating all fifteen
`account.id` references against their tables' dispositions rather than by
reading pairs. The third was invisible to a reading of pairs, which is
the argument for the enumeration:

===================== ========================== ========= =========
Table                 Column                     Today     After
===================== ========================== ========= =========
``enrollment``        ``student_account_id``     CASCADE   SET NULL
``payment_claim``     ``submitted_by_account_id``CASCADE   SET NULL
``queued_submission`` ``submitted_by_account_id``CASCADE   SET NULL
===================== ========================== ========= =========

**Two of the three are `NOT NULL`, so each needs a nullability change as
well.** PostgreSQL does not accept `ON DELETE SET NULL` against a
`NOT NULL` column, and a bare `ondelete` flip fails at migration time.
That failure would be the GOOD outcome; the hazard is the reverse
ordering -- making the column nullable in one change and deferring the
`ondelete` flip -- which leaves the cascade in place while the schema
looks prepared. ``tests/db/test_cascade_contradictions.py`` is what
catches that, because it asserts the ``confdeltype`` and not the
nullability.

**The constraint names here look wrong and are right**, which is the one
thing a later reader is most likely to "correct". The names in the
database are not the names the model's convention implies:

* ``fk_enrollment_account_id_account`` was created by ``0001:201``,
  named for the column as it then was (``account_id``). ``0002:132``
  renamed the COLUMN with ``alter_column(new_column_name=...)``, which
  renames the column and **not** its constraint.
* ``fk_enrollment_guardian_account`` was hand-named in ``0002:363`` and
  never matched the convention at all.

A migration written against the model's implied names **fails on a
migrated database while passing against a metadata-created one** -- the
worst shape of divergence, because a suite that builds its schema from
metadata stays green while production cannot migrate. The real names are
named explicitly below and verified against the migration sources.

The other two constraints were created by inline ``sa.ForeignKey``
declarations in ``0005`` and ``0006``, so they DO carry the convention's
name and are spelled that way.

**The guardian link is dropped and recreated unchanged.** It is already
``SET NULL`` and needs no behaviour change; it is touched only because
``enrollment`` is where both links live and leaving one constraint
undisturbed would make the asymmetry between them look deliberate again.
That is not a reason to alter it, so it is not altered -- it is listed
here as the reference that was CHECKED and found correct.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Each contradicting reference as ``(table, column, constraint name)``.
#:
#: **The constraint name is data here rather than derived**, because two
#: of the four names in this schema do not follow the convention and a
#: derived name would be wrong for exactly those two. The enrollment
#: entry is the one that looks wrong; see this module's docstring.
CASCADE_CONTRADICTIONS: tuple[tuple[str, str, str], ...] = (
    ("enrollment", "student_account_id", "fk_enrollment_account_id_account"),
    (
        "payment_claim",
        "submitted_by_account_id",
        "fk_payment_claim_submitted_by_account_id_account",
    ),
    (
        "queued_submission",
        "submitted_by_account_id",
        "fk_queued_submission_submitted_by_account_id_account",
    ),
)

#: The two columns that are ``NOT NULL`` today and must admit a NULL
#: before ``SET NULL`` is acceptable to PostgreSQL. ``enrollment``'s
#: student link is already nullable -- ``0002:135`` made it so, because
#: dormancy is expressed as a NULL student link.
NEWLY_NULLABLE: tuple[tuple[str, str], ...] = (
    ("payment_claim", "submitted_by_account_id"),
    ("queued_submission", "submitted_by_account_id"),
)


def upgrade() -> None:
    """Make three account references survivable, and two columns nullable.

    Order is load-bearing: the nullability change comes first, because
    ``SET NULL`` against a ``NOT NULL`` column is refused.

    :return: None
    """
    for table, column in NEWLY_NULLABLE:
        op.alter_column(
            table,
            column,
            existing_type=sa.UUID(as_uuid=True),
            nullable=True,
        )

    for table, column, constraint in CASCADE_CONTRADICTIONS:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(
            constraint,
            table,
            "account",
            [column],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Restore the three cascades and the two ``NOT NULL`` columns.

    **This downgrade can fail, and failing is correct.** Restoring
    ``NOT NULL`` on a column that has since been nulled by an account
    deletion is refused by PostgreSQL, which is the honest outcome: the
    rows it would have to invent are rows whose owning account no longer
    exists. The deploy runbook takes a ``pg_dump`` before any production
    migration for exactly this class of step.

    :return: None
    """
    for table, column, constraint in CASCADE_CONTRADICTIONS:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(
            constraint,
            table,
            "account",
            [column],
            ["id"],
            ondelete="CASCADE",
        )

    for table, column in NEWLY_NULLABLE:
        op.alter_column(
            table,
            column,
            existing_type=sa.UUID(as_uuid=True),
            nullable=False,
        )
