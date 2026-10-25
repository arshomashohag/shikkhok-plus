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
import re
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

    **Two languages, because one named obligation lives in Kotlin.**
    D2's Back-after-child-switch test [NFR23.6] is the only mechanism
    that can observe its rule -- no server-side control can, since both
    requests are legitimately authorized and neither response is
    anomalous -- so it has to be nameable here. A manifest that could
    only hold Python entries would have quietly dropped the one
    obligation most at risk of becoming a review note.

    :param source: The test file to parse.
    :return: Test names defined in the file.
    """
    if source.suffix == ".kt":
        return _kotlin_test_names(source)

    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }


def _kotlin_test_names(source: Path) -> set[str]:
    """
    Collect the backtick-quoted names of a Kotlin test file's tests.

    A regex rather than a Kotlin parser, and the scope is what makes
    that safe: it matches ``fun `...`()`` on the line after an
    ``@Test`` annotation, which is the only shape this project's
    Kotlin tests use. A test whose annotation and signature were
    separated by a blank line would be missed -- and a MISS fails the
    manifest check loudly rather than passing it, which is the right
    direction for a guard to be wrong in.

    :param source: The Kotlin test file to read.
    :return: The declared test names, without their backticks.
    """
    text = source.read_text(encoding="utf-8")
    return set(re.findall(r"@Test\s+fun\s+`([^`]+)`", text))


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
