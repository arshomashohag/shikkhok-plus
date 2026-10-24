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
    JSON,
    Boolean,
    CheckConstraint,
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
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.money_type import MoneyColumn

# Imported at runtime, not under TYPE_CHECKING: SQLAlchemy resolves
# mapped annotations when the class is declared, so a guarded import
# leaves it unable to map the column.
from app.money import Money

#: The three representable per-link decisions, in state-machine order.
#: A link starts ``pending``, its holder may move it to ``accepted`` or
#: ``declined``, and a declined link may later become ``accepted``.
#: Nothing returns a link to ``pending`` [BR6.1].
DECISION_VALUES: tuple[str, ...] = ("pending", "accepted", "declined")

#: The database enum backing both decision columns, named so the model
#: and migration ``0004`` cannot drift. ``create_type=False`` because
#: the migration owns the type's lifecycle; a model that also tried to
#: create it would fail against a migrated database.
_DECISION = PgEnum(
    *DECISION_VALUES,
    name="enrollment_decision",
    create_type=False,
)

#: The seven ledger kinds, closed [ADR-002]. Spelled here as strings
#: rather than imported from :class:`app.money.LedgerEntryKind` because
#: this is the DATABASE type's value list and migration ``0005`` owns the
#: type's lifecycle; the two are asserted equal by a test rather than
#: collapsed into one declaration, so a kind added to the enumeration
#: without a migration fails loudly instead of silently diverging.
LEDGER_KIND_VALUES: tuple[str, ...] = (
    "charge",
    "receipt",
    "carry_forward",
    "carried_out",
    "forgiveness",
    "credit_grant",
    "credit_apply",
)

_LEDGER_KIND = PgEnum(
    *LEDGER_KIND_VALUES,
    name="ledger_entry_kind",
    create_type=False,
)

#: What a claimant is shown [BR6.3]. Server-set at verification.
CLAIM_STATUS_VALUES: tuple[str, ...] = (
    "pending",
    "approved_full",
    "approved_partial",
    "rejected",
)

_CLAIM_STATUS = PgEnum(
    *CLAIM_STATUS_VALUES,
    name="payment_claim_status",
    create_type=False,
)

#: The teacher's choice on approving less than was CHARGED [BR5.4].
#: Two values and no third: a default would silently choose for the
#: teacher and the two have opposite consequences for the student.
DISPOSITION_VALUES: tuple[str, ...] = ("carried", "waived")

_DISPOSITION = PgEnum(
    *DISPOSITION_VALUES,
    name="shortfall_disposition",
    create_type=False,
)

#: A reminder's delivery outcome [BR7.2]. ``pending`` exists because the
#: event commits BEFORE the push is dispatched: writing it afterwards
#: loses the record of a send that happened if the process dies between
#: the two, and a flag cannot express a failed send at all.
REMINDER_OUTCOME_VALUES: tuple[str, ...] = ("pending", "sent", "failed")

_REMINDER_OUTCOME = PgEnum(
    *REMINDER_OUTCOME_VALUES,
    name="reminder_outcome",
    create_type=False,
)

#: The one job name the heartbeat carries in V1 [NFR25.9].
FEE_GENERATION_JOB = "fee_cycle_generation"

