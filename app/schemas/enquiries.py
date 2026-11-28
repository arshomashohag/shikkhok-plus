"""Request and response bodies for hub join requests [H5].

**No response says who sent a request.** Neither side's body carries an
account id or the guardian's own name for themselves.
``tests/contract/test_enquiry_privacy.py`` walks every join-request route's
response against :data:`~app.contract.privacy.ENQUIRY_FORBIDDEN_FIELDS`.
The owner reads the guardian's contact as ``guardian_phone`` or
``guardian_email``, and only while the guardian chose to share it.

**Consent is strict** [F9]. ``share_contact`` is a JSON ``true`` or
``false`` the client sent, with no default, and the adult-guardian
declaration is a JSON ``true``: Pydantic's lax mode would otherwise record
``1`` or ``"on"`` in a column called consent. The declaration cannot be
spelled ``Annotated[Literal[True], Field(strict=True)]``: Pydantic 2.14
refuses a strict constraint on a literal when the model is built, and a
lax ``Literal[True]`` accepts ``1`` and ``1.0``. So it is
:data:`StrictTrue`, a ``Literal[True]`` (published as ``const: true``)
behind a check that the value is a JSON boolean at all.

**Text is bounded after stripping** [H4 F14], as the service counts it, so
a padded 80-character name is accepted and a blank one is the standard
validation error.

**The wire mirrors the services one to one**:
:class:`EnquiryTargetResponse` is
:class:`~app.hub.enquiries.sending.EnquiryTarget`, :class:`MyEnquiryWire`
is :class:`~app.hub.enquiries.sending.MyEnquiry` and
:class:`OwnerEnquiryWire` is :class:`~app.hub.enquiries.owner.OwnerEnquiry`,
field for field; ``tests/contract/test_enquiry_contract.py`` asserts it.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    StrictBool,
    StringConstraints,
)

from app.hub.enquiries.sending import (
    MAX_MESSAGE,
    MAX_STUDENT_NAME,
    EnquiryOutcome,
    EnquiryStatus,
)
from app.schemas.hub import ClassLevel

__all__ = [
    "EnquiryClose",
    "EnquiryTargetResponse",
    "EnquiryWrite",
    "InterestTargetResponse",
    "InterestWrite",
    "MyEnquiryWire",
    "MyInterestWire",
    "OwnerEnquiryWire",
    "OwnerInterestWire",
]


def _json_boolean(value: object) -> object:
    """Refuse anything but a JSON boolean, before a literal compares it.

    :param value: The value as decoded
    :return: The value, unchanged
    :raises ValueError: ``1``, ``1.0``, ``"true"`` or any other non-boolean
    """
    if not isinstance(value, bool):
        msg = "must be a JSON boolean"
        raise ValueError(msg)
    return value


#: The JSON value ``true`` and nothing a lax mode would coerce to it [F9].
StrictTrue = Annotated[Literal[True], BeforeValidator(_json_boolean)]


class EnquiryWrite(BaseModel):
    """Ask an owner, or one of its batches, to take a student.

    :ivar student_name: 1 to 80 characters once stripped
    :ivar class_level: One of the hub class levels
    :ivar message: At most 300 characters once stripped; a blank message
        is stored as none
    :ivar batch_id: The listed batch asked about, or None for the owner
    :ivar share_contact: Whether the people who run the listing may see
        the account's phone, or its email when it has no phone. Required
    :ivar declares_adult_guardian: The sender declares they are the
        student's parent or guardian and an adult; only ``true`` is
        accepted. Not stored
    """

    model_config = ConfigDict(extra="forbid")

    student_name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=MAX_STUDENT_NAME
        ),
    ]
    class_level: ClassLevel
    message: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_MESSAGE)]
        | None
    ) = None
    batch_id: uuid.UUID | None = None
    share_contact: StrictBool
    declares_adult_guardian: StrictTrue


class InterestWrite(BaseModel):
    """Share interest in a listed batch [0049].

    Nothing is typed: the batch is the path's and the number the account's.
    The sender declares, as for a join request, that they are a parent or
    guardian and an adult, since a number shared with a stranger should
    never be a child's.

    :ivar declares_adult_guardian: Only ``true`` is accepted. Not stored
    """

    model_config = ConfigDict(extra="forbid")

    declares_adult_guardian: StrictTrue


class EnquiryClose(BaseModel):
    """Answer a join request.

    :ivar outcome: One of the request's ``outcomes_allowed``
    """

    model_config = ConfigDict(extra="forbid")

    outcome: EnquiryOutcome


class EnquiryTargetResponse(BaseModel):
    """What the request form shows before the guardian sends.

    :ivar owner_public_name: Whoever would receive the request
    :ivar batch_title: The batch's public title, or None for the owner
    :ivar contact_kind: What "share" would share: ``phone`` when the
        account has one, else ``email``
    :ivar already_open: The caller already has a request open with this
        owner, so a send would answer ``ENQUIRY_ALREADY_OPEN``
    """

    owner_public_name: str
    batch_title: str | None
    contact_kind: Literal["phone", "email"]
    already_open: bool


class MyEnquiryWire(BaseModel):
    """One of the caller's own join requests.

    :ivar id: The request, to withdraw it
    :ivar owner_public_name: The listing's public name, or None once the
        listing itself is gone
    :ivar batch_title: The batch's public title, or None
    :ivar student_name: As sent
    :ivar class_level: One of the hub class levels
    :ivar message: As sent, or None
    :ivar share_contact: Whether the caller shared their contact
    :ivar status: ``open`` or ``closed``
    :ivar outcome: How the owner answered, or None while open
    :ivar sent_on: The day it was sent, in Bangladesh
    :ivar owner_contact_phone: The owner's published number, only on a
        ``call_us`` answer and only while the owner is public
    """

    id: uuid.UUID
    owner_public_name: str | None
    batch_title: str | None
    student_name: str
    class_level: ClassLevel
    message: str | None
    share_contact: bool
    status: EnquiryStatus
    outcome: EnquiryOutcome | None
    sent_on: dt.date
    owner_contact_phone: str | None


class OwnerEnquiryWire(BaseModel):
    """One join request, as the people who run the listing read it.

    :ivar id: The request
    :ivar batch_id: The batch asked about, or None for the owner as a whole
    :ivar batch_title: That batch's public title, or None
    :ivar student_name: As the guardian typed it
    :ivar class_level: One of the hub class levels
    :ivar message: As typed, or None
    :ivar status: ``open`` or ``closed``
    :ivar outcome: How it was answered, or None while open
    :ivar received_at: When it was sent
    :ivar guardian_phone: The guardian's phone, only when they shared
        their contact
    :ivar guardian_email: The guardian's email, only when they shared
        their contact and have no phone
    :ivar outcomes_allowed: What a close would accept now; empty once
        closed. Clients offer exactly these
    """

    id: uuid.UUID
    batch_id: uuid.UUID | None
    batch_title: str | None
    student_name: str
    class_level: ClassLevel
    message: str | None
    status: EnquiryStatus
    outcome: EnquiryOutcome | None
    received_at: dt.datetime
    guardian_phone: str | None
    guardian_email: str | None
    outcomes_allowed: list[EnquiryOutcome]


class InterestTargetResponse(BaseModel):
    """What the interest confirm screen shows before the family shares [0049].

    Mirrors :class:`~app.hub.enquiries.interest.InterestTarget`. It says
    whether there is a number to share, never the number.

    :ivar owner_public_name: The listing's public name
    :ivar batch_title: The batch's public title
    :ivar has_phone: Whether the caller's account has a phone number to
        share; without one, sharing answers ``HUB_INTEREST_NEEDS_PHONE``
    :ivar already_shared: The caller already has an open interest here
    """

    owner_public_name: str
    batch_title: str
    has_phone: bool
    already_shared: bool


class MyInterestWire(BaseModel):
    """One of the caller's own interests [0049].

    Mirrors :class:`~app.hub.enquiries.interest.MyInterest`.

    :ivar id: The interest, to take it back
    :ivar owner_public_name: The listing's public name, or None once gone
    :ivar batch_title: The batch's public title, or None once gone
    :ivar status: ``open`` while shared, ``closed`` once the owner saw it
    :ivar shared_on: The day it was shared, in Bangladesh
    """

    id: uuid.UUID
    owner_public_name: str | None
    batch_title: str | None
    status: EnquiryStatus
    shared_on: dt.date


class OwnerInterestWire(BaseModel):
    """One open interest, as the people who run the listing read it [0049].

    Mirrors :class:`~app.hub.enquiries.interest.OwnerInterest`. No name:
    only the number the family chose to share, read from their account now.

    :ivar id: The interest, to close it
    :ivar batch_id: The batch, or None once its listing is gone
    :ivar batch_title: Its public title, or None
    :ivar guardian_phone: The family's phone, or None if since removed
    :ivar shared_on: The day it was shared, in Bangladesh
    """

    id: uuid.UUID
    batch_id: uuid.UUID | None
    batch_title: str | None
    guardian_phone: str | None
    shared_on: dt.date
