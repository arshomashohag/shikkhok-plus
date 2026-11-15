"""Request and response bodies for the username routes [U1: C1].

**No username travels in a URL** [NFR3.5, Q4]. Both availability lookups
take the candidate in a JSON body, so the host's default access log
records only ``POST /v1/... HTTP/1.1`` for them and FR9.3 holds for that
log too.

**The lookup answers two fields and no more** [BR3.1, NFR1.4]: a status,
and for ``invalid`` the rule it broke. Never an account id, the stored
casing, a hold's expiry, or whether a name is held rather than taken.

**The username reaches a response only here and on ``MeResponse``**, and
only on the owner's own lens-exempt routes [BR8.1]; the every-route
privacy walk asserts it (:func:`app.contract.privacy.account_private_leaks`).
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "UsernameAvailabilityRequest",
    "UsernameAvailabilityResponse",
    "UsernameChangeRequest",
    "UsernameChangeResponse",
]

#: The longest input accepted; FR1's own 20 is judged on the server, so a
#: too-long name gets its own key rather than a generic 422 [BR1.3].
_INPUT = Field(max_length=64, description="What the person typed.")


class UsernameAvailabilityRequest(BaseModel):
    """Ask whether a name could be taken, in a body [NFR3.5].

    :ivar username: The candidate, as typed
    """

    model_config = ConfigDict(extra="forbid")

    username: str = _INPUT


class UsernameAvailabilityResponse(BaseModel):
    """What a lookup may say about a name [BR3.1].

    :ivar status: ``available``, ``unavailable`` (taken and held alike),
        ``invalid`` or ``reserved``
    :ivar message_key: For ``invalid``, which FR1 rule failed; else null
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["available", "unavailable", "invalid", "reserved"]
    message_key: str | None = Field(
        default=None,
        description="For invalid: which username rule failed (account.username.*).",
    )


class UsernameChangeRequest(BaseModel):
    """Choose the first username, rename, or take a released one back.

    :ivar username: The candidate, as typed
    :ivar password: The account's password: required when it already
        has a username (a rename, a reclaim or a case-only change),
        ignored for the first choice [BR5.3, BR6.1]
    """

    model_config = ConfigDict(extra="forbid")

    username: str = _INPUT
    password: str | None = Field(
        default=None,
        max_length=1024,
        description=(
            "Required when the account already has a username; ignored for "
            "the first choice."
        ),
    )


class UsernameChangeResponse(BaseModel):
    """The username as stored, and when it may next change.

    :ivar username: The display form, as stored. Owner-only: an
        ``OWN_ACCOUNT_FIELDS`` pair (ADR-010)
    :ivar next_change_at: When an ordinary rename is next allowed, or
        null when no limit applies now [BR6.2]
    """

    model_config = ConfigDict(extra="forbid")

    username: str
    next_change_at: dt.datetime | None = Field(
        description=(
            "When an ordinary rename is next allowed, as an ISO 8601 UTC "
            "instant; null when no limit applies."
        ),
    )
