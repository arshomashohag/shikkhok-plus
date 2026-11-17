"""HEAD on the public hub's pages: GET's answer, without its body.

CloudFront forwards a viewer's HEAD to the origin, and link checkers and
crawlers send one before a GET. FastAPI registers a route for exactly the
methods it names, so the hub's four GET routes answered HEAD with 405.

**Served as GET, not registered as HEAD.** Registering HEAD would add a
``(HEAD, path)`` pair beside each page's ``(GET, path)``, and every route
gate counts pairs: ``PUBLIC_ROUTES`` would grow from nineteen to
twenty-three and ``PUBLIC_CACHEABLE_ROUTES`` would hold a method other
than GET, changing what both stated counts mean. So nothing is
registered: :class:`HeadAsGet` hands a HEAD under ``/hub`` to the same GET
handler, which the gates already cover -- the same lensless, read-only,
cacheable page -- and drops the body on the way out. Status and every
header, ``Content-Length`` included, are GET's, as HTTP requires of HEAD.

Only paths under ``/hub``; HEAD anywhere else is refused as before.
"""

from __future__ import annotations

from typing import Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

__all__ = ["HUB_PREFIX", "HeadAsGet"]

#: The public hub's path prefix; ``/hub`` itself and everything below it.
HUB_PREFIX: Final[str] = "/hub"


def _is_hub(path: str) -> bool:
    """Report whether a path is the hub's.

    :param path: The request path
    :return: True for ``/hub`` and anything below ``/hub/``
    """
    return path == HUB_PREFIX or path.startswith(f"{HUB_PREFIX}/")


class HeadAsGet:
    """Serve a HEAD under ``/hub`` with the GET handler, minus the body."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the application.

        :param app: The rest of the stack
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass a request through, as GET when it is a HEAD on the hub.

        :param scope: The connection scope
        :param receive: The request channel
        :param send: The response channel
        :return: None
        """
        if (
            scope["type"] != "http"
            or scope["method"] != "HEAD"
            or not _is_hub(scope["path"])
        ):
            await self.app(scope, receive, send)
            return

        async def bodiless(message: Message) -> None:
            """Forward the response with every body chunk emptied.

            :param message: One response message
            :return: None
            """
            if message["type"] == "http.response.body":
                if message.get("more_body", False):
                    return
                message = {**message, "body": b""}
            await send(message)

        # A copy, so the server's own scope still says HEAD and it sends
        # no body of its own accord either.
        await self.app({**scope, "method": "GET"}, receive, bodiless)
