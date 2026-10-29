"""The staging outbox route. Not registered in production.

**This route hands out an OTP**, which is why it does not exist unless
the environment permits it and an operator opted in. See
:mod:`app.gateway.outbox` for the three independent mechanisms.

It is on ``PUBLIC_ROUTES`` because it must be reachable before anyone
is authenticated -- that is its whole purpose. The route-enumeration
gate therefore needs it allowlisted, and allowlisting a route that only
exists in staging is itself worth a second look, which is why this
module is short enough to read in full.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.errors import ValidationError
from app.gateway.outbox import read_outbox
from app.schemas.phone import PhoneField

__all__ = ["router"]

router = APIRouter(prefix="/staging", tags=["staging"])


@router.get("/last-otp")
def last_otp(
    phone: Annotated[PhoneField, Query()],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    """Return the most recent unsent message for a number.

    The **whole rendered message**, not the extracted code: parsing a
    code out of it here would mean this module knowing the message
    template, and a template change would silently break the one tool
    an operator uses to sign in.

    :param phone: The number the code was requested for
    :param session: The request-scoped session
    :return: The rendered message and when it was recorded
    :raises ValidationError: No unexpired message for that number
    """
    entry = read_outbox(session, phone=phone)
    if entry is None:
        raise ValidationError(
            code="NO_STAGING_MESSAGE",
            message_key="staging.outbox.empty",
        )
    return {
        "phone": entry.phone,
        "message": entry.message,
        "recorded_at": entry.recorded_at.isoformat(),
    }
