"""No table the manifest retains is reachable from ``account`` by cascade.

**This is the strongest thing D6 builds**, and it is a statement about
the live schema rather than about three columns. ``0007`` fixes three
``ON DELETE CASCADE`` edges; a test asserting *those three* is a test of
that migration and passes forever afterwards while a fourth
contradicting constraint arrives in some later unit. The property worth
asserting is **"no contradiction exists"**.

The rule, which falls out of the manifest rather than being asserted
over it [BR1.2]:

    A CASCADE reaching a table whose disposition is RETAIN_WITH_BASIS is
    wrong, because the manifest already says that row must survive an
    account deletion -- and a cascade deletes it.

**Reachability is transitive and the first draft of this was not.**
Until ``0010`` several ``RETAIN_WITH_BASIS`` tables were reachable from
``account`` only through ``owner -> batch``, and BR1.6's refusal of a
teacher's deletion was what made that chain unreachable. ``0010``
amended BR1.6 -- a teacher may delete and their batches stay -- and set
``owner.account_id`` to ``SET NULL``, so the property asserted here is
now the unqualified one: no retained table is reachable at all.

**The query carries the path**, because a failure saying only "a
contradiction exists" sends the next reader to ``models.py`` to work out
which of fifteen foreign keys it means.

Why ``pg_constraint`` and never ``information_schema`` -- see
:func:`_cascade_reachable`. That choice is load-bearing and switching it
looks like a simplification.
"""

from __future__ import annotations

from typing import Final

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.governance.dispositions import DISPOSITIONS, Disposition
from tests.db.migration_support import stage_at

#: The root every deletion starts from.
ROOT_TABLE: Final = "account"

#: A recursive walk over the cascade graph, carrying the path.
#:
#: **``pg_constraint``, never ``information_schema``** [DESIGN-8], and
#: the difference is not stylistic. Measured against a real PostgreSQL
#: 16 on 2026-10-25: a table the restricted role holds no grant on is
#: **invisible** in ``information_schema.tables`` and
#: ``information_schema.referential_constraints``, and **visible** in
#: ``pg_constraint`` -- because the system catalog is not
#: permission-filtered by table grant while the information-schema views
#: are.
#:
#: This project has already met that failure once: the money-column gate
#: silently stopped covering ``batch.default_fee`` until a grant was
#: added, and the governance suite's comment concludes that a control
#: which quietly narrows is worse than one that fails. Switching this
#: query to ``information_schema.referential_constraints`` would
#: reintroduce exactly that narrowing, it would look like a
#: simplification, and **the test would keep passing**.
#:
#: ``confdeltype = 'c'`` is CASCADE; ``'n'`` is SET NULL. The cycle
#: guard on ``path`` is required rather than defensive: a self-referencing
#: cascade would otherwise recurse without end.
_REACHABLE: Final = sa.text(
    """
    WITH RECURSIVE reached(table_name, path, depth) AS (
        SELECT
            c.conrelid::regclass::text,
            ARRAY[:root, c.conrelid::regclass::text],
            1
        FROM pg_constraint c
        WHERE c.contype = 'f'
          AND c.confdeltype = 'c'
          AND c.confrelid = (:root)::regclass

        UNION ALL

        SELECT
            c.conrelid::regclass::text,
            r.path || c.conrelid::regclass::text,
            r.depth + 1
        FROM pg_constraint c
        JOIN reached r ON c.confrelid = (r.table_name)::regclass
        WHERE c.contype = 'f'
          AND c.confdeltype = 'c'
          AND NOT (c.conrelid::regclass::text = ANY(r.path))
    )
    SELECT table_name, path, depth FROM reached
    """
)


def _cascade_reachable(session: Session) -> dict[str, list[str]]:
    """Every table reachable from ``account`` by ``ON DELETE CASCADE``.

    :param session: The session to read the catalog through
    :return: Each reachable table mapped to one path that reaches it
    """
    rows = session.execute(_REACHABLE, {"root": ROOT_TABLE}).all()

    shortest: dict[str, list[str]] = {}
    for table, path, _depth in rows:
        existing = shortest.get(table)
        if existing is None or len(path) < len(existing):
            shortest[table] = list(path)
    return shortest


def _retained_reachable(reachable: dict[str, list[str]]) -> dict[str, list[str]]:
    """Every reachable table the manifest says must survive a deletion.

    :param reachable: Table-to-path mapping from the catalog walk
    :return: The retained subset, each with the path that reaches it
    """
    return {
        table: path
        for table, path in reachable.items()
        if (governance := DISPOSITIONS.get(table)) is not None
        and governance.disposition is Disposition.RETAIN_WITH_BASIS
    }


def _contradictions(reachable: dict[str, list[str]]) -> list[str]:
    """Describe every retained table a deletion would cascade into.

    **No qualifier.** Before ``0010`` this skipped chains through
    ``owner``, because BR1.6 refused any deletion that would reach them.
    That refusal is gone, so every reached retained table is a real
    contradiction.

    :param reachable: Table-to-path mapping from the catalog walk
    :return: One human-readable line per contradiction, path included
    """
    return [
        f"{' -> '.join(path)}  ({table})"
        for table, path in sorted(_retained_reachable(reachable).items())
    ]


