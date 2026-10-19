"""The money gate over the generated schema.

Test-after by the team's predicate: this asserts a *schema shape* rather
than arithmetic, so a wrong answer here is a contract defect rather than a
money error. U1 owns the arithmetic at 100% branch coverage.

What this gate catches that U1's import rule cannot: a money value typed as
a free-form string. Such a field imports nothing and computes nothing, so
no import check can see it -- only the generated document can.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import FastAPI
from pydantic import BaseModel

from app.contract.money_schema import money_schema_violations
from app.money.wire import WIRE_PATTERN
from app.schemas.money import MONEY_COMPONENT_NAME, MoneyField


class CleanInvoice(BaseModel):
    """An invoice whose amount references the shared component.

    :ivar amount: The canonical money value
    """

    amount: MoneyField


class InlineMoney(BaseModel):
    """An invoice declaring the money shape inline.

    This is the realistic defect: the author knew the pattern and typed it
    directly rather than reaching for the shared component.

    :ivar amount: A money-shaped string that references nothing
    """

    amount: str


class OrphanDisplay(BaseModel):
    """A display string with no canonical sibling.

    :ivar amount_display: Presentation with nothing behind it
    """

    amount_display: str


class PairedDisplay(BaseModel):
    """A display string beside the amount it renders.

    :ivar amount: The canonical money value
    :ivar amount_display: Its presentation sibling
    """

    amount: MoneyField
    amount_display: str


def _app_with(model: type[BaseModel]) -> FastAPI:
    """Build an application exposing one model as a response.

    :param model: The response model to expose
    :return: An application carrying exactly that route
    """
    app = FastAPI()

    @app.get("/v1/probe", response_model=model)
    def _probe() -> dict[str, str]:
        return {}

    return app


def test_component_referencing_amount_passes() -> None:
    """A money property that references the shared component is clean.

    :return: None
    """
    assert money_schema_violations(_app_with(CleanInvoice)) == []


def test_inline_money_shape_is_reported() -> None:
    """A money shape declared inline is reported, naming the property.

    :return: None
    """
    app = _app_with(InlineMoney)
    document = app.openapi()
    document["components"]["schemas"]["InlineMoney"]["properties"]["amount"] = {
        "type": "string",
        "pattern": WIRE_PATTERN.pattern,
    }
    app.openapi_schema = document

    violations = money_schema_violations(app)

    assert len(violations) == 1
    assert violations[0].field == "amount"
    assert violations[0].kind == "inline-money"


def test_orphan_display_is_reported() -> None:
    """A display field with no canonical sibling is reported by name.

    :return: None
    """
    violations = money_schema_violations(_app_with(OrphanDisplay))

    assert len(violations) == 1
    assert violations[0].field == "amount_display"
    assert violations[0].kind == "orphan-display"


def test_paired_display_passes() -> None:
    """A display field beside its canonical amount is clean.

    :return: None
    """
    assert money_schema_violations(_app_with(PairedDisplay)) == []


def test_display_string_is_not_pattern_matched() -> None:
    """The display sibling is presentation and carries no pattern.

    Its content is the rendering specification settled at OQ-B1-1 --
    Western digits, lakh/crore grouping, a prefixed symbol -- none of which
    matches the canonical wire pattern. Asserting the pattern on it would
    reject every correctly rendered value.

    :return: None
    """
    document = _app_with(PairedDisplay).openapi()
    display = document["components"]["schemas"]["PairedDisplay"]["properties"][
        "amount_display"
    ]

    assert "pattern" not in display


def test_the_shared_component_carries_the_pattern() -> None:
    """The one component declares the canonical pattern, so fields need not.

    :return: None
    """
    document = _app_with(CleanInvoice).openapi()
    schemas = document["components"]["schemas"]

    assert MONEY_COMPONENT_NAME in schemas or any(
        node.get("pattern") == WIRE_PATTERN.pattern
        for schema in schemas.values()
        for node in schema.get("properties", {}).values()
    )


def test_the_pattern_is_u1s_and_not_restated() -> None:
    """The schema pattern is imported from U1, not duplicated here.

    Two sources of truth would agree today and drift silently after the
    first change to either, with nothing failing in between.

    :return: None
    """
    from app.schemas import money as money_schemas

    assert money_schemas.WIRE_PATTERN is WIRE_PATTERN


def test_the_real_app_passes() -> None:
    """The real application passes the gate.

    Zero money endpoints exist in B2, which is why the committed fixture
    carries the proof that this gate can fire at all.

    :return: None
    """
    from app.main import app as real_app

    assert money_schema_violations(real_app) == []


# --------------------------------------------------------------------------
# The two holes a $ref-only predicate leaves open
#
# Both were found by TESTING the gate rather than by reading it, and both
# sit at the place project.md cares most about: "NEVER use float or double
# for a money value anywhere in the stack, in any language, in storage, in
# transit or in memory."
# --------------------------------------------------------------------------


class NumericMoney(BaseModel):
    """A model whose money field crosses as a JSON number.

    :ivar balance: A float, which emits {"type": "number"} and carries no
        pattern for a pattern-matching check to find
    """

    balance: float


class UnconstrainedMoney(BaseModel):
    """A model whose money field crosses as a bare string.

    :ivar amount: A Decimal. Pydantic serializes it as a string with NO
        pattern, so it is precisely the free-form-string defect this gate
        exists to catch -- and the $ref predicate alone did not see it.
    """

    amount: Decimal


class NotMoney(BaseModel):
    """A model whose numeric fields are not money.

    :ivar page_count: A count, which must not be reported
    :ivar note: Free text, which must not be reported
    """

    page_count: int
    note: str


def test_a_float_money_field_is_reported() -> None:
    """A money-named float is caught, though it carries no pattern.

    project.md forbids a float or double for a money value anywhere in the
    stack, and a JSON number is an IEEE 754 double in most client parsers.
    A $ref-only check is silent here.

    :return: None
    """
    violations = money_schema_violations(_app_with(NumericMoney))

    assert [(v.kind, v.field) for v in violations] == [("numeric-money", "balance")]


def test_an_unconstrained_money_string_is_reported() -> None:
    """A money-named bare string is caught.

    This is the defect the module docstring already claimed to catch. A
    Decimal field emits {"type": "string"} with no pattern and no $ref.

    :return: None
    """
    violations = money_schema_violations(_app_with(UnconstrainedMoney))

    assert [(v.kind, v.field) for v in violations] == [
        ("unconstrained-money", "amount")
    ]


def test_non_money_fields_are_not_reported() -> None:
    """A count and a free-text field are left alone.

    The name match is narrow by necessity: a bare {"type": "number"}
    offers nothing else to distinguish a fee from a page count. A gate
    that reported either would be silenced the first time it fired on a
    legitimate field.

    :return: None
    """
    assert money_schema_violations(_app_with(NotMoney)) == []


def test_a_display_sibling_is_not_an_unconstrained_money_string() -> None:
    """The presentation sibling is exempt from the bare-string check.

    Its content is the rendering specification settled at OQ-B1-1 --
    Western digits, lakh/crore grouping, a prefixed symbol -- which is
    deliberately not the canonical wire form.

    :return: None
    """
    assert money_schema_violations(_app_with(PairedDisplay)) == []
