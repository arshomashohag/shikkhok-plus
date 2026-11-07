"""The platform administration surface on the wire [TC-14, D-6].

**These schemas are the administrator boundary.** They carry aggregate
counts, teacher and centre names, the apps people use, and what people
wrote to support. They carry no phone number, no ``profile`` field, and
no name for a student or a guardian: a requester who is not a teacher
appears as a role and an opaque ``ref``. ``tests/contract`` walks every
administration route's response schema and fails on any field outside
that boundary.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.accounts.clients import Platform
from app.schemas.help import HelpBody, HelpMessageResponse
from app.schemas.phone import PhoneField

__all__ = [
    "AdminAppVersion",
    "AdminChallengeResponse",
    "AdminEnrollment",
    "AdminMfaRequest",
    "AdminOtpRequest",
    "AdminOverviewResponse",
    "AdminPlatformUsage",
    "AdminReplyRequest",
    "AdminRequester",
    "AdminRequesterSummary",
    "AdminRequestersResponse",
    "AdminSessionResponse",
    "AdminTicket",
    "AdminTicketDetailResponse",
    "AdminTicketListResponse",
    "AdminTicketStatusRequest",
    "AdminVerifyRequest",
    "AdminWorkspace",
    "AdminWorkspacesResponse",
]


class AdminPlatformUsage(BaseModel):
    """How many accounts use one app.

    :ivar platform: ``android`` or ``web``
    :ivar accounts: Accounts ever seen on it
    :ivar active_7_days: Seen on it in the last seven days
    :ivar active_30_days: Seen on it in the last thirty days
    """

    model_config = ConfigDict(extra="forbid")

    platform: Platform
    accounts: int
    active_7_days: int
    active_30_days: int


class AdminAppVersion(BaseModel):
    """How many accounts reported one app version in the last 30 days.

    :ivar platform: ``android`` or ``web``
    :ivar version: The version string
    :ivar accounts: Accounts on it
    """

    model_config = ConfigDict(extra="forbid")

    platform: Platform
    version: str
    accounts: int


class AdminOverviewResponse(BaseModel):
    """The platform at a glance. Every figure is an aggregate.

    :ivar generated_at: When these figures were read
    :ivar accounts: Accounts that have signed in at least once
    :ivar new_7_days: First signed in during the last 7 days
    :ivar new_30_days: First signed in during the last 30 days
    :ivar active_7_days: Seen on any app in the last 7 days
    :ivar active_30_days: Seen on any app in the last 30 days
    :ivar teachers: Accounts owning a solo-tutor workspace
    :ivar centres: Coaching centres
    :ivar centre_members: Accounts holding a live centre membership
    :ivar students: Accounts holding an accepted student seat
    :ivar guardians: Accounts holding an accepted guardian seat
    :ivar batches: Active batches
    :ivar seats: Accepted student seats in active batches
    :ivar platforms: Usage per app
    :ivar both_platforms: Accounts seen on both apps
    :ivar no_platform: Signed-in accounts no app has reported yet, such
        as those last seen on an app build that predates reporting
    :ivar versions: App versions seen in the last 30 days
    :ivar help_open: Tickets waiting on support
    :ivar help_answered: Tickets waiting on the requester
    :ivar help_closed: Closed tickets
    """

    model_config = ConfigDict(extra="forbid")

    generated_at: dt.datetime
    accounts: int
    new_7_days: int
    new_30_days: int
    active_7_days: int
    active_30_days: int
    teachers: int
    centres: int
    centre_members: int
    students: int
    guardians: int
    batches: int
    seats: int
    platforms: list[AdminPlatformUsage]
    both_platforms: int
    no_platform: int
    versions: list[AdminAppVersion]
    help_open: int
    help_answered: int
    help_closed: int


class AdminWorkspace(BaseModel):
    """One teacher or coaching centre.

    :ivar workspace_id: The workspace
    :ivar kind: ``teacher`` for a solo tutor, ``centre`` for a centre
    :ivar name: The name shown to its students, if one has been given
    :ivar platforms: The apps its people use
    :ivar joined_at: When the workspace was created
    :ivar last_seen_at: The latest sign-in or refresh, if any
    :ivar ref: A solo tutor's help-centre label, to find their tickets
    """

    model_config = ConfigDict(extra="forbid")

    workspace_id: uuid.UUID
    kind: Literal["teacher", "centre"]
    name: str | None = None
    platforms: list[Platform]
    joined_at: dt.datetime
    last_seen_at: dt.datetime | None = None
    ref: str | None = None


class AdminWorkspacesResponse(BaseModel):
    """Teachers and centres, most recently seen first.

    :ivar workspaces: The workspaces
    """

    model_config = ConfigDict(extra="forbid")

    workspaces: list[AdminWorkspace]


class AdminRequester(BaseModel):
    """Who asked, within the administrator boundary.

    :ivar ref: An opaque label, stable per person
    :ivar roles: The roles the account holds now
    :ivar name: Set only when a role is ``teacher`` or ``centre_member``
    :ivar centre: The centre's name, set only for a centre member
    """

    model_config = ConfigDict(extra="forbid")

    ref: str
    roles: list[Literal["teacher", "centre_member", "student", "guardian"]]
    name: str | None = None
    centre: str | None = None


class AdminTicket(BaseModel):
    """A ticket in an administrator's list.

    :ivar ticket_id: The ticket
    :ivar subject: The one-line summary
    :ivar status: ``open``, ``answered`` or ``closed``
    :ivar platform: The app it was asked from, if known
    :ivar created_at: When it was asked
    :ivar updated_at: The latest activity
    :ivar message_count: Messages in the thread
    :ivar preview: The start of the latest message
    :ivar requester: Who asked
    """

    model_config = ConfigDict(extra="forbid")

    ticket_id: uuid.UUID
    subject: str
    status: Literal["open", "answered", "closed"]
    platform: Platform | None = None
    created_at: dt.datetime
    updated_at: dt.datetime
    message_count: int
    preview: str
    requester: AdminRequester


class AdminTicketListResponse(BaseModel):
    """Tickets, waiting-on-support first.

    :ivar tickets: The tickets
    """

    model_config = ConfigDict(extra="forbid")

    tickets: list[AdminTicket]


class AdminTicketDetailResponse(BaseModel):
    """A ticket and its thread.

    :ivar ticket: The ticket
    :ivar messages: Its messages, oldest first
    """

    model_config = ConfigDict(extra="forbid")

    ticket: AdminTicket
    messages: list[HelpMessageResponse]


class AdminRequesterSummary(BaseModel):
    """One person's tickets.

    :ivar requester: Who
    :ivar tickets: How many tickets they have opened
    :ivar open: How many wait on support
    :ivar last_activity: Their latest ticket activity
    """

    model_config = ConfigDict(extra="forbid")

    requester: AdminRequester
    tickets: int
    open: int
    last_activity: dt.datetime


class AdminRequestersResponse(BaseModel):
    """Everyone who has asked, latest activity first.

    :ivar requesters: One row per person
    """

    model_config = ConfigDict(extra="forbid")

    requesters: list[AdminRequesterSummary]


class AdminReplyRequest(BaseModel):
    """Answer a ticket as ShikkhokPlus support.

    :ivar body: The reply
    """

    model_config = ConfigDict(extra="forbid")

    body: HelpBody


class AdminTicketStatusRequest(BaseModel):
    """Close or reopen a ticket.

    :ivar status: ``closed`` or ``open``
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["open", "closed"]