def test_no_cascade_reaches_a_retained_table(restricted_session: Session) -> None:
    """A cascade to a ``RETAIN_WITH_BASIS`` table is a contradiction.

    :param restricted_session: The non-superuser session
    :return: None
    """
    contradictions = _contradictions(_cascade_reachable(restricted_session))

    assert contradictions == [], (
        "deleting an account would CASCADE into tables the governance "
        "manifest says must survive that deletion [BR1.2]. Each line is "
        "the chain that reaches it:\n  " + "\n  ".join(contradictions)
    )


# ---------------------------------------------------------------------------
# THE VACUITY GUARD.
#
# **A test that queries pg_constraint and finds nothing passes.** A typo
# in a regclass cast, a join that drops rows, a recursion that never
# recurses -- each returns an empty set, and `contradictions == []` is
# satisfied. It would have passed before 0007 too, when three real
# contradictions existed.
#
# So the walk's own REACH is asserted, in the manner
# `test_the_money_assertion_is_no_longer_vacuous` already establishes in
# this repository.
# ---------------------------------------------------------------------------


def test_the_walk_reaches_a_known_table_at_depth_one(
    restricted_session: Session,
) -> None:
    """``profile`` cascades directly from ``account``.

    :param restricted_session: The non-superuser session
    :return: None
    """
    reachable = _cascade_reachable(restricted_session)

    assert reachable.get("profile") == [ROOT_TABLE, "profile"], (
        "the walk does not reach `profile` at depth one, so it is not "
        f"walking the cascade graph at all. Reached: {sorted(reachable)}"
    )


def test_before_0010_the_walk_reached_retained_tables_through_owner(
    postgres_url: str,
) -> None:
    """Transitive reach, exercised on the schema that still had it.

    At ``0009`` ``attendance`` hangs off ``enrollment``, off ``batch``,
    off ``owner``, and is reachable only through that chain -- exactly
    the shape a non-recursive query reports as clean. Asserting it there
    proves the walk recurses, and that ``0010`` is what cleared it.

    :param postgres_url: The container's owner URL
    :return: None
    """
    with stage_at(postgres_url, "0009") as staged:
        with staged.connect() as connection:
            reachable = _cascade_reachable(Session(bind=connection))

    path = reachable.get("attendance")
    assert path is not None, (
        "the walk does not reach `attendance` at 0009, so it is not "
        f"recursing. Reached: {sorted(reachable)}"
    )
    assert path[:3] == [ROOT_TABLE, "owner", "batch"]
    assert _contradictions(reachable) != [], (
        "at 0009 a teacher's deletion cascaded into retained tables; the "
        "walk reports none, so the gate is vacuous."
    )


def test_after_0010_the_owner_chain_no_longer_cascades(
    restricted_session: Session,
) -> None:
    """``owner`` and everything beneath it is out of the walk at head.

    :param restricted_session: The non-superuser session
    :return: None
    """
    reachable = _cascade_reachable(restricted_session)

    assert "owner" not in reachable
    assert "attendance" not in reachable


def test_the_walk_is_bounded_by_the_manifest(
    restricted_session: Session,
) -> None:
    """Every table the walk names is a table the manifest declares.

    A reached name that is not in ``DISPOSITIONS`` would be silently
    skipped by :func:`_contradictions`, so the skip is asserted never to
    happen rather than left as a quiet pass.

    :param restricted_session: The non-superuser session
    :return: None
    """
    unknown = set(_cascade_reachable(restricted_session)) - set(DISPOSITIONS)

    assert unknown == set(), (
        f"the cascade walk reached undeclared tables {sorted(unknown)}, "
        "which `_contradictions` skips silently -- so a cascade into one "
        "of them would never be reported."
    )


# ---------------------------------------------------------------------------
# BOTH STATES EXERCISED.
#
# **A test only ever seen passing is a test never seen working.** The
# pre-0007 schema carried three real contradictions, so the assertion is
# run against it and required to FAIL. Staged in a throwaway database at
# 0006 rather than mutated in place, so the session fixture's schema is
# untouched.
# ---------------------------------------------------------------------------

#: What the walk must report at ``0006``, from the enumeration in
#: `entities.md` § 2: the three CASCADE references whose tables are
#: RETAIN_WITH_BASIS.
PRE_0007_DIRECT_CONTRADICTIONS: Final = frozenset(
    {"enrollment", "payment_claim", "queued_submission"}
)


