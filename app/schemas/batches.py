"""Request and response bodies for batches and enrollment seats.

**Every response carries a server-computed decision, never the inputs to
one** [TC-9, D-31]. A roster row carries ``status`` rather than leaving
the client to compare a balance, because "if balance > 0 then Due" is a
business rule about what counts as due, rendered as if it were
presentation and nearly invisible in review.

The teacher-facing key is ``enrollment_id`` and never a student account
id [ADR-001], asserted schema-wide by the privacy gate U2 built.

``fee_due_day`` is an integer day-of-month that matches the money gates'
name tokens while carrying nothing of the kind, which is why BR3.3
allowlists it on each of the schemas below rather than removing a token
from the shared vocabulary.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import MoneyField

__all__ = [
    "BatchCreateRequest",
    "BatchResponse",
    "BatchUpdateRequest",
    "EnrollmentCreateRequest",
    "GuardianChildResponse",
    "InactiveFromRequest",
    "RosterRowResponse",
]


class BatchCreateRequest(BaseModel):
    """Create a batch [AC2.1.1, AC2.1.2].

    :ivar name: The teacher's name for the class
    :ivar subjects: One or more subjects taught
    :ivar teacher_display_name: What students see the teacher called
    :ivar default_fee: The fee an enrollment inherits when it sets none
    :ivar fee_due_day: Day of month 1-31; 29-31 clamp at generation
    :ivar collection_number: Where payments are sent
    :ivar collection_channel: Which service that number belongs to
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    subjects: list[str] = Field(min_length=1)
    teacher_display_name: str | None = Field(default=None, max_length=120)
    default_fee: MoneyField | None = None
    fee_due_day: int | None = Field(default=None, ge=1, le=31)
    collection_number: str | None = Field(default=None, max_length=32)
    collection_channel: str | None = Field(default=None, max_length=32)


class BatchUpdateRequest(BaseModel):
    """Edit a batch [AC2.3.1].

    Every field optional, because a PATCH names only what changes.

    :ivar name: The teacher's name for the class
    :ivar teacher_display_name: What students see the teacher called
    :ivar default_fee: The inherited fee
    :ivar fee_due_day: Day of month 1-31
    :ivar collection_number: Where payments are sent
    :ivar collection_channel: Which service that number belongs to
    :ivar marksheet_visible: U6's toggle
    :ivar active: False collapses the batch to read-only history
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    teacher_display_name: str | None = Field(default=None, max_length=120)
    default_fee: MoneyField | None = None
    fee_due_day: int | None = Field(default=None, ge=1, le=31)
    collection_number: str | None = Field(default=None, max_length=32)
    collection_channel: str | None = Field(default=None, max_length=32)
    marksheet_visible: bool | None = None
    active: bool | None = None


class BatchResponse(BaseModel):
    """A batch as its owner sees it.

    :ivar id: The batch
    :ivar name: The teacher's name for the class
    :ivar subjects: The subjects taught
    :ivar teacher_display_name: What students see the teacher called
    :ivar default_fee: The inherited fee
    :ivar fee_due_day: Day of month 1-31
    :ivar collection_number: Where payments are sent
    :ivar collection_channel: Which service that number belongs to
    :ivar marksheet_visible: U6's toggle
    :ivar active: False means read-only history
    :ivar enrollment_count: How many seats, computed server-side. The
        **denominator** of "9 of 12 accepted", and it counts every seat
        the teacher created including declined ones [BR1.4]
    :ivar accepted_count: How many of those seats at least one link has
        accepted [BR1.2], computed server-side and **never counted by
        the client** [BR1.3, TC-9]. A client counting rows is a client
        deciding what counts as accepted, and it is wrong the moment the
        roster paginates because it can only count the rows it holds
    """

    id: uuid.UUID
    name: str
    subjects: list[str]
    teacher_display_name: str | None
    default_fee: MoneyField | None
    fee_due_day: int | None
    collection_number: str | None
    collection_channel: str | None
    marksheet_visible: bool
    active: bool
    enrollment_count: int
    accepted_count: int


class EnrollmentCreateRequest(BaseModel):
    """Add a student to a batch [AC2.2.2, AC2.2.5].

    ``fee_amount`` is nullable and null means **inherit** the batch
    default. Zero is a real fee of zero, which is a waiver -- a
    non-nullable column defaulting to zero would make the two
    indistinguishable and silently charge nothing.

    :ivar display_name: The teacher-typed name for this seat
    :ivar student_phone: The student's number, typed by the teacher
    :ivar guardian_phone: The guardian's number, if one is recorded
    :ivar fee_amount: This seat's fee, or null to inherit
    :ivar joined_on: When the student joined
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=120)
    student_phone: str | None = Field(default=None, max_length=20)
    guardian_phone: str | None = Field(default=None, max_length=20)
    fee_amount: MoneyField | None = None
    joined_on: dt.date | None = None


class InactiveFromRequest(BaseModel):
    """Mark a seat inactive from a date, or clear it [AC2.4.1].

    :ivar inactive_from: The date, or null to reactivate the seat
    """

    model_config = ConfigDict(extra="forbid")

    inactive_from: dt.date | None = None


class RosterRowResponse(BaseModel):
    """One seat as a teacher sees it.

    ``status`` is a **server-computed decision**, not an input to one
    [TC-9]: the client switches on this enum and never compares a date
    or an amount of its own.

    :ivar enrollment_id: The teacher-facing key for this seat
    :ivar display_name: The teacher-typed name
    :ivar guardian_phone: The teacher-typed guardian contact
    :ivar fee_amount: This seat's fee, or null when it inherits
    :ivar status: ``dormant``, ``active`` or ``inactive``.

        **Unchanged, and the two new fields sit beside it rather than
        replacing it.** Acceptance is a different axis from activity:
        an inactive seat keeps whatever decisions its links carry,
        because leaving a batch is not un-accepting it. Folding the two
        together would produce a product of two axes and a value set
        nobody can switch on exhaustively
    :ivar student_state: The student link's own decision --
        ``pending``, ``accepted`` or ``declined`` [BR2.1]
    :ivar guardian_state: The guardian link's own decision, plus
        ``absent`` when no guardian was recorded [BR2.2]. ``absent`` is
        a fourth VALUE and not a null, because a decision nobody was
        asked for is not an outstanding one
    :ivar is_removable: Whether removal would succeed [BR3.1].

        **A decision the client reads and never derives** [NFR14.31].
        Removal tests two conditions -- no link accepted, and no erasure
        marker set -- and this row carries only the first. A client
        inferring removability from the link states it displays would
        offer the action on an erased seat, which is a wrong answer
        presented as an available action rather than a style violation
    :ivar inactive_from: The recorded date, if any
    """

    enrollment_id: uuid.UUID
    display_name: str
    guardian_phone: str | None
    fee_amount: MoneyField | None
    status: str
    student_state: str
    guardian_state: str
    is_removable: bool
    inactive_from: dt.date | None


class GuardianChildResponse(BaseModel):
    """One reachable child as a guardian sees it.

    Carries ``batch_name`` and ``teacher_display_name`` because
    attribution is required even in the single-child case [AC2.8.5] --
    that is where it is most needed, since the selection list is where
    it would otherwise have been shown.

    :ivar enrollment_id: The seat, which BR5.1 keys the route on
    :ivar display_name: The teacher-typed name for the child
    :ivar batch_name: Which class
    :ivar teacher_display_name: Which teacher recorded this
    """

    enrollment_id: uuid.UUID
    display_name: str
    batch_name: str
    teacher_display_name: str | None
