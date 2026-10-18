"""The shared ``Money`` schema component.

**One component, referenced by every money-carrying property.** This is the
API-level half of the money boundary, and it is the half U1's import rule
cannot see: a money value typed as a free-form ``str`` imports nothing and
computes nothing, so no import check can catch it. Only the generated
schema can.

The pattern is **imported from** :mod:`app.money.wire` rather than restated
here. Restating it would create a second source of truth that drifts
silently: the two would agree today and disagree after the first change to
either, with nothing failing in between.

The pattern admits **no sign**. A negative amount cannot cross the
boundary; every quantity that legitimately does is one the sign rules
already forbid to be negative.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, RootModel

from app.money.wire import WIRE_PATTERN

__all__ = ["MONEY_COMPONENT_NAME", "Money", "MoneyField"]

#: The component name every money property must ``$ref``. The gate asserts
#: reference to *this* name rather than re-checking the pattern per field.
MONEY_COMPONENT_NAME = "Money"


class Money(RootModel[str]):
    """A money value as it crosses the API.

    **A ``RootModel``, deliberately, and not an ``Annotated`` alias.** An
    annotated alias is *inlined* into every property that uses it, so the
    generated document carries a copy of the pattern per field and no
    component to reference -- which makes the ``$ref`` predicate the gate
    depends on unimplementable. Verified by generating both: the alias
    produces an inline ``{"type": "string", "pattern": ...}``, the root
    model produces ``{"$ref": "#/components/schemas/Money"}`` beside one
    shared definition.

    That single definition is what the gate checks reference to, and it is
    why "does this reference the one definition" is decidable where "does
    this carry money" is not.

    Always a JSON **string**, never a number. A JSON number is an IEEE 754
    double in most parsers, so emitting one converts the value to a float
    on the client, where none of U1's controls reach.

    :ivar root: The canonical wire form
    """

    root: Annotated[
        str,
        Field(
            pattern=WIRE_PATTERN.pattern,
            description=(
                "A BDT amount in canonical form: exactly two decimal "
                "places, no separator, no symbol, no sign."
            ),
        ),
    ]


#: Spelling used at call sites that read as a field type rather than a
#: model. The same class: the component name the gate checks is the class
#: name, so there is exactly one definition in the generated document.
MoneyField = Money
