"""Join requests: ``listing_enquiry``, ``accepts_enquiries`` and the enquirable view.

Revision ID: 0047
Revises: 0046
Create Date: 2026-11-20

A signed-in guardian asks a listed teacher or centre to take a student
(H5). The request holds what the guardian typed for it -- the student's
name and class level, an optional message -- and whether they chose to
share their contact; the contact itself is read live from ``account`` and
never copied here (Call 4).

**The owner opts in separately from publishing** (Call 3):
``owner_listing.accepts_enquiries`` defaults to false, so every listing
that exists when this runs is unaffected.

**``share_contact`` has no default.** Whether to share a number is the
guardian's answer; an insert that does not state it fails.

**States.** A request is ``open`` until the owner closes it with one of
three outcomes (Call 7). Three CHECKs keep that honest: a closed request
carries its outcome and its closing time, an open one neither, and
``added`` needs a shared contact, since without one the owner cannot seat
anyone.

**One open request per owner and guardian** (Call 9): a partial unique
index, so the send is an ``INSERT ... ON CONFLICT DO NOTHING``, never a
check-then-insert. A closed request does not block a new one.

**The class-level list is frozen here** [F21], as ``0036`` froze its own:
a migration that read ``HUB_CLASS_LEVELS`` would change meaning when the
model changed. The model's CHECK reads the tuple, and
``tests/db/test_schema_parity.py`` compares the two.

**``hub_public_enquirable``** (Call 15) lists the owners a guardian may ask:
those in ``hub_public_owner`` whose listing accepts requests. It reads that
view rather than restating its filter, so a draft, hidden or suspended
listing is never a target, and from ``owner_listing`` only ``owner_id`` and
``accepts_enquiries``. A new view rather than a changed one: altering
``hub_public_owner`` would need ``CREATE OR REPLACE`` under two dependent
views, and its downgrade could not drop the column.

**Deviation from spec section 2, recorded** [F22]: the spec lists four
reader views; ``0043`` and ``0045`` made seven, and this is the eighth. It
exposes the id and slug of owners already public, nothing more, which
``tests/privacy/test_hub_public_enquirable_view.py`` pins through
``pg_depend``.

**Grants.** The reader gets ``SELECT`` on the new view and nothing on the
table: a request is never public. The application role gets CRUD on the
table and ``SELECT`` on ``hub_public_owner``, ``hub_public_batch`` and the
new view (Call 16), so a send's target checks and a guardian's view of a
``call_us`` number use the public pages' own predicates inside a write
transaction, without ``SET LOCAL ROLE``. It already reads every base table
those views read, so nothing new is reachable. The downgrade revokes the
two ``0040`` grants, which outlive this revision's own objects.

**Cascades.** A request goes with the guardian's account and with its owner
row; deleting the batch listing it named only clears ``batch_id``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.sql.elements import conv

from app.db.roles import APP_ROLE, HUB_READER_ROLE

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Each enum this revision creates and its labels, in declaration order.
ENUMS: Final[dict[str, tuple[str, ...]]] = {
    "hub_enquiry_status": ("open", "closed"),
    "hub_enquiry_outcome": ("added", "not_now", "call_us"),
}

#: The class levels a request may name, frozen at this revision [F21].
CLASS_LEVELS: Final[tuple[str, ...]] = (
    *(f"class_{n}" for n in range(1, 13)),
    "ssc",
    "hsc",
    "admission",
    "o_level",
    "a_level",
    "other",
)

#: The view this revision creates.
VIEW: Final[str] = "hub_public_enquirable"

#: Its body: the published owners who accept requests.
VIEW_BODY: Final[str] = """
    SELECT o.owner_id, o.slug
    FROM hub_public_owner o
    JOIN owner_listing l ON l.owner_id = o.owner_id
    WHERE l.accepts_enquiries
