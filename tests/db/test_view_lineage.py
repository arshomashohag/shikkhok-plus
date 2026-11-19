"""The view half of the money-type gate refuses what it must, and only that.

``test_every_money_column_is_numeric_12_2`` holds a view's money column to
its source rather than to its reported type (see ``view_lineage``). These
tests plant views, inside a transaction that is rolled back, over a
NUMERIC(12,2) column and over every way a view could carry a money value
that no NUMERIC(12,2) column holds -- a float column, an unconstrained
numeric column, arithmetic, a cast, a constant and an aggregate -- and
assert the checker accepts the first and refuses each of the others.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from tests.db.view_lineage import money_source_offence, parse_node_tree


@pytest.fixture
def planting(owner_session: Session) -> Iterator[Session]:
    """Yield a session whose DDL is rolled back afterwards.

    Two scratch tables stand in for a money column of the wrong type:
    ``probe_float`` holds a ``double precision`` fee and ``probe_loose``
    an unconstrained ``numeric`` one.

    :param owner_session: The table owner's session, which may create views
    :return: The session, inside the open transaction
    """
    owner_session.execute(sa.text("CREATE TABLE probe_float (fee double precision)"))
    owner_session.execute(sa.text("CREATE TABLE probe_loose (fee numeric)"))
    yield owner_session
    owner_session.rollback()


def _plant(session: Session, body: str) -> str | None:
    """Create ``probe_view`` from a body and check its ``fee`` column.

    :param session: The planting session
    :param body: The view's ``SELECT``
    :return: The checker's verdict on ``probe_view.fee``
    """
    session.execute(sa.text("DROP VIEW IF EXISTS probe_outer, probe_view"))
    session.execute(sa.text(f"CREATE VIEW probe_view AS {body}"))
    return money_source_offence(session, "probe_view", "fee")


@pytest.mark.parametrize(
    "body",
    [
        "SELECT b.default_fee AS fee FROM batch b",
        "SELECT CASE WHEN b.active THEN b.default_fee END AS fee FROM batch b",
        "SELECT CASE WHEN b.active THEN b.default_fee ELSE NULL END AS fee "
        "FROM batch b",
        "SELECT CASE WHEN b.active THEN b.default_fee "
        "WHEN e.id IS NOT NULL THEN e.fee_amount END AS fee "
        "FROM batch b JOIN enrollment e ON e.batch_id = b.id",
    ],
    ids=["plain", "case", "case-else-null", "two-tables"],
)
def test_a_pass_through_of_a_numeric_12_2_column_is_accepted(
    planting: Session, body: str
) -> None:
    """A view may show a NUMERIC(12,2) amount as it is, or only sometimes.

    :param planting: The planting session
    :param body: A view body passing a money column through
    :return: None
    """
    assert _plant(planting, body) is None


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("SELECT p.fee FROM probe_float p", "double precision"),
        ("SELECT p.fee FROM probe_loose p", "reads probe_loose.fee, a numeric"),
        ("SELECT b.default_fee * 1.5 AS fee FROM batch b", "computed"),
        ("SELECT b.default_fee / 3 AS fee FROM batch b", "computed"),
        ("SELECT b.default_fee::float8 AS fee FROM batch b", "computed"),
        ("SELECT b.default_fee::numeric AS fee FROM batch b", "computed"),
        ("SELECT 100.005::numeric AS fee FROM batch b", "computed"),
        ("SELECT sum(b.default_fee) AS fee FROM batch b", "computed"),
        (
            "SELECT CASE WHEN b.active THEN b.default_fee ELSE 0.001 END AS fee "
            "FROM batch b",
            "computed",
        ),
        (
            "SELECT CASE WHEN b.active THEN p.fee END AS fee "
            "FROM batch b CROSS JOIN probe_loose p",
            "a numeric",
        ),
        (
            "SELECT s.fee FROM (SELECT b.default_fee * 2 AS fee FROM batch b) s",
            "not a relation",
        ),
    ],
    ids=[
        "float-column",
        "loose-numeric-column",
        "multiplied",
        "divided",
        "cast-to-float",
        "cast-to-loose-numeric",
        "constant",
        "aggregate",
        "case-else-constant",
        "case-over-loose-column",
        "through-a-subquery",
    ],
)
def test_a_money_value_no_numeric_12_2_column_holds_is_refused(
    planting: Session, body: str, reason: str
) -> None:
    """Every other way of producing an amount is refused, with its reason.

    :param planting: The planting session
    :param body: A view body producing a money value some other way
    :param reason: Text the refusal must contain
    :return: None
    """
    offence = _plant(planting, body)

    assert offence is not None
    assert reason in offence


def test_a_view_over_a_view_is_followed_to_the_table(planting: Session) -> None:
    """A view reading another view's fee passes or fails with the inner one.

    :param planting: The planting session
    :return: None
    """
    _plant(planting, "SELECT b.default_fee AS fee FROM batch b")
    planting.execute(
        sa.text("CREATE VIEW probe_outer AS SELECT v.fee FROM probe_view v")
    )
    assert money_source_offence(planting, "probe_outer", "fee") is None

    _plant(planting, "SELECT p.fee FROM probe_loose p")
    planting.execute(
        sa.text("CREATE VIEW probe_outer AS SELECT v.fee FROM probe_view v")
    )
    offence = money_source_offence(planting, "probe_outer", "fee")
    assert offence is not None
    assert offence.startswith("probe_outer.fee <- probe_view.fee")


def test_the_real_public_fee_is_a_pass_through(restricted_session: Session) -> None:
    """``hub_public_batch.fee`` shows ``batch.default_fee`` only when chosen.

    :param restricted_session: A session as the application role
    :return: None
    """
    assert money_source_offence(restricted_session, "hub_public_batch", "fee") is None


def test_the_parser_reads_escapes_lists_and_multi_token_fields() -> None:
    """Escaped spaces, quoted names, empty values and a constant's bytes.

    :return: None
    """
    tree = parse_node_tree(
        '({QUERY :name a\\ b :cols ("x y" "z") :empty <> '
        ":bytes 4 [ 0 0 0 0 ] :sub {VAR :varno 1}})"
    )

    assert tree == [
        {
            "_node": "QUERY",
            "name": "a b",
            "cols": ["x y", "z"],
            "empty": None,
            "bytes": ["4", "[", "0", "0", "0", "0", "]"],
            "sub": {"_node": "VAR", "varno": "1"},
        }
    ]


def _plant_renamed(session: Session) -> None:
    """Plant ``probe_view`` whose money name now labels the computed column.

    ``ALTER VIEW ... RENAME COLUMN`` renames the view's attribute and leaves
    the stored rule's ``resname`` as it was, so after these two renames the
    rule still calls the pass-through ``fee`` and the arithmetic ``markup``,
    while the view's ``fee`` is the arithmetic and ``shown`` the
    pass-through.

    :param session: The planting session
    :return: None
    """
    _plant(
        session,
        "SELECT b.default_fee AS fee, b.default_fee * 1.5 AS markup FROM batch b",
    )
    session.execute(sa.text("ALTER VIEW probe_view RENAME COLUMN fee TO shown"))
    session.execute(sa.text("ALTER VIEW probe_view RENAME COLUMN markup TO fee"))


def test_a_renamed_column_is_checked_by_position_not_by_its_old_name(
    planting: Session,
) -> None:
    """The column called ``fee`` now is the one checked, not the stale label.

    :param planting: The planting session
    :return: None
    """
    _plant_renamed(planting)

    offence = money_source_offence(planting, "probe_view", "fee")
    assert offence is not None
    assert "computed" in offence
    assert money_source_offence(planting, "probe_view", "shown") is None


@pytest.mark.parametrize(
    ("inner", "verdict"),
    [("shown", None), ("fee", "computed")],
    ids=["renamed-pass-through", "renamed-computed"],
)
def test_a_view_over_a_renamed_view_follows_the_column_by_position(
    planting: Session, inner: str, verdict: str | None
) -> None:
    """The walk into an inner view follows its column number, not its name.

    :param planting: The planting session
    :param inner: The inner view's column the outer one shows as ``fee``
    :param verdict: None when accepted, else text the refusal must contain
    :return: None
    """
    _plant_renamed(planting)
    planting.execute(
        sa.text(
            f"CREATE VIEW probe_outer AS SELECT v.{inner} AS fee "  # noqa: S608  parametrised constants
            "FROM probe_view v"
        )
    )

    offence = money_source_offence(planting, "probe_outer", "fee")
    if verdict is None:
        assert offence is None
    else:
        assert offence is not None
        assert verdict in offence
