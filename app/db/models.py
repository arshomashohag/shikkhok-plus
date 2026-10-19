"""The nine tables: seven owned, two created empty.

Three of them carry a security property in their **shape** rather than in
the code that touches them, which is the principle that where a rule
matters it should be mechanical:

================== ========================= ==============================
Entity             The shape                 What it prevents
================== ========================= ==============================
``OtpRequest``     ``otp_hash``, not ``otp`` A leaked row yielding codes
``RefreshToken``   ``family_id``             Invalidating one token and
                                             leaving the thief's working
``RateLimitCounter`` A row, not a variable   A limit that works in testing
                                             and not in production
================== ========================= ==============================

And one carries it in an **absence**: :class:`Account` has no role column,
so there is nothing to read a stale role from [BR1.1].
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.money_type import MoneyColumn

# Imported at runtime, not under TYPE_CHECKING: SQLAlchemy resolves
# mapped annotations when the class is declared, so a guarded import
# leaves it unable to map the column.
from app.money import Money

__all__ = [
    "Account",
    "AuthAuditLog",
    "Batch",
    "BatchSubject",
    "Enrollment",
    "HiddenBatchPreference",
    "OtpRequest",
    "Owner",
    "Profile",
    "RateLimitCounter",
    "RefreshToken",
    "ScheduleSlot",
    "VerifyAttempt",
]


def _uuid_column() -> Mapped[uuid.UUID]:
    """Build the standard surrogate primary key.

    :return: A UUID primary-key column defaulted in Python
    """
    return mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Account(Base):
    """An identity keyed on a permanent phone number.

    Created dormant when a teacher records a number, activated on first
    successful sign-in -- which is what lets a student or guardian claim a
    record without being invited [AC1.2.1].

    **There is deliberately no role column.** No ``role``, no
    ``is_teacher``, no ``kind``. The lens is computed per request from
    owned batches and enrollments [BR1.1], and a column here would be the
    exact stale-role defect the rule exists to prevent -- while looking
    entirely reasonable to whoever added it.

    :ivar id: Surrogate key
    :ivar phone: The permanent, unique key; never logged [RC-1, RC-2]
    :ivar created_at: When the record was created, dormant or otherwise
    :ivar activated_at: Set on first successful verify; null while dormant
    :ivar deleted_at: Reserved for U11's deletion paths
    """

    __tablename__ = "account"

    id: Mapped[uuid.UUID] = _uuid_column()
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    activated_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Profile(Base):
    """What a person writes about themselves. Visible only to its owner.

    **Row-level security lives on this table** [BR3.2], with a policy keyed
    on the session's account id. It is one of three layers: U2 shipped the
    response-schema layer, and this Unit adds this policy plus the table
    split.

    The teacher-typed display name lives on :class:`Enrollment`, written
    only by the teacher, so "which name does a teacher see" is answered by
    **which table the query reads** rather than by a filter someone
    remembers to apply [BR3.1, AC1.5.2].

    :ivar account_id: The owning account, and the policy's key
    :ivar self_name: The name the person chose for themselves
    :ivar photo_ref: An opaque reference to a self-supplied photo
    """

    __tablename__ = "profile"

    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        primary_key=True,
    )
    self_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_ref: Mapped[str | None] = mapped_column(Text, nullable=True)


class OtpRequest(Base):
    """One issued code, carrying four of the seven abuse controls.

    :ivar id: Surrogate key
    :ivar phone: The number the code was issued for; never logged
    :ivar otp_hash: A keyed digest, **never** the transmitted value
    :ivar purpose: Required, with exactly one V1 value
    :ivar issued_at: When the code was issued
    :ivar expires_at: Compared server-side; a client timestamp would make
        the five-minute window advisory [AC1.1.3]
    :ivar consumed_at: Set in the same transaction as the check that read
        it, so a concurrent second verify cannot slip between them
    """

    __tablename__ = "otp_request"

    id: Mapped[uuid.UUID] = _uuid_column()
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    otp_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    issued_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (Index("ix_otp_request_phone_issued_at", "phone", "issued_at"),)


class VerifyAttempt(Base):
    """One attempt against one code.

    A row per attempt rather than a counter on :class:`OtpRequest`, so the
    audit log can answer "was this code attacked" rather than only "how
    many times".

    :ivar id: Surrogate key
    :ivar otp_request_id: The code this attempt was made against
    :ivar attempted_at: When the attempt was made
    :ivar succeeded: Whether the presented code matched
    """

    __tablename__ = "verify_attempt"

    id: Mapped[uuid.UUID] = _uuid_column()
    otp_request_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("otp_request.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempted_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (Index("ix_verify_attempt_otp_request_id", "otp_request_id"),)


class RefreshToken(Base):
    """One refresh token in a rotation chain.

    **The family is the unit of invalidation, not the token** [BR4.1].
    Presenting a rotated-out token invalidates every token sharing its
    family id; invalidating only the presented one would leave the thief's
    working, which inverts the control.

    :ivar id: Surrogate key
    :ivar account_id: The account this token authenticates
    :ivar token_hash: A digest, never the token
    :ivar family_id: The rotation chain, and the unit of invalidation
    :ivar issued_at: When the token was issued
    :ivar expires_at: Thirty days out
    :ivar rotated_at: Set when superseded; presenting such a token is reuse
    :ivar reuse_detected_at: Records the event for the audit log, and makes
        a mass-logout incident explicable afterwards
    """

    __tablename__ = "refresh_token"

    id: Mapped[uuid.UUID] = _uuid_column()
    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    issued_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    rotated_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reuse_detected_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (Index("ix_refresh_token_family_id", "family_id"),)


class RateLimitCounter(Base):
    """A counter in the datastore, not in a process.

    **Datastore-backed is a correctness requirement, not hardening**
    [BR2.1]. A per-process dictionary is the obvious implementation, passes
    every naive test, and silently stops working the moment there are two
    workers -- which Phase 1 has, since one Lightsail host runs several
    Uvicorn workers.

    ``scope_kind`` distinguishes number, ip_prefix and global, so the
    sub-ceilings sit **beneath** the global one: a global-only ceiling
    converts a financial attack into a total lockout of every legitimate
    teacher for the rest of the day [BR2.5].

    :ivar id: Surrogate key
    :ivar scope_kind: ``number``, ``ip_prefix`` or ``global``
    :ivar scope_value: The number, prefix, or the global sentinel
    :ivar window_start: The truncated start of this counter's window
    :ivar count: How many sends this scope has consumed in that window
    """

    __tablename__ = "rate_limit_counter"

    id: Mapped[uuid.UUID] = _uuid_column()
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_value: Mapped[str] = mapped_column(String(64), nullable=False)
    window_start: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        # The unique constraint is what makes the atomic upsert-and-increment
        # possible: two workers racing on the same window cannot both read a
        # stale count, because the second one conflicts and updates instead.
        UniqueConstraint(
            "scope_kind",
            "scope_value",
            "window_start",
            name="uq_rate_limit_counter_scope_window",
        ),
    )


class AuthAuditLog(Base):
    """Append-only. Five event types, and no content.

    **No OTP, no token, no phone number, no child name.** An audit log that
    leaks what it audits is a common and self-defeating mistake, so the
    correlation id is how a row is tied back to a request without carrying
    its contents [BR6.2].

    ``account_id`` is **nullable**, because an OTP issued for an unknown
    number has no account -- and recording a placeholder would reintroduce
    the existence oracle the issue path exists to close [BR2.7].

    :ivar id: Surrogate key
    :ivar account_id: Null when the number had no account
    :ivar event: One of the five values in the closed enum
    :ivar occurred_at: When the event happened
    :ivar correlation_id: Ties the row to a request, carrying no content
    """

    __tablename__ = "auth_audit_log"

    id: Mapped[uuid.UUID] = _uuid_column()
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True,
    )
    event: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (Index("ix_auth_audit_log_occurred_at", "occurred_at"),)


# ---------------------------------------------------------------------------
# Created EMPTY and never written by this Unit. [BR6.1]
#
# Empty is not absent: a query against a table that does not exist fails, so
# lens resolution needs both to exist. This is table shape only -- not an
# ownership transfer, and not a dependency on U4, which owns their behaviour
# and extends their columns. A test asserts this Unit contains no INSERT,
# UPDATE or DELETE against either.
# ---------------------------------------------------------------------------


class Owner(Base):
    """A teacher's ownership of batches. Read by lens resolution.

    **U4 owns this table's behaviour; U3 creates its shape.** The rows the
    skeleton needs come from a committed seed script, never from
    application code [BR6.3].

    :ivar id: Surrogate key
    :ivar account_id: The account that owns batches
    :ivar created_at: When ownership was recorded
    """

    __tablename__ = "owner"

    id: Mapped[uuid.UUID] = _uuid_column()
    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (Index("ix_owner_account_id", "account_id"),)


class Enrollment(Base):
    """A student's place in a batch, and the teacher-typed display name.

    ``display_name`` lives here rather than on :class:`Profile`, and that
    split is what makes the privacy boundary structural: a teacher reads
    this column and never reaches ``Profile`` [BR3.1].

    **There is no ``role`` column** [BR1.1]. U3 carried one, because its
    shell seated one account per row and needed to say which part that
    account played. U4 puts both links on a single row instead, so the
    seat IS the relationship: a guardian reaching this enrollment reaches
    the child's enrollment, which ``role`` could not express.

    **The two erasure markers are per LINK, not per row** [BR6.2]. One
    flag cannot express the four states, because a guardian's erasure
    would then permanently block a student who never claimed that seat
    and never erased anything.

    :ivar id: Surrogate key
    :ivar batch_id: The batch this seat belongs to
    :ivar student_account_id: The student, or NULL while the seat is
        dormant
    :ivar guardian_account_id: The guardian recorded for this seat, if any
    :ivar display_name: The teacher-typed name
    :ivar guardian_phone: The teacher-typed guardian contact
    :ivar fee_amount: This seat's fee, or NULL to inherit the batch
        default. Zero is a real fee of zero, which is a waiver
    :ivar joined_on: When the student joined
    :ivar inactive_from: The date after which no cycle generates
    :ivar student_relink_blocked_at: Set when the student erased
    :ivar guardian_relink_blocked_at: Set when the guardian erased
    :ivar created_at: When the enrollment was recorded
    """

    __tablename__ = "enrollment"

    id: Mapped[uuid.UUID] = _uuid_column()
    batch_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    student_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=True,
    )
    guardian_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True,
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    guardian_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fee_amount: Mapped[Money | None] = mapped_column(MoneyColumn, nullable=True)
    joined_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    inactive_from: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    student_relink_blocked_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    guardian_relink_blocked_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_enrollment_account_id", "student_account_id"),
        Index("ix_enrollment_batch_id", "batch_id"),
        Index("ix_enrollment_guardian_account_id", "guardian_account_id"),
        Index(
            "uq_enrollment_batch_student",
            "batch_id",
            "student_account_id",
            unique=True,
            postgresql_where=text("student_account_id IS NOT NULL"),
        ),
    )


class Batch(Base):
    """A teacher's class, carrying the fee defaults enrollments inherit.

    Keyed on ``owner_id`` rather than on an account, which is the
    indirection [AC2.1.3] that lets a batch outlive the person who
    created it -- a subscription anchored to a person cannot be handed
    over.

    ``collection_number`` is a teacher-typed payment **destination**, not
    money, and must never acquire a money type. ``fee_due_day`` is an
    integer day-of-month that matches the money gates' name tokens while
    carrying nothing of the kind, which is why BR3.3 allowlists it.

    :ivar id: Surrogate key
    :ivar owner_id: The owner whose batch this is
    :ivar name: The teacher's name for the class
    :ivar teacher_display_name: What students see the teacher called
    :ivar collection_number: Where payments are sent
    :ivar collection_channel: Which service that number belongs to
    :ivar default_fee: The fee an enrollment inherits when it sets none
    :ivar fee_due_day: Day of month 1-31; 29-31 clamp at generation
    :ivar marksheet_visible: U6's toggle; U4 only creates the column
    :ivar active: False collapses the batch to read-only history
    :ivar created_at: When the batch was created
    """

    __tablename__ = "batch"

    id: Mapped[uuid.UUID] = _uuid_column()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("owner.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    teacher_display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    collection_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    collection_channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    default_fee: Mapped[Money | None] = mapped_column(MoneyColumn, nullable=True)
    fee_due_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    marksheet_visible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (Index("ix_batch_owner_id", "owner_id"),)


class BatchSubject(Base):
    """One subject taught in a batch.

    A row rather than a column because a batch has one or more
    [AC2.1.1], and a separate table rather than an array because U6
    attaches exams to a subject and needs a key to reference.

    :ivar id: Surrogate key
    :ivar batch_id: The batch this subject belongs to
    :ivar name: The subject's name
    """

    __tablename__ = "batch_subject"

    id: Mapped[uuid.UUID] = _uuid_column()
    batch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("batch.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("ix_batch_subject_batch_id", "batch_id"),)


class ScheduleSlot(Base):
    """One weekly recurring slot. U5 generates sessions from these.

    ``weekday`` is an integer with a CHECK constraint rather than a
    string, because a string admits 'Monday', 'monday' and 'Mon' as three
    different Mondays. The times are ``TIME`` rather than timestamps: a
    weekly recurrence has no date until U5 instantiates it.

    :ivar id: Surrogate key
    :ivar batch_id: The batch this slot belongs to
    :ivar weekday: 0-6, Monday through Sunday
    :ivar start_time: When the class starts
    :ivar end_time: When the class ends
    """

    __tablename__ = "schedule_slot"

    id: Mapped[uuid.UUID] = _uuid_column()
    batch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("batch.id", ondelete="CASCADE"),
        nullable=False,
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[dt.time] = mapped_column(Time, nullable=False)


class HiddenBatchPreference(Base):
    """One person's choice to hide one inactive batch from their list.

    **A separate table, not a column on Enrollment** [AC2.6.3]. Hiding is
    per viewer: a student hiding a batch must not hide it from the
    guardian or the teacher, and a column on the shared enrollment row
    would be read by every lens that touches it.

    Keyed on ``account_id`` because the preference follows the person
    across lenses rather than the seat.

    :ivar id: Surrogate key
    :ivar account_id: Whose preference this is
    :ivar batch_id: The batch they hid
    :ivar hidden_at: When they hid it
    """

    __tablename__ = "hidden_batch_preference"

    id: Mapped[uuid.UUID] = _uuid_column()
    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("batch.id", ondelete="CASCADE"),
        nullable=False,
    )
    hidden_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("account_id", "batch_id", name="uq_hidden_batch_preference"),
    )
