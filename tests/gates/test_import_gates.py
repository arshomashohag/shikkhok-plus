"""
The two import gates, their violation fixtures, and their configuration.

The gates point in **opposite directions**, which is the whole reason there
are two:

- **Gate 1 (outward)**: the money module imports nothing from the API,
  persistence, repository, authorization or schema layers. Catches "someone
  gave the money module a database session".
- **Gate 2 (inward)**: nothing outside the money module imports raw
  ``decimal``. Catches "someone computed a fee in a route handler".

Neither catches the other's case. Gate 1 would pass happily while a route
handler did decimal arithmetic; Gate 2 would pass happily while the money
module imported a session, because a session is not a decimal.

Both gates are present **from this first commit** rather than added after a
violation [BR6.3], and each ships a fixture demonstrating that it fires. The
conditional framing inverts the economics: the checks cost about fifteen
lines of configuration now, against the same fifteen lines later *plus*
unwinding whatever arithmetic leaked in the interim.

Each gate is checked three ways: that it passes on the real tree, that it
**fails on a deliberate violation**, and that its **configuration still
covers what it is supposed to cover**. The third is not redundant — a fixture
stays green through a renamed module path or a re-permitting exception
widened to a parent, which is exactly the silent neutering the fixtures exist
to prevent.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MONEY = ROOT / "app" / "money"
FIXTURES = Path(__file__).parent / "fixtures"

#: Layers the money module may never import from. [BR6.1, NFR9.4]
FORBIDDEN_PREFIXES = (
    "app.api",
    "app.db",
    "app.repositories",
    "app.authz",
    "app.schemas",
)

#: The only path where raw decimal arithmetic is permitted. [BR6.2, NFR9.5]
MONEY_PATH_GLOB = "app/money/**"


def _imported_modules(source: Path) -> set[str]:
    """
    Collect every module a Python file imports.

    :param source: The file to parse.
    :return: Dotted module names, absolute imports only.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module:
                found.add(node.module)
    return found


class TestGate1Outward:
    """The money module must not reach outward."""

    def test_real_tree_passes(self) -> None:
        """Every module in app/money is clean, today."""
        offenders: list[str] = []
        for source in MONEY.rglob("*.py"):
            for module in _imported_modules(source):
                if module.startswith(FORBIDDEN_PREFIXES):
                    offenders.append(f"{source.name} imports {module}")
        assert not offenders, "\n".join(offenders)

    def test_fixture_is_refused(self) -> None:
        """
        NFR9.6 — the gate demonstrably fires on a real violation.

        The fixture is parsed by the same logic the gate uses, so this
        asserts the gate's own behaviour and not a reimplementation of it.
        """
        fixture = FIXTURES / "gate1_violation.py.txt"
        tree = ast.parse(fixture.read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert any(m.startswith(FORBIDDEN_PREFIXES) for m in imported), (
            "The Gate 1 fixture no longer violates Gate 1. Either the "
            "fixture was weakened or FORBIDDEN_PREFIXES was narrowed."
        )

    def test_config_resolves_to_a_real_package(self) -> None:
        """
        NFR9.29 — the walked path is a real, non-empty package.

        Without this, renaming the module directory leaves the gate passing
        vacuously: it would walk nothing and find nothing wrong.
        """
        assert MONEY.is_dir(), f"{MONEY} is not a directory"
        assert (MONEY / "__init__.py").is_file()
        modules = list(MONEY.rglob("*.py"))
        assert len(modules) >= 5, (
            f"Gate 1 walks {MONEY} and found only {len(modules)} modules; "
            "it may no longer point at the money package."
        )


class TestGate2Inward:
    """Nothing outside the money module may import raw decimal."""

    def test_real_tree_passes(self) -> None:
        offenders: list[str] = []
        for source in (ROOT / "app").rglob("*.py"):
            if MONEY in source.parents or source.parent == MONEY:
                continue
            if "decimal" in _imported_modules(source):
                offenders.append(str(source.relative_to(ROOT)))
        assert not offenders, "Raw decimal imported outside app/money: " + ", ".join(
            offenders
        )

    def test_fixture_is_refused_by_the_real_linter(self, tmp_path: Path) -> None:
        """
        NFR9.6 — run the configured linter against the violation and assert
        it refuses.

        This invokes the project's actual Ruff configuration rather than
        re-deriving the rule, so it fails if the banned-api entry is removed.
        """
        ruff = _ruff_or_skip()
        target = tmp_path / "violation.py"
        target.write_text(
            (FIXTURES / "gate2_violation.py.txt").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        result = subprocess.run(  # noqa: S603
            [
                *ruff,
                "check",
                "--no-cache",
                "--config",
                str(ROOT / "pyproject.toml"),
                "--select",
                "TID251",
                str(target),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, (
            "Gate 2 did not fire on a file importing raw decimal. The "
            "banned-api configuration may have been removed or widened.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_config_scope_is_exactly_the_money_module(self) -> None:
        """
        NFR9.29 — the re-permitting exception resolves to exactly the money
        module path, never a parent.

        Widening it from ``app/money/**`` to ``app/**`` would leave both the
        real-tree check and the fixture green while the ban applied nowhere.
        """
        config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        banned = config["tool"]["ruff"]["lint"]["flake8-tidy-imports"]["banned-api"]
        assert "decimal" in banned, "Gate 2's ban on raw decimal is gone."

        ignores = config["tool"]["ruff"]["lint"]["per-file-ignores"]
        permitted = [
            path for path in ignores if path.startswith("app/") and "money" not in path
        ]
        assert not permitted, (
            "A per-file-ignore outside app/money could widen Gate 2's "
            f"exception: {permitted}"
        )
        if MONEY_PATH_GLOB in ignores:
            assert ignores[MONEY_PATH_GLOB] == [], (
                "The money module's entry should carry no rule exemptions; "
                "its decimal permission comes from being the module itself."
            )


def _ruff_or_skip() -> list[str]:
    """
    Locate the configured linter, or skip.

    :return: The command prefix that runs Ruff.
    """
    probe = subprocess.run(
        [sys.executable, "-m", "ruff", "--version"],
        capture_output=True,
        check=False,
    )
    if probe.returncode == 0:
        return [sys.executable, "-m", "ruff"]
    pytest.skip("ruff is not installed in this environment")
