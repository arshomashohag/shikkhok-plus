"""Applications violating each half of the money contract.

**Why these exist.** In B2 the money gate iterates the real application's
schemas, and no money endpoint exists yet. The gate returns green having
examined nothing. These two fixtures are the only proof it can fire.

**Each violates exactly one rule and is otherwise valid.** A merely
malformed document would fail the gate for the wrong reason and certify
nothing about the rule it was written for, while looking like a working
test.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from app.money.wire import WIRE_PATTERN

#: The property the inline-money fixture declares wrongly.
INLINE_MONEY_FIELD = "amount"
INLINE_MONEY_SCHEMA = "InlineInvoice"

#: The orphan display field, and the canonical sibling it is missing.
ORPHAN_DISPLAY_FIELD = "amount_display"
ORPHAN_DISPLAY_SCHEMA = "OrphanInvoice"


class InlineInvoice(BaseModel):
    """An invoice declaring the money shape inline.

    The realistic defect: the author knew the canonical pattern and typed
    it directly rather than reaching for the shared component. The value is
    perfectly well-formed -- which is the point, since a malformed one
    would fail for the wrong reason.

    :ivar amount: A money-shaped string referencing no component
    """

    amount: str


class OrphanInvoice(BaseModel):
    """An invoice whose display string has no canonical sibling.

    :ivar amount_display: Presentation with nothing behind it
    """

    amount_display: str


def build_inline_money_app() -> FastAPI:
    """Build an application declaring a money shape inline.

    The pattern is injected into the generated document directly, because
    a plain ``str`` annotation carries no pattern for Pydantic to emit.
    What the gate must catch is a property that *looks* like money and
    references nothing, which is exactly this shape.

    :return: An application the money gate must reject
    """
    app = FastAPI(title="inline money fixture")

    @app.get("/v1/fixture/invoice", response_model=InlineInvoice)
    def _invoice() -> dict[str, str]:
        """Return an invoice whose amount bypasses the component.

        :return: An empty payload
        """
        return {}

    document = app.openapi()
    document["components"]["schemas"][INLINE_MONEY_SCHEMA]["properties"][
        INLINE_MONEY_FIELD
    ] = {"type": "string", "pattern": WIRE_PATTERN.pattern}
    app.openapi_schema = document
    return app


def build_orphan_display_app() -> FastAPI:
    """Build an application whose display field has no sibling.

    :return: An application the money gate must reject
    """
    app = FastAPI(title="orphan display fixture")

    @app.get("/v1/fixture/orphan", response_model=OrphanInvoice)
    def _orphan() -> dict[str, str]:
        """Return a rendered amount with no canonical value.

        :return: An empty payload
        """
        return {}

    return app
