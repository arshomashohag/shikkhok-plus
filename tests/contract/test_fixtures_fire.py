"""Every gate is proven to fire against a committed violation.

**This file is the answer to the central risk of this Unit.** Each schema
assertion U2 ships iterates a collection that is empty in B2: no routes, no
money endpoints, no response schemas. Each returns green having examined
nothing. Four green checks that have never looked at anything is worse than
having no checks, because it manufactures documented confidence.

Two properties make these tests meaningful rather than ceremonial:

* **Each fixture is otherwise valid and violates exactly one rule.** A
  merely malformed fixture fails every gate for the wrong reason.
* **Each assertion names the specific violation.** A fixture that failed for
  a cheaper reason -- a missing key, a parse error -- would certify nothing
  about the rule it was written for while looking like a working test.

**A fixture that stops failing is itself a build failure** [NFR17.1]. These
are the one part of this Unit whose *failure* is the passing condition.
"""

from __future__ import annotations

from app.contract.routes import unlensed_routes
from tests.contract.fixtures.unlensed_app import UNLENSED_PATH, build_unlensed_app


def test_route_gate_fires_on_the_unlensed_fixture() -> None:
    """The route gate reports the fixture's route, naming its path.

    :return: None
    """
    violations = unlensed_routes(build_unlensed_app())

    assert len(violations) == 1, "the gate examined nothing"
    assert violations[0].path == UNLENSED_PATH
    assert violations[0].method == "GET"
