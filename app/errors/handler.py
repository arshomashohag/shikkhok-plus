"""The single exception handler.

**No endpoint writes its own try/except for the taxonomy.** This handler
sits on every error path in the system, which drives its one hard
requirement: it performs **no I/O**. No database call, no network call, no
file read. A handler that can itself fail turns a handled 403 into an
unhandled 500 at exactly the moment the system is already degraded.

That prohibition is enforced by the layered import test in
``tests/gates/test_import_gates.py``, not by convention. The realistic
violation is not an obvious one -- it is structured error logging that
writes to the database, or a lookup enriching ``details`` with a
human-readable name. Both look like improvements, and both put a query on
every error path.

**Totality is proved in two places, because neither half reaches the
other.** ``assert_never`` cannot serve in the match below: ``TaxonomyError``
is itself instantiable, so mypy cannot narrow the default arm to ``Never``.
The static proof therefore lives in ``_exhaustive.py``, over a closed union
of the five concrete classes, where ``assert_never`` does narrow -- that
catches a class added to the union but not to a match. The remaining gap --
a sixth class added to the taxonomy and to *neither* -- is closed by a
runtime test asserting the union equals the actual subclass set. Verified
by adding a sixth class and confirming mypy stayed silent while the test
failed.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.errors._classes import (
    AuthorizationError,
    ConflictError,
    FatalError,
    TaxonomyError,
    TransientError,
    ValidationError,
)
from app.schemas.errors import ErrorBody, ErrorEnvelope

__all__ = ["register_error_handler", "to_response"]


def _envelope(error: TaxonomyError, *, retryable: bool) -> ErrorEnvelope:
    """Build the response envelope for an error.

    :param error: The taxonomy error being rendered
    :param retryable: Derived from the class, never from the raise site
    :return: The envelope
    """
    return ErrorEnvelope(
        error=ErrorBody(
            code=error.code,
            retryable=retryable,
            message_key=error.message_key,
            details=error.details,
        )
    )


def to_response(error: TaxonomyError) -> JSONResponse:
    """Map a taxonomy error to its response.

    ``retryable`` is read from the class here and nowhere else, which is
    what stops two raise sites of one class disagreeing.

    :param error: The error to render
    :return: The JSON response, carrying the single error envelope
    """
    match error:
        case ValidationError():
            status, retryable = 400, False
        case AuthorizationError():
            status, retryable = error.status, False
        case ConflictError():
            status, retryable = 409, False
        case TransientError():
            status, retryable = 503, True
        case FatalError():
            status, retryable = 500, False
        case _:
            # Reached only by a direct TaxonomyError, which is abstract by
            # intent: every raise site chooses one of the five. A sixth
            # SUBCLASS is caught statically instead, by the exhaustiveness
            # assertion in app/errors/_exhaustive.py -- assert_never cannot
            # serve here because the base class is itself instantiable, so
            # mypy cannot narrow this arm to Never.
            raise TypeError(
                f"{type(error).__name__} is not one of the five taxonomy "
                f"classes; every raise site must choose one"
            )

    return JSONResponse(
        status_code=status,
        content=_envelope(error, retryable=retryable).model_dump(),
    )


async def _handle(request: Request, exc: Exception) -> JSONResponse:
    """Render any taxonomy error raised during a request.

    :param request: The request being served; unused, no I/O is performed
    :param exc: The exception that reached the handler
    :return: The rendered response
    :raises Exception: The exception, when it is not a taxonomy error
    """
    if not isinstance(exc, TaxonomyError):
        raise exc
    return to_response(exc)


def register_error_handler(app: object) -> None:
    """Register the single handler on an application.

    :param app: The FastAPI application to register against
    :return: None
    """
    app.add_exception_handler(TaxonomyError, _handle)  # type: ignore[attr-defined]
