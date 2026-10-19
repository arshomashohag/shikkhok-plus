"""
The named-test manifest check.

100% branch coverage measures whether branches *executed*, never whether the
right tests *exist*. A missing named test whose branches another test already
covers is completely invisible to it — the multi-period carry test is the
worked example, since the single-carry test exercises all the same branches.

So this asserts every manifest entry resolves to a test that exists and runs.
What it cannot do is verify that a test asserts anything worthwhile; that is
why each entry states its acceptance criterion, which makes a
trivially-asserting test visible to a reader as a mismatch.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).parent / "named_tests.toml"


def _manifest() -> list[dict[str, str]]:
    """
    Read the manifest.

    :return: Every declared entry.
    """
    return tomllib.loads(MANIFEST.read_text(encoding="utf-8"))["test"]


def _defined_test_names(source: Path) -> set[str]:
    """
    Collect every test function defined in a file, including methods.

    :param source: The test file to parse.
    :return: Function names beginning with ``test_``.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }


ENTRIES = _manifest()


def test_manifest_is_not_empty() -> None:
    """A manifest nobody populated would pass every other check here."""
    assert len(ENTRIES) >= 25, (
        f"The manifest declares only {len(ENTRIES)} tests, which is fewer "
        "than this Unit's named obligations."
    )


@pytest.mark.parametrize("entry", ENTRIES, ids=[e["id"] for e in ENTRIES])
def test_manifest_entry_resolves(entry: dict[str, str]) -> None:
    """
    Each entry names a test that exists in the file it claims.

    :param entry: One manifest row.
    """
    source = ROOT / entry["file"]
    assert source.is_file(), (
        f"{entry['id']} claims {entry['file']}, which does not exist."
    )
    defined = _defined_test_names(source)
    assert entry["id"] in defined, (
        f"{entry['id']} is declared in the manifest but is not defined in "
        f"{entry['file']}. Either the test was deleted or renamed, or the "
        "manifest was not updated with it."
    )


@pytest.mark.parametrize("entry", ENTRIES, ids=[e["id"] for e in ENTRIES])
def test_manifest_entry_states_a_criterion(entry: dict[str, str]) -> None:
    """
    Each entry states what the test must assert, not merely that it exists.

    A criterion restating the test's own name carries no information, so a
    minimum length is enforced: "covers carry-forward" is not a criterion,
    "a three-period carry reads 3000, not 4000" is.

    :param entry: One manifest row.
    """
    criterion = entry.get("criterion", "")
    assert len(criterion) >= 40, (
        f"{entry['id']} has a criterion of {len(criterion)} characters. "
        "State what the test must assert, not that it exists."
    )
    assert entry.get("rule"), f"{entry['id']} names no rule it enforces."