class AdminOtpRequest(BaseModel):
    """Ask for an admin sign-in code by SMS.

    :ivar phone: The administrator's number, in any spelling
    """

    model_config = ConfigDict(extra="forbid")

    phone: PhoneField


class AdminVerifyRequest(BaseModel):
    """Spend the SMS code.

    :ivar phone: The number the code was sent to
    :ivar code: The code from the SMS
    """

    model_config = ConfigDict(extra="forbid")

    phone: PhoneField
    code: str = Field(min_length=4, max_length=10)


class AdminEnrollment(BaseModel):
    """A new authenticator secret, shown once at a first sign-in.

    :ivar secret: The base32 secret, for typing into an app by hand
    :ivar otpauth_uri: The same secret as a URI, for a QR code or a link
    """

    model_config = ConfigDict(extra="forbid")

    secret: str
    otpauth_uri: str


class AdminChallengeResponse(BaseModel):
    """The SMS step passed; now the authenticator step.

    :ivar challenge: Carries the person to the next step; grants nothing
    :ivar expires_in: Seconds until the challenge lapses
    :ivar stage: ``enroll`` (set up the app first) or ``verify``
    :ivar enrollment: The secret to set up, only when ``stage`` is enroll
    """

    model_config = ConfigDict(extra="forbid")

    challenge: str
    expires_in: int
    stage: Literal["enroll", "verify"]
    enrollment: AdminEnrollment | None = None


class AdminMfaRequest(BaseModel):
    """Finish signing in: exactly one of the two codes.

    :ivar challenge: From the SMS step
    :ivar code: Six digits from the authenticator app
    :ivar recovery_code: A recovery code, only after setup
    """

    model_config = ConfigDict(extra="forbid")

    challenge: str = Field(min_length=1, max_length=2048)
    code: str | None = Field(default=None, min_length=6, max_length=8)
    recovery_code: str | None = Field(default=None, min_length=10, max_length=16)


class AdminSessionResponse(BaseModel):
    """A signed-in administrator.

    :ivar access_token: Send as ``Authorization: Bearer`` to admin routes
    :ivar expires_in: Seconds until it lapses; sign in again after
    :ivar recovery_codes: Ten one-time codes, shown once at setup
    """

    model_config = ConfigDict(extra="forbid")

    access_token: str
    expires_in: int
    recovery_codes: list[str] | None = None
