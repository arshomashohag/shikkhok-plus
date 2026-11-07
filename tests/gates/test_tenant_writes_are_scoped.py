"""Every lens-taking write in a tenant package reaches rows through a scope.

**The older gate parsed one file** [audit C-15]. ``tests/batches/
test_every_write_is_scoped.py`` sweeps ``app/batches/service.py`` -- the
module the first IDOR was found in -- while tenant isolation for every
other table rests on hand-written owner predicates across two dozen
modules, and row-level security covers only ``profile``. Staff, payroll,
expenses, rooms and the timetable arrived after that gate and were never
under it.

This sweeps every package that writes tenant data. A public function that
takes a lens and writes must either scope on the lens's id itself or reach
its rows through a helper whose NAME declares that it scopes -- owned,
writable, reachable, readable, or the centre resolver -- and each such
helper must itself mention the lens's id or call another scoping helper.
Like the older gate, this cannot prove a scope correct; it makes an
entirely unscoped tenant write impossible to add quietly.
"""

from __future__ import annotations

import ast
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

#: The packages whose services write rows a tenant owns.
TENANT_PACKAGES: tuple[str, ...] = (
    "batches",
    "centres",
    "expenses",
    "fees",
    "guardians",
    "marks",
    "notifications",
    "payroll",
    "staff",
    "students",
    "teaching",
)

#: A lens id used directly, or a call to a helper whose name says it scopes.
SCOPED: re.Pattern[str] = re.compile(
    r"lens\.\w*_id\b"
    r"|\b_?(owned|writable|reachable|readable)\w*\("
    r"|\bcentre_of\("
)

#: Writers that scope through a helper whose name does not say so, each
#: with the helper and the reason. Reviewed, not inferred.
SCOPED_BY_NAMED_HELPER: dict[str, str] = {
    "create_student": (
        "find_or_create_student sets owner_id from lens.owner_id, and "
        "seat_for reaches the batch through _owned_batch"
    ),
}

#: Calls that write through a session.
WRITE_METHODS = frozenset({"add", "add_all", "delete", "merge", "commit", "flush"})


def _functions() -> list[tuple[pathlib.Path, ast.FunctionDef]]:
    """Every module-level function in the tenant packages.

    :return: ``(path, function)`` pairs
    """
    found: list[tuple[pathlib.Path, ast.FunctionDef]] = []
    for package in TENANT_PACKAGES:
        for path in sorted((APP / package).glob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            found.extend(
                (path, node) for node in tree.body if isinstance(node, ast.FunctionDef)
            )
    return found


def _takes_lens(node: ast.FunctionDef) -> bool:
    """Report whether a function takes a ``lens`` parameter.

    :param node: The function
    :return: True if one of its parameters is named ``lens``
    """
    return "lens" in {arg.arg for arg in node.args.args + node.args.kwonlyargs}


def _writes(node: ast.FunctionDef) -> bool:
    """Report whether a function writes through a session.

    :param node: The function
    :return: True if it calls a write or commit method
    """
    return any(
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr in WRITE_METHODS
        for call in ast.walk(node)
    )


def _lens_writers() -> list[tuple[pathlib.Path, ast.FunctionDef]]:
    """Collect the public functions that take a lens and write.

    :return: ``(path, function)`` pairs
    """
    return [
        (path, node)
        for path, node in _functions()
        if not node.name.startswith("_") and _takes_lens(node) and _writes(node)
    ]


def test_every_lens_taking_writer_reaches_rows_through_a_scope() -> None:
    """No tenant write that skips the lens.

    :return: None
    """
    offenders = [
        f"{path.relative_to(APP.parent)}:{node.name}"
        for path, node in _lens_writers()
        if not SCOPED.search(ast.unparse(node))
        and node.name not in SCOPED_BY_NAMED_HELPER
    ]
    assert offenders == [], (
        "these functions take a lens and write without scoping on it or "
        f"calling a scoping helper: {offenders}"
    )


def test_every_scoping_helper_mentions_a_lens_or_another_scope() -> None:
    """A helper's name is a claim; its body must back it.

    :return: None
    """
    helper = re.compile(r"^_?(owned|writable|reachable|readable)\w*$|^centre_of$")
    offenders = [
        f"{path.relative_to(APP.parent)}:{node.name}"
        for path, node in _functions()
        if helper.match(node.name)
        and not re.search(
            r"lens\.\w*_id\b|\b_?(owned|writable|reachable|readable)\w*\(|"
            r"\bcentre_of\(|owner_id|account_id",
            "\n".join(ast.unparse(statement) for statement in node.body[1:]),
        )
    ]
    assert offenders == [], f"scoping helpers that scope on nothing: {offenders}"


def test_the_sweep_sees_the_writers_it_claims_to_check() -> None:
    """Guard against a walk that matches nothing and passes vacuously.

    :return: None
    """
    names = {node.name for _path, node in _lens_writers()}
    assert {"remove_enrollment", "add_adjustment", "update_staff", "approve"} <= names
    assert set(SCOPED_BY_NAMED_HELPER) <= names, "a stale exemption"
