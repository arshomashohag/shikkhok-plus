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

from app.contract.money_schema import money_schema_violations
from app.contract.privacy import forbidden_fields
from app.contract.routes import unlensed_routes
from tests.contract.fixtures.leaky_app import (
    ACCOUNT_ID_LEAK_FIELD,
    PROFILE_LEAK_FIELD,
    build_leaky_app,
)
from tests.contract.fixtures.money_app import (
    INLINE_MONEY_FIELD,
    ORPHAN_DISPLAY_FIELD,
    build_inline_money_app,
    build_orphan_display_app,
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


def test_money_gate_fires_on_an_inline_money_shape() -> None:
    """The money gate reports a money shape that references nothing.

    This is the defect U1's import rule cannot see: a free-form string
    carrying the canonical pattern imports nothing and computes nothing,
    so only the generated document can catch it.

    :return: None
    """
    violations = money_schema_violations(build_inline_money_app())

    assert len(violations) == 1, "the gate examined nothing"
    assert violations[0].field == INLINE_MONEY_FIELD
    assert violations[0].kind == "inline-money"


def test_money_gate_fires_on_an_orphan_display_field() -> None:
    """The money gate reports a display string with no canonical sibling.

    A display field alone leaves the client nothing to compare, cache or
    re-render, and leaves the server's rendering decision unverifiable.

    :return: None
    """
    violations = money_schema_violations(build_orphan_display_app())

    assert len(violations) == 1, "the gate examined nothing"
    assert violations[0].field == ORPHAN_DISPLAY_FIELD
    assert violations[0].kind == "orphan-display"
