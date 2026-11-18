"""``0039`` adds the city corporations and their metropolitan thanas.

The rows come from two committed CSVs: ``bd_city_area.csv``, derived from
the BBS geocode dataset, and ``bd_metro_thana_bn.csv``, the Bangla names
the dataset lacks, entered by hand and reviewed by the owner. The 567
rows ``0035`` loaded must come through untouched, because listings store
their codes.
"""

from __future__ import annotations

import csv
import datetime as dt
import pathlib
import uuid
from collections.abc import Iterator
from typing import Final

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from tests.db.migration_support import (
    _alembic_config,
    insert_account,
    stage_at,
    upgrade_to_head,
)

DATA: Final[pathlib.Path] = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "hub" / "listings" / "data"
)

#: Dhaka district's BBS geocode.
DHAKA: Final[str] = "BD3026"

#: The kinds ``0035`` created, which ``0039`` must not disturb.
EARLIER_KINDS: Final[tuple[str, ...]] = ("division", "district", "upazila")


def _csv(name: str) -> list[dict[str, str]]:
    """Read one committed data file.

    :param name: The file's name under the data directory
    :return: Its rows
    """
    with (DATA / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_0039_adds_city_corporations_and_metro_thanas(
    restricted_session: Session,
) -> None:
    """Twelve city corporations, Dhaka's two among them, and Mirpur under DNCC.

    :param restricted_session: A session as the application role
    :return: None
    """
    count = restricted_session.execute(
        sa.text("SELECT count(*) FROM bd_area WHERE kind = 'city_corporation'")
    ).scalar_one()
    assert count == 12

    under_dhaka = set(
        restricted_session.execute(
            sa.text(
                "SELECT name_en FROM bd_area "
                "WHERE parent_code = :d AND kind = 'city_corporation'"
            ),
            {"d": DHAKA},
        ).scalars()
    )
    assert under_dhaka == {
        "Dhaka North City Corporation",
        "Dhaka South City Corporation",
    }

    mirpur = restricted_session.execute(
        sa.text(
            "SELECT t.code FROM bd_area t JOIN bd_area c ON c.code = t.parent_code "
            "WHERE t.kind = 'metro_thana' AND t.name_en = 'Mirpur' "
            "AND c.name_en = 'Dhaka North City Corporation'"
        )
    ).all()
    assert len(mirpur) == 1


def test_city_hierarchy_is_closed(restricted_session: Session) -> None:
    """A city corporation sits in a district, a metro thana in a city corporation.

    :param restricted_session: A session as the application role
    :return: None
    """
    bad = restricted_session.execute(
        sa.text(
            "SELECT c.code FROM bd_area c LEFT JOIN bd_area p "
            "ON p.code = c.parent_code "
            "WHERE (c.kind = 'city_corporation' "
            "AND (p.code IS NULL OR p.kind <> 'district')) "
            "OR (c.kind = 'metro_thana' "
            "AND (p.code IS NULL OR p.kind <> 'city_corporation'))"
        )
    ).all()
    assert bad == []


def test_every_metro_thana_has_reviewed_bangla_name(
    restricted_session: Session,
) -> None:
    """The hand-entered file names every thana, in Bangla, and nothing else.

    :param restricted_session: A session as the application role
    :return: None
    """
    loaded = {
        r.code: (r.name_en, r.name_bn)
        for r in restricted_session.execute(
            sa.text(
                "SELECT code, name_en, name_bn FROM bd_area WHERE kind = 'metro_thana'"
            )
        )
    }
    reviewed = {row["code"]: row["name_bn"] for row in _csv("bd_metro_thana_bn.csv")}

    assert loaded
    assert set(reviewed) == set(loaded)
    for code, (name_en, name_bn) in loaded.items():
        assert name_bn.strip(), code
        assert name_bn != name_en, code
        assert name_bn == reviewed[code], code


def test_every_new_code_fits_the_column(restricted_session: Session) -> None:
    """A metro thana code is ``MT`` plus ten digits, twelve characters.

    :param restricted_session: A session as the application role
    :return: None
    """
    rows = _csv("bd_city_area.csv")
    assert rows
    for row in rows:
        assert len(row["code"]) <= 12, row["code"]
        if row["kind"] == "metro_thana":
            assert len(row["code"]) == 12, row["code"]
            assert row["code"].startswith("MT"), row["code"]
            assert row["code"][2:].isdigit(), row["code"]
    width = restricted_session.execute(
        sa.text(
            "SELECT character_maximum_length FROM information_schema.columns "
            "WHERE table_name = 'bd_area' AND column_name = 'code'"
        )
    ).scalar_one()
    assert width == 12


def test_metro_thana_codes_number_by_english_name(
    restricted_session: Session,
) -> None:
    """Each city corporation's thanas run 01, 02, ... in English-name order.

    :param restricted_session: A session as the application role
    :return: None
    """
    rows = restricted_session.execute(
        sa.text(
            "SELECT t.code, t.name_en, c.code AS parent FROM bd_area t "
            "JOIN bd_area c ON c.code = t.parent_code "
            "WHERE t.kind = 'metro_thana'"
        )
    ).all()
    by_parent: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        by_parent.setdefault(row.parent, []).append((row.name_en, row.code))
    for parent, thanas in by_parent.items():
        expected = [
            "MT" + parent.removeprefix("BD") + f"{n:02d}"
            for n in range(1, len(thanas) + 1)
        ]
        assert [code for _, code in sorted(thanas)] == expected


def test_the_new_rows_match_the_committed_csv(restricted_session: Session) -> None:
    """Every derived row is loaded, no more and no fewer.

    :param restricted_session: A session as the application role
    :return: None
    """
    expected = {
        (row["code"], row["kind"], row["parent_code"], row["name_en"])
        for row in _csv("bd_city_area.csv")
    }
    loaded = {
        tuple(row)
        for row in restricted_session.execute(
            sa.text(
                "SELECT code, kind::text, parent_code, name_en FROM bd_area "
                "WHERE kind IN ('city_corporation', 'metro_thana')"
            )
        )
    }
    assert loaded == expected


def test_existing_codes_unchanged(restricted_session: Session) -> None:
    """The 567 rows ``0035`` loaded are byte-for-byte what its CSV holds.

    :param restricted_session: A session as the application role
    :return: None
    """
    expected = {
        (
            row["code"],
            row["kind"],
            row["parent_code"] or None,
            row["name_en"],
            row["name_bn"],
        )
        for row in _csv("bd_area.csv")
    }
    loaded = {
        tuple(row)
        for row in restricted_session.execute(
            sa.text(
                "SELECT code, kind::text, parent_code, name_en, name_bn "
                "FROM bd_area WHERE kind::text = ANY(:k)"
            ),
            {"k": list(EARLIER_KINDS)},
        )
    }
    assert len(expected) == 567
    assert loaded == expected


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0039``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0039") as engine:
        yield engine


def _downgrade(engine: Engine) -> None:
    """Downgrade the staged database to ``0038``.

    :param engine: The staged engine
    :return: None
    """
    url = engine.url.render_as_string(hide_password=False)
    command.downgrade(_alembic_config(url), "0038")


def _kinds(engine: Engine) -> list[str]:
    """Read the ``bd_area_kind`` labels, in their sort order.

    :param engine: The staged engine
    :return: The labels
    """
    with engine.connect() as connection:
        return list(
            connection.execute(
                sa.text("SELECT unnest(enum_range(NULL::bd_area_kind))::text")
            ).scalars()
        )


def test_0039_downgrade_restores_the_three_kinds_and_re_upgrades(
    staged: Engine,
) -> None:
    """Down removes the rows and the labels; up again loads them again.

    :param staged: The engine staged at ``0039``
    :return: None
    """
    _downgrade(staged)
    assert _kinds(staged) == list(EARLIER_KINDS)
    with staged.connect() as connection:
        total = connection.execute(sa.text("SELECT count(*) FROM bd_area"))
        assert total.scalar_one() == 567

    url = staged.url.render_as_string(hide_password=False)
    command.upgrade(_alembic_config(url), "0039")
    assert _kinds(staged) == [*EARLIER_KINDS, "city_corporation", "metro_thana"]


def test_0039_downgrade_refuses_while_a_listing_names_a_metro_thana(
    staged: Engine,
) -> None:
    """A stored metro thana code blocks the downgrade and survives it.

    :param staged: The engine staged at ``0039``
    :return: None
    """
    owner_id = uuid.uuid4()
    with staged.begin() as connection:
        account_id = insert_account(connection, "+8801711110039")
        connection.execute(
            sa.text(
                "INSERT INTO owner (id, account_id, created_at) "
                "VALUES (:id, :account, :now)"
            ),
            {"id": owner_id, "account": account_id, "now": dt.datetime.now(dt.UTC)},
        )
        connection.execute(
            sa.text(
                "INSERT INTO owner_listing (owner_id, public_name, district_code, "
                "upazila_code) VALUES (:o, 'Rahim Sir', :d, 'MT3026250003')"
            ),
            {"o": owner_id, "d": DHAKA},
        )

    with pytest.raises(Exception, match="Cannot downgrade 0039"):
        _downgrade(staged)

    with staged.connect() as connection:
        kept = connection.execute(
            sa.text("SELECT count(*) FROM bd_area WHERE kind = 'metro_thana'")
        ).scalar_one()
    assert kept > 0


@pytest.fixture
def at_0038(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0038``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0038") as engine:
        yield engine


def test_0039_keeps_the_lock_timeout_for_what_follows(at_0038: Engine) -> None:
    """Every statement after the enum labels still runs under the 10s timeout.

    ``env.py`` sets ``lock_timeout`` with ``SET LOCAL`` inside Alembic's
    transaction, and the autocommit block commits that transaction, so
    without a restore 0039's inserts and every later migration in the same
    run would queue for a lock indefinitely [audit C-18]. Each statement's
    setting is read on the same connection, straight after it ran.

    :param at_0038: The engine staged at ``0038``
    :return: None
    """
    seen: list[tuple[str, str]] = []

    def record(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        """Read the timeout in force after each statement, on its connection.

        :param conn: The SQLAlchemy connection
        :param cursor: The DBAPI cursor that ran the statement
        :param statement: The statement
        :param parameters: Its parameters
        :param context: The execution context
        :param executemany: Whether it ran for many rows
        :return: None
        """
        probe = cursor.connection.cursor()  # type: ignore[attr-defined]
        probe.execute("SHOW lock_timeout")
        seen.append((statement, str(probe.fetchone()[0])))
        probe.close()

    sa.event.listen(Engine, "after_cursor_execute", record)
    try:
        upgrade_to_head(at_0038)
    finally:
        sa.event.remove(Engine, "after_cursor_execute", record)

    labels = [i for i, (sql, _) in enumerate(seen) if "ADD VALUE" in sql]
    assert len(labels) == 2
    after = seen[labels[-1] + 1 :]
    assert any("INSERT INTO bd_area" in sql for sql, _ in after)
    assert any("hub_public_owner" in sql for sql, _ in after)
    assert [(sql, timeout) for sql, timeout in after if timeout != "10s"] == []


def test_0039_reruns_after_failing_past_its_enum_labels(at_0038: Engine) -> None:
    """A run that committed the labels and then failed can simply run again.

    The labels commit on their own, before the rows, so a failure after
    them leaves the type widened at revision ``0038``; the next deploy
    must not then fail on "already exists".

    :param at_0038: The engine staged at ``0038``
    :return: None
    """
    with at_0038.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for kind in ("city_corporation", "metro_thana"):
            conn.execute(sa.text(f"ALTER TYPE bd_area_kind ADD VALUE '{kind}'"))

    url = at_0038.url.render_as_string(hide_password=False)
    command.upgrade(_alembic_config(url), "0039")

    assert _kinds(at_0038) == [*EARLIER_KINDS, "city_corporation", "metro_thana"]
    with at_0038.connect() as connection:
        thanas = connection.execute(
            sa.text("SELECT count(*) FROM bd_area WHERE kind = 'metro_thana'")
        ).scalar_one()
    assert thanas == 18
