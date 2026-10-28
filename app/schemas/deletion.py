"""Request and response bodies for the two deletion paths.

**The external route must work with no app and no session** [AC1.7.1,
RC-4], on a page a person reaches from the Play listing, so the only
thing it can establish ownership with is the OTP mechanism the app
already uses.

**The acknowledgements are deliberately thin.** A response that differed
between "deleted an account" and "there was no account" would be the
same existence oracle the issue endpoint spends a transaction-shaped
rollback to close, reintroduced on a public route that takes a bare
phone number.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import MoneyField
from app.schemas.phone import PhoneField

__all__ = [
    "DeletionOutcome",
    "DeletionRequest",
    "DeletionResponse",
    "DeletionSummaryResponse",
]


class DeletionRequest(BaseModel):
    """Ask for a deletion code, or confirm with one.

    **``code`` is optional and that is what selects the step.** The
    external route is one route with two steps rather than two routes,
    because ``PUBLIC_ROUTES`` declares exactly two external deletion
    entries and asserts its own count -- a separate code endpoint would
    be a ninth public route [BR3.2].

    :ivar phone: The number whose account is to be deleted
    :ivar code: The deletion code, or None to be sent one
    """

    model_config = ConfigDict(extra="forbid")

    phone: PhoneField
    code: str | None = Field(default=None, min_length=4, max_length=10)


class DeletionOutcome(BaseModel):
    """What the external route did: sent a code, or deleted.

    The two values are the two steps, and nothing distinguishes a known
    number from an unknown one within either. A second request for an
    account already deleted returns ``deleted`` [BR1.4]: on a deletion
    screen an error reads as "it did not work", and the action already
    succeeded.

    :ivar status: ``requested`` after a code is sent, ``deleted``
        after one is spent
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["requested", "deleted"]


class DeletionResponse(BaseModel):
    """The in-app acknowledgement.

    A distinct model from :class:`DeletionOutcome` because the in-app
    route has exactly one outcome: it is authenticated, so there is no
    code step. Carrying the two-valued model here would publish a
    ``requested`` the route can never return.

    **No row counts and no ``existed`` flag**, however useful they would
    be to a client. The in-app route could afford one -- the caller is
    authenticated -- and does not take one anyway: two shapes for one
    outcome is how the paths start to drift [BR3.1].

    :ivar status: Always ``deleted``
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["deleted"] = "deleted"


class DeletionSummaryResponse(BaseModel):
    """What stays after this account is deleted, for the confirm screen.

    Zeros for anyone who owns no batch: the screen then shows the plain
    variant rather than a refusal.

    :ivar batch_count: Batches the account owns
    :ivar student_count: Students in them
    :ivar outstanding: What those students still owe; it stays on their
        records and can no longer be collected
    """

    model_config = ConfigDict(extra="forbid")

    batch_count: int = Field(ge=0)
    student_count: int = Field(ge=0)
    outstanding: MoneyField
