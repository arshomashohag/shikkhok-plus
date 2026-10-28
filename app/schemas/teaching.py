"""Request and response bodies for sessions, attendance and notes.

**No schema here carries a ``queue_state`` field** [BR3.9]. The four
queue states are client-side vocabulary: the server cannot know whether
an item is queued on a device it has never heard from, so whatever
value it invented would be wrong for every device except the one that
just called. A test iterates the generated document rather than
remembering this per endpoint.

**Exactly two request bodies in this unit carry
``client_mutation_id``** -- the roster submission and the topic
write. § B.7 names the four writes that need it explicitly and says
that enumerating them is what makes the rule reviewable, so
generalising it would contradict a decision rather than extend one. A
schema-level assertion over the generated document checks exactly this
pair.

**No teacher-facing response carries an owner-private profile field or
a global account identifier** [BR5.3]. A roster is literally a list of
people and is the most natural place in the product to leak a
student's self-authored name to a teacher; every row here exposes an
``enrollment_id`` and the TEACHER-typed ``display_name``.

**Every response carries a server-computed DECISION, not the inputs to
one** [TC-9, D-31]. ``topic_logged`` is a boolean the server computes,
because ``topic == ""`` is a business rule about what counts as logged
wearing presentation's clothes -- and the distinction between an
unwritten topic and one saved as blank is the whole content of
AC3.4.2.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AnnouncementBodyRequest",
    "AnnouncementResponse",
    "AttendanceEntryResponse",
    "AttendanceSubmitRequest",
    "AttendanceSubmitResponse",
    "FamilyBatchViewResponse",
    "MarksheetToggleRequest",
    "RosterSeatResponse",
    "SeatMarkRequest",
    "SessionCreateRequest",
    "SessionOrigin",
    "SessionRescheduleRequest",
    "SessionResponse",
    "SessionRosterResponse",
    "SessionStatus",
    "SessionSubjectRequest",
    "TopicWriteRequest",
    "TopicWriteResponse",
]

#: FR3.3's three states, as a closed set the generated document
#: publishes so a client author reads the contract rather than
#: guessing it.
SessionStatus = Literal["scheduled", "held", "cancelled"]

#: Whether generation produced the row or a teacher did [AC3.0.3].
SessionOrigin = Literal["recurrence", "ad_hoc"]


class SessionResponse(BaseModel):
    """One session, for any lens entitled to read it.

    ``topic_logged`` is the DECISION; ``topic`` is carried for display
    and is never what the client computes a logged-ness from [BR2.2].

    :ivar session_id: The session
    :ivar date: When it meets
    :ivar start_time: When it starts
    :ivar end_time: When it ends, or null
    :ivar status: Its state
    :ivar origin: Whether generation or a teacher created it
    :ivar topic: What was covered, or null if never logged
    :ivar topic_logged: Whether a topic was ever written
    :ivar subject_name: The subject taught, or null
    :ivar attendance_version: The roster's version, for the queue
    :ivar topic_version: The topic log's own version
    """

    model_config = ConfigDict(extra="forbid")

    session_id: uuid.UUID
    date: dt.date
    start_time: dt.time
    end_time: dt.time | None = None
    status: SessionStatus
    origin: SessionOrigin
    topic: str | None = None
    topic_logged: bool
    subject_name: str | None = None
    attendance_version: int
    topic_version: int


class SessionCreateRequest(BaseModel):
    """Create an ad-hoc session [AC3.0.3].

    :ivar date: When it meets
    :ivar start_time: When it starts
    :ivar end_time: When it ends, or null
    :ivar batch_subject_id: The subject, or null
    """

    model_config = ConfigDict(extra="forbid")

    date: dt.date
    start_time: dt.time
    end_time: dt.time | None = None
    batch_subject_id: uuid.UUID | None = None


class SessionRescheduleRequest(BaseModel):
    """Move a session, preserving its identity [BR1.7].

    **No version field**: this is an interactive write and cannot
    conflict [BR3.11].

    :ivar date: Its new date
    :ivar start_time: Its new start time
    """

    model_config = ConfigDict(extra="forbid")

    date: dt.date
    start_time: dt.time


class SessionSubjectRequest(BaseModel):
    """Set which subject a session taught.

    :ivar batch_subject_id: The subject, or null to clear it
    """

    model_config = ConfigDict(extra="forbid")

    batch_subject_id: uuid.UUID | None = None


class RosterSeatResponse(BaseModel):
    """One seat on a session's roster.

    The key is ``enrollment_id`` and never an account id [ADR-001,
    BR5.3], asserted schema-wide by the built privacy gate.

    ``present`` is **null where nothing was recorded**, which is a
    different fact from ``false``: AC3.1.4 defaults every seat to
    present in the UI and the teacher marks only exceptions, so
    collapsing the two would tell a guardian their child was marked
    absent from a class nobody has marked at all.

    :ivar enrollment_id: The teacher-facing key
    :ivar display_name: The TEACHER-typed name
    :ivar present: What was recorded, or null
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_id: uuid.UUID
    display_name: str
    present: bool | None = None


