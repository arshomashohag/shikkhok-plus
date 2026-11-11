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

The page carries no script, no stylesheet, no image and no inline
style, so the policy grants nothing but posting its own form.
"""

from __future__ import annotations

from typing import Final

from fastapi.responses import HTMLResponse

__all__ = ["HTML_SECURITY_HEADERS", "html_response"]

#: The headers every HTML page is served with.
HTML_SECURITY_HEADERS: Final[dict[str, str]] = {
    "Content-Security-Policy": (
        "default-src 'none'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def html_response(content: str, status_code: int = 200) -> HTMLResponse:
    """Build an HTML response carrying the security headers.

    :param content: The page
    :param status_code: The HTTP status
    :return: The response
    """
    return HTMLResponse(
        content=content, status_code=status_code, headers=HTML_SECURITY_HEADERS
    )
