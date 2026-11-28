"""Page views of the public hub, one number per page per day.

Revision ID: 0050
Revises: 0049
Create Date: 2026-11-28

Amends owner decision D9 (owner decision, 2026-11-28): the hub now counts
how often each published owner page and batch page is viewed, **and only
that**. One row per page per Bangladesh day holds a count. Nothing about a
visitor is stored -- no IP address, cookie, user agent, referrer or
account -- and only the page's owner reads the counts, in the app; no
public page, search order or ranking uses them.

**The counting request is an image, not the page.** Pages are cached at
the edge, so the origin sees one read per cache window, not one per view.
Each page carries a 1x1 image the origin answers with ``no-store``, and
each load adds one to its page's row for the day, by one upsert.

**No column can identify a person.** ``page_kind`` and ``page_id`` name a
published owner or batch, both already public as report ids; ``day`` is a
date. The table is not personal data: it is kept 12 months by the purge
and is granted to the application role only, never to the hub reader.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.sql.elements import conv

from app.db.roles import APP_ROLE

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Which kind of page a row counts.
KINDS: Final[tuple[str, ...]] = ("owner", "batch")

#: The table this revision creates.
TABLE: Final[str] = "hub_page_view"


def upgrade() -> None:
    """Create the enum and the table, and grant the application role.

    :return: None
    """
    postgresql.ENUM(*KINDS, name="hub_page_kind").create(op.get_bind())
    op.create_table(
        TABLE,
        sa.Column(
            "page_kind",
            postgresql.ENUM(*KINDS, name="hub_page_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("page_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint(
            "page_kind", "page_id", "day", name=conv("pk_hub_page_view")
        ),
        sa.CheckConstraint("views > 0", name=conv("ck_hub_page_view_views")),
    )
    op.create_index("ix_hub_page_view_day", TABLE, ["day"])
    op.execute(
        sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO {APP_ROLE}")
    )


def downgrade() -> None:
    """Drop the table and the enum. Counts hold nobody's data, so no refusal.

    :return: None
    """
    op.drop_table(TABLE)
    postgresql.ENUM(name="hub_page_kind").drop(op.get_bind())
