"""Request and response bodies for centres, members and their offers [0022].

**A member is shown as the centre typed them**: the name a manager
entered and the number invited, never the person's own profile, which is
owner-private and reaches no teacher-lens response.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.identifier import RecordedEmailField
from app.schemas.phone import PhoneField

__all__ = [
    "CentreCreateRequest",
    "CentreResponse",
    "MemberDecision",
    "MemberInviteRequest",
    "MemberResponse",
    "MemberRole",
    "MembershipDecisionResponse",
    "MembershipResponse",
    "WorkspaceResponse",
]

#: A member's part in a centre.
MemberRole = Literal["manager", "teacher"]

#: Where an offer stands.
MemberDecision = Literal["pending", "accepted", "declined"]


class CentreCreateRequest(BaseModel):
    """Open a coaching centre, as its first manager.

    :ivar name: The centre's name, shown to its members and families
    :ivar manager_name: How the centre's members see you
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    manager_name: str = Field(min_length=1, max_length=120)


class CentreResponse(BaseModel):
    """The centre just opened.

    :ivar owner_id: The workspace id, sent as ``X-Workspace-Id`` to act on it
    :ivar name: Its name
    """

    owner_id: uuid.UUID
    name: str


class WorkspaceResponse(BaseModel):
    """One workspace this account may act on.

    :ivar owner_id: The id to send as ``X-Workspace-Id``
    :ivar kind: ``solo`` for a tutor's own, ``centre`` for a centre
    :ivar name: The centre's name, or None for a solo workspace
    """

    owner_id: uuid.UUID
    kind: Literal["solo", "centre"]
    name: str | None = None


class MemberInviteRequest(BaseModel):
    """Invite a number, an address, or both, to the centre [U2: FR6.4].

    At least one of the two; a request naming neither is refused at the
    schema [BR1.8].

    :ivar phone: The number, typed by the manager, or null
    :ivar email: The address, typed by the manager, or null
    :ivar display_name: The name the centre knows them by
    :ivar role: ``manager`` or ``teacher``
    """

    model_config = ConfigDict(extra="forbid")

    phone: PhoneField | None = None
    email: RecordedEmailField = None
    display_name: str = Field(min_length=1, max_length=120)
    role: MemberRole

    @model_validator(mode="after")
    def _at_least_one(self) -> MemberInviteRequest:
        """Refuse an invitation that names nobody.

        :return: The request
        :raises ValueError: Neither a phone nor an email was given
        """
        if self.phone is None and self.email is None:
            raise ValueError("give a phone number, an email address, or both")
        return self


class MemberResponse(BaseModel):
    """One membership, as a manager sees it.

    :ivar member_id: The membership
    :ivar display_name: The name the centre typed
    :ivar phone: The number invited, or null for an invitation by email
        alone [U2: BR1.9]
    :ivar invited_email: The address invited, or null. Centre-written,
        never the member's own account address [BR1.4]
    :ivar role: ``manager`` or ``teacher``
    :ivar decision: Where the offer stands
    :ivar invited_at: When they were invited
    :ivar revoked: Whether the membership has been ended
    :ivar is_you: Whether this is the caller's own membership
    """

    member_id: uuid.UUID
    display_name: str
    phone: str | None
    invited_email: str | None
    role: MemberRole
    decision: MemberDecision
    invited_at: dt.datetime
    revoked: bool
    is_you: bool


class MembershipResponse(BaseModel):
    """One offer, as the person invited sees it.

    :ivar member_id: The membership
    :ivar centre_name: The centre making the offer
    :ivar role: ``manager`` or ``teacher``
    :ivar decision: ``pending`` or ``declined``
    """

    member_id: uuid.UUID
    centre_name: str
    role: MemberRole
    decision: Literal["pending", "declined"]


class MembershipDecisionResponse(BaseModel):
    """What the holder decided.

    :ivar member_id: The membership
    :ivar decision: ``accepted`` or ``declined``
    """

    member_id: uuid.UUID
    decision: Literal["accepted", "declined"]
