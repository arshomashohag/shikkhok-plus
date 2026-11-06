"""An exam's examiner at a coaching centre.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-06

**``exam.examiner_member_id``** names the centre member who enters and
publishes an exam's marks (decided 2026-11-06: "a manager creates the
exam and names the examiner"). NULL for a solo tutor's exams, who mark
their own, and for a centre exam not yet given one. ``SET NULL`` keeps
the exam when a membership row goes; a removed teacher is cleared from
unpublished exams by the application, and a published exam keeps its
examiner as the record of who marked it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the examiner column and its index.

    :return: None
    """
    op.add_column(
        "exam",
        sa.Column(
            "examiner_member_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("owner_member.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_exam_examiner_member_id", "exam", ["examiner_member_id"])


def downgrade() -> None:
    """Drop the examiner, refusing while any exam names one.

    :return: None
    """
    named = (
        op.get_bind()
        .execute(
            sa.text("SELECT count(*) FROM exam WHERE examiner_member_id IS NOT NULL")
        )
        .scalar()
    )
    if named:
        raise RuntimeError(
            f"{named} exam(s) name an examiner; downgrading would forget who "
            "marked them. Refusing."
        )
    op.drop_index("ix_exam_examiner_member_id", table_name="exam")
    op.drop_column("exam", "examiner_member_id")