"""

#: The public views the application role is granted ``SELECT`` on.
APP_VIEWS: Final[tuple[str, ...]] = ("hub_public_owner", "hub_public_batch", VIEW)


def _enum(name: str) -> postgresql.ENUM:
    """Return one of this revision's enums, without creating it again.

    :param name: The enum's name
    :return: The enum type
    """
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    """Add the column, the enums, the table, the view and their grants.

    :return: None
    """
    op.add_column(
        "owner_listing",
        sa.Column(
            "accepts_enquiries",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    bind = op.get_bind()
    for name, labels in ENUMS.items():
        postgresql.ENUM(*labels, name=name).create(bind)

    op.create_table(
        "listing_enquiry",
        sa.Column(
            "id",
            PgUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "owner_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey(
                "owner.id",
                ondelete="CASCADE",
                name=conv("fk_listing_enquiry_owner_id"),
            ),
            nullable=False,
        ),
        sa.Column(
            "batch_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey(
                "batch_listing.batch_id",
                ondelete="SET NULL",
                name=conv("fk_listing_enquiry_batch_id"),
            ),
            nullable=True,
        ),
        sa.Column(
            "enquirer_account_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey(
                "account.id",
                ondelete="CASCADE",
                name=conv("fk_listing_enquiry_enquirer_account_id"),
            ),
            nullable=False,
        ),
        sa.Column("student_name", sa.Text(), nullable=False),
        sa.Column("class_level", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("share_contact", sa.Boolean(), nullable=False),
        sa.Column(
            "status",
            _enum("hub_enquiry_status"),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("outcome", _enum("hub_enquiry_outcome"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(btrim(student_name)) BETWEEN 1 AND 80",
            name=conv("ck_listing_enquiry_student_name"),
        ),
        sa.CheckConstraint(
            f"class_level IN ({', '.join(repr(c) for c in CLASS_LEVELS)})",
            name=conv("ck_listing_enquiry_class_level"),
        ),
        sa.CheckConstraint(
            "message IS NULL OR char_length(message) BETWEEN 1 AND 300",
            name=conv("ck_listing_enquiry_message"),
        ),
        sa.CheckConstraint(
            "(status = 'closed') = (outcome IS NOT NULL)",
            name=conv("ck_listing_enquiry_outcome_iff_closed"),
        ),
        sa.CheckConstraint(
            "(status = 'closed') = (closed_at IS NOT NULL)",
            name=conv("ck_listing_enquiry_closed_at_iff_closed"),
        ),
        sa.CheckConstraint(
            "outcome IS DISTINCT FROM 'added' OR share_contact",
            name=conv("ck_listing_enquiry_added_needs_contact"),
        ),
    )
    op.create_index(
        "uq_listing_enquiry_open",
        "listing_enquiry",
        ["owner_id", "enquirer_account_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(
        "ix_listing_enquiry_owner_created",
        "listing_enquiry",
        ["owner_id", "created_at"],
    )
    op.create_index(
        "ix_listing_enquiry_enquirer",
        "listing_enquiry",
        ["enquirer_account_id"],
    )
    op.execute(
        sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON listing_enquiry TO {APP_ROLE}"
        )
    )

    op.execute(sa.text(f"CREATE VIEW {VIEW} WITH (security_barrier) AS {VIEW_BODY}"))
    op.execute(sa.text(f"GRANT SELECT ON {VIEW} TO {HUB_READER_ROLE}"))
    for name in APP_VIEWS:
        op.execute(sa.text(f"GRANT SELECT ON {name} TO {APP_ROLE}"))


def downgrade() -> None:
    """Drop what ``upgrade`` added, refusing while a request exists.

    A request holds a child's name as a guardian typed it and cannot be
    rebuilt, so any row blocks the downgrade.

    :return: None
    :raises RuntimeError: A request exists
    """
    bind = op.get_bind()
    requests = bind.execute(sa.text("SELECT count(*) FROM listing_enquiry")).scalar()
    if requests:
        raise RuntimeError(
            f"Cannot downgrade 0047: {requests} join request(s) that guardians "
            "sent would be lost. Refusing."
        )
    for name in ("hub_public_owner", "hub_public_batch"):
        op.execute(sa.text(f"REVOKE SELECT ON {name} FROM {APP_ROLE}"))  # noqa: S608  module constants
    op.execute(sa.text(f"DROP VIEW {VIEW}"))
    op.drop_table("listing_enquiry")
    for name in reversed(ENUMS):
        postgresql.ENUM(name=name).drop(bind)
    op.drop_column("owner_listing", "accepts_enquiries")
