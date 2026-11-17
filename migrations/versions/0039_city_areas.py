"""City corporations and their metropolitan thanas.

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-17

Dhaka district holds only five rural upazilas in ``0035``'s vocabulary, so
a listing in Mirpur or Dhanmondi had no area to name. This revision adds
two kinds below a district:

* ``city_corporation``, whose parent is a district, coded by its BBS
  geocode (``BD30262500`` for Dhaka North);
* ``metro_thana``, whose parent is a city corporation, coded ``MT`` plus
  the city corporation's geocode digits plus a two-digit ordinal
  (``MT3026250003`` for Mirpur).

The rows come from ``app/hub/listings/data/bd_city_area.csv``, derived
from the BBS geocode dataset, and the metropolitan thanas' Bangla names
from ``bd_metro_thana_bn.csv``, which the dataset does not carry and
which were entered by hand. Both are read with the standard library,
deliberately not through application code that may change later. No
existing row changes.

A new enum label cannot be used in the transaction that adds it, so the
labels are added in an autocommit block before the rows are inserted.
PostgreSQL cannot drop an enum label, so the downgrade rebuilds the type;
it refuses while a listing names a city area, because those codes are
the listing's location.
"""

from __future__ import annotations

import csv
import pathlib
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The enum type's name, shared by upgrade and downgrade.
KIND_TYPE: Final[str] = "bd_area_kind"

#: The labels ``0035`` created, which the downgrade restores.
EARLIER_KINDS: Final[tuple[str, ...]] = ("division", "district", "upazila")

#: The labels this revision adds, outermost first.
CITY_KINDS: Final[tuple[str, ...]] = ("city_corporation", "metro_thana")

#: The seed files' directory, relative to the repository root.
DATA: Final[pathlib.Path] = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "hub" / "listings" / "data"
)


def _read(name: str) -> list[dict[str, str]]:
    """Read one seed file.

    :param name: The file's name under the data directory
    :return: Its rows
    """
    with (DATA / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _rows() -> list[dict[str, str]]:
    """Merge the derived rows with the hand-entered Bangla thana names.

    :return: One mapping per area, city corporations before their thanas
    :raises RuntimeError: A metro thana has no Bangla name, or a Bangla
        name names no thana
    """
    bangla = {
        row["code"]: row["name_bn"].strip() for row in _read("bd_metro_thana_bn.csv")
    }
    rows = []
    for row in _read("bd_city_area.csv"):
        name_bn = row["name_bn"]
        if row["kind"] == "metro_thana":
            name_bn = bangla.pop(row["code"], "")
        if not name_bn:
            raise RuntimeError(f"0039: {row['code']} has no Bangla name")
        rows.append(
            {
                "code": row["code"],
                "kind": row["kind"],
                "parent_code": row["parent_code"],
                "name_en": row["name_en"],
                "name_bn": name_bn,
            }
        )
    if bangla:
        raise RuntimeError(f"0039: Bangla names for unknown thanas {sorted(bangla)}")
    return rows


def upgrade() -> None:
    """Add the two labels, then the city corporations and their thanas.

    :return: None
    """
    with op.get_context().autocommit_block():
        for kind in CITY_KINDS:
            op.execute(sa.text(f"ALTER TYPE {KIND_TYPE} ADD VALUE '{kind}'"))
    # City corporations precede their thanas in the file, so each row's
    # parent is already present when the foreign key is checked.
    table = sa.table(
        "bd_area",
        sa.column("code", sa.String),
        sa.column("kind", sa.Enum(*EARLIER_KINDS, *CITY_KINDS, name=KIND_TYPE)),
        sa.column("parent_code", sa.String),
        sa.column("name_en", sa.Text),
        sa.column("name_bn", sa.Text),
    )
    op.bulk_insert(table, _rows())


def downgrade() -> None:
    """Refuse while a listing names a city area; else remove them and the labels.

    :return: None
    :raises RuntimeError: A listing's district or upazila is a city area
    """
    bind = op.get_bind()
    used = bind.execute(
        sa.text(
            "SELECT count(*) FROM owner_listing l JOIN bd_area a "
            "ON a.code IN (l.district_code, l.upazila_code) "
            "WHERE a.kind::text = ANY(:kinds)"
        ),
        {"kinds": list(CITY_KINDS)},
    ).scalar_one()
    if used:
        raise RuntimeError(
            f"Cannot downgrade 0039: {used} listing(s) name a city corporation "
            "or metropolitan thana; move them to an upazila first."
        )
    op.execute(sa.text("DELETE FROM bd_area WHERE kind = 'metro_thana'"))
    op.execute(sa.text("DELETE FROM bd_area WHERE kind = 'city_corporation'"))
    # The type cannot lose a label in place: build the narrower one, move
    # the column onto it, and drop the old. Grants are on the table, not
    # the type, so they are unaffected.
    labels = ", ".join(f"'{k}'" for k in EARLIER_KINDS)
    op.execute(sa.text(f"ALTER TYPE {KIND_TYPE} RENAME TO {KIND_TYPE}_0039"))
    op.execute(sa.text(f"CREATE TYPE {KIND_TYPE} AS ENUM ({labels})"))
    op.execute(
        sa.text(
            f"ALTER TABLE bd_area ALTER COLUMN kind TYPE {KIND_TYPE} "
            f"USING kind::text::{KIND_TYPE}"
        )
    )
    op.execute(sa.text(f"DROP TYPE {KIND_TYPE}_0039"))
