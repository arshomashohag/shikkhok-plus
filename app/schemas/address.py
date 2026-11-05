"""The four address fields every request schema uses.

Decided by the owner on 2026-11-05: an address is required at sign-up,
as separate House, Road, City and Postcode fields, so a teacher's own
address and a child's home are both written the same, checkable way.

The parts are **owner-private** like the rest of ``Profile`` [BR3.4]:
their names are enrolled in ``OWNER_PRIVATE_FIELDS`` and no teacher-lens
response may carry them.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field, StringConstraints

__all__ = ["CityField", "HouseField", "PostcodeField", "RoadField"]

#: Bangla digits to Latin ones, so a postcode typed on a Bangla keyboard
#: is the same postcode.
_LATIN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def _latin_postcode(value: object) -> object:
    """Read a postcode typed in Bangla or Latin digits.

    :param value: What arrived
    :return: The text with Bangla digits as Latin ones, or the value
        unchanged when it is not text, for the type check to refuse
    """
    if isinstance(value, str):
        return value.translate(_LATIN_DIGITS)
    return value


#: House or flat, such as "House 12" or "Flat 4B".
HouseField = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=60),
    Field(description="House or flat number."),
]

#: Road or area, such as "Road 5, Dhanmondi".
RoadField = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    Field(description="Road number or name, and area."),
]

#: City or district, such as "Dhaka".
CityField = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=60),
    Field(description="City or district."),
]

#: A Bangladeshi postcode: four digits, Latin or Bangla.
PostcodeField = Annotated[
    str,
    BeforeValidator(_latin_postcode),
    StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{4}$"),
    Field(description="Four digits; Bangla digits are accepted and stored as Latin."),
]
