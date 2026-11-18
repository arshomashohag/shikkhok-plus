"""The teacher reads review content only through the two public views.

**Why a source gate** [T2-b, F6]. The threshold that hides a batch's
reviews below three published ones lives in ``hub_public_review`` and
``hub_public_rating``, not in Python (Review Focus 2). A teacher-side query
on the ``review`` base table would see a batch's first or second review --
the exact attribution the threshold exists to prevent -- and would pass
every behavioural test written against a batch already over it. So the
teacher module may not name the base table at all.

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

ROOT = Path(__file__).resolve().parents[2]
OWNER_MODULE = ROOT / "app" / "reviews" / "owner.py"

#: SQL naming the base table; ``review_reply`` and ``hub_public_review``
#: do not match, because ``\b`` needs a non-word character on each side.
_BASE_TABLE: Final = (
    re.compile(r"\bFROM\s+review\b", re.IGNORECASE),
    re.compile(r"\bJOIN\s+review\b", re.IGNORECASE),
)


def violations(source: str) -> list[str]:
    """List how a teacher-side module reaches the ``review`` base table.

    :param source: The module's source
    :return: One line per violation; empty when the module is clean
    """
    found = [
        f"SQL names the review table: {match.group(0)!r}"
        for pattern in _BASE_TABLE
        for match in pattern.finditer(source)
    ]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            found.extend(
                f"imports the Review model from {node.module}"
                for alias in node.names
                if alias.name == "Review"
            )
        elif isinstance(node, ast.Attribute) and node.attr == "Review":
            found.append("reaches the Review model by attribute")
    return found


def test_owner_module_never_reads_review_base_table() -> None:
    assert violations(OWNER_MODULE.read_text()) == []


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
