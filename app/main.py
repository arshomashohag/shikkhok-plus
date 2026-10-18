"""The application object.

**This Unit registers no routes.** U2 owns the contract and the gates that
check it; the Units that own the features add the endpoints. The app exists
here so the route-enumeration gate has a real object to walk at test
collection time, and so the committed OpenAPI document has something to be
generated from.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.errors import register_error_handler

__all__ = ["app", "create_app"]


def create_app() -> FastAPI:
    """Build the application.

    :return: The configured application, with no routes in this Unit
    """
    app = FastAPI(
        title="ShikhokPlus API",
        version="1.0.0",
        description=(
            "Private tuition management. Every money value crosses this "
            "boundary as a JSON string; every lens-scoped response names "
            "the lens that produced it."
        ),
    )
    register_error_handler(app)
    _publish_shared_components(app)
    return app


def _publish_shared_components(app: FastAPI) -> None:
    """Place the shared components in the generated document.

    FastAPI emits a component only when some route references it, and this
    Unit declares no routes. Without this, ``Money`` and the error envelope
    would be **absent from the committed contract** -- so a regression in
    the one definition every money property must reference, or in the
    envelope every error response carries, would not appear in the diff
    the reviewer reads. The gate would still pass, over nothing.

    :param app: The application whose schema is being built
    :return: None
    """
    from app.schemas.errors import ErrorEnvelope
    from app.schemas.money import Money

    document = app.openapi()
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
    for model in (Money, ErrorEnvelope):
        schemas.update(
            model.model_json_schema(ref_template="#/components/schemas/{model}").pop(
                "$defs", {}
            )
        )
        schemas[model.__name__] = {
            key: value
            for key, value in model.model_json_schema(
                ref_template="#/components/schemas/{model}"
            ).items()
            if key != "$defs"
        }
    app.openapi_schema = document


app = create_app()
