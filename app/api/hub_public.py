"""The public hub's pages, wired to the per-network read ceiling.

The handlers live in :mod:`app.hub.public.routes`, inside the public
package's import gate, which forbids it the authentication and ceiling
modules: the rate-limit counter is a table the hub reader cannot see and
the page code must not reach. So the ceiling is defined here, outside the
gate, and handed to the router when it is built. The handlers receive only
its verdict.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.auth.ceilings import CeilingBreach, CeilingChecker
from app.auth.client_address import viewer_prefix
from app.hub.public.routes import build_router

__all__ = ["public_read_allowed", "router"]


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
