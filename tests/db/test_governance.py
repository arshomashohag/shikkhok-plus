"""Every live table carries a disposition and a retention class.

**Iteration over the migrated schema, not enumeration.** A per-table test
covers the tables someone remembered; walking the schema covers the table
added three Units later, after everyone stopped thinking about it.

Step 28 also lives here: the money column assertion **B1 authored and
could not run**, because B1 had no schema. B3 is the first Bolt with one.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.contract.money_names import NON_MONEY_COLUMNS, is_money_name
from app.governance.dispositions import DISPOSITIONS, RETENTION

#: Tables the framework owns, which carry no user data.
INFRASTRUCTURE_TABLES = frozenset({"alembic_version"})


def _live_tables(session: Session) -> set[str]:
    """Read every table the migration actually created.

    :param session: The session to read through
    :return: The table names, excluding framework tables
    """
    rows = session.execute(
        sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    return {row[0] for row in rows} - INFRASTRUCTURE_TABLES


def test_every_live_table_has_a_disposition(restricted_session: Session) -> None:
    undeclared = _live_tables(restricted_session) - set(DISPOSITIONS)
    assert undeclared == set(), (
        f"these tables exist but no deletion disposition was decided: "
        f"{sorted(undeclared)}. The privacy policy is generated from "
        "these, so an undeclared table means a policy that does not "
        "describe the implementation."
    )


def test_every_live_table_has_a_retention_class(
    restricted_session: Session,
) -> None:
    undeclared = _live_tables(restricted_session) - set(RETENTION)
    assert undeclared == set(), (
        f"no retention class for: {sorted(undeclared)}. An unbounded "
        "table holding a phone number is both a storage cost and a "
        "growing disclosure surface."
    )


def test_no_disposition_names_a_table_that_does_not_exist(
    restricted_session: Session,
) -> None:
    # The other direction: a stale entry describes a table nobody has,
    # which makes the generated policy claim something untrue.
    phantom = set(DISPOSITIONS) - _live_tables(restricted_session)
    assert phantom == set(), f"dispositions for nonexistent tables: {phantom}"


def test_every_disposition_states_a_basis() -> None:
    # The basis IS the policy text. An empty one produces a privacy
    # policy that says a table is retained and not why.
    missing = [
        table
        for table, governance in DISPOSITIONS.items()
        if len(governance.basis.strip()) < 20
    ]
    assert missing == []


# ---------------------------------------------------------------------------
# STEP 28 — the money column assertion B1 could not run. [NFR9.32]
#
# B1 authored this and had no schema to run it against. It iterates the
# MIGRATED schema rather than the ORM metadata, so it holds REGARDLESS
# of how a column was created -- including by hand-written SQL in a
# migration, which is exactly the path that would bypass the SQLAlchemy
# TypeDecorator the money boundary relies on.
# ---------------------------------------------------------------------------

#: The only type a money column may have. NUMERIC(12,2), never float,
#: never double precision, never an unconstrained numeric.
REQUIRED_MONEY_TYPE = "numeric"
REQUIRED_PRECISION = 12
REQUIRED_SCALE = 2


def _money_columns(session: Session) -> list[sa.Row[tuple[str, str, int, int]]]:
    """Find every column whose name implies it carries money.

    :param session: The session to read through
    :return: The matching rows
    """
    rows = session.execute(
        sa.text(
            "SELECT table_name, column_name, data_type, "
            "numeric_precision, numeric_scale "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public'"
        )
    ).all()
    return [
        row
        for row in rows
        if is_money_name(row[1]) and (row[0], row[1]) not in NON_MONEY_COLUMNS
    ]


def test_no_money_column_is_a_floating_point_type(
    restricted_session: Session,
) -> None:
    # The project-level NEVER rule, asserted against the real schema
    # rather than against the models that are supposed to produce it.
    offenders = [
        (row[0], row[1], row[2])
        for row in _money_columns(restricted_session)
        if row[2] in {"real", "double precision"}
    ]
    assert offenders == [], f"floating-point money columns: {offenders}"


def test_every_money_column_is_numeric_12_2(
    restricted_session: Session,
) -> None:
    offenders = [
        (row[0], row[1], row[2], row[3], row[4])
        for row in _money_columns(restricted_session)
        if row[2] != REQUIRED_MONEY_TYPE
        or row[3] != REQUIRED_PRECISION
        or row[4] != REQUIRED_SCALE
    ]
    assert offenders == [], (
        f"money columns not NUMERIC(12,2): {offenders}. An unconstrained "
        "numeric silently accepts more precision than the ledger models."
    )


def test_the_money_assertion_is_no_longer_vacuous(
    restricted_session: Session,
) -> None:
    # U3 asserted there were NO money columns, and recorded that the
    # type assertion above was therefore vacuously true. U4 brings the
    # first real ones, so the honest marker is the inverse: the gate
    # now has something to check, and a regression that removed every
    # money column would make it silently vacuous again.
    found = {(row[0], row[1]) for row in _money_columns(restricted_session)}

    assert ("batch", "default_fee") in found
    assert ("enrollment", "fee_amount") in found


# ---------------------------------------------------------------------------
# The grant gate. A table created by a later migration inherits NOTHING
# from 0001's `GRANT ... ON ALL TABLES`, which covered only the tables
# that existed when it ran.
#
# This is not merely "the app cannot read it". An ungranted table is
# invisible to the restricted role in `information_schema`, so every
# gate above silently stops covering it -- the money assertion reported
# `enrollment.fee_amount` and skipped `batch.default_fee` entirely until
# the grant was added. A control that quietly narrows is worse than one
# that fails.
# ---------------------------------------------------------------------------


def test_the_restricted_role_can_read_every_live_table(
    restricted_session: Session,
) -> None:
    unreadable: list[tuple[str, str]] = []
    for table in sorted(_live_tables(restricted_session)):
        try:
            restricted_session.execute(
                sa.text(f"SELECT 1 FROM {table} LIMIT 1")  # noqa: S608  fixed literal
            ).all()
        except sa.exc.ProgrammingError as error:
            restricted_session.rollback()
            unreadable.append((table, type(error).__name__))

    assert unreadable == [], (
        f"the application role cannot read: {unreadable}. A migration "
        "that creates a table must grant it explicitly; 0001's "
        "GRANT ON ALL TABLES covered only what existed then."
    )


def test_every_owned_table_is_visible_to_the_restricted_role(
    restricted_session: Session, owner_session: Session
) -> None:
    # The stronger half: compare what the OWNER sees against what the
    # restricted role sees. A table missing from the restricted view is
    # one every gate above has stopped checking without saying so.
    owner_tables = {
        row[0]
        for row in owner_session.execute(
            sa.text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename <> 'alembic_version'"
            )
        )
    }
    invisible = owner_tables - _live_tables(restricted_session)

    assert invisible == set(), (
        f"invisible to the application role, and therefore to every "
        f"governance gate in this file: {sorted(invisible)}"
    )
