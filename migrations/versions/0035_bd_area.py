"""The Bangladesh area vocabulary: divisions, districts and upazilas.

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-15

A fixed, three-level list a listing's location is chosen from. It is
about no person, so it is shared with both the application role and the
public hub reader.

``code`` is the Bangladesh Bureau of Statistics geocode of the row
(``BD20`` for a division, ``BD2019`` for a district, ``BD20190040`` for
an upazila) and ``parent_code`` is the parent row's. The rows are read
straight from ``app/hub/listings/data/bd_area.csv`` with the standard
library, deliberately not through application code that may change after
this revision is applied.
"""

from __future__ import annotations

import csv
import pathlib
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op

from app.db.roles import APP_ROLE, HUB_READER_ROLE

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The enum type's name, shared by upgrade and downgrade.
KIND_TYPE: Final[str] = "bd_area_kind"

#: The three levels, outermost first.
KIND_VALUES: Final[tuple[str, ...]] = ("division", "district", "upazila")

#: The seed file, relative to the repository root this revision lives in.
CSV_PATH: Final[pathlib.Path] = (
    pathlib.Path(__file__).resolve().parents[2]
    / "app"
    / "hub"
    / "listings"
    / "data"
    / "bd_area.csv"
)


def _rows() -> list[dict[str, str | None]]:
    """Read the seed file, a blank parent becoming ``None``.

    :return: One mapping per area, divisions first
    """
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        return [
            {
                "code": row["code"],
                "kind": row["kind"],
                "parent_code": row["parent_code"] or None,
                "name_en": row["name_en"],
                "name_bn": row["name_bn"],
            }
            for row in csv.DictReader(handle)
        ]


def upgrade() -> None:
    """Create the type and table, seed them and grant read access.

    :return: None
    """
    kind = sa.Enum(*KIND_VALUES, name=KIND_TYPE)
    table = op.create_table(
        "bd_area",
        sa.Column("code", sa.String(12), nullable=False),
        sa.Column("kind", kind, nullable=False),
        sa.Column("parent_code", sa.String(12), nullable=True),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("name_bn", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_bd_area"),
        sa.ForeignKeyConstraint(
            ["parent_code"], ["bd_area.code"], name="fk_bd_area_parent_code_bd_area"
        ),
    )
    op.create_index("ix_bd_area_parent_code", "bd_area", ["parent_code"])
    # Divisions precede districts precede upazilas in the file, so each
    # row's parent is already present when the foreign key is checked.
    op.bulk_insert(table, _rows())
    op.execute(sa.text(f"GRANT SELECT ON bd_area TO {HUB_READER_ROLE}, {APP_ROLE}"))


def downgrade() -> None:
    """Revoke the grants, then drop the table and the type.

    :return: None
    """
    op.execute(
        sa.text(
            f"REVOKE SELECT ON bd_area FROM {HUB_READER_ROLE}, {APP_ROLE}"  # noqa: S608
        )
    )
    op.drop_table("bd_area")
    sa.Enum(name=KIND_TYPE).drop(op.get_bind(), checkfirst=False)