__all__ = [
    "CLAIM_STATUS_VALUES",
    "DECISION_VALUES",
    "DISPOSITION_VALUES",
    "FEE_GENERATION_JOB",
    "LEDGER_KIND_VALUES",
    "REMINDER_OUTCOME_VALUES",
    "Account",
    "AuthAuditLog",
    "Batch",
    "BatchSubject",
    "Enrollment",
    "FeeCycle",
    "HiddenBatchPreference",
    "JobHeartbeat",
    "LedgerEntryRow",
    "OtpRequest",
    "Owner",
    "PaymentClaim",
    "Profile",
    "RateLimitCounter",
    "RefreshToken",
    "ReminderEvent",
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
    :ivar address: Collected at signup, and the single most consequential
        disclosure available in this product. Nullable because the
        already-added path reaches signup with no address yet. **Adding
        the column did not enrol it in the privacy gate**: the
        owner-private field set is matched by NAME and maintained by
        hand, so ``address`` joins it in this same Unit [BR3.4]
    """

    __tablename__ = "profile"

    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        primary_key=True,
    )
    self_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)


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
    """Append-only. A closed set of event types, and no content.

    **No OTP, no token, no phone number, no child name.** An audit log that
    leaks what it audits is a common and self-defeating mistake, so the
    correlation id is how a row is tied back to a request without carrying
    its contents [BR6.2].

    ``account_id`` is **nullable**, because an OTP issued for an unknown
    number has no account -- and recording a placeholder would reintroduce
    the existence oracle the issue path exists to close [BR2.7].

    :ivar id: Surrogate key
    :ivar account_id: Null when the number had no account
    :ivar event: One value from the closed ``AuthEvent`` enum
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
    :ivar student_decision: Whether the student link's holder accepted
    :ivar guardian_decision: Whether the guardian link's holder accepted
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
    # NO default, in Python or in the database [ADR-013]. Every insert
    # path must STATE the seat's initial state: a default is how a
    # future insert skips the decision silently, and the decision is
    # the only thing standing between a mistyped digit and a stranger
    # holding a lens over a child's records.
    student_decision: Mapped[str] = mapped_column(_DECISION, nullable=False)
    guardian_decision: Mapped[str] = mapped_column(_DECISION, nullable=False)
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


class FeeCycle(Base):
    """One enrollment's obligation for one period.

    **Deliberately thin, and the thinness is the design** [BR1.2]. Five
    columns and not one of them is money -- not charged, not paid, not
    outstanding, not a status. Every such quantity is derived by folding
    :class:`LedgerEntryRow` rows through ``app.money.derive``. A money
    column here would be a second source of truth that drifts from the
    entries producing it, silently and in the direction of whichever
    write path forgot to update it.

    The column set is asserted by a test rather than claimed in this
    docstring, on the project's standing rule that where a comment states
    a fact the fact is a claim and something must check it.

    **The unique constraint is the whole idempotency mechanism**
    [BR1.3, FR5.4]. Generation inserts with ``ON CONFLICT DO NOTHING``
    and the conflict is the SUCCESS path, never an error. This follows
    :class:`RateLimitCounter`'s built precedent: the second worker
    conflicts instead of reading a stale value. An application-level
    "has this already run?" guard passes a sequential test and
    double-charges under the two workers Phase 1 has.

    :ivar id: Surrogate key
    :ivar enrollment_id: The seat this obligation belongs to
    :ivar period: The calendar month as ``YYYY-MM``
    :ivar due_date: The computed due date after the short-month clamp,
        stored so a later change to the batch anchor does not move a due
        date a student has already been shown
    :ivar created_at: When the cycle was generated
    """

    __tablename__ = "fee_cycle"

    id: Mapped[uuid.UUID] = _uuid_column()
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("enrollment.id", ondelete="CASCADE"),
        nullable=False,
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    due_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "enrollment_id",
            "period",
            name="uq_fee_cycle_enrollment_period",
        ),
        Index("ix_fee_cycle_enrollment_id", "enrollment_id"),
    )