class SessionRosterResponse(BaseModel):
    """One session's roster, with the version it is at.

    **A wrapper rather than a bare array, and the version is why.**
    Attendance writes carry a `base_attendance_version` and a stale
    one is refused with a 409 [TC-8, D-9]. After that refusal the app
    re-reads the roster to show what changed — and without the current
    version here it cannot compose the next write, so a conflict
    becomes a dead end rather than something a person can resolve.

    :ivar seats: One row per seat on the roster
    :ivar attendance_version: The roster's current version
    :ivar writable: Whether a roster write would be accepted now,
        decided by the write path's own refusals [BR1.6, BR5.5]
    """

    model_config = ConfigDict(extra="forbid")

    seats: list[RosterSeatResponse]
    attendance_version: int
    writable: bool


class SeatMarkRequest(BaseModel):
    """One seat's presence within a roster submission.

    :ivar enrollment_id: The seat
    :ivar present: Whether the student attended
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_id: uuid.UUID
    present: bool


class AttendanceSubmitRequest(BaseModel):
    """A whole roster, written in one atomic operation [BR3.5].

    **One of exactly two D4 bodies carrying ``client_mutation_id``**
    [§ B.7]. ``base_attendance_version`` travels in the BODY rather
    than an ``If-Match`` header [§ B.8]: a queued write is serialized
    into the device's queue and replayed hours later by a sync worker,
    and a body field survives that naturally where a header is a
    second thing the queue must remember and the first thing a retry
    wrapper drops.

    ``composed_at`` is the DEVICE's clock, recorded for the pilot's
    queue-latency question and **used in no decision** [NFR24.20]. A
    device clock in a conflict rule would let a wrong phone time
    silently reorder two teachers' writes.

    :ivar base_attendance_version: The version this was composed
        against
    :ivar client_mutation_id: The replay key, per account
    :ivar seats: One mark per seat, the whole roster at once
    :ivar composed_at: When the device composed it, or null
    """

    model_config = ConfigDict(extra="forbid")

    base_attendance_version: int = Field(ge=0)
    client_mutation_id: uuid.UUID
    seats: list[SeatMarkRequest]
    composed_at: dt.datetime | None = None


class AttendanceSubmitResponse(BaseModel):
    """What an accepted or replayed roster write produced.

    **No ``queue_state`` field** [BR3.9]: the server returns the
    applied version, and the client derives its own state.

    :ivar attendance_version: The version now in force
    :ivar submission_id: The accepted write's record
    """

    model_config = ConfigDict(extra="forbid")

    attendance_version: int
    submission_id: uuid.UUID


class TopicWriteRequest(BaseModel):
    """A session's topic [BR2.1].

    **The second and last D4 body carrying ``client_mutation_id``.**

    An empty string is a topic logged as BLANK and is a different fact
    from never writing one [BR2.2].

    :ivar base_topic_version: The version this was composed against
    :ivar client_mutation_id: The replay key, per account
    :ivar topic: What was covered; '' means logged-and-blank
    """

    model_config = ConfigDict(extra="forbid")

    base_topic_version: int = Field(ge=0)
    client_mutation_id: uuid.UUID
    topic: str = Field(max_length=2000)


class TopicWriteResponse(BaseModel):
    """What an accepted topic write produced.

    :ivar topic_version: The version now in force
    """

    model_config = ConfigDict(extra="forbid")

    topic_version: int


class AnnouncementResponse(BaseModel):
    """One visible announcement.

    ``edited`` is the DECISION the server computes from
    ``edited_at``'s non-null-ness [AC3.3.2]; the timestamp itself does
    not cross the wire, so there is no second source of truth for a
    client to disagree with.

    **No expiry field**, because there is no expiry [AC3.3.4].

    :ivar announcement_id: The note
    :ivar body: What it says
    :ivar created_at: When it was posted
    :ivar edited: Whether it has been edited
    """

    model_config = ConfigDict(extra="forbid")

    announcement_id: uuid.UUID
    body: str
    created_at: dt.datetime
    edited: bool


class AnnouncementBodyRequest(BaseModel):
    """Post or edit a note.

    :ivar body: What it says
    """

    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=4000)


class AttendanceEntryResponse(BaseModel):
    """One past session, as a student or guardian sees it.

    :ivar session_id: The session
    :ivar date: When it met
    :ivar start_time: When it started
    :ivar topic: What was covered, or null if never logged
    :ivar topic_logged: Whether a topic was ever written
    :ivar present: What was recorded for THIS seat, or null
    """

    model_config = ConfigDict(extra="forbid")

    session_id: uuid.UUID
    date: dt.date
    start_time: dt.time
    topic: str | None = None
    topic_logged: bool
    present: bool | None = None


class FamilyBatchViewResponse(BaseModel):
    """What a student or guardian sees of one batch [BR7.2].

    ``served_at`` is BR7.3's server timestamp, so a client rendering
    this from cache can state its age without consulting the device
    clock -- which is the thing excluded from decisions.

    :ivar next_session_date: The next scheduled session's date, or
        null
    :ivar next_session_start_time: Its start time, or null
    :ivar past_sessions: Past sessions with topics and attendance
    :ivar announcements: The batch's visible notes
    :ivar served_at: When the server computed this
    """

    model_config = ConfigDict(extra="forbid")

    next_session_date: dt.date | None = None
    next_session_start_time: dt.time | None = None
    past_sessions: list[AttendanceEntryResponse]
    announcements: list[AnnouncementResponse]
    served_at: dt.datetime


class MarksheetToggleRequest(BaseModel):
    """Set whether families may see a marksheet [BR5.4].

    :ivar visible: Whether families may see it
    """

    model_config = ConfigDict(extra="forbid")

    visible: bool
