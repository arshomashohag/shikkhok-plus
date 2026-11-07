"""Request and response bodies for the three auth endpoints.

**The issue response is deliberately contentless.** It carries no
``account_exists``, no ``message``, and nothing else that would differ
between a known and an unknown number -- the byte-identical requirement
is a property of this schema as much as of the handler [BR2.7].
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.phone import PhoneField

__all__ = [
    "IssueRequest",
    "IssueResponse",
    "MfaSignInRequest",
    "RefreshRequest",
    "TokenResponse",
    "VerifyRequest",
    "VerifyResponse",
]


class IssueRequest(BaseModel):
    """Ask for a code to be sent to a number.

    The number is **typed by the user** and never read from the SIM
    [AC1.1.6]: there is no device-side source for this field.

    :ivar phone: The destination number in international form
    """

    model_config = ConfigDict(extra="forbid")

    phone: PhoneField


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

    phone: PhoneField
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


class VerifyResponse(BaseModel):
    """What a verified SMS code yields: tokens, or the authenticator step.

    **For an account without two-step verification this is exactly the
    token pair it always was**, so clients built before the authenticator
    step keep working for everyone who has not turned it on. For an
    account with it on, the token fields are absent and ``mfa_challenge``
    carries the person to ``POST /v1/auth/mfa``.

    :ivar access_token: The bearer token, when no second step is needed
    :ivar refresh_token: The rotation token, likewise
    :ivar expires_in: Access-token lifetime in seconds, likewise
    :ivar mfa_required: True when an authenticator code must follow
    :ivar mfa_challenge: Carries the sign-in to that step; grants nothing
    :ivar mfa_expires_in: Seconds until the challenge lapses
    """

    model_config = ConfigDict(extra="forbid")

    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None
    mfa_required: bool = False
    mfa_challenge: str | None = None
    mfa_expires_in: int | None = None


class MfaSignInRequest(BaseModel):
    """The second step of signing in: exactly one of the two codes.

    :ivar challenge: From ``POST /v1/auth/verify``
    :ivar code: Six digits from the authenticator app
    :ivar recovery_code: A recovery code, if the phone with the app is lost
    """

    model_config = ConfigDict(extra="forbid")

    challenge: str = Field(min_length=1, max_length=2048)
    code: str | None = Field(default=None, min_length=6, max_length=8)
    recovery_code: str | None = Field(default=None, min_length=10, max_length=16)