class PaymentClaim(Base):
    """A claim that money was paid out of band, and its verification.

    One table rather than two, because one claim has at most one
    verification and the verification is a decision *about* that claim.
    FR9.2 requires the previous decision to be retained and visible,
    which is a column on the thing corrected rather than a second row.

    **A claim is an ASSERTION and a charge is the OBLIGATION.** That
    distinction is why the shortfall is measured against what the cycle
    CHARGED and never against what was claimed [BR5.3]: measuring against
    the claim would let a payer change what they owe by changing what
    they assert.

    ``claimed_amount`` is **not capped** at the outstanding balance
    [BR5.2]. Money may genuinely have been overpaid out of band, and
    blocking an over-claim at submission makes a real overpayment
    unreportable -- leaving a phone call as the only route, which is the
    thing this feature exists to remove.

    :ivar id: Surrogate key
    :ivar enrollment_id: The seat the claim is against
    :ivar period: The period the claim resolved to at submission --
        the oldest unpaid cycle, resolved once and stored
    :ivar claimed_amount: What the claimant says they paid
    :ivar channel: Which service the money moved through
    :ivar transaction_id: The reference the claimant quotes; nullable
        regardless of how OQ-1 is answered
    :ivar submitted_by_account_id: Who submitted it
    :ivar submitted_at: When it was submitted
    :ivar status: The server-set outcome the claimant is shown
    :ivar approved_amount: What the teacher accepted; null while pending
    :ivar shortfall_disposition: Carried or waived, required when the
        approval is below the charge and null when it is not
    :ivar verified_by_account_id: Who decided
    :ivar verified_at: When they decided
    :ivar previous_decision: The prior decision, retained on a correction
        and visible to the teacher AND to the student and guardian
    """

    __tablename__ = "payment_claim"

    id: Mapped[uuid.UUID] = _uuid_column()
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("enrollment.id", ondelete="CASCADE"),
        nullable=False,
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    claimed_amount: Mapped[Money] = mapped_column(MoneyColumn, nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    transaction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submitted_by_account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
    )
    submitted_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # NO default, in Python or in the database, on the same reasoning as
    # the decision columns: every insert path states the claim's initial
    # status rather than inheriting one.
    status: Mapped[str] = mapped_column(_CLAIM_STATUS, nullable=False)
    approved_amount: Mapped[Money | None] = mapped_column(MoneyColumn, nullable=True)
    shortfall_disposition: Mapped[str | None] = mapped_column(
        _DISPOSITION, nullable=True
    )
    verified_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True,
    )
    verified_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    previous_decision: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "claimed_amount > 0",
            name="ck_payment_claim_claimed_amount_positive",
        ),
        CheckConstraint(
            "approved_amount IS NULL OR approved_amount >= 0",
            name="ck_payment_claim_approved_amount_non_negative",
        ),
        Index("ix_payment_claim_enrollment_id", "enrollment_id"),
        Index("ix_payment_claim_status", "status"),
    )


class LedgerEntryRow(Base):
    """One append-only movement of money against an enrollment.

    **The persisted counterpart of ``app.money.LedgerEntry``**, which is
    a value *shape* owning no table, no row, no identifier and no
    supersession. Named ``LedgerEntryRow`` rather than ``LedgerEntry``
    precisely so the two cannot be confused at a call site: one is what
    an entry MEANS arithmetically, the other is where it lives.

    ``period`` is a **plain string, not a foreign key** to
    :class:`FeeCycle`, and the reason is a real case. A
    ``carry_forward`` lands on the receiving period, and at the moment a
    teacher approves a short January payment the February cycle row does
    not exist yet. Keying the entry to a cycle row would force generation
    to run before a carry could be written, which inverts the
    dependency -- and ``period`` is the opaque key the money module folds
    on, with no calendar knowledge of its own.

    ``amount`` is **always non-negative; the sign lives in the kind**
    [BR3.4]. The value type refuses a negative already; the table carries
    its own ``CHECK`` because the fold never sees a row a migration or a
    repair script inserted.

    ``superseded_by_id`` **drives what a teacher SEES, not what the
    balance IS** [BR3.3]. The fold sums every row including superseded
    ones and their compensations, because a compensating pair sums to
    zero.

    :ivar id: Surrogate key
    :ivar enrollment_id: The ledger balances at enrollment level, which
        is why credit belongs here and not to a cycle
    :ivar period: The period this entry sits in, as ``YYYY-MM``
    :ivar kind: One of the seven, closed
    :ivar amount: A non-negative amount
    :ivar payment_claim_id: The verification that produced this entry,
        so a guardian can be shown what happened to their payment
    :ivar superseded_by_id: The compensating entry, on a correction
    :ivar created_by_account_id: Who caused this entry; NULL for the
        generation job, which is the honest value -- nobody did
    :ivar created_at: When the entry was appended
    """

    __tablename__ = "ledger_entry"

    id: Mapped[uuid.UUID] = _uuid_column()
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("enrollment.id", ondelete="CASCADE"),
        nullable=False,
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    kind: Mapped[str] = mapped_column(_LEDGER_KIND, nullable=False)
    amount: Mapped[Money] = mapped_column(MoneyColumn, nullable=False)
    payment_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("payment_claim.id", ondelete="SET NULL"),
        nullable=True,
    )
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("ledger_entry.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_ledger_entry_amount_non_negative"),
        Index("ix_ledger_entry_enrollment_id", "enrollment_id"),
        Index("ix_ledger_entry_enrollment_period", "enrollment_id", "period"),
        Index("ix_ledger_entry_payment_claim_id", "payment_claim_id"),
    )


