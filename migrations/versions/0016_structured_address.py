"""The address in four parts: house, road, city and postcode.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-05

The owner decided on 2026-11-05 that an address is required at sign-up,
as separate House, Road, City and Postcode fields. Four columns on
``profile``, which already carries the row-level-security policy and the
``app`` role's grants, so neither changes. All four are nullable: every
account created before this revision has none, and an account a teacher
added by number has no profile fields until its owner signs up. The
request schema, not the column, is what makes them required at sign-up.

The single free-text ``address`` stays, so an address typed before this
revision is not lost; nothing writes it any more.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Each part and its bound, matching the request schema's limits.
PARTS: tuple[tuple[str, int], ...] = (
    ("address_house", 60),
    ("address_road", 120),
    ("address_city", 60),
    ("address_postcode", 10),
)


def upgrade() -> None:
    """Add the four nullable address columns.

    :return: None
    """
    for name, length in PARTS:
        op.add_column("profile", sa.Column(name, sa.String(length), nullable=True))


def downgrade() -> None:
    """Drop the four address columns.

    :return: None
    """
    for name, _length in reversed(PARTS):
        op.drop_column("profile", name)
