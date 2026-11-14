"""Teachers and centres record people by email as well as by phone.

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-14

A teacher may now record a student's and a guardian's email address, and
a centre may invite a member by email [FR6.1, FR6.4]. An account that
verifies the address is then linked to those records exactly as a phone
number links them today [FR6.5]. What this revision adds:

* **``student.student_email``** and **``student.guardian_email``**, and
  the synchronized copies on **``enrollment``** that linking matches
  against, as ``enrollment.student_phone`` is matched today [BR1.5].
* **``owner_member.invited_email``**, and ``invited_phone`` made
  nullable under a CHECK that one of the two is present [BR1.8]. Every
  existing row holds a number or the legacy ``""`` a manager row was
  written with, so the CHECK validates without a rewrite.
* **``otp_request.requested_by_account_id``**: the account that confirmed
  its password for a contact replacement, so only that account can spend
  the code [BR5.3]. ``ON DELETE SET NULL``; an absent binding never
  matches a verifying account.

**Stored lowercased, and the database says so.** The services canonicalise
every address before it is written; the CHECKs make a mixed-case address
a refused write rather than a quiet second spelling that the matcher's
equality comparison would never find.

**Uniqueness follows the phone wherever the phone has it** [BR1.2,
BR1.8]: a student email per teacher, archived students included, and a
live invited email per centre. A guardian email is unique nowhere, as a
guardian phone is unique nowhere.

The partial indexes serve the matcher's set-based link statements, the
email form of the already-added lookup and the two uniqueness checks
[NFR8.3, NFR8.8]. All columns are nullable with no default and no
existing row is updated [NFR7.1], so the revision runs as fast DDL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: RFC 5321's limit on a forward path, as ``account.email`` is sized.
EMAIL_LENGTH = 254

#: Every recorded-email column this revision adds: (table, column).
_EMAIL_COLUMNS = (
    ("student", "student_email"),
    ("student", "guardian_email"),
    ("enrollment", "student_email"),
    ("enrollment", "guardian_email"),
    ("owner_member", "invited_email"),
)


def upgrade() -> None:
    """Add the recorded-email columns, their checks and their indexes.

    :return: None
    """
    for table, column in _EMAIL_COLUMNS:
        op.add_column(table, sa.Column(column, sa.String(EMAIL_LENGTH), nullable=True))
        op.create_check_constraint(
            f"ck_{table}_{column}_lower", table, f"{column} = lower({column})"
        )

    op.create_index(
        "uq_student_owner_email",
        "student",
        ["owner_id", "student_email"],
        unique=True,
        postgresql_where=sa.text("student_email IS NOT NULL"),
    )
    op.create_index(
        "ix_enrollment_student_email",
        "enrollment",
        ["student_email"],
        postgresql_where=sa.text("student_email IS NOT NULL"),
    )
    op.create_index(
        "ix_enrollment_guardian_email",
        "enrollment",
        ["guardian_email"],
        postgresql_where=sa.text("guardian_email IS NOT NULL"),
    )

    op.alter_column(
        "owner_member", "invited_phone", existing_type=sa.String(20), nullable=True
    )
    op.create_check_constraint(
        "ck_owner_member_has_contact",
        "owner_member",
        "invited_phone IS NOT NULL OR invited_email IS NOT NULL",
    )
    op.create_index(
        "uq_owner_member_live_email",
        "owner_member",
        ["owner_id", "invited_email"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL AND invited_email IS NOT NULL"),
    )
    op.create_index(
        "ix_owner_member_unlinked_email",
        "owner_member",
        ["invited_email"],
        postgresql_where=sa.text(
            "revoked_at IS NULL AND account_id IS NULL AND invited_email IS NOT NULL"
        ),
    )

    op.add_column(
        "otp_request",
        sa.Column(
            "requested_by_account_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "account.id",
                ondelete="SET NULL",
                name="fk_otp_request_requested_by_account_id_account",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_otp_request_requested_by_account_id",
        "otp_request",
        ["requested_by_account_id"],
        postgresql_where=sa.text("requested_by_account_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop what :func:`upgrade` added.

    **Refuses while an email-only invitation exists**: restoring
    ``NOT NULL`` on ``invited_phone`` would fail on it anyway, and a
    downgrade that deleted invitations to make room would be data loss
    disguised as a rollback.

    :return: None
    """
    held = (
        op.get_bind()
        .execute(
            sa.text("SELECT count(*) FROM owner_member WHERE invited_phone IS NULL")
        )
        .scalar()
    )
    if held:
        raise RuntimeError(
            f"{held} invitation(s) carry no phone number; downgrading would "
            "leave them invalid. Refusing."
        )
    op.drop_index("ix_otp_request_requested_by_account_id", table_name="otp_request")
    op.drop_column("otp_request", "requested_by_account_id")
    op.drop_index("ix_owner_member_unlinked_email", table_name="owner_member")
    op.drop_index("uq_owner_member_live_email", table_name="owner_member")
    op.drop_constraint("ck_owner_member_has_contact", "owner_member", type_="check")
    op.alter_column(
        "owner_member", "invited_phone", existing_type=sa.String(20), nullable=False
    )
    op.drop_index("ix_enrollment_guardian_email", table_name="enrollment")
    op.drop_index("ix_enrollment_student_email", table_name="enrollment")
    op.drop_index("uq_student_owner_email", table_name="student")
    for table, column in reversed(_EMAIL_COLUMNS):
        op.drop_constraint(f"ck_{table}_{column}_lower", table, type_="check")
        op.drop_column(table, column)
