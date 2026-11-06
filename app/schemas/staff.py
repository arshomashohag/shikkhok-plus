"""Request and response bodies for the Teachers & staff console [0023].

**Manager-only, and the gate says so.** The contact and address fields
here are in ``STAFF_PRIVATE_FIELDS`` and may appear only in responses
under ``/v1/centre/staff``; the address carries its own names, never the
profile's, so the profile boundary is untouched.

Every amount is the shared ``Money`` component, a JSON string.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.address import CityField, HouseField, PostcodeField, RoadField
from app.schemas.money import MoneyField
from app.schemas.phone import PhoneField

__all__ = [
    "PayBasis",
    "StaffAccess",
    "StaffLeaveRequest",
    "StaffOtherRequest",
    "StaffResponse",
    "StaffTeacherRequest",
    "StaffUpdateRequest",
]

#: How a person is paid [D12].
PayBasis = Literal["monthly", "per_class", "none"]

#: Where a staff member's app access stands: ``none`` for other staff, and
#: otherwise the linked membership's own state.
StaffAccess = Literal["none", "invited", "declined", "active", "revoked"]

#: An email, checked for shape only and used for nothing yet.
EmailField = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    ),
]

#: A name the manager typed.
NameField = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]

#: What other staff do, such as "Receptionist".
RoleLabelField = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)
]


class _Details(BaseModel):
    """The facts both kinds of staff record carry.

    :ivar display_name: Their name
    :ivar email: Their email, or None
    :ivar staff_house: House or flat, or None
    :ivar staff_road: Road or area, or None
    :ivar staff_city: City or district, or None
    :ivar staff_postcode: Four digits, or None
    :ivar pay_basis: How they are paid
    :ivar pay_rate: The salary or rate per class; None when unpaid
    :ivar joined_on: When they started; today when omitted
    """

    model_config = ConfigDict(extra="forbid")

    display_name: NameField
    email: EmailField | None = None
    staff_house: HouseField | None = None
    staff_road: RoadField | None = None
    staff_city: CityField | None = None
    staff_postcode: PostcodeField | None = None
    pay_basis: PayBasis
    pay_rate: MoneyField | None = None
    joined_on: dt.date | None = None


class StaffTeacherRequest(_Details):
    """Invite a teacher: their record, and an offer of app access.

    :ivar phone: The number the offer goes to, typed by the manager
    """

    phone: PhoneField


class StaffOtherRequest(_Details):
    """Record someone who works at the centre without app access.

    :ivar phone: Their number, or None
    :ivar role_label: What they do
    """

    phone: PhoneField | None = None
    role_label: RoleLabelField | None = None


class StaffUpdateRequest(BaseModel):
    """Correct a record. An omitted field is unchanged; null clears it.

    The kind and the phone a teacher's access was offered to are not
    here: a teacher's number is the membership's, and a person does not
    change from teacher to other staff by an edit.

    :ivar display_name: Their name
    :ivar email: Their email
    :ivar staff_house: House or flat
    :ivar staff_road: Road or area
    :ivar staff_city: City or district
    :ivar staff_postcode: Four digits
    :ivar role_label: What they do, for other staff
    :ivar pay_basis: How they are paid
    :ivar pay_rate: The salary or rate per class
    :ivar joined_on: When they started
    """

    model_config = ConfigDict(extra="forbid")

    display_name: NameField | None = None
    email: EmailField | None = None
    staff_house: HouseField | None = None
    staff_road: RoadField | None = None
    staff_city: CityField | None = None
    staff_postcode: PostcodeField | None = None
    role_label: RoleLabelField | None = None
    pay_basis: PayBasis | None = None
    pay_rate: MoneyField | None = None
    joined_on: dt.date | None = None


class StaffLeaveRequest(BaseModel):
    """Mark someone as having left.

    :ivar left_on: Their last day; today when omitted
    """

    model_config = ConfigDict(extra="forbid")

    left_on: dt.date | None = None


class StaffResponse(BaseModel):
    """One staff record, as the centre's manager sees it.

    :ivar staff_id: The record
    :ivar kind: ``teacher`` or ``other``
    :ivar display_name: Their name
    :ivar role_label: What they do, or None
    :ivar phone: Their number, or None
    :ivar email: Their email, or None
    :ivar staff_house: House or flat, or None
    :ivar staff_road: Road or area, or None
    :ivar staff_city: City or district, or None
    :ivar staff_postcode: Four digits, or None
    :ivar pay_basis: How they are paid
    :ivar pay_rate: The salary or rate per class, or None
    :ivar joined_on: When they started
    :ivar left_on: When they left, or None
    :ivar status: ``active`` or ``left``
    :ivar access: Where their app access stands
    """

    staff_id: uuid.UUID
    kind: Literal["teacher", "other"]
    display_name: str
    role_label: str | None = None
    phone: str | None = None
    email: str | None = None
    staff_house: str | None = None
    staff_road: str | None = None
    staff_city: str | None = None
    staff_postcode: str | None = None
    pay_basis: PayBasis
    pay_rate: MoneyField | None = None
    joined_on: dt.date
    left_on: dt.date | None = None
    status: Literal["active", "left"]
    access: StaffAccess = Field(
        description="none, invited, declined, active or revoked"
    )