class ReminderEvent(Base):
    """One fee reminder, recorded as an event and not as a flag.

    **An event, because a boolean cannot express channel, a failed send,
    or a second reminder** [BR7.1, FR10.3], and would force a migration
    the moment a second channel arrives. The teacher-facing "reminded 3
    days ago" / "Never reminded" state is derived as the latest event per
    ``(enrollment, period)``.

    ``outcome`` carries ``pending`` as well as ``sent`` and ``failed``
    because the row is committed BEFORE the push is dispatched
    [reliability-design § 5]. The order is the opposite of the intuitive
    one deliberately: writing the event after a successful dispatch loses
    the record of a send that happened if the process dies in between.

    A failed send is **recorded, not swallowed** [BR7.2]. Best-effort
    delivery is the project's stated exception to "silent failures are
    not acceptable", and that exception covers not SURFACING the failure;
    it does not cover failing to record it, which is why ``outcome`` is a
    column.

    :ivar id: Surrogate key
    :ivar enrollment_id: The seat the reminder was about
    :ivar period: The period being chased, as ``YYYY-MM``
    :ivar channel: V1 ships ``push`` only; the column exists so a second
        channel is data rather than a migration
    :ivar sent_at: When the reminder was dispatched
    :ivar sent_by_account_id: The teacher who sent it
    :ivar outcome: ``pending`` before dispatch, then ``sent`` or
        ``failed``
    """

    __tablename__ = "reminder_event"

    id: Mapped[uuid.UUID] = _uuid_column()
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("enrollment.id", ondelete="CASCADE"),
        nullable=False,
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    sent_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    sent_by_account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
    )
    outcome: Mapped[str] = mapped_column(_REMINDER_OUTCOME, nullable=False)

    __table_args__ = (
        Index("ix_reminder_event_enrollment_period", "enrollment_id", "period"),
    )


class JobHeartbeat(Base):
    """When a scheduled job last succeeded, and what it did.

    **The mechanism behind the absence-of-success alert** [NFR25.9], and
    the most important row in the unit. D3 is the first thing in this
    product that acts without a user, and the failure that matters is not
    a job that fails loudly -- it is a job that *stops existing*.
    Self-healing is what makes that silence invisible: the system looks
    healthy right up to the moment somebody notices nobody has been
    billed since March.

    Four properties, each answering a way this could be built uselessly:

    * **Written by the job, not by the scheduler.** A scheduler firing a
      command that immediately crashes would still stamp a timer-level
      heartbeat. This row means *the work ran*.
    * **One row, updated in place.** The question is "when did this last
      succeed", which is a single value; an append-only run log would
      answer the same question and grow unboundedly.
    * **The counts ride along**, because they are in hand at the moment
      the row is written and are queryable without a metrics backend.
    * **A table, not a file and not process memory.** The instance is
      replaced on every deploy -- the exact event the alert exists to
      detect.

    **A run that finds nothing due still writes the row**, with
    ``cycles_created = 0`` [observability-design § 1.1a]. Generation is
    monthly, so most days legitimately create nothing; stamping only on
    ``> 0`` would leave the row stale for weeks during correct operation,
    fire the 48-hour alert constantly, and get it muted -- reaching the
    alert's own failure mode by the opposite route. The write is
    unconditional on OUTCOME and conditional only on COMPLETION.

    :ivar job_name: The job this row describes, and the primary key
    :ivar last_success_at: When the job last completed
    :ivar cycles_created: Cycles inserted on that run
    :ivar cycles_skipped: Cycles that conflicted and did nothing
    :ivar periods_failed: Enrollment-periods that raised and were skipped
    """

    __tablename__ = "job_heartbeat"

    job_name: Mapped[str] = mapped_column(Text, primary_key=True)
    last_success_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    cycles_created: Mapped[int] = mapped_column(Integer, nullable=False)
    cycles_skipped: Mapped[int] = mapped_column(Integer, nullable=False)
    periods_failed: Mapped[int] = mapped_column(Integer, nullable=False)
