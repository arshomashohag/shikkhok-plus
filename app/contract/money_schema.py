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


@dataclass(frozen=True, slots=True)
class MoneyViolation:
    """A money-contract violation in the generated schema.

    :ivar schema: The component the violation was found in
    :ivar field: The offending property name
    :ivar kind: ``inline-money`` for a money shape not referencing the
        shared component, ``orphan-display`` for a display field with no
        canonical sibling
    """

    schema: str
    field: str
    kind: Literal["inline-money", "orphan-display"]


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
    """Report whether a property declares a money shape inline.

    This is the violation worth catching: a string carrying the canonical
    pattern, or a numeric money amount, declared directly on the property
    instead of referencing the one component.

    :param node: The property schema node
    :return: True if the node declares a money shape of its own
    """
    if not isinstance(node, dict):
        return False

    pattern = node.get("pattern")
    return isinstance(pattern, str) and pattern == WIRE_PATTERN.pattern


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
