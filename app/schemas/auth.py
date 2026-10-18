"""Request and response bodies for the three auth endpoints.

**The issue response is deliberately contentless.** It carries no
``account_exists``, no ``message``, and nothing else that would differ
between a known and an unknown number -- the byte-identical requirement
is a property of this schema as much as of the handler [BR2.7].
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "IssueRequest",
    "IssueResponse",
    "RefreshRequest",
    "TokenResponse",
    "VerifyRequest",
]


class IssueRequest(BaseModel):
    """Ask for a code to be sent to a number.

    The number is **typed by the user** and never read from the SIM
    [AC1.1.6]: there is no device-side source for this field.

    :ivar phone: The destination number in international form
    """

    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=8, max_length=20)


class IssueResponse(BaseModel):
    """The response to an issue request, for **any** number.

    One field, and it is a fixed string. Anything varying between the
    known and unknown branches -- a count, a timestamp, a message -- is
    the existence oracle re-entering through the schema.

    :ivar status: Always ``requested``
    """

    model_config = ConfigDict(extra="forbid")

    status: str = "requested"


class VerifyRequest(BaseModel):
    """Present a code for verification.

    :ivar phone: The number the code was issued for
    :ivar code: The six-digit code
    """

    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=8, max_length=20)
    code: str = Field(min_length=4, max_length=10)


class RefreshRequest(BaseModel):
    """Present a refresh token for rotation.

    :ivar refresh_token: The opaque token previously issued
    """

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=16, max_length=512)


class TokenResponse(BaseModel):
    """A freshly issued token pair.

    **No lens and no role here either.** The response says nothing about
    what the account may do; that is resolved per request from the data
    [BR1.1].

    :ivar access_token: The short-lived bearer token
    :ivar refresh_token: The long-lived rotation token
    :ivar expires_in: Access-token lifetime in seconds
    """

    model_config = ConfigDict(extra="forbid")

    access_token: str
    refresh_token: str
    expires_in: int
