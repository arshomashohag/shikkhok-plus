"""The public hub's pages, wired to the per-network read ceiling.

The handlers live in :mod:`app.hub.public.routes`, inside the public
package's import gate, which forbids it the authentication and ceiling
modules: the rate-limit counter is a table the hub reader cannot see and
the page code must not reach. So the ceiling is defined here, outside the
gate, and handed to the router when it is built. The handlers receive only
its verdict.

**The page-view count is here too, for the same reason** [0050]. Its
counting image writes a table the hub reader cannot see, so its handler
sits outside the gate with the ceiling, and never touches a page view
model.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Final

import sqlalchemy as sa
from fastapi import Depends, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.auth.ceilings import CeilingBreach, CeilingChecker
from app.auth.client_address import viewer_prefix
from app.hub.public.routes import build_router

__all__ = ["VIEW_PIXEL", "VIEW_PIXEL_PATH", "public_read_allowed", "router"]

_log = logging.getLogger(__name__)

#: The counting image's path: ``o`` for an owner page, ``b`` for a batch
#: page, and the page's public id.
VIEW_PIXEL_PATH: Final[str] = "/hub/v/{kind}/{page_id}.gif"

#: A transparent 1x1 GIF, the same bytes for every answer.
VIEW_PIXEL: Final[bytes] = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\x00\x00\x00"
    b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00"
    b"\x00\x02\x02D\x01\x00;"
)

#: Each page kind's path letter, its ``hub_page_kind`` value, and the public
#: view that says whether the page is published. Only a published page is
#: counted; an unknown id counts nothing.
_KINDS: Final[dict[str, tuple[str, str]]] = {
    "o": ("owner", "SELECT 1 FROM hub_public_owner WHERE owner_id = :id"),
    "b": ("batch", "SELECT 1 FROM hub_public_batch WHERE batch_id = :id"),
}

_COUNT: Final[str] = """
    INSERT INTO hub_page_view (page_kind, page_id, day, views)
    SELECT CAST(:kind AS hub_page_kind), :id,
           (now() AT TIME ZONE 'Asia/Dhaka')::date, 1
    WHERE EXISTS ({published})
    ON CONFLICT (page_kind, page_id, day)
    DO UPDATE SET views = hub_page_view.views + 1
"""


def public_read_allowed(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> bool:
    """Consume one page read from the viewer's per-minute allowance.

    The counter is written and committed through the request's own
    session, as the application role, before the page opens its separate
    reading session -- never inside the hub reader's transaction.

    :param request: The incoming request
    :param session: The request-scoped session, used for the counter only
    :return: True when the read is allowed, False when the network has
        made ``HUB_PUBLIC_READ_IP_MINUTE`` reads this minute
    """
    try:
        CeilingChecker(session).check_and_consume_hub_public_read(
            viewer_prefix(request)
        )
    except CeilingBreach:
        return False
    return True


#: The four public pages, each consuming one read before it renders.
router = build_router(public_read_allowed)


def _pixel() -> Response:
    """Answer the counting image: never cached, so every load reaches here.

    :return: The 1x1 image
    """
    return Response(
        content=VIEW_PIXEL,
        media_type="image/gif",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


def _page_id(value: str) -> uuid.UUID | None:
    """Read a page id, or None for anything that is not one.

    :param value: The path segment before ``.gif``
    :return: The id, or None
    """
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


@router.get(
    VIEW_PIXEL_PATH,
    response_class=Response,
    responses={
        200: {
            "description": "A 1x1 image, the same for every request",
            "content": {"image/gif": {"schema": {"type": "string"}}},
        }
    },
)
def hub_page_view(
    kind: str,
    page_id: str,
    allowed: Annotated[bool, Depends(public_read_allowed)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Count one view of a published owner or batch page [0050].

    **Only a number is written**: the page and the Bangladesh day, plus one.
    Nothing about the request -- address, cookie, user agent, referrer or
    account -- is read or stored. The read ceiling bounds how fast one
    network can count, and a request over it, or naming no published page,
    counts nothing. Every request gets the same image, so the answer says
    nothing about whether a page exists.

    Counting is best effort: a database failure is logged and the image is
    still returned, since a missed count must never break a page.

    :param kind: ``o`` for an owner page, ``b`` for a batch page
    :param page_id: The page's public id
    :param allowed: Whether this request was within the read ceiling
    :param session: The request-scoped session, as the application role
    :return: The 1x1 image
    """
    target = _KINDS.get(kind)
    parsed = _page_id(page_id)
    if not allowed or target is None or parsed is None:
        return _pixel()
    page_kind, published = target
    try:
        session.execute(
            sa.text(_COUNT.format(published=published)),
            {"kind": page_kind, "id": parsed},
        )
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        _log.warning("hub page view not counted", extra={"page_kind": page_kind})
    return _pixel()