def test_the_assertion_fails_against_the_schema_before_0007(
    postgres_url: str,
) -> None:
    """At ``0006`` the three contradicting edges are found and named.

    :param postgres_url: The container's owner URL
    :return: None
    """
    with stage_at(postgres_url, "0006") as staged:
        with staged.connect() as connection:
            session = Session(bind=connection)
            reachable = _cascade_reachable(session)
            contradictions = _contradictions(reachable)

    assert contradictions != [], (
        "the assertion passed against the schema it was written to "
        "reject, which means the query finds nothing and the gate is "
        "vacuous at head as well."
    )

    direct = {
        table
        for table, path in reachable.items()
        if len(path) == 2 and table in PRE_0007_DIRECT_CONTRADICTIONS
    }
    assert direct == set(PRE_0007_DIRECT_CONTRADICTIONS), (
        "at 0006 these three tables cascade DIRECTLY from account and "
        f"the walk found {sorted(direct)} instead of "
        f"{sorted(PRE_0007_DIRECT_CONTRADICTIONS)}."
    )


def test_the_three_edges_are_set_null_after_0007(
    restricted_session: Session,
) -> None:
    """The three edges ``0007`` altered no longer cascade.

    Named per edge rather than left to the aggregate, because the
    aggregate assertion is satisfied by a schema where one edge was
    fixed and another was dropped entirely.

    :param restricted_session: The non-superuser session
    :return: None
    """
    rows = restricted_session.execute(
        sa.text(
            "SELECT c.conrelid::regclass::text, a.attname, c.confdeltype "
            "FROM pg_constraint c "
            "JOIN unnest(c.conkey) AS k(attnum) ON true "
            "JOIN pg_attribute a "
            "  ON a.attrelid = c.conrelid AND a.attnum = k.attnum "
            "WHERE c.contype = 'f' "
            "  AND c.confrelid = 'account'::regclass "
            "  AND c.conrelid::regclass::text = ANY(:tables)"
        ),
        {"tables": sorted(PRE_0007_DIRECT_CONTRADICTIONS)},
    ).all()

    altered = {
        (table, column): deltype
        for table, column, deltype in rows
        if column in ("student_account_id", "submitted_by_account_id")
    }

    expected = {
        ("enrollment", "student_account_id"),
        ("payment_claim", "submitted_by_account_id"),
        ("queued_submission", "submitted_by_account_id"),
    }
    assert set(altered) == expected, (
        f"expected the three altered references to exist; found {sorted(altered)}"
    )
    cascading = sorted(key for key, deltype in altered.items() if deltype == "c")
    assert cascading == [], f"these still CASCADE after 0007: {cascading}"


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("payment_claim", "submitted_by_account_id"),
        ("queued_submission", "submitted_by_account_id"),
    ],
)
def test_the_two_not_null_columns_admit_a_null(
    restricted_session: Session, table: str, column: str
) -> None:
    """``SET NULL`` is only acceptable against a nullable column.

    Asserted separately from the ``confdeltype`` check because the two
    halves fail independently, and a migration that made the columns
    nullable while deferring the ``ondelete`` flip leaves the cascade in
    place while the schema *looks* prepared.

    :param restricted_session: The non-superuser session
    :param table: The table to inspect
    :param column: The column to inspect
    :return: None
    """
    not_null = restricted_session.execute(
        sa.text(
            "SELECT a.attnotnull FROM pg_attribute a "
            "WHERE a.attrelid = (:table)::regclass AND a.attname = :column"
        ),
        {"table": table, "column": column},
    ).scalar_one()

    assert not_null is False, (
        f"{table}.{column} is still NOT NULL, so PostgreSQL cannot apply "
        "the SET NULL this migration configured."
    )


def test_the_catalog_choice_is_not_narrowed_by_the_role(
    restricted_session: Session, owner_engine: Engine
) -> None:
    """``pg_constraint`` sees a table the restricted role cannot read.

    **This is the measurement the module docstring cites, run rather
    than quoted.** A child table with ``ON DELETE CASCADE`` is created
    and deliberately left ungranted. The restricted role cannot see it
    in ``information_schema``; it must still see its cascade here, or a
    retained table whose grant was forgotten would stop being checked.

    :param restricted_session: The non-superuser session
    :param owner_engine: The owner engine, used only to arrange
    :return: None
    """
    with owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE ungranted_probe ("
                "  id uuid PRIMARY KEY,"
                "  account_id uuid REFERENCES account(id) ON DELETE CASCADE"
                ")"
            )
        )
    try:
        in_catalog = restricted_session.execute(
            sa.text(
                "SELECT count(*) FROM pg_constraint "
                "WHERE contype = 'f' AND confdeltype = 'c' "
                "AND conrelid = 'ungranted_probe'::regclass"
            )
        ).scalar_one()
        in_information_schema = restricted_session.execute(
            sa.text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'ungranted_probe'"
            )
        ).scalar_one()
        restricted_session.rollback()

        assert in_catalog == 1, (
            "pg_constraint did not report an ungranted table's cascade, "
            "which is the whole reason this gate reads the system catalog."
        )
        assert in_information_schema == 0, (
            "information_schema reported the ungranted table, so the "
            "measured difference this gate depends on no longer holds -- "
            "re-measure before relying on either catalog."
        )
    finally:
        with owner_engine.begin() as connection:
            connection.execute(sa.text("DROP TABLE IF EXISTS ungranted_probe"))
