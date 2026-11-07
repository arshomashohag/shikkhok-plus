"""Two-step verification settings on the wire.

Addressed to the account itself. The secret appears once, in the setup
response, and the recovery codes once, when issued; neither is ever
readable again.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MfaCodeRequest",
    "MfaProofRequest",
    "MfaRecoveryCodesResponse",
    "MfaSetupResponse",
    "MfaStatusResponse",
]


class MfaStatusResponse(BaseModel):
    """Whether two-step verification is on, and what to suggest.

    :ivar enabled: An authenticator app is set up
    :ivar enabled_at: When it was turned on
    :ivar recovery_codes_left: Unused recovery codes
    :ivar recommended: Suggest it: the account teaches or runs a centre
    :ivar required: It cannot be turned off: a platform administrator
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    enabled_at: dt.datetime | None = None
    recovery_codes_left: int
    recommended: bool
    required: bool


class MfaSetupResponse(BaseModel):
    """A new secret to add to an authenticator app.

    :ivar secret: The base32 secret, for typing in by hand
    :ivar otpauth_uri: The same secret as a link or a QR code
    """

    model_config = ConfigDict(extra="forbid")

    secret: str
    otpauth_uri: str


class MfaCodeRequest(BaseModel):
    """An authenticator code.

    :ivar code: Six digits from the app
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=8)


class MfaProofRequest(BaseModel):
    """Proof of the factor: exactly one of the two codes.

    :ivar code: Six digits from the app
    :ivar recovery_code: Or a recovery code
    """

    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, min_length=6, max_length=8)
    recovery_code: str | None = Field(default=None, min_length=10, max_length=16)


class MfaRecoveryCodesResponse(BaseModel):
    """Ten single-use recovery codes, shown once.

    :ivar recovery_codes: The codes
    """

    model_config = ConfigDict(extra="forbid")

    recovery_codes: list[str]
