"""The application object.

U2 created this with **no routes**: it owned the contract and the gates
that check it, and the Units owning the features add the endpoints. U3 is
the first such Unit, and it adds four -- three auth routes and the health
check.

**One transaction per request**, opened by the middleware and committed
by the endpoint. A repository method that committed on its own would make
a partial write possible across the pair of statements the OTP path
depends on being atomic.

**The middleware commits only a successful response** and rolls back
every 4xx and 5xx, whether the error escaped as an exception or was
already rendered by the taxonomy handler [PA-ARCH-1].
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker
from starlette.concurrency import run_in_threadpool

from app.config import check_startup_configuration
from app.db.session import build_engine
from app.errors import register_error_handler
from app.logging_setup import configure_logging
from app.web_origins import register_web_origins

__all__ = ["app", "create_app"]

#: Responses at or above this status roll the request transaction back.
_FIRST_ERROR_STATUS = 400


def create_app() -> FastAPI:
    """Build the application.

    :return: The configured application with this Unit's routes
    :raises ConfigurationError: A production value is missing
    """
    # BEFORE anything is wired. A production process missing a value
    # would otherwise serve requests while silently lacking a
    # guarantee -- no SMS sent, or the test ceiling as the money
    # ceiling -- and nothing would report it.
    check_startup_configuration()

    # **Before the first log line.** Several call sites carry their
    # real content in `extra=` -- the SMS gateway's outcome and
    # provider code above all -- and the default formatter drops it,
    # so `sms send` reached production carrying no verdict at all.
    configure_logging()

    app = FastAPI(
        title="ShikkhokPlus API",
        version="1.0.0",
        description=(
            "Private tuition management. Every money value crosses this "
            "boundary as a JSON string; every lens-scoped response names "
            "the lens that produced it."
        ),
    )
    register_error_handler(app)
    _register_request_scope(app)
    # After the request scope, so it wraps it: a CORS preflight is
    # answered without opening a database session. Off unless the web
    # client is served from its own origin; see app/web_origins.py.
    register_web_origins(app)
    _register_routes(app)
    _publish_shared_components(app)
    return app


def _register_routes(app: FastAPI) -> None:
    """Attach this Unit's routers.

    :param app: The application being built
    :return: None
    """
    from app.api.accounts import router as accounts_router
    from app.api.admin import router as admin_router
    from app.api.admin_auth import router as admin_auth_router
    from app.api.analytics import router as analytics_router
    from app.api.auth import router as auth_router
    from app.api.batches import router as batches_router
    from app.api.centres import router as centres_router
    from app.api.deletion import router as deletion_router
    from app.api.expenses import router as expenses_router
    from app.api.extra_fees import router as extra_fees_router
    from app.api.fees import router as fees_router
    from app.api.guardian import router as guardian_router
    from app.api.health import router as health_router
    from app.api.help import router as help_router
    from app.api.marks import router as marks_router
    from app.api.me import router as me_router
    from app.api.my_classes import router as my_classes_router
    from app.api.my_exams import router as my_exams_router
    from app.api.notifications import router as notifications_router
    from app.api.payment_methods import router as payment_methods_router
    from app.api.payroll import router as payroll_router
    from app.api.staff import router as staff_router
    from app.api.students import router as students_router
    from app.api.teaching import router as teaching_router
    from app.api.timetable import router as timetable_router

    # Recorded as they are included, so the contract gates enumerate
    # what this application ACTUALLY registered. A gate reading a
    # hardcoded list cannot see a router added later.
    app.state.included_routers = []

    for router in (
        accounts_router,
        admin_router,
        admin_auth_router,
        analytics_router,
        auth_router,
        batches_router,
        centres_router,
        deletion_router,
        expenses_router,
        extra_fees_router,
        fees_router,
        guardian_router,
        health_router,
        help_router,
        marks_router,
        me_router,
        my_classes_router,
        my_exams_router,
        notifications_router,
        payment_methods_router,
        payroll_router,
        staff_router,
        students_router,
        teaching_router,
        timetable_router,
    ):
        app.include_router(router)
        app.state.included_routers.append(router)

    # NOT REGISTERED unless the environment permits it. An absent route
    # rather than a route that refuses: there is nothing to reach, no
    # handler to misconfigure, and no 404 that might one day become a
    # 200 through an unrelated change.
    from app.gateway.outbox import outbox_enabled

    if outbox_enabled():
        from app.api.staging import router as staging_router

        app.include_router(staging_router)
        app.state.included_routers.append(staging_router)


def _register_request_scope(app: FastAPI) -> None:
    """Open one session and one correlation id per request.

    The correlation id is generated here so **every** log line and audit
    row in the request can carry it, including ones written before any
    handler runs [NFR8.6].

    :param app: The application being built
    :return: None
    """

    @app.middleware("http")
    async def request_scope(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Bind a session and a correlation id to this request.

        :param request: The incoming request
        :param call_next: The rest of the stack
        :return: The response
        """
        request.state.correlation_id = request.headers.get("X-Correlation-Id") or str(
            uuid.uuid4()
        )

        engine = _engine_for(app)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        session = factory()
        request.state.session = session
        try:
            response = await call_next(request)
            # Committing is decided by the STATUS, not by whether an
            # exception escaped [PA-ARCH-1]. The taxonomy handler runs
            # inside `call_next` and turns a raised ValidationError or
            # ConflictError into an ordinary 4xx response, so by here
            # the exception is gone -- and a service that flushed and
            # then raised would have its partial write committed while
            # the client was told it failed. A write that must survive
            # a refusal (a failed OTP attempt, a reuse-detected token
            # family) is committed by its service before it raises,
            # which this does not undo.
            if response.status_code < _FIRST_ERROR_STATUS:
                await run_in_threadpool(session.commit)
            else:
                await run_in_threadpool(session.rollback)
            return response
        except Exception:
            await run_in_threadpool(session.rollback)
            raise
        finally:
            # Off the event loop [PERF-7]: each of the three is a
            # blocking round trip on a sync driver, and on the loop it
            # stalls every other in-flight request for its duration.
            # Moving them changes no transaction boundary -- the RLS
            # account is set with `set_config(..., true)` inside the
            # request transaction, and commit or rollback discards it
            # wherever they run.
            await run_in_threadpool(session.close)


