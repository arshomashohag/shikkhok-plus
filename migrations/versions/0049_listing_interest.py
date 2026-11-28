"""Interest in a batch: a second kind of ``listing_enquiry``.

Revision ID: 0049
Revises: 0048
Create Date: 2026-11-28

A signed-in family can tell the people who run a listed batch that they
are interested in it, sharing the phone number on their account, so the
owner can call them when a seat opens (owner decision, 2026-11-28). It is
a join request with nothing typed: no student name, no class, no message,
and the contact always shared. So it is stored as one, with a ``kind``,
and inherits everything already built and tested for a request: the phone
read live from ``account`` and never copied, deletion with either party,
withdrawal, the 90-day purge, and no grant to the public hub reader.

**Existing rows are join requests.** ``kind`` defaults to ``join``.

**A join request still needs a name and a class; an interest has neither.**
``student_name`` and ``class_level`` become nullable, and two CHECKs say
which kind holds what: a join request has both, an interest has neither,
no message, and ``share_contact`` true -- sharing the number is what an
interest is.

**Uniqueness is per kind.** One open join request per owner and family,
as before; one open interest per batch and family. ``uq_listing_enquiry_open``
is rebuilt to cover join requests only, so an interest never blocks a
request and a request never blocks an interest.

**The downgrade refuses while an interest exists**: it would have to delete
a family's shared number to fit ``0048``'s shape.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import conv

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The kinds a ``listing_enquiry`` row may be.
KINDS: Final[tuple[str, ...]] = ("join", "interest")

#: The student-name CHECK as ``0047`` wrote it, and as it now reads.
NAME_CHECK: Final[str] = "ck_listing_enquiry_student_name"
NAME_BEFORE: Final[str] = "char_length(btrim(student_name)) BETWEEN 1 AND 80"
NAME_AFTER: Final[str] = (
    "student_name IS NULL OR char_length(btrim(student_name)) BETWEEN 1 AND 80"
)

#: The CHECKs this revision adds, by name.
CHECKS: Final[dict[str, str]] = {
    "ck_listing_enquiry_join_fields": (
        "kind <> 'join' OR (student_name IS NOT NULL AND class_level IS NOT NULL)"
    ),
    "ck_listing_enquiry_interest_fields": (
        "kind <> 'interest' OR (student_name IS NULL AND class_level IS NULL "
        "AND message IS NULL AND share_contact)"
    ),
}

#: One open join request per owner and family, as ``0047`` built it.
OPEN_INDEX: Final[str] = "uq_listing_enquiry_open"

#: One open interest per batch and family.
INTEREST_INDEX: Final[str] = "uq_listing_enquiry_interest_open"


def upgrade() -> None:
    """Add the kind, relax the join-only columns, and split the uniqueness.

    :return: None
    """
    postgresql.ENUM(*KINDS, name="hub_enquiry_kind").create(op.get_bind())
    op.add_column(
        "listing_enquiry",
        sa.Column(
            "kind",
            postgresql.ENUM(*KINDS, name="hub_enquiry_kind", create_type=False),
            nullable=False,
            server_default=sa.text("'join'"),
        ),
    )
    op.alter_column("listing_enquiry", "student_name", nullable=True)
    op.alter_column("listing_enquiry", "class_level", nullable=True)
    op.drop_constraint(conv(NAME_CHECK), "listing_enquiry", type_="check")
    op.create_check_constraint(conv(NAME_CHECK), "listing_enquiry", NAME_AFTER)
    for name, condition in CHECKS.items():
        op.create_check_constraint(conv(name), "listing_enquiry", condition)

    op.drop_index(OPEN_INDEX, table_name="listing_enquiry")
    op.create_index(
        OPEN_INDEX,
        "listing_enquiry",
        ["owner_id", "enquirer_account_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open' AND kind = 'join'"),
    )
    op.create_index(
        INTEREST_INDEX,
        "listing_enquiry",
        ["batch_id", "enquirer_account_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open' AND kind = 'interest'"),
    )


def downgrade() -> None:
    """Restore ``0048``'s shape, refusing while any interest exists.

    :return: None
    :raises RuntimeError: An interest exists
    """
    bind = op.get_bind()
    interests = bind.execute(
        sa.text("SELECT count(*) FROM listing_enquiry WHERE kind = 'interest'")
    ).scalar()
    if interests:
        raise RuntimeError(
            f"Cannot downgrade 0049: {interests} interest(s) that families "
            "shared would be lost. Refusing."
        )
    op.drop_index(INTEREST_INDEX, table_name="listing_enquiry")
    op.drop_index(OPEN_INDEX, table_name="listing_enquiry")
    op.create_index(
        OPEN_INDEX,
        "listing_enquiry",
        ["owner_id", "enquirer_account_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    for name in reversed(CHECKS):
        op.drop_constraint(conv(name), "listing_enquiry", type_="check")
    op.drop_constraint(conv(NAME_CHECK), "listing_enquiry", type_="check")
    op.create_check_constraint(conv(NAME_CHECK), "listing_enquiry", NAME_BEFORE)
    op.alter_column("listing_enquiry", "class_level", nullable=False)
    op.alter_column("listing_enquiry", "student_name", nullable=False)
    op.drop_column("listing_enquiry", "kind")
    postgresql.ENUM(name="hub_enquiry_kind").drop(bind)
