"""The phone-number field every request schema uses.

**Canonicalised on the way in**, so no handler, service or query ever sees
a second spelling of one number (see ``app.accounts.phone`` for why that
mattered). A schema field typed ``PhoneField`` arrives as ``+8801XXXXXXXXX``
or not at all: a number that is not a Bangladeshi mobile raises the app's
own ``ValidationError``, which reaches the client as an envelope with a
``message_key`` rather than FastAPI's untranslatable 422.

``app.schemas`` is a strict type-checking island and imports the function
from ``app.accounts.phone``; that module is fully annotated, and the
strict ``mypy app`` run is what shows no ``Any`` crosses the boundary.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field

from app.accounts.phone import canonical_phone

__all__ = ["PhoneField"]

#: A Bangladeshi mobile number, stored and compared as ``+8801XXXXXXXXX``.
#:
#: **No length constraint in the published schema, deliberately.** Pydantic
#: applies length limits AFTER the before-validator, so ``14..14`` would
#: hold at runtime -- but the request contract would then tell every
#: client that ``01711-234567`` (twelve characters) is invalid, when it is
#: accepted. The description says what is actually accepted instead.
PhoneField = Annotated[
    str,
    BeforeValidator(canonical_phone),
    Field(
        description=(
            "A Bangladeshi mobile number. Any common spelling is accepted "
            "(01711234567, 01711-234567, +8801711234567, Bangla digits); "
            "it is stored and returned as +8801XXXXXXXXX."
        ),
    ),
]