def _engine_for(app: FastAPI) -> Engine:
    """Return the application's engine, building it once.

    :param app: The application
    :return: The engine
    """
    engine: Engine | None = getattr(app.state, "engine", None)
    if engine is None:
        engine = build_engine()
        app.state.engine = engine
    return engine


def _publish_shared_components(app: FastAPI) -> None:
    """Place the shared components in the generated document.

    FastAPI emits a component only when some route references it, and
    **no money crosses this Unit's surface** -- U3 is authentication, so
    its four routes reference neither ``Money`` nor, on their success
    paths, the error envelope.

    Without this, both would be **absent from the committed contract**,
    so a regression in the one definition every money property must
    reference, or in the envelope every error response carries, would not
    appear in the diff the reviewer reads. The gate would still pass,
    over nothing.

    This stays until a Unit whose routes genuinely reference them lands,
    at which point it becomes a no-op rather than a lie.

    **That Unit is D3, and this is now a no-op** [functional-spec § 8].
    U4 made ``Money`` referenced by real response properties, and D3's
    nine fee routes declare their 400, 401, 403 and 409 responses
    against ``ErrorEnvelope`` — so both components would be emitted
    whether or not this function ran.

    It is **kept rather than deleted**, and the reason is the one this
    docstring already gave: a Unit whose routes stopped referencing
    either would silently drop it from the committed contract, and the
    diff gate would pass over the absence. ``test_the_injection_is_now
    _redundant`` asserts the no-op is real rather than claimed, so the
    sentence above cannot quietly become false again — which is this
    project's rule that a comment stating a fact needs something
    checking it.

    :param app: The application whose schema is being built
    :return: None
    """
    from app.schemas.errors import ErrorEnvelope
    from app.schemas.money import Money

    build = app.openapi

    def openapi() -> dict[str, Any]:
        """Build the document once, on first use, with the components in.

        **Lazy, and that is a measured requirement** [CI time]. Building
        the whole document costs about half a second and grows with every
        route; done inside :func:`create_app` it was paid by every test
        that builds an app, hundreds of times a run, and took the backend
        job past its time limit. The document served and committed is
        unchanged: the same injection, applied to the same document, the
        first time anything asks for it.

        :return: The document
        """
        if app.openapi_schema is None:
            document = build()
            schemas = document.setdefault("components", {}).setdefault("schemas", {})
            for model in (Money, ErrorEnvelope):
                schemas.update(
                    model.model_json_schema(
                        ref_template="#/components/schemas/{model}"
                    ).pop("$defs", {})
                )
                schemas[model.__name__] = {
                    key: value
                    for key, value in model.model_json_schema(
                        ref_template="#/components/schemas/{model}"
                    ).items()
                    if key != "$defs"
                }
            app.openapi_schema = document
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


app = create_app()
