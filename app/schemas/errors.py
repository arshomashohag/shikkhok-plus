"""The single error envelope every error response carries.

Three properties, each load-bearing:

* **``retryable`` is server-provided.** The client holds no business logic
  [TC-9, D-31], so it does not infer retryability from an HTTP status -- it
  is told.
* **``code`` is a stable machine value.** The client switches on it, never
  on text.
* **``message_key`` rather than ``message``.** A server-authored English
  string cannot be localized, and in a Bangla-first UI that guarantees
  untranslated English error text in front of a teacher [TC-15, D-43].
  ``extra="forbid"`` makes the absence of a ``message`` field structural
  rather than a convention somebody maintains: such a field fails schema
  validation and the committed-schema diff gate.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ErrorBody", "ErrorEnvelope"]


class ErrorBody(BaseModel):
    """The error payload.

    :ivar code: A stable machine value the client switches on
    :ivar retryable: Derived from the exception class at the handler
    :ivar message_key: Names a client string resource
    :ivar details: Typed per code; rendered, never interpreted
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="Stable machine value; never message text.")
    retryable: bool = Field(
        description="Server-provided. The client is told, never infers."
    )
    message_key: str = Field(
        description="Names a client string resource. No English is emitted."
    )
    details: dict[str, str] | None = Field(
        default=None,
        description="Typed per code. Rendered, never interpreted.",
    )


class ErrorEnvelope(BaseModel):
    """The shape of every error response in the system.

    :ivar error: The error payload
    """

    model_config = ConfigDict(extra="forbid")

    error: ErrorBody
