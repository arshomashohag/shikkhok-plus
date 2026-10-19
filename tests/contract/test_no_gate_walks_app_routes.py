"""No gate enumerates ``app.routes`` directly.

**Two gates were found reporting clean while checking zero routes.**
In this FastAPI version an included router appears as an opaque
``_IncludedRouter``, so ``isinstance(route, APIRoute)`` over
``app.routes`` matches nothing:

* the **route-enumeration gate**, which guarantees no endpoint ships
  unlensed;
* the **privacy gate**, which enforces ``project.md``'s NEVER rule that
  no teacher-lens response carries a profile field.

Both had correct logic and passing fixture tests -- the leaky fixture
fired three violations exactly as designed. Only the enumeration of the
*real application* was empty, which is why they looked thoroughly
tested. That is this project's "the assertion is real, the setup makes
it vacuous" class, with the setup broken by a dependency upgrade rather
than by a commit.

The second was found by asking what else enumerated routes the same
way, after the first was fixed. This test is what makes that sweep
permanent: ``app/contract/routes.py`` owns the one correct enumeration,
and nothing else may walk ``app.routes``.
"""

from __future__ import annotations

import ast
import pathlib

CONTRACT = pathlib.Path(__file__).resolve().parents[2] / "app" / "contract"

#: The one module permitted to read ``app.routes``, because it is the
#: module that knows how to do it correctly.
ENUMERATION_OWNER = "routes.py"


def _reads_app_routes(tree: ast.Module) -> list[str]:
    """Find reads of a ``.routes`` attribute on an application.

    :param tree: The parsed module
    :return: One description per read
    """
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or node.attr != "routes":
            continue
        base = node.value
        name = base.id if isinstance(base, ast.Name) else None
        if name == "app":
            found.append(f"{name}.routes")
    return found


def test_no_gate_other_than_the_owner_walks_app_routes() -> None:
    offenders: list[str] = []

    for path in CONTRACT.rglob("*.py"):
        if path.name == ENUMERATION_OWNER:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for read in _reads_app_routes(tree):
            offenders.append(f"{path.name}: {read}")

    assert offenders == [], (
        "these modules enumerate app.routes directly, which matches "
        "nothing in this FastAPI version and makes the gate vacuous. "
        f"Use app.contract.routes._api_routes instead: {offenders}"
    )


def test_the_owner_still_enumerates_something() -> None:
    # Guards the check itself: the rule above is only worth having while
    # the owner's enumeration actually works.
    from app.contract.routes import _api_routes
    from app.main import app as real_app

    assert len(_api_routes(real_app)) >= 10


def test_the_privacy_gate_sees_every_route_the_route_gate_sees() -> None:
    # The two gates must agree on the route set. A privacy gate checking
    # a subset would silently stop covering whatever it missed -- which
    # is exactly what happened, with the subset being empty.
    from app.contract.privacy import forbidden_fields, is_teacher_facing
    from app.contract.routes import _api_routes
    from app.main import app as real_app

    routes = _api_routes(real_app)
    teacher_facing = [route for route in routes if is_teacher_facing(route)]

    assert teacher_facing, (
        "no route is teacher-facing, so the privacy gate checks nothing"
    )
    assert forbidden_fields(real_app) == []
