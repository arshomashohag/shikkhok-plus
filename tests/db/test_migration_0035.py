"""``0035`` seeds the Bangladesh area vocabulary and shares it with the hub.

The rows come from the committed CSV, which is derived from the BBS
geocodes; these tests assert the shape of what the migration loaded, not
the CSV's individual names.
"""

from __future__ import annotations

import csv
import pathlib
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.hub.public.db import as_hub_reader

CSV_PATH: Final[pathlib.Path] = (
    pathlib.Path(__file__).resolve().parents[2]
    / "app"
    / "hub"
    / "listings"
    / "data"
    / "bd_area.csv"
)


def _count(session: Session, kind: str) -> int:
    """Count the vocabulary rows of one kind.

    :param session: A session
    :param kind: ``division``, ``district`` or ``upazila``
    :return: The row count
    """
    return int(
        session.execute(
            sa.text("SELECT count(*) FROM bd_area WHERE kind = :k"), {"k": kind}
        ).scalar_one()
    )


def test_0035_seeds_8_divisions_and_64_districts(
    restricted_session: Session,
) -> None:
    """Bangladesh has eight divisions and sixty-four districts.

    :param restricted_session: A session as the application role
    :return: None
    """
    assert _count(restricted_session, "division") == 8
    assert _count(restricted_session, "district") == 64


def test_every_district_parent_is_a_division_and_every_upazila_parent_is_a_district(
    restricted_session: Session,
) -> None:
    """The hierarchy is closed: no orphan, no skipped level.

    :param restricted_session: A session as the application role
    :return: None
    """
    bad = restricted_session.execute(
        sa.text(
            "SELECT c.code FROM bd_area c LEFT JOIN bd_area p "
            "ON p.code = c.parent_code "
            "WHERE (c.kind = 'division' AND c.parent_code IS NOT NULL) "
            "OR (c.kind = 'district' "
            "AND (p.code IS NULL OR p.kind <> 'division')) "
            "OR (c.kind = 'upazila' "
            "AND (p.code IS NULL OR p.kind <> 'district'))"
        )
    ).all()
    assert bad == []


def test_upazila_count_is_at_least_490(restricted_session: Session) -> None:
    """The BBS list carries around five hundred upazilas.

    :param restricted_session: A session as the application role
    :return: None
    """
    assert _count(restricted_session, "upazila") >= 490


def test_names_are_nonblank_in_both_languages(restricted_session: Session) -> None:
    """Every area is named in English and in Bangla.

    :param restricted_session: A session as the application role
    :return: None
    """
    blank = restricted_session.execute(
        sa.text(
            "SELECT code FROM bd_area WHERE btrim(name_en) = '' OR btrim(name_bn) = ''"
        )
    ).all()
    assert blank == []


def test_the_table_matches_the_committed_csv(restricted_session: Session) -> None:
    """The migration loads every CSV row, no more and no fewer.

    :param restricted_session: A session as the application role
    :return: None
    """
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        expected = {row["code"] for row in csv.DictReader(handle)}
    loaded = {
        row[0]
        for row in restricted_session.execute(sa.text("SELECT code FROM bd_area"))
    }
    assert loaded == expected


def test_hub_reader_can_select_bd_area(restricted_session: Session) -> None:
    """The public hub role may read the vocabulary.

    :param restricted_session: A session as the application role
    :return: None
    """
    as_hub_reader(restricted_session)
    total = restricted_session.execute(sa.text("SELECT count(*) FROM bd_area"))
    assert total.scalar_one() >= 562
