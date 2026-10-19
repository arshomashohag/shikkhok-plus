"""The five closed exception classes.

Five, because they map to five distinct things a caller does next. A sixth
would mean a caller behaviour nobody has named; a looser hierarchy means
every layer re-derives what to do.

**Retryability is a property of the class, not a judgement at the raise
site.** The distinction is made once, by choosing a class, and every layer
above reads it off the type. A raise site that set ``retryable`` itself
would let two sites of the same class disagree, which is the condition this
hierarchy exists to prevent.
"""

from __future__ import annotations

from typing import Literal

__all__ = [
    "AuthorizationError",
    "ConflictError",
    "FatalError",
    "TaxonomyError",
    "TransientError",
    "ValidationError",
]


class TaxonomyError(Exception):
    """The base every raise site in the backend chooses a subclass of.

    :ivar code: A stable machine value the client switches on
    :ivar message_key: Names a client string resource, never English text
    :ivar details: Rendered by the client, never interpreted
    """

    def __init__(
        self,
        code: str,
        message_key: str,
        details: dict[str, str] | None = None,
    ) -> None:
        """Initialize a taxonomy error.

        :param code: A stable machine value
        :param message_key: The client string resource to render
        :param details: Optional typed payload, rendered not interpreted
        """
        super().__init__(code)
        self.code = code
        self.message_key = message_key
        self.details = details


class ValidationError(TaxonomyError):
    """The request is wrong. Fix and resubmit; never retry as-is."""


class AuthorizationError(TaxonomyError):
    """No lens grants this. Re-authenticate or stop.

    The one class carrying several statuses, because the taxonomy
    genuinely needs them: **401** when there is no token or it has
    expired, **403** when the token is valid but no lens reaches the
    resource, and **404** when saying 403 would itself disclose
    something.

    **404 is an authorization status here, not a routing one** [U4,
    NFR14.13]. A teacher reading another teacher's batch must not be
    told the batch exists: a 403 for a real id and a 404 for an invented
    one is an existence oracle, letting a caller enumerate which ids are
    real. So the refusal is deliberately indistinguishable from absence,
    which makes it an authorization decision wearing a not-found's
    clothes -- and it belongs in this class rather than in
    ``ValidationError``, whose 400 would say "your request was
    malformed" about a perfectly well-formed one.

    ``status`` is typed ``Literal[401, 403, 404]`` rather than ``int``. The
    handler's ``assert_never`` proves its match total over the five
    *classes*; it says nothing about values *inside* a branch. Constraining
    the status at the type makes a third value a build-time error at the
    raise site -- where the author knows which case it is -- instead of a
    runtime assertion inside the one piece of code whose whole requirement
    is to have no failure path.

    :ivar status: 401 for a missing or expired token, 404 where a 403
        would disclose existence, 403 otherwise
    """

    def __init__(
        self,
        code: str,
        message_key: str,
        status: Literal[401, 403, 404] = 403,
        details: dict[str, str] | None = None,
    ) -> None:
        """Initialize an authorization error.

        :param code: A stable machine value
        :param message_key: The client string resource to render
        :param status: 401 for a missing or expired token, 404 where a
            403 would disclose existence, else 403
        :param details: Optional typed payload
        """
        super().__init__(code, message_key, details)
        self.status: Literal[401, 403, 404] = status


class ConflictError(TaxonomyError):
    """Valid request; current state forbids it. Refetch and decide.

    Retrying as-is is wrong, which is why a cost-ceiling or balance refusal
    is this class and never :class:`TransientError`.
    """


class TransientError(TaxonomyError):
    """May succeed if repeated. Retry with backoff."""


class FatalError(TaxonomyError):
    """A bug, or unrecoverable. Do not retry; alert."""
