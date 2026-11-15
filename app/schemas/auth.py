"""Request and response bodies for the three auth endpoints.

**The issue response is deliberately contentless.** It carries no
``account_exists``, no ``message``, and nothing else that would differ
between a known and an unknown number -- the byte-identical requirement
is a property of this schema as much as of the handler [BR2.7].
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.accounts.identifier import LoginSubject, classify_login
from app.auth.passwords import MAX_LENGTH, MIN_LENGTH
from app.schemas.identifier import IdentifierFields

__all__ = [
    "IssueRequest",
    "IssueResponse",
    "MfaSignInRequest",
    "PasswordSetupRequest",
    "PasswordSignInRequest",
    "RefreshRequest",
    "TokenResponse",
    "VerifyRequest",
    "VerifyResponse",
]


class IssueRequest(IdentifierFields):
    """Ask for a code to be sent to a number or an address.

    The number is **typed by the user** and never read from the SIM
    [AC1.1.6]: there is no device-side source for this field.

    Since passwords [0032] a code no longer signs anyone in: it completes
    a signup, recovers a forgotten password, or gives an account its
    first one, by way of ``POST /v1/auth/password/setup``.

    :ivar phone: The destination number, or None
    :ivar email: The destination address, or None; exactly one is given
    """

    model_config = ConfigDict(extra="forbid")


class IssueResponse(BaseModel):
    """The response to an issue request, for **any** number.

    One field, and it is a fixed string. Anything varying between the
    known and unknown branches -- a count, a timestamp, a message -- is
    the existence oracle re-entering through the schema.

    :ivar status: Always ``requested``
    """

    model_config = ConfigDict(extra="forbid")

    status: str = "requested"


class VerifyRequest(IdentifierFields):
    """Present a code for verification.

    :ivar phone: The number the code was issued for, or None
    :ivar email: Or the address it was emailed to
    :ivar code: The six-digit code
    :ivar username: A replacement username, sent only after the draft's
        own was answered ``account.username.unavailable`` [U1: BR2.5].
        Ignored when the destination already has an account
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=4, max_length=10)
    username: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Optional replacement username, used only after "
            "account.username.unavailable."
        ),
    )


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
    """What a verified code or a password yields.

    **From ``POST /v1/auth/verify``** [0032]: never tokens. A
    ``password_setup_token`` carries the person to
    ``POST /v1/auth/password/setup``, and ``mfa_required`` says the
    authenticator code must come with the password there.

    **From ``POST /v1/auth/password``**: the token pair, or, for an
    account with two-step verification on, ``mfa_challenge`` for the
    existing ``POST /v1/auth/mfa``.

    :ivar access_token: The bearer token, when signed in
    :ivar refresh_token: The rotation token, likewise
    :ivar expires_in: Access-token lifetime in seconds, likewise
    :ivar mfa_required: True when an authenticator code must follow
    :ivar mfa_challenge: Carries a password sign-in to that step
    :ivar mfa_expires_in: Seconds until the challenge lapses
    :ivar password_setup_token: From a verified code: the right to choose
        a password, and nothing else
    :ivar password_setup_expires_in: Seconds until it lapses
    """

    model_config = ConfigDict(extra="forbid")

    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None
    mfa_required: bool = False
    mfa_challenge: str | None = None
    mfa_expires_in: int | None = None
    password_setup_token: str | None = None
    password_setup_expires_in: int | None = None


#: The published bounds. The server enforces them with its own messages
#: (:func:`app.auth.passwords.check_policy`), so the schema states them
#: for clients and does not refuse a length itself: a 422 here would
#: replace the localized "too short" with a generic validation error.
_PASSWORD_DESCRIPTION = (
    f"{MIN_LENGTH} to {MAX_LENGTH} characters. Very common passwords are refused."
)


class PasswordSignInRequest(IdentifierFields):
    """Sign in with a username, a phone number or an email, and a password.

    **Exactly one of ``login``, ``phone`` and ``email``** [U1: BR4.1,
    NFR6.1]. ``login`` is what the person typed into the one field and is
    classified on the server (ADR-003); ``phone`` and ``email`` keep their
    meaning, so a client that sends them is unchanged. The inherited
    exactly-one-of-two validator is overridden BY NAME, so a login-only
    body is accepted here while :class:`IdentifierFields` itself, which
    every other request uses, still refuses a body with neither.

    :ivar login: A username, number or address, as typed, or None
    :ivar phone: The account's number, or None
    :ivar email: Or its address
    :ivar password: The password
    """

    model_config = ConfigDict(extra="forbid")

    login: str | None = Field(
        default=None,
        max_length=254,
        description=(
            "What the person typed: a username, a phone number or an email "
            "address, classified on the server. Exactly one of login, "
            "phone and email."
        ),
    )
    password: str = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def _exactly_one(self) -> PasswordSignInRequest:
        """Refuse none, and more than one, of the three [NFR6.1].

        :return: The request
        :raises ValueError: None, or more than one, was given
        """
        given = [
            value for value in (self.login, self.phone, self.email) if value is not None
        ]
        if len(given) != 1:
            raise ValueError("give exactly one of login, phone and email")
        return self

    @property
    def subject(self) -> LoginSubject:
        """Return who this sign-in names, classified [BR4.2].

        :return: A phone or email identifier, or a username subject
        :raises ValidationError: ``login`` holds ``@`` and is no address
        """
        if self.login is not None:
            return classify_login(self.login)
        return self.identifier


class PasswordSetupRequest(BaseModel):
    """Choose a password with the token a verified code yielded.

    :ivar token: ``password_setup_token`` from ``POST /v1/auth/verify``
    :ivar password: The new password
    :ivar code: Six digits from the authenticator app, when
        ``mfa_required`` was true
    :ivar recovery_code: Or a recovery code
    """

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=2048)
    password: str = Field(max_length=1024, description=_PASSWORD_DESCRIPTION)
    code: str | None = Field(default=None, min_length=6, max_length=8)
    recovery_code: str | None = Field(default=None, min_length=10, max_length=16)


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
