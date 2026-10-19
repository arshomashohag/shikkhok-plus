"""Every write in this module is scoped by the lens it was handed.

**Review found two functions that took no lens at all**, so
``session.get(Enrollment, id)`` loaded any row in the database and any
authenticated teacher could delete or deactivate another teacher's seat
by guessing a UUID. Both looked correct, because the route above them
resolved a lens.

Two is the number I found by reading. This test is what answers "were
there three?" mechanically, now and for every Unit that extends this
module — the project's third recurring defect class is fixing where the
reviewer pointed and leaving the identical error standing nearby.

The check is structural rather than semantic: a function that writes
must reach its rows through one of the owned-row helpers, or scope on
``lens.owner_id`` itself. That cannot prove the scope is *correct*, but
it makes an entirely unscoped write impossible to add quietly.
"""

from __future__ import annotations

import ast
import pathlib

SERVICE = pathlib.Path(__file__).resolve().parents[2] / "app" / "batches" / "service.py"

#: Helpers that establish ownership before returning a row. A function
#: reaching its rows through one of these is scoped by construction.
OWNED_ROW_HELPERS = frozenset({"_owned_batch", "_owned_enrollment"})

#: Session methods that write.
WRITE_METHODS = frozenset({"add", "add_all", "delete", "merge"})

#: ``commit`` is a write signal in its own right, and leaving it out is
#: how this sweep first missed ``set_inactive_from`` -- the very
#: function the IDOR was found in. It writes by MUTATING A LOADED
#: ATTRIBUTE and committing, with no ``add`` or ``delete`` call
#: anywhere, which is the most natural way to write through an ORM and
#: the shape a method-name check does not see.
COMMIT_METHODS = frozenset({"commit", "flush"})

#: Functions exempt from the owner scope, each with its reason.
#:
#: A guardian has no ``owner_id`` -- that is the whole point of the
#: lens being computed rather than stored. Guardian reachability scopes
#: on ``guardian_account_id`` instead [BR5.3], and a test in
#: test_guardian_reachability.py covers the leak this prevents.
#: Listing it here keeps the exemption reviewable rather than implicit.
NOT_OWNER_SCOPED: dict[str, str] = {
    "list_guardian_children": (
        "scoped on guardian_account_id, since a guardian owns no batches"
    ),
}


def _writes(node: ast.FunctionDef) -> bool:
    """Report whether a function writes through the session.

    :param node: The function to inspect
    :return: True if it calls a write method or commits
    """
    return any(
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr in WRITE_METHODS | COMMIT_METHODS
        for call in ast.walk(node)
    )


def _is_scoped(node: ast.FunctionDef) -> bool:
    """Report whether a function reaches rows through an owned scope.

    :param node: The function to inspect
    :return: True if it scopes on the lens or uses an owned-row helper
    """
    source = ast.unparse(node)
    if "lens.owner_id" in source:
        return True
    return any(helper in source for helper in OWNED_ROW_HELPERS)


def _public_functions() -> list[ast.FunctionDef]:
    """Collect the module's top-level functions.

    :return: Every function defined at module scope
    """
    tree = ast.parse(SERVICE.read_text(), filename=str(SERVICE))
    return [node for node in tree.body if isinstance(node, ast.FunctionDef)]


def test_every_function_that_writes_is_scoped_by_the_lens() -> None:
    offenders = [
        node.name
        for node in _public_functions()
        if _writes(node) and not _is_scoped(node) and node.name not in NOT_OWNER_SCOPED
    ]

    assert offenders == [], (
        f"these functions write without reaching rows through an owned "
        f"scope, so any authenticated teacher can reach another's data: "
        f"{offenders}"
    )


def test_every_public_function_takes_a_lens() -> None:
    # The parameter is the first half: a function that does not take a
    # lens cannot be scoped by one, and the omission is invisible at the
    # call site because the route resolved one anyway.
    offenders: list[str] = []
    for node in _public_functions():
        if node.name.startswith("_"):
            continue
        names = {a.arg for a in node.args.args + node.args.kwonlyargs}
        if "lens" not in names:
            offenders.append(node.name)

    assert offenders == [], f"public functions taking no lens: {offenders}"


def test_the_sweep_sees_the_functions_it_claims_to_check() -> None:
    # Guards the check itself. An AST walk matching nothing would pass
    # vacuously, which is this project's most common defect shape --
    # and the first version of a similar walk in this Bolt did exactly
    # that.
    writers = [node.name for node in _public_functions() if _writes(node)]

    assert len(writers) >= 4, f"only found {writers}"
    assert "remove_enrollment" in writers
    assert "set_inactive_from" in writers


def test_every_exemption_names_a_function_that_exists() -> None:
    # A stale exemption permits nothing and tells the next reader a
    # function is scoped differently when it is simply gone.
    names = {node.name for node in _public_functions()}
    missing = [name for name in NOT_OWNER_SCOPED if name not in names]

    assert missing == [], f"exemptions for absent functions: {missing}"
