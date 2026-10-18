"""The money gate: every money property references the shared component.

**The predicate is ``$ref``, not "carries money"** [BR2.2, NFR9.1]. The
latter is undecidable from a generated document and circular besides:
selecting properties *by the pattern* then checking they have the pattern
proves nothing, and the defect this gate exists to catch -- a money value
typed as a free-form string -- is exactly what a pattern-based selector
cannot see.

Referencing the single declared component is decidable, and it inverts the
question from "does this match the pattern" to "does this reference the one
definition". That is the half of the money boundary U1's import rule cannot
reach, because a free-form ``str`` imports nothing.

**The ``$ref`` predicate alone leaves two holes, and both were found by
testing this gate rather than by reading it.** A money field typed
``float`` emits ``{"type": "number"}``; one typed ``Decimal`` emits a bare
``{"type": "string"}``. Neither carries a pattern, so neither was reported
-- at exactly the place ``project.md`` is most absolute: *never use float
or double for a money value anywhere in the stack*. Two name-matched
backstops close them. Matching on a name is weaker than ``$ref`` and is
used only where nothing stronger exists, since a bare ``{"type":
"number"}`` offers no way to tell a fee from a page count.

**The ``*_display`` pairing** [BR2.3, NFR9.2]: a display string never
appears without the canonical amount it renders. A display field alone
leaves the client nothing to compare, cache or re-render, and leaves the
server's rendering decision unverifiable. The display string itself is
**not** pattern-matched -- it is presentation, and its content is the
rendering specification settled at OQ-B1-1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import FastAPI

from app.money.wire import WIRE_PATTERN
from app.schemas.money import MONEY_COMPONENT_NAME

__all__ = ["MoneyViolation", "money_schema_violations"]

#: The suffix marking a presentation sibling of a canonical money field.
DISPLAY_SUFFIX = "_display"

#: Name fragments that mark a property as money-carrying. Used ONLY to
#: catch a numeric money field, which carries no pattern to match on.
#: Narrow and money-specific by design: a bare {"type": "number"} offers
#: nothing else to distinguish a fee from a page count.
MONEY_NAME_TOKENS: tuple[str, ...] = (
    "amount",
    "balance",
    "fee",
    "due",
    "paid",
    "price",
    "total",
    "outstanding",
    "credit",
    "charge",
)


@dataclass(frozen=True, slots=True)
class MoneyViolation:
    """A money-contract violation in the generated schema.

    :ivar schema: The component the violation was found in
    :ivar field: The offending property name
    :ivar kind: ``inline-money`` for a money shape not referencing the
        shared component, ``numeric-money`` for a money-named property
        crossing as a JSON number, ``unconstrained-money`` for one
        crossing as a bare string, ``orphan-display`` for a display field
        with no canonical sibling
    """

    schema: str
    field: str
    kind: Literal[
        "inline-money",
        "numeric-money",
        "unconstrained-money",
        "orphan-display",
    ]


def _references_money(node: object) -> bool:
    """Report whether a property node references the shared component.

    Looks through ``allOf``/``anyOf``/``oneOf`` wrappers, which is how
    Pydantic emits an annotated type alongside a description or default.

    :param node: The property schema node
    :return: True if the node reaches the shared Money component
    """
    if not isinstance(node, dict):
        return False

    ref = node.get("$ref")
    if isinstance(ref, str) and ref.rsplit("/", 1)[-1] == MONEY_COMPONENT_NAME:
        return True

    for keyword in ("allOf", "anyOf", "oneOf"):
        branches = node.get(keyword)
        if isinstance(branches, list):
            if any(_references_money(branch) for branch in branches):
                return True
    return False


def _is_inline_money(node: object) -> bool:
    """Report whether a property declares the money *shape* inline.

    Catches a string carrying the canonical pattern where a ``$ref``
    belongs. A numeric money field carries no pattern to match, so it is
    caught by :func:`_is_numeric_money_name` instead.

    :param node: The property schema node
    :return: True if the node declares a money shape of its own
    """
    if not isinstance(node, dict):
        return False

    pattern = node.get("pattern")
    return isinstance(pattern, str) and pattern == WIRE_PATTERN.pattern


def _is_numeric_money_name(field: str, node: object) -> bool:
    """Report whether a money-named property crossed as a JSON number.

    **The hole this closes, found by testing rather than by reading.** A
    field typed ``Decimal`` or ``float`` emits ``{"type": "number"}`` with
    no pattern at all, so a pattern-matching check reports nothing -- while
    ``project.md`` forbids a float or double for a money value *anywhere in
    the stack*, and a JSON number is an IEEE 754 double in most client
    parsers. The gate was silent at exactly the place the project cares
    most.

    Matching on the **name** is a deliberate weakening of the ``$ref``
    predicate, and it is the only decidable signal available here: a bare
    ``{"type": "number"}`` carries nothing else to distinguish a fee from a
    page count. The name list is therefore narrow and money-specific. A
    money field named outside it still escapes -- which is why this is a
    backstop and the ``$ref`` rule remains the control.

    :param field: The property name
    :param node: The property schema node
    :return: True if a money-named property is typed as a number
    """
    if not isinstance(node, dict):
        return False
    if node.get("type") not in {"number", "integer"}:
        return False
    return any(token in field.lower() for token in MONEY_NAME_TOKENS)


def _is_unconstrained_money_name(field: str, node: object) -> bool:
    """Report whether a money-named property is an unconstrained string.

    **The second hole, and the one the module docstring already claimed to
    close.** A field typed ``Decimal`` emits ``{"type": "string"}`` with no
    pattern and no ``$ref`` -- Pydantic serializes a Decimal as a string --
    so it is exactly the "money value typed as a free-form string" this
    gate exists to catch, and the ``$ref`` predicate alone did not see it.

    Like :func:`_is_numeric_money_name`, this matches on the name because a
    bare ``{"type": "string"}`` offers nothing else to go on. Also a
    backstop; the ``$ref`` rule remains the control.

    :param field: The property name
    :param node: The property schema node
    :return: True if a money-named property is a bare string
    """
    if not isinstance(node, dict):
        return False
    if node.get("type") != "string":
        return False
    if node.get("pattern") is not None or node.get("$ref") is not None:
        return False
    if field.endswith(DISPLAY_SUFFIX):
        # Presentation, by design: its content is the rendering
        # specification settled at OQ-B1-1, not the canonical wire form.
        return False
    return any(token in field.lower() for token in MONEY_NAME_TOKENS)


def money_schema_violations(app: FastAPI) -> list[MoneyViolation]:
    """List every money-contract violation in the generated schema.

    Takes the application as an argument so the committed violation fixture
    and the real gate call one function rather than two implementations
    that drift.

    :param app: The application whose generated schema is checked
    :return: One entry per violation, empty when the schema is clean
    """
    document = app.openapi()
    schemas: dict[str, dict[str, object]] = (
        document.get("components", {}).get("schemas", {}) or {}
    )

    violations: list[MoneyViolation] = []

    for name, schema in schemas.items():
        if name == MONEY_COMPONENT_NAME:
            continue
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            continue

        for field, node in properties.items():
            if _is_inline_money(node) and not _references_money(node):
                violations.append(
                    MoneyViolation(schema=name, field=str(field), kind="inline-money")
                )

            if _is_numeric_money_name(str(field), node):
                violations.append(
                    MoneyViolation(schema=name, field=str(field), kind="numeric-money")
                )

            if _is_unconstrained_money_name(str(field), node):
                violations.append(
                    MoneyViolation(
                        schema=name, field=str(field), kind="unconstrained-money"
                    )
                )

            if str(field).endswith(DISPLAY_SUFFIX):
                canonical = str(field)[: -len(DISPLAY_SUFFIX)]
                sibling = properties.get(canonical)
                if sibling is None or not _references_money(sibling):
                    violations.append(
                        MoneyViolation(
                            schema=name,
                            field=str(field),
                            kind="orphan-display",
                        )
                    )

    return violations
