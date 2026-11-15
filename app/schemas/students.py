"""Request and response bodies for a teacher's students [0018].

A student is the teacher's own record -- the name and numbers they typed
-- and every response here is at that width. No field comes from a
student's or guardian's own profile [TC-13], and the student is keyed by
``student_id``, the teacher's record, never by an account id [ADR-001].

Every decision the client shows is computed by the server: the link
states, what each seat owes, and whether removal would succeed [TC-9].
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.identifier import RecordedEmailField
from app.schemas.money import MoneyField
from app.schemas.phone import PhoneField

__all__ = [
    "AddStudentsRequest",
    "AddStudentsResponse",
    "StudentCreateRequest",
    "StudentEnrollRequest",
    "StudentResponse",
    "StudentSeatRequest",
    "StudentSeatResponse",
    "StudentUpdateRequest",
]


class StudentSeatRequest(BaseModel):
    """One batch to put a new student in.

    :ivar batch_id: The batch
    :ivar fee_amount: This seat's fee, or null to inherit the batch's.
        Zero is a real fee of zero, a waiver
    """

    model_config = ConfigDict(extra="forbid")

    batch_id: uuid.UUID
    fee_amount: MoneyField | None = None


class StudentCreateRequest(BaseModel):
    """Record a student, and optionally seat them in batches [D3].

    :ivar display_name: The teacher-typed name
    :ivar student_phone: The student's number; unique per teacher [D2]
    :ivar guardian_phone: The guardian's number, if one is recorded
    :ivar student_email: The student's address; unique per teacher [U2]
    :ivar guardian_email: The guardian's address, if one is recorded
    :ivar enrollments: The batches to put them in, possibly none
    :ivar client_mutation_id: The retry key; a resend under it returns the
        student the first request created
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=120)
    student_phone: PhoneField | None = None
    guardian_phone: PhoneField | None = None
    student_email: RecordedEmailField = None
    guardian_email: RecordedEmailField = None
    enrollments: list[StudentSeatRequest] = Field(default_factory=list, max_length=50)
    client_mutation_id: uuid.UUID | None = None


class StudentUpdateRequest(BaseModel):
    """Edit a student's name or contacts. Omitted fields are unchanged.

    A number or an address can be changed only while nobody holding that
    link has accepted it and it was never erased; the name can always
    change.

    :ivar display_name: The new name
    :ivar student_phone: The new student number, or null to clear it
    :ivar guardian_phone: The new guardian number, or null to clear it
    :ivar student_email: The new student address, or null to clear it
    :ivar guardian_email: The new guardian address, or null to clear it
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    student_phone: PhoneField | None = None
    guardian_phone: PhoneField | None = None
    student_email: RecordedEmailField = None
    guardian_email: RecordedEmailField = None


class StudentEnrollRequest(BaseModel):
    """Put an existing student in one more batch.

    :ivar batch_id: The batch
    :ivar fee_amount: This seat's fee, or null to inherit the batch's
    """

    model_config = ConfigDict(extra="forbid")

    batch_id: uuid.UUID
    fee_amount: MoneyField | None = None


class AddStudentsRequest(BaseModel):
    """Seat existing students in one batch, all or nothing.

    :ivar student_ids: The students
    """

    model_config = ConfigDict(extra="forbid")

    student_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class AddStudentsResponse(BaseModel):
    """How many seats were created.

    :ivar added: The count
    """

    added: int


class StudentSeatResponse(BaseModel):
    """One of a student's seats.

    :ivar enrollment_id: The seat, which fees, attendance and marks use
    :ivar batch_id: Its batch
    :ivar batch_name: That batch's name
    :ivar fee_amount: What the seat is charged -- its own fee, else the
        batch default -- or null when neither is set
    :ivar status: ``active``, or ``inactive`` once the student left
    :ivar inactive_from: The date they left, if they did
    :ivar outstanding: What this seat owes now
    :ivar is_removable: Whether the seat itself can be deleted
    """

    enrollment_id: uuid.UUID
    batch_id: uuid.UUID
    batch_name: str
    fee_amount: MoneyField | None
    status: str
    inactive_from: dt.date | None
    outstanding: MoneyField
    is_removable: bool


class StudentResponse(BaseModel):
    """One of this teacher's students, with every seat.

    :ivar student_id: The student
    :ivar display_name: The teacher-typed name
    :ivar student_phone: The student's number as the teacher typed it
    :ivar guardian_phone: The guardian's number as the teacher typed it
    :ivar student_email: The student's address as the teacher typed it,
        lowercased. Teacher-written, never an account's own [U2: BR1.4]
    :ivar guardian_email: The guardian's address, likewise
    :ivar student_state: ``pending``, ``accepted`` or ``declined``
    :ivar guardian_state: The same, or ``absent`` with no guardian
    :ivar enrollments: The seats, by batch name; possibly none
    :ivar total_outstanding: What the student owes across every seat
    :ivar is_removable: Whether removing the student would succeed [D4]
    """

    student_id: uuid.UUID
    display_name: str
    student_phone: str | None
    guardian_phone: str | None
    student_email: str | None
    guardian_email: str | None
    student_state: str
    guardian_state: str
    enrollments: list[StudentSeatResponse]
    total_outstanding: MoneyField
    is_removable: bool
