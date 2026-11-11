"""What every request is given, and how every failure leaves it.

Two concerns the taxonomy handler in :mod:`app.errors` cannot reach,
because that module is forbidden every I/O library, ``sqlalchemy``
included [NFR17.2], and these are about I/O:

* **The correlation id** [audit C-22]. A client may send
  ``X-Correlation-Id`` so its logs and ours line up, and the value is
  written into ``auth_audit_log.correlation_id``, a ``VARCHAR(64)``. It
  used to be trusted as sent: a longer value made every audit insert of
  that request fail, the audit savepoint swallowed the failure, and the
  rows recording a brute-force attempt or a replayed token were never
  written. Anything that is not a short, plain token is now replaced by a
  fresh id, and the id in force is returned on every response.
* **Failures that are not taxonomy errors** [audit C-17]. A dropped
  connection, an exhausted pool, a serialization failure, a statement or
  lock timeout, a constraint no service mapped, a malformed request or an
  outright bug each used to reach the client as Starlette's plain text or
  FastAPI's ``{"detail": ...}``. Both clients decide whether to offer a
  retry from the envelope's ``retryable``, so the failure most worth
  retrying was the one shown as final. Each is now rendered through the
  same envelope, by mapping it onto the taxonomy class it is an instance
  of in all but type.
* **A value the database cannot hold** [SEC-3]. An integer past
  ``int4``, a string past a column's width, a malformed literal: each
  raises ``DataError``, which used to fall through to the 500 handler
  and log its traceback. It is the caller's input that is wrong, so it
  renders as a 400 validation envelope and is logged by class only.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.errors import ConflictError, FatalError, TransientError, ValidationError
from app.errors.handler import to_response

__all__ = [
    "CORRELATION_HEADER",
    "correlation_id_from",
    "register_infrastructure_errors",
    "render_infrastructure_error",
]

log = logging.getLogger(__name__)

#: The header a client may send and that every response carries back.
CORRELATION_HEADER: Final = "X-Correlation-Id"

#: What a client-sent id may look like. The upper bound is the audit
#: column's width; the alphabet keeps the value inert in a log line.
_USABLE_ID: Final = re.compile(r"[A-Za-z0-9-]{1,64}")


def correlation_id_from(sent: str | None) -> str:
    """Return the client's correlation id if usable, else a fresh one.

    :param sent: The header value as received, or None
    :return: The id to bind to this request
    """
    if sent is not None and _USABLE_ID.fullmatch(sent):
        return sent
    return str(uuid.uuid4())


def render_infrastructure_error(error: Exception) -> JSONResponse | None:
    """Render a database failure as the envelope it amounts to, if it is one.

    Shared by the route-level handlers below and the request scope's
    commit, which runs after the route has returned and so is outside
    every handler.

    :param error: The exception that escaped
    :return: The rendered response, or None when it is not one of these
    """
    if isinstance(error, (OperationalError, PoolTimeoutError)):
        # A connection lost, the pool exhausted, a serialization failure,
        # a deadlock, a statement or lock timeout: all transient, all
        # worth the client's retry.
        return to_response(
            TransientError(
                code="SERVICE_UNAVAILABLE",
                message_key="error.temporarily_unavailable",
            )
        )
    if isinstance(error, DataError):
        # The input does not fit the column: an integer past int4, a
        # string past its width. No value is echoed back, and the
        # schema bounds that should have caught it first are gated by
        # tests/contract/test_int_bounds.py.
        return to_response(
            ValidationError(code="REQUEST_INVALID", message_key="error.unexpected")
        )
    if isinstance(error, IntegrityError):
        # A constraint a service did not map is a race lost to another
        # write; the state forbids this request as it stands.
        return to_response(
            ConflictError(code="CONFLICT", message_key="error.unexpected")
        )
    return None


def _with_correlation(request: Request, response: JSONResponse) -> JSONResponse:
    """Attach the request's correlation id to a rendered failure.

    :param request: The request being served
    :param response: The rendered failure
    :return: The same response
    """
    correlation = getattr(request.state, "correlation_id", None)
    if correlation:
        response.headers[CORRELATION_HEADER] = correlation
    return response


async def _database(request: Request, exc: Exception) -> JSONResponse:
    """Render a database failure raised inside a route.

    :param request: The request being served
    :param exc: The failure
    :return: The rendered envelope
    :raises Exception: The failure, when it is not a database one
    """
    rendered = render_infrastructure_error(exc)
    if rendered is None:
        raise exc
    log.warning(
        "database failure rendered as an envelope",
        extra={
            "error_class": type(exc).__name__,
            "correlation_id": getattr(request.state, "correlation_id", None),
        },
    )
    return _with_correlation(request, rendered)


async def _invalid_request(request: Request, exc: Exception) -> JSONResponse:
    """Render a request FastAPI could not parse, naming fields only.

    **No input value is echoed back.** FastAPI's own body carries each
    offending ``input``, which for this API is a phone number or a name;
    the envelope names where the problem is and nothing that was sent.

    :param request: The request being served
    :param exc: The validation failure
    :return: The rendered envelope, with FastAPI's 422 status kept
    """
    fields = (
        ",".join(
            ".".join(str(part) for part in issue.get("loc", ()))
            for issue in exc.errors()
        )
        if isinstance(exc, RequestValidationError)
        else ""
    )
    response = to_response(
        ValidationError(
            code="REQUEST_INVALID",
            message_key="error.unexpected",
            details={"fields": fields} if fields else None,
        )
    )
    # 422, as FastAPI answered before: what changes is the body, so a
    # client that branches on the status still does.
    response.status_code = 422
    return _with_correlation(request, response)


async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
    """Render a failure nothing anticipated, revealing nothing about it.

    :param request: The request being served
    :param exc: The failure
    :return: The rendered envelope
    """
    log.error(
        "unhandled failure",
        exc_info=exc,
        extra={"correlation_id": getattr(request.state, "correlation_id", None)},
    )
    return _with_correlation(
        request,
        to_response(FatalError(code="INTERNAL", message_key="error.unexpected")),
    )


def register_infrastructure_errors(app: FastAPI) -> None:
    """Register the envelope renderers for non-taxonomy failures.

    :param app: The application being built
    :return: None
    """
    app.add_exception_handler(OperationalError, _database)
    app.add_exception_handler(PoolTimeoutError, _database)
    app.add_exception_handler(IntegrityError, _database)
    app.add_exception_handler(DataError, _database)
    app.add_exception_handler(RequestValidationError, _invalid_request)
    # Registered on Exception, Starlette runs this from its outermost
    # error middleware: it renders the response and still re-raises, so
    # the server's own log keeps the traceback.
    app.add_exception_handler(Exception, _unexpected)
