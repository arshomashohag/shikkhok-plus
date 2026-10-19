"""
The wire chokepoint: the only path a money value takes across the API.

One chokepoint per boundary, both living in this module [BR5.3]. Not a
per-field serializer: that approach works until one endpoint forgets, and a
forgotten serializer is invisible in review because the field still renders.
An annotated type cannot be forgotten, because forgetting it means not having
a money type at all.

One canonical form, defined once:

- exactly two decimal places
- no currency symbol, no thousands separator
- Latin digits only
- **no sign** — the pattern admits none

A value is emitted as a JSON **string**, never a number. JSON numbers are
IEEE 754 doubles in most parsers, so a money value emitted as a number is
converted to a float by the *client*, reintroducing the exact representation
error this module exists to prevent, on the far side of the wire where none
of these controls reach.

The dangerous failure here is a **lenient decoder**: one that quietly accepts
a number and converts it, so a happy-path test on both sides passes while the
value is already wrong. Hence :func:`parse` rejects a number loudly rather
than coercing.

Presentation for a human is a different operation producing a different
value. It is not in this module and not in this Bolt — see the deferral note
in :mod:`app.money`.
"""

from __future__ import annotations

import re
from typing import Final

from ._errors import MoneyValidationError
from ._money import Money

#: The canonical wire form. Note the absence of a sign.
WIRE_PATTERN: Final = re.compile(r"^[0-9]+\.[0-9]{2}$")


def to_wire(value: Money) -> str:
    """
    Render an amount for transmission.

    :param value: The amount to render.
    :return: The canonical two-decimal string.
    :raises MoneyValidationError: If the amount is negative. The canonical
        pattern admits no sign, so there is no representation to emit — and
        every quantity that legitimately crosses the API is one the sign
        rules already forbid to be negative. A negative value reaching here
        means a floor was missed upstream, and failing loudly beats emitting
        a string the client cannot parse or, worse, dropping the sign and
        displaying a debt as a credit.
    """
    if value.is_negative():
        raise MoneyValidationError(
            f"A negative amount ({value}) cannot cross the API boundary: "
            "the canonical form admits no sign. A sign rule was violated "
            "upstream."
        )
    return str(value.amount)


def parse(raw: object) -> Money:
    """
    Read an amount from an incoming field.

    :param raw: The received value. Must be a string in canonical form.
    :return: The parsed amount.
    :raises MoneyValidationError: If the value is a JSON number rather than a
        string, or is a string not in canonical form.
    """
    if isinstance(raw, bool) or isinstance(raw, int | float):
        raise MoneyValidationError(
            "A money field must arrive as a JSON string, not a number. A "
            "decoder that quietly converts a number is the actual failure "
            "mode, and it passes a happy-path test on both sides."
        )
    if not isinstance(raw, str):
        raise MoneyValidationError(
            f"A money field must be a string, not {type(raw).__name__}."
        )
    if not WIRE_PATTERN.match(raw):
        raise MoneyValidationError(
            f"{raw!r} is not in canonical money form: exactly two decimal "
            "places, no sign, no separator, Latin digits."
        )
    return Money(raw)
