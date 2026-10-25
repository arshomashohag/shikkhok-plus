"""No feature package may define a push client [NFR19.24, OQ-4].

**The mechanism that makes OQ-4's answer binding rather than
remembered.** D3 owns the FCM adapter and D4 consumes the same one; the
failure OQ-4 names is two adapters with two different ``UNREGISTERED``
behaviours, and absent this check that outcome is prevented only by D4's
author importing rather than copying.

Written in the same shape as the money module's import gate, which this
project already relies on: an AST walk over the real source tree, so the
gate holds against a file nobody thought to add to a list.

**It must be able to fire.** A gate reporting "no violations" is
indistinguishable from a gate that checks nothing, and this project has
now found that exact defect twice -- in the route gate and in the
privacy gate, both of which passed over zero routes. The last test here
plants a violation and asserts the walk reports it.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Packages that implement a feature. A push client belongs in none of
#: them: it is shared infrastructure, and the one place it lives is
#: ``app/notifications``.
FEATURE_PACKAGES = ("fees", "batches", "accounts", "auth", "authz", "api")

#: Names that mark a definition as a push client. Matched on the
#: CLASS and FUNCTION names a second adapter would have to introduce,
#: rather than on an import -- importing the shared adapter is exactly
#: what a feature SHOULD do, so an import-based check would forbid the
#: correct thing and permit the wrong one.
CLIENT_MARKERS = ("fcm", "firebase", "pushadapter", "pushclient", "messaging")

#: The one module permitted to define a push client.
PERMITTED = ROOT / "app" / "notifications" / "fcm.py"


def _defines_a_push_client(source: str) -> list[str]:
    """Report every push-client definition in one module's source.

    An AST walk rather than a text search: a comment or a docstring
    mentioning FCM is not a definition, and a gate that cannot tell
    them apart is one somebody turns off.

    :param source: The module source
    :return: The offending definition names
    """
    tree = ast.parse(source)
    offenders: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            lowered = node.name.lower()
            if any(marker in lowered for marker in CLIENT_MARKERS):
                offenders.append(node.name)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            lowered = node.name.lower()
            # A FUNCTION named for the client is the likelier second
            # adapter: `def send_fcm(...)` in a feature module, written
            # because importing felt like more work than retyping.
            if any(marker in lowered for marker in CLIENT_MARKERS):
                offenders.append(node.name)

    return offenders


def test_no_feature_package_defines_a_push_client() -> None:
    violations: dict[str, list[str]] = {}

    for package in FEATURE_PACKAGES:
        for path in (ROOT / "app" / package).rglob("*.py"):
            if path == PERMITTED:
                continue
            found = _defines_a_push_client(path.read_text())
            if found:
                violations[str(path.relative_to(ROOT))] = found

    assert violations == {}, (
        f"a push client is defined outside app/notifications: "
        f"{violations}. D3 owns the adapter and D4 consumes the same "
        "one [OQ-4]; a second adapter means two different UNREGISTERED "
        "behaviours and a dead-token table that grows for ever on "
        "whichever side got it wrong."
    )


def test_the_shared_adapter_really_is_where_the_gate_says() -> None:
    # Not vacuous: if the adapter moved, the loop above would pass
    # while covering nothing, which is how a control retires quietly.
    assert PERMITTED.exists()
    assert _defines_a_push_client(PERMITTED.read_text()), (
        "the permitted module defines no push client, so the exemption "
        "above is exempting nothing and the gate is checking an empty set"
    )


def test_the_gate_fires_on_a_planted_violation() -> None:
    planted = """
class FcmClient:
    def send(self, token, message):
        return None
"""
    assert _defines_a_push_client(planted) == ["FcmClient"]


def test_the_gate_fires_on_a_planted_function() -> None:
    planted = """
def send_fcm_message(token, body):
    return None
"""
    assert _defines_a_push_client(planted) == ["send_fcm_message"]


def test_the_gate_does_not_fire_on_a_mere_mention() -> None:
    # A feature that IMPORTS the shared adapter is doing the right
    # thing. A gate flagging that would forbid the correct behaviour
    # and push the next author towards a local copy -- the exact
    # outcome it exists to prevent.
    importing = """
from app.notifications.fcm import build_push_adapter


def send_fee_reminder(session, token):
    '''Dispatch through the shared FCM adapter.'''
    return build_push_adapter().send(token, None, "")
"""
    assert _defines_a_push_client(importing) == []


def test_the_fee_feature_imports_rather_than_defines() -> None:
    # The positive statement of the rule against the real file: D3's
    # reminder path reaches the adapter by import.
    source = (ROOT / "app" / "fees" / "reminders.py").read_text()

    assert "from app.notifications.fcm import" in source
    assert _defines_a_push_client(source) == []
