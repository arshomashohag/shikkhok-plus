"""The application object.

**This Unit registers no routes.** U2 owns the contract and the gates that
check it; the Units that own the features add the endpoints. The app exists
here so the route-enumeration gate has a real object to walk at test
collection time, and so the committed OpenAPI document has something to be
generated from.
"""

from __future__ import annotations

from fastapi import FastAPI

__all__ = ["app", "create_app"]


def create_app() -> FastAPI:
    """Build the application.

    :return: The configured application, with no routes in this Unit
    """
    return FastAPI(
        title="ShikhokPlus API",
        version="1.0.0",
        description=(
            "Private tuition management. Every money value crosses this "
            "boundary as a JSON string; every lens-scoped response names "
            "the lens that produced it."
        ),
    )


app = create_app()
