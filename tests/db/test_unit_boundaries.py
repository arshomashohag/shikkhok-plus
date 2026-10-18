"""BR6.1 and BR6.3, asserted over this Unit's own source.

Two boundaries that no runtime test can see, because the violation of each
one *works*:

* An ``INSERT INTO owner`` inside U3 would make the demo pass. It is the
  ownership transfer BR6.1 forbids, arriving disguised as a fixture.
* An application module importing the seed script would turn a throwaway
  verification aid into a runtime dependency, and B5's obligation to
  delete it would then break the app.

Both are therefore checked statically, over the text and the AST.
"""

from __future__ import annotations

import ast
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

#: The two tables this Unit creates and must never write [BR6.1].
SHELL_TABLES = ("owner", "enrollment")

#: Write verbs, as they would appear in raw SQL against a shell table.
WRITE_PATTERN = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(owner|enrollment)\b",
    re.IGNORECASE,
)


def _application_sources() -> list[pathlib.Path]:
    """Collect every application module except the seed script itself.

    :return: The paths to check
    """
    seed = APP / "db" / "seed_skeleton.py"
    return [path for path in APP.rglob("*.py") if path != seed]


def test_no_application_module_writes_a_shell_table() -> None:
    offenders: list[str] = []
    for path in _application_sources():
        for match in WRITE_PATTERN.finditer(path.read_text()):
            offenders.append(f"{path.name}: {match.group(0)}")
    assert offenders == [], (
        "U3 creates owner and enrollment EMPTY and never writes them "
        f"[BR6.1]. Found: {offenders}"
    )


def test_no_application_module_imports_the_seed_script() -> None:
    offenders: list[str] = []
    for path in _application_sources():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any("seed_skeleton" in name for name in names):
                offenders.append(path.name)
    assert offenders == [], (
        "The seed script is a manual verification precondition, never "
        f"imported by application code [BR6.3]. Found: {offenders}"
    )


def test_the_seed_script_is_guarded_by_a_main_block() -> None:
    # A module that does its work on import is importable-by-accident,
    # which is exactly what BR6.3 is trying to prevent.
    source = (APP / "db" / "seed_skeleton.py").read_text()
    assert '__name__ == "__main__"' in source


def test_the_orm_models_declare_the_shell_tables() -> None:
    # Empty is not absent: the shells must be declared, or lens resolution
    # queries a table that does not exist and fails.
    from app.db.base import Base

    for table in SHELL_TABLES:
        assert table in Base.metadata.tables
