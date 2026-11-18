"""The public hub's four pages: search, owner, batch and the sitemap.

**Anonymous, cacheable, and read only as the hub reader.** Each handler
opens its own session, separate from the request's, calls one function of
:mod:`app.hub.public.queries` -- which drops to the hub reader before its
first statement -- renders through :mod:`app.hub.public.render`, and ends
that session with a rollback. Nothing is written in it.

**The read ceiling is handed in, not imported.** The package's import gate
forbids the ceiling module, so :func:`build_router` takes the dependency
that consumes one read (``app.api.hub_public`` supplies it) and each
handler sees only its verdict. That dependency commits its counter through
the request's own session before the handler opens the reading one.

**One 404 for everything that is not public**: an unknown locale, a
missing or unpublished owner, a draft, hidden or suspended batch, an
inactive batch, and a batch under an unpublished owner all answer the same
bytes, built once, echoing nothing from the request.

**Only six query keys are read** -- ``q``, ``district``, ``upazila``,
``subject``, ``level``, ``page`` -- each at its first value, so a tracking
parameter or a repeated key never changes a page and a cache key stays
bounded. ``q`` is cut to :data:`MAX_QUERY_LENGTH` characters before it is
searched or echoed.

No ``from __future__ import annotations`` here: the handlers' dependency
annotations name a closure variable, which FastAPI can resolve only from a
live annotation, never from a string.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.html import HUB_PAGE_CSP, html_response
from app.hub.public import queries, render
from app.hub.public.messages import LOCALES, Locale

__all__ = [
    "BATCH_CACHE",
    "MAX_QUERY_LENGTH",
    "NOT_FOUND_CACHE",
    "OWNER_CACHE",
    "QUERY_KEYS",
    "SEARCH_CACHE",
    "SITEMAP_CACHE",
    "build_router",
]

#: The query keys a search page reads; everything else is ignored.
QUERY_KEYS: Final[tuple[str, ...]] = (
    "q",
    "district",
    "upazila",
    "subject",
    "level",
    "page",
)

#: The longest search text read or echoed; the edge cuts it the same way.
MAX_QUERY_LENGTH: Final[int] = 200

#: The longest page number read; a longer one reads as the first page.
_MAX_PAGE_DIGITS: Final[int] = 9

#: Cache lifetimes, verbatim from the plan's Cache-Control table.
OWNER_CACHE: Final[str] = "public, max-age=60, s-maxage=600"
BATCH_CACHE: Final[str] = OWNER_CACHE
SEARCH_CACHE: Final[str] = "public, max-age=60, s-maxage=300"
SITEMAP_CACHE: Final[str] = "public, s-maxage=3600"
NOT_FOUND_CACHE: Final[str] = "public, s-maxage=60"

#: A refusal is about one caller, so no cache may keep it.
_REFUSED_CACHE: Final[str] = "no-store"

_HTML: Final[dict[int | str, dict[str, Any]]] = {
    200: {
        "description": "The page",
        "content": {"text/html": {"schema": {"type": "string"}}},
    },
    404: {
        "description": "Not public: the same page for every such path",
        "content": {"text/html": {"schema": {"type": "string"}}},
    },
    429: {
        "description": "Too many reads from this network this minute",
        "content": {"text/html": {"schema": {"type": "string"}}},
    },
}

_XML: Final[dict[int | str, dict[str, Any]]] = {
    200: {
        "description": "The sitemap",
        "content": {"application/xml": {"schema": {"type": "string"}}},
    },
    429: _HTML[429],
}

#: The six read keys, documented; the handler reads them from the request
#: itself so a repeated key yields its first value.
_SEARCH_PARAMETERS: Final[dict[str, Any]] = {
    "parameters": [
        {
            "name": key,
            "in": "query",
            "required": False,
            "schema": {"type": "string"},
        }
        for key in QUERY_KEYS
    ]
}


@contextmanager
def _reading(request: Request) -> Iterator[Session]:
    """Open a session of its own for one page read, and end it unwritten.

    Bound to the same engine as the request's session, so it reaches the
    same database, but it is a separate transaction: the hub reader role
    the queries set stays inside it, and the read ceiling's counter -- in
    the request's session -- never shares it.

    :param request: The incoming request
    :return: A context manager yielding the session
    """
    request_session: Session = request.state.session
    session = Session(bind=request_session.get_bind())
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _locale(value: str) -> Locale | None:
    """Accept exactly ``en`` or ``bn``.

    :param value: The path segment
    :return: The locale, or None for anything else
    """
    for locale in LOCALES:
        if value == locale:
            return locale
    return None


def _first(request: Request, key: str) -> str | None:
    """Read a query key's first value.

    :param request: The incoming request
    :param key: One of :data:`QUERY_KEYS`
    :return: The first value, or None when the key is absent
    """
    values = request.query_params.getlist(key)
    return values[0] if values else None


def _search_text(value: str | None) -> str | None:
    """Cut the search text to its cap before anything reads or echoes it.

    :param value: ``q`` as sent
    :return: At most :data:`MAX_QUERY_LENGTH` characters, or None if blank
    """
    if value is None:
        return None
    return value[:MAX_QUERY_LENGTH].strip() or None


def _page_number(value: str | None) -> int:
    """Read a page number, treating anything unreadable as the first page.

    :param value: The ``page`` value as sent
    :return: A page number, at least 1
    """
    if (
        value is None
        or not value.isascii()
        or not value.isdigit()
        or len(value) > _MAX_PAGE_DIGITS
    ):
        return 1
    return max(1, int(value))


def _not_found() -> HTMLResponse:
    """Answer a page that is not public.

    :return: The one 404 response
    """
    return html_response(
        render.not_found_page(),
        404,
        csp=HUB_PAGE_CSP,
        cache_control=NOT_FOUND_CACHE,
    )


def _refused() -> HTMLResponse:
    """Answer a read over the per-network ceiling.

    :return: The 429 response
    """
    return html_response(
        render.too_many_page(),
        429,
        csp=HUB_PAGE_CSP,
        cache_control=_REFUSED_CACHE,
    )


def build_router(read_allowed: Callable[..., bool]) -> APIRouter:
    """Build the four public pages around a read-ceiling dependency.

    :param read_allowed: A dependency that consumes one read and returns
        whether it was within the ceiling
    :return: The router
    """
    router = APIRouter(tags=["hub-public"])

    # Registered first: ``/hub/sitemap.xml`` would otherwise match
    # ``/hub/{locale}`` and answer as an unknown locale.
    @router.get("/hub/sitemap.xml", response_class=Response, responses=_XML)
    def hub_sitemap(
        request: Request, allowed: Annotated[bool, Depends(read_allowed)]
    ) -> Response:
        """Serve every public owner and batch page, in both locales.

        :param request: The incoming request
        :param allowed: Whether this read was within the ceiling
        :return: The sitemap, or the 429 page
        """
        if not allowed:
            return _refused()
        with _reading(request) as session:
            body = render.sitemap_xml(queries.sitemap(session))
        return Response(
            content=body,
            media_type="application/xml",
            headers={
                "Cache-Control": SITEMAP_CACHE,
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.get(
        "/hub/{locale}",
        response_class=HTMLResponse,
        responses=_HTML,
        openapi_extra=_SEARCH_PARAMETERS,
    )
    def hub_search(
        locale: str,
        request: Request,
        allowed: Annotated[bool, Depends(read_allowed)],
    ) -> HTMLResponse:
        """Serve the landing page, or a page of search results.

        :param locale: ``en`` or ``bn``
        :param request: The incoming request, whose six keys are read
        :param allowed: Whether this read was within the ceiling
        :return: The page, the 404 page, or the 429 page
        """
        if not allowed:
            return _refused()
        page_locale = _locale(locale)
        if page_locale is None:
            return _not_found()
        with _reading(request) as session:
            view = queries.search(
                session,
                locale=page_locale,
                q=_search_text(_first(request, "q")),
                district=_first(request, "district"),
                upazila=_first(request, "upazila"),
                subject=_first(request, "subject"),
                level=_first(request, "level"),
                page=_page_number(_first(request, "page")),
            )
            body = render.page(view, "search.html", page_locale)
        return html_response(body, csp=HUB_PAGE_CSP, cache_control=SEARCH_CACHE)

    @router.get(
        "/hub/{locale}/t/{owner_slug}", response_class=HTMLResponse, responses=_HTML
    )
    def hub_owner(
        locale: str,
        owner_slug: str,
        request: Request,
        allowed: Annotated[bool, Depends(read_allowed)],
    ) -> HTMLResponse:
        """Serve a published owner's page.

        :param locale: ``en`` or ``bn``
        :param owner_slug: The owner's slug
        :param request: The incoming request
        :param allowed: Whether this read was within the ceiling
        :return: The page, the 404 page, or the 429 page
        """
        if not allowed:
            return _refused()
        page_locale = _locale(locale)
        if page_locale is None:
            return _not_found()
        with _reading(request) as session:
            view = queries.owner_page(session, page_locale, owner_slug)
            if view is None:
                return _not_found()
            body = render.page(view, "owner.html", page_locale)
        return html_response(body, csp=HUB_PAGE_CSP, cache_control=OWNER_CACHE)

    @router.get(
        "/hub/{locale}/t/{owner_slug}/{batch_slug}",
        response_class=HTMLResponse,
        responses=_HTML,
    )
    def hub_batch(
        locale: str,
        owner_slug: str,
        batch_slug: str,
        request: Request,
        allowed: Annotated[bool, Depends(read_allowed)],
    ) -> HTMLResponse:
        """Serve a published batch's page under its published owner.

        :param locale: ``en`` or ``bn``
        :param owner_slug: The owner's slug
        :param batch_slug: The batch's slug
        :param request: The incoming request
        :param allowed: Whether this read was within the ceiling
        :return: The page, the 404 page, or the 429 page
        """
        if not allowed:
            return _refused()
        page_locale = _locale(locale)
        if page_locale is None:
            return _not_found()
        with _reading(request) as session:
            view = queries.batch_page(session, page_locale, owner_slug, batch_slug)
            if view is None:
                return _not_found()
            body = render.page(view, "batch.html", page_locale)
        return html_response(body, csp=HUB_PAGE_CSP, cache_control=BATCH_CACHE)

    return router
