"""Request and response bodies for a teacher's payment methods [P1-P3].

**These responses are the only ones carrying a method's number or
account fields**, and a contract test asserts that as an equality. The
destination snapshot a payment review embeds is declared here too, and
the routes carrying it are listed separately by the same gate.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

__all__ = [
    "FamilyPaymentMethodsResponse",
    "PaymentDestinationResponse",
    "PaymentMethodRequest",
    "PaymentMethodResponse",
]


class PaymentMethodRequest(BaseModel):
    """Add or replace a payment method.

    Completeness and length are checked by the service so every refusal
    reaches the client as the one error envelope.

    :ivar kind: ``mobile`` or ``bank``
    :ivar provider: The mobile service or the bank's name
    :ivar mobile_number: The number, mobile methods only
    :ivar account_number: The account number, bank methods only
    :ivar account_name: The account holder, bank methods only
    :ivar branch_name: The branch, bank methods only
    :ivar note: Optional text shown with the method
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["mobile", "bank"]
    provider: str | None = None
    mobile_number: str | None = None
    account_number: str | None = None
    account_name: str | None = None
    branch_name: str | None = None
    note: str | None = None


class PaymentMethodResponse(BaseModel):
    """One payment method as the teacher or a family reads it.

    :ivar method_id: The method
    :ivar kind: ``mobile`` or ``bank``
    :ivar provider: The mobile service or the bank's name
    :ivar mobile_number: The number, mobile methods only
    :ivar account_number: The account number, bank methods only
    :ivar account_name: The account holder, bank methods only
    :ivar branch_name: The branch, bank methods only
    :ivar note: Optional text shown with the method
    """

    method_id: uuid.UUID
    kind: Literal["mobile", "bank"]
    provider: str | None
    mobile_number: str | None
    account_number: str | None
    account_name: str | None
    branch_name: str | None
    note: str | None


class FamilyPaymentMethodsResponse(BaseModel):
    """The methods a family may pay to, with the server's suggestions.

    An empty ``methods`` list is the "ask the teacher" state.

    :ivar methods: The teacher's live methods, in display order
    :ivar services: Mobile service names the form suggests
    :ivar teacher_display_name: Who the money goes to, or null
    """

    methods: list[PaymentMethodResponse]
    services: list[str]
    teacher_display_name: str | None


class PaymentDestinationResponse(BaseModel):
    """Where a family said they paid, copied when they paid.

    A later edit or retirement of the method leaves this as it was, so
    the teacher checks against the number the family was shown.

    :ivar kind: ``mobile``, ``bank``, ``cash`` for money in hand, or
        ``legacy`` for a payment reported before methods existed
    :ivar channel: The service a ``legacy`` payment named, else null
    :ivar method_id: The method paid to, or null for cash
    :ivar provider: The mobile service or the bank's name
    :ivar mobile_number: The number, mobile methods only
    :ivar account_number: The account number, bank methods only
    :ivar account_name: The account holder, bank methods only
    :ivar branch_name: The branch, bank methods only
    :ivar note: The text shown with the method
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["mobile", "bank", "cash", "legacy"]
    channel: str | None = None
    method_id: uuid.UUID | None = None
    provider: str | None = None
    mobile_number: str | None = None
    account_number: str | None = None
    account_name: str | None = None
    branch_name: str | None = None
    note: str | None = None
