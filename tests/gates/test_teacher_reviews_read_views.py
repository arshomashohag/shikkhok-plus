"""The teacher reads review content only through the two public views.

**Why a source gate** [T2-b, F6]. The threshold that hides a batch's
reviews below three published ones lives in ``hub_public_review`` and
``hub_public_rating``, not in Python (Review Focus 2). A teacher-side query
on the ``review`` base table would see a batch's first or second review --
the exact attribution the threshold exists to prevent -- and would pass
every behavioural test written against a batch already over it. So the
teacher module may not name the base table.

**One allowlisted exception** [T5-a]. Deleting one's own reply is never
gated by publication, so the delete must find the owner's reply while its
review is held or below the threshold, which the views do not show. That
ownership check, :data:`ALLOWED_HELPER`, is the one function exempted, and
only on terms checked here: its SQL aliases ``review`` and reads no column
of it but ``id`` and ``batch_id`` -- no rating, body, status, author or
time. Everywhere else in the module the forbidden patterns still fail.

It may read ``batch_listing`` (its owned batches), ``review_reply`` (its
own replies), ``owner_listing`` (for the suspension refusal), the ceiling
counter and the invalidation outbox through their helpers: none of those
carries what a guardian wrote.

The gate is checked both ways: it passes on the real module, and it fires
on each shape of violation, so a regex that stopped matching would fail
here rather than go quiet.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Final

import pytest

from app.db.models import Review

ROOT = Path(__file__).resolve().parents[2]
OWNER_MODULE = ROOT / "app" / "reviews" / "owner.py"

#: The one function allowed to name the ``review`` table [T5-a].
ALLOWED_HELPER: Final = "_reply_target_batch_owned"

#: The only columns of ``review`` the allowed function may read.
ALLOWED_COLUMNS: Final = frozenset({"id", "batch_id"})

#: SQL naming the base table; ``review_reply`` and ``hub_public_review``
#: do not match, because ``\b`` needs a non-word character on each side.
_BASE_TABLE: Final = (
    re.compile(r"\bFROM\s+review\b", re.IGNORECASE),
    re.compile(r"\bJOIN\s+review\b", re.IGNORECASE),
)

#: The base table with the alias the allowed function must give it.
_ALIASED: Final = re.compile(
    r"\b(?:FROM|JOIN)\s+review\b(?:\s+(?:AS\s+)?(\w+))?", re.IGNORECASE
)

#: SQL words that can follow a table name where an alias would be.
_NOT_ALIASES: Final = frozenset(
    {"where", "join", "left", "inner", "on", "for", "order", "group", "limit"}
)


def _model_violations(tree: ast.AST) -> list[str]:
    """List how source reaches the ``Review`` model.

    :param tree: The parsed source
    :return: One line per violation
    """
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found.extend(
                f"imports the Review model from {node.module}"
                for alias in node.names
                if alias.name == "Review"
            )
        elif isinstance(node, ast.Attribute) and node.attr == "Review":
            found.append("reaches the Review model by attribute")
    return found


def violations(source: str) -> list[str]:
    """List how source reaches the ``review`` base table.

    :param source: The source
    :return: One line per violation; empty when it is clean
    """
    found = [
        f"SQL names the review table: {match.group(0)!r}"
        for pattern in _BASE_TABLE
        for match in pattern.finditer(source)
    ]
    return found + _model_violations(ast.parse(source))


def split_allowed(source: str) -> tuple[str, list[str]]:
    """Separate the allowed function from the rest of a module.

    :param source: The module's source
    :return: The module with each top-level :data:`ALLOWED_HELPER` blanked
        out line for line, and that function's source, once per definition
    """
    lines = source.splitlines(keepends=True)
    helpers: list[str] = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name == ALLOWED_HELPER:
            start = node.lineno - 1
            if node.decorator_list:
                start = node.decorator_list[0].lineno - 1
            end = node.end_lineno or node.lineno
            helpers.append("".join(lines[start:end]))
            for index in range(start, end):
                lines[index] = "\n"
    return "".join(lines), helpers


def helper_violations(helper: str) -> list[str]:
    """List how the allowed function reads more of ``review`` than it may.

    Its SQL is every string literal in it but the docstring. ``review`` must
    be aliased, the alias may reach only :data:`ALLOWED_COLUMNS`, nothing is
    selected with ``*``, and no other column of ``review`` is named at all,
    qualified or not.

    :param helper: The function's source
    :return: One line per violation
    """
    tree = ast.parse(helper)
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    docstring = ast.get_docstring(function, clean=False)
    sql = "\n".join(
        node.value
        for node in ast.walk(function)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value != docstring
    )
    found = _model_violations(tree)
    if "*" in sql:
        found.append("selects with *")
    forbidden = {c.name for c in Review.__table__.columns} - ALLOWED_COLUMNS
    found.extend(
        f"names review column {column!r}"
        for column in sorted(forbidden)
        if re.search(rf"\b{column}\b", sql)
    )
    for match in _ALIASED.finditer(sql):
        alias = match.group(1)
        if alias is None or alias.lower() in _NOT_ALIASES:
            found.append("leaves review unaliased, so its columns are uncheckable")
            continue
        found.extend(
            f"reads review column {column!r} through {alias}"
            for column in re.findall(rf"\b{alias}\.(\w+)", sql)
            if column not in ALLOWED_COLUMNS
        )
    return found


def test_owner_module_never_reads_review_base_table() -> None:
    rest, helpers = split_allowed(OWNER_MODULE.read_text())

    assert violations(rest) == []
    assert len(helpers) == 1, f"exactly one {ALLOWED_HELPER} is allowed"
    assert helper_violations(helpers[0]) == []


def test_the_allowed_helper_reads_only_id_and_batch_id() -> None:
    """The exemption is real: the helper does name the table, narrowly."""
    _, helpers = split_allowed(OWNER_MODULE.read_text())
    (helper,) = helpers

    assert violations(helper) != []
    assert set(re.findall(r"\br\.(\w+)", helper)) <= ALLOWED_COLUMNS


def test_owner_module_reads_both_views() -> None:
    """The positive half: the content comes from the views."""
    source = OWNER_MODULE.read_text()

    assert "hub_public_review" in source
    assert "hub_public_rating" in source


@pytest.mark.parametrize(
    "source",
    [
        'SQL = "SELECT body FROM review WHERE batch_id = :b"',
        'SQL = "SELECT 1 FROM batch_listing bl\\n JOIN review r ON true"',
        'SQL = "select body from   review r"',
        "from app.db.models import BatchListing, Review",
        "import app.db.models as m\nX = m.Review",
    ],
)
def test_gate_fires_on_each_violation(source: str) -> None:
    assert violations(source) != []


@pytest.mark.parametrize(
    "source",
    [
        'SQL = "SELECT body FROM review_reply WHERE review_id = :r"',
        'SQL = "SELECT id FROM hub_public_review v JOIN hub_public_rating g ON 1=1"',
        "SQL = \"DELETE FROM hub_report WHERE target_kind = 'reply'\"",
        "from app.db.models import ReviewReply",
    ],
)
def test_gate_passes_what_is_allowed(source: str) -> None:
    assert violations(source) == []


_GOOD_HELPER: Final = '''
def HELPER(session, lens, review_id):
    """Say whether the review is the owner's; reads the review table."""
    return session.execute(
        sa.text(
            "SELECT r.id FROM review r JOIN batch_listing bl "
            "ON bl.batch_id = r.batch_id WHERE r.id = :i FOR SHARE OF r"
        )
    )
'''
_GOOD_HELPER_SOURCE: Final = _GOOD_HELPER.replace("HELPER", ALLOWED_HELPER, 1)


def test_the_allowlist_exempts_only_the_named_helper() -> None:
    other = 'def elsewhere():\n    return "SELECT r.id FROM review r"\n'
    rest, helpers = split_allowed(_GOOD_HELPER_SOURCE + "\n" + other)

    assert len(helpers) == 1
    assert helper_violations(helpers[0]) == []
    assert violations(rest) != []


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT r.body FROM review r WHERE r.id = :i",
        "SELECT r.* FROM review r WHERE r.id = :i",
        "SELECT r.id, rating FROM review r WHERE r.id = :i",
        "SELECT r.id FROM review r WHERE r.status = 'published'",
        "SELECT id FROM review WHERE id = :i",
        "SELECT x.id FROM batch_listing bl JOIN review AS x ON x.batch_id = :a "
        "AND x.author_account_id = :a",
    ],
)
def test_helper_gate_fires_on_a_wider_read(sql: str) -> None:
    helper = f'def {ALLOWED_HELPER}(session):\n    return session.execute("{sql}")\n'

    assert helper_violations(helper) != []
