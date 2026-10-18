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

from app.contract.privacy import forbidden_fields
from app.contract.routes import unlensed_routes
from tests.contract.fixtures.leaky_app import (
    ACCOUNT_ID_LEAK_FIELD,
    PROFILE_LEAK_FIELD,
    build_leaky_app,
)
from tests.contract.fixtures.unlensed_app import UNLENSED_PATH, build_unlensed_app


def test_route_gate_fires_on_the_unlensed_fixture() -> None:
    """The route gate reports the fixture's route, naming its path.

    :return: None
    """
    violations = unlensed_routes(build_unlensed_app())

    assert len(violations) == 1, "the gate examined nothing"
    assert violations[0].path == UNLENSED_PATH
    assert violations[0].method == "GET"


def test_privacy_gate_fires_on_both_forbidden_sets() -> None:
    """The privacy gate reports TWO violations, one per forbidden set.

    Asserting two rather than "at least one" is the point. The gate carries
    both sets on a single iteration, so a fixture tripping only the
    owner-private set would leave ADR-001's account-id half entirely
    unexercised while the gate still reported green.

    :return: None
    """
    violations = forbidden_fields(build_leaky_app())

    assert len(violations) == 2, "the gate examined nothing, or only one set"

    by_set = {violation.field_set: violation.field for violation in violations}
    assert by_set["owner-private"] == PROFILE_LEAK_FIELD
    assert by_set["account-id"] == ACCOUNT_ID_LEAK_FIELD
