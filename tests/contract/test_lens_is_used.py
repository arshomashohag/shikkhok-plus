"""A resolved lens must be USED, not merely declared [TC-11].

**The route-enumeration gate U2 built checks that a lens dependency
exists on the route. It cannot see whether the handler does anything
with it** -- and a handler that resolves a lens and then discards it
works perfectly, authorizes nothing, and passes every existing check.

That is not hypothetical. Review found exactly it in U4:
``remove_enrollment`` and ``set_inactive_from`` took no lens at all,
while their routes resolved one and dropped it. Any authenticated
teacher could delete or deactivate another teacher's seat by guessing a
UUID, and the lens convention was followed everywhere else in the same
module.

So this gate asserts the second half: every handler that takes a lens
parameter **references it in its body**. That is weaker than proving it
is used *correctly* -- nothing static can prove that -- but it closes
the specific gap where a lens is resolved and then ignored entirely.
"""

from __future__ import annotations

import ast
import pathlib

from app.contract.routes import _api_routes, _resolves_a_lens
from app.main import create_app

API = pathlib.Path(__file__).resolve().parents[2] / "app" / "api"


def _lens_parameter_names(function: ast.FunctionDef) -> list[str]:
    """Find parameters annotated as a lens dependency.

    :param function: The handler to inspect
    :return: The names of its lens-typed parameters
    """
    names: list[str] = []
    arguments = function.args
    for argument in [*arguments.args, *arguments.kwonlyargs]:
        annotation = ast.unparse(argument.annotation) if argument.annotation else ""
        if "Lens" in annotation and "Depends" in annotation:
            names.append(argument.arg)
    return names


def _referenced_names(function: ast.FunctionDef) -> set[str]:
    """Collect every name read inside a function body.

    :param function: The handler to inspect
    :return: The names its body reads
    """
    return {
        node.id
        for statement in function.body
        for node in ast.walk(statement)
        if isinstance(node, ast.Name)
    }


def test_every_handler_that_resolves_a_lens_uses_it() -> None:
    offenders: list[str] = []

    for path in API.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            lens_names = _lens_parameter_names(node)
            if not lens_names:
                continue
            used = _referenced_names(node)
            for name in lens_names:
                if name not in used:
                    offenders.append(f"{path.name}:{node.name} ignores '{name}'")

    assert offenders == [], (
        "these handlers resolve a lens and never read it, so they "
        f"authorize nothing while passing the route gate: {offenders}"
    )


def test_the_gate_sees_the_handlers_it_claims_to_check() -> None:
    # Guards the check itself. An AST walk that matched no handler would
    # pass vacuously, which is this project's most common defect shape.
    checked = 0
    for path in API.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and _lens_parameter_names(node):
                checked += 1

    assert checked >= 6, f"only {checked} lensed handlers found"


def test_every_lensed_route_has_a_handler_this_gate_can_read() -> None:
    # The two halves must agree on the same set: a route whose handler
    # lives outside app/api would resolve a lens that this gate never
    # inspects.
    app = create_app()
    lensed_routes = 0
    # _api_routes, not app.routes: the latter does not hold APIRoute
    # objects in this FastAPI version, which is what made the route gate
    # itself vacuous.
    for route in _api_routes(app):
        endpoint = route.endpoint
        dependant = route.dependant
        # The SAME recursive helper the route gate uses. A one-level
        # walk finds nothing, because a lens is routinely nested inside a
        # composed dependency -- which is what the guard above caught
        # when this test first reported zero lensed routes.
        if _resolves_a_lens(dependant):
            lensed_routes += 1
            module = getattr(endpoint, "__module__", "")
            assert module.startswith("app.api"), (
                f"{module}.{endpoint.__name__} resolves a lens but lives "
                "outside app/api, where this gate does not look"
            )

    assert lensed_routes >= 6, f"only {lensed_routes} lensed routes found"
