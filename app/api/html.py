"""The one way this API answers with an HTML page [SEC-7].

The external deletion page is the product's only HTML, and it is a
state-changing form reachable without a session. Served bare, it could
be framed by a phishing page that borrows the genuine origin to talk a
person into typing their code, and nothing told a browser not to sniff
it or to keep its URL out of a ``Referer``.

So every HTML response goes through :func:`html_response`, which sets
the headers below. They are set by the application rather than only at
the CDN, so they hold on every path to the page, including a direct hit
on the origin.

The deletion page carries no script, no stylesheet, no image and no
inline style, so its policy (:data:`DEFAULT_CSP`) grants nothing but
posting its own form. The public hub's pages add one same-origin
stylesheet and nothing executable (:data:`HUB_PAGE_CSP`), and say how
long a cache may keep them.
"""

from __future__ import annotations

from typing import Final

from fastapi.responses import HTMLResponse

__all__ = ["DEFAULT_CSP", "HTML_SECURITY_HEADERS", "HUB_PAGE_CSP", "html_response"]

#: The policy of a page that loads nothing and posts only its own form.
DEFAULT_CSP: Final[str] = (
    "default-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)

#: The public hub's page policy, verbatim from the plan: its own
#: stylesheet, images and fonts, a search form posting to itself, and no
#: script of any kind. The JSON-LD data block is not a script a browser
#: runs, so nothing here grants one.
HUB_PAGE_CSP: Final[str] = (
    "default-src 'none'; style-src 'self'; img-src 'self'; font-src 'self'; "
    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)

#: The headers every HTML page is served with.
HTML_SECURITY_HEADERS: Final[dict[str, str]] = {
    "Content-Security-Policy": DEFAULT_CSP,
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def html_response(
    content: str,
    status_code: int = 200,
    *,
    csp: str = DEFAULT_CSP,
    cache_control: str | None = None,
) -> HTMLResponse:
    """Build an HTML response carrying the security headers.

    :param content: The page
    :param status_code: The HTTP status
    :param csp: The page's Content-Security-Policy
    :param cache_control: The ``Cache-Control`` value, or None to send none
    :return: The response
    """
    headers = {**HTML_SECURITY_HEADERS, "Content-Security-Policy": csp}
    if cache_control is not None:
        headers["Cache-Control"] = cache_control
    return HTMLResponse(content=content, status_code=status_code, headers=headers)
