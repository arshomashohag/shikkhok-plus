"""The phone-or-email pair every identifying request carries.

**Exactly one of the two** [0032]. A request naming both would make the
server choose which to believe, and a request naming neither is not a
request for anyone; both are refused at the schema, so no handler ever
sees them.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from app.accounts.identifier import Channel, Identifier, canonical_email
from app.schemas.phone import PhoneField

__all__ = ["EmailField", "IdentifierFields"]

#: An email address, stored and compared trimmed and lowercased.
EmailField = Annotated[
    str,
    BeforeValidator(canonical_email),
    Field(
        description=(
            "An email address, at most 254 characters. It is stored and "
            "returned trimmed and lowercased."
        ),
    ),
]


class IdentifierFields(BaseModel):
    """A phone number or an email address: exactly one.

    :ivar phone: A Bangladeshi mobile number, or None
    :ivar email: An email address, or None
    """

    phone: PhoneField | None = None
    email: EmailField | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> IdentifierFields:
        """Refuse both and neither.

        :return: The request
        :raises ValueError: Both or neither were given
        """
        if (self.phone is None) == (self.email is None):
            raise ValueError("give exactly one of phone and email")
        return self

    @property
    def identifier(self) -> Identifier:
        """Return the identifier this request names.

        Both values were canonicalised by their fields, so they are
        tagged here, not re-validated.

        :return: The phone or email identifier
        """
        if self.phone is not None:
            return Identifier(Channel.PHONE, self.phone)
        return Identifier(Channel.EMAIL, self.email or "")
