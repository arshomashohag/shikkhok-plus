"""A public application that leaks a forbidden field on a public route.

The real gate returns green over an empty view-model registry, and a
passing test and a vacuous test are the same colour. This fixture proves
the public audience can fire, through the same function the gate calls.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

#: The field this fixture leaks, and the public route carrying it.
PUBLIC_LEAK_FIELD = "collection_number"
PUBLIC_LEAK_PATH = "/health"


class LeakyHealth(BaseModel):
    """A health payload carrying a per-person key.

    :ivar status: A harmless field
    :ivar collection_number: Forbidden on any public surface
    """

    status: str
    collection_number: str


def build_public_leak_app() -> FastAPI:
    """Build an application with a public route that leaks a field.

    :return: An application the public gate must reject
    """
    app = FastAPI(title="public leak fixture")

    @app.get(PUBLIC_LEAK_PATH, response_model=LeakyHealth)
    def _health() -> dict[str, str]:
        """Return a payload that leaks a collection number.

        :return: An empty payload
        """
        return {}

    return app
