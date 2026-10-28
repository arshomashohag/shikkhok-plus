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

#: The fee job's heartbeat name [NFR25.9].
FEE_GENERATION_JOB = "fee_cycle_generation"

#: D4's session-generation job, registered under its OWN name beside the
#: fee job [observability-design § 4.1, NFR1.8]. A shared name would let
#: a healthy fee run mask a session job that has never fired, and session
#: generation self-heals -- so a job whose cron entry was never wired
#: looks completely healthy right up to the morning a teacher opens the
#: app and there is no class to mark attendance against.
SESSION_GENERATION_JOB = "session_generation"

#: D6's retention purge, registered under its OWN name beside the other
#: two [BR4.1]. Registering a heartbeat is the WHOLE of what the purge
#: does to get freshness coverage: ``check_all_jobs`` enumerates every
#: row in ``job_heartbeat`` rather than naming a job, so a third job
#: appears in the freshness report without the checker, the host's bare
#: ``check-freshness`` invocation, or ``user_data.sh.tftpl`` changing.
#: That property is why option B was chosen on 2026-10-25, and this
#: constant is the first time it is cashed in by a unit that did not
#: write the checker.
RETENTION_PURGE_JOB = "retention_purge"

#: A session's three states [FR3.3]. ``cancelled`` forbids attendance
#: and topic writes [BR1.6] and is the only transition that does.
#: ``held`` is reached by RECORDING, never by the clock passing: a class
#: whose time has gone and which nobody recorded stays ``scheduled``,
#: which is what keeps an unrecorded class visible [NFR19.45].
SESSION_STATUS_VALUES: tuple[str, ...] = ("scheduled", "held", "cancelled")

_SESSION_STATUS = PgEnum(
    *SESSION_STATUS_VALUES,
    name="session_status",
    create_type=False,
)

#: Whether generation produced a session row or a teacher created it
#: [AC3.0.3]. **No default, on ADR-013's reasoning applied to a second
#: column**: a later insert path that does not state the origin is a
#: path that forgot to think about it, and generation must never
#: re-create or delete an ad-hoc session [BR1.4].
SESSION_ORIGIN_VALUES: tuple[str, ...] = ("recurrence", "ad_hoc")

_SESSION_ORIGIN = PgEnum(
    *SESSION_ORIGIN_VALUES,
    name="session_origin",
    create_type=False,
)

#: Which queued path produced a submission row [BR2.1, § B.7]. The
#: roster and the topic log share one replay store and one set of
#: rules, and this column is what keeps their version counters from
#: colliding in ``uq_queued_submission_version``. **No default**, on
#: ``origin``'s reasoning: a later insert path that does not state the
#: kind is a path that forgot to think about it.
SUBMISSION_KIND_VALUES: tuple[str, ...] = ("attendance", "topic")

_SUBMISSION_KIND = PgEnum(
    *SUBMISSION_KIND_VALUES,
    name="queued_submission_kind",
    create_type=False,
)

#: FR4.3's four result states, and the enum is the point: a zero is a
#: ``marked`` result with ``marks`` 0 and is never conflated with
#: ``absent``. ``not_entered`` is a seat the teacher has not reached yet
#: [AC4.1.4] and ``joined_after`` is a seat that could not have sat the
#: exam [AC4.1.5]. **A client switches on this enum**, so adding a value
#: is a breaking change under the contract's § B.1.1 rule.
RESULT_STATE_VALUES: tuple[str, ...] = (
    "marked",
    "absent",
    "not_entered",
    "joined_after",
)

_RESULT_STATE = PgEnum(
    *RESULT_STATE_VALUES,
    name="mark_result_state",
    create_type=False,
)

__all__ = [
    "CLAIM_STATUS_VALUES",
    "DECISION_VALUES",
    "DISPOSITION_VALUES",
    "FEE_GENERATION_JOB",
    "LEDGER_KIND_VALUES",
    "REMINDER_OUTCOME_VALUES",
    "RESULT_STATE_VALUES",
    "RETENTION_PURGE_JOB",
    "SESSION_GENERATION_JOB",
    "SESSION_ORIGIN_VALUES",
    "SESSION_STATUS_VALUES",
    "SUBMISSION_KIND_VALUES",
    "Account",
    "Announcement",
    "Attendance",
    "AuthAuditLog",
    "Batch",
    "BatchSubject",
    "Enrollment",
    "Exam",
    "FeeCycle",
    "HiddenBatchPreference",
    "JobHeartbeat",
    "LedgerEntryRow",
    "Mark",
    "OtpRequest",
    "Owner",
    "PaymentClaim",
    "Profile",
    "QueuedSubmission",
    "RateLimitCounter",
    "RefreshToken",
    "ReminderEvent",
    "ScheduleSlot",
    "Session",
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
    :ivar deleted_at: Unused. D6 hard-deletes the row [BR1.1], so
        nothing ever writes this column; it is kept rather than
        dropped because dropping it is irreversible and an unused
        column is the smaller change
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
    :ivar student_phone: The teacher-typed STUDENT number, canonical. What
        links the seat to the student's account, at creation when that
        account exists and at sign-up when it does not [0008]
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
    # SET NULL on BOTH links, matched deliberately [BR1.2, 0007]. The
    # student link was CASCADE until 0007 while the guardian link beside
    # it was SET NULL, so one user action meant two different things
    # depending on which role the account held -- a student's deletion
    # removed the enrollment row and the six tables cascading from it,
    # taking the teacher's attendance, marks and settled fee ledger for
    # that seat, while a guardian's deletion lost nothing.
    #
    # The rule the enumeration produced: a CASCADE to account.id is
    # wrong exactly when its table's disposition is RETAIN_WITH_BASIS,
    # because the manifest already says the row must survive.
    student_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True,
    )
    guardian_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True,
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    guardian_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    student_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
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
        Index("ix_enrollment_student_phone", "student_phone"),
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
    # NULLABLE and SET NULL since 0007, matching `verified_by_account_id`
    # beside it [BR1.2]. The asymmetry was inside ONE table: a teacher's
    # deletion unlinked the verification and kept the claim, while a
    # student's deleted the claim outright -- the record of a payment
    # they submitted, with its transaction id and channel, on a table
    # the manifest marks RETAIN_WITH_BASIS.
    #
    # The column admits NULL because `SET NULL` against a NOT NULL
    # column is refused by PostgreSQL; the nullability is the
    # constraint's precondition, not an independent relaxation.
    submitted_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True,
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


class Session(Base):
    """One instance of a class: a date and time a batch met.

    **Materialised rows, not a computed view of the recurrence rule.**
    ``ScheduleSlot`` holds the weekly recurrence; the instances are rows
    because attendance, the topic log and a reschedule all attach to a
    specific occurrence, and AC3.0.2 requires a schedule change to leave
    past sessions untouched -- which a computed view cannot do, because
    recomputing it moves history [BR1.2].

    **This row carries the product's first optimistic-concurrency
    version.** Verified rather than assumed: no other table in this
    module has a version column, and the only concurrency primitives in
    the backend are ``SELECT ... FOR UPDATE`` in three places. A
    pessimistic lock is the wrong tool for this path specifically -- the
    contender is not a concurrent request but a STALE one, composed
    hours earlier on a phone with no connectivity, and there is no
    transaction to hold open across that gap [BR3.3, ADR-006].

    ``topic_version`` is **separate** from ``attendance_version``
    because the two queued paths touch disjoint columns. One shared
    counter would refuse a topic log because a roster arrived, which is
    a conflict the teacher cannot act on: there is nothing to compare
    and nothing to re-apply differently.

    :ivar id: Surrogate key
    :ivar batch_id: The batch that met
    :ivar batch_subject_id: Which subject this taught, or NULL
    :ivar date: The occurrence's date
    :ivar start_time: When it starts
    :ivar end_time: When it ends, or NULL
    :ivar topic: What was covered, or NULL while unlogged [BR2.2]
    :ivar status: ``scheduled``, ``held`` or ``cancelled``
    :ivar origin: ``recurrence`` or ``ad_hoc``; no default [BR1.4]
    :ivar attendance_version: The roster's optimistic version
    :ivar topic_version: The topic log's own optimistic version
    :ivar created_at: When the row was created
    """

    __tablename__ = "session"

    id: Mapped[uuid.UUID] = _uuid_column()
    batch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("batch.id", ondelete="CASCADE"),
        nullable=False,
    )
    # SET NULL rather than CASCADE: a subject removed from the batch
    # must not delete the history of the classes that taught it.
    batch_subject_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("batch_subject.id", ondelete="SET NULL"),
        nullable=True,
    )
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    start_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    # Nullable, and that is BR2.2: an unwritten topic is a different
    # fact from one the teacher saved as blank, and collapsing the two
    # makes "topics covered in each" unanswerable.
    topic: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(_SESSION_STATUS, nullable=False)
    origin: Mapped[str] = mapped_column(_SESSION_ORIGIN, nullable=False)
    attendance_version: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        # The whole idempotency mechanism [BR1.3]. Generation inserts
        # with ON CONFLICT DO NOTHING and the conflict is the SUCCESS
        # path -- the same shape as uq_fee_cycle_enrollment_period and
        # RateLimitCounter's constraint before it.
        UniqueConstraint(
            "batch_id",
            "date",
            "start_time",
            name="uq_session_batch_date_start",
        ),
        Index("ix_session_batch_id", "batch_id"),
        Index("ix_session_batch_date", "batch_id", "date"),
        CheckConstraint(
            "attendance_version >= 0",
            name="ck_session_attendance_version_non_negative",
        ),
        CheckConstraint(
            "topic_version >= 0",
            name="ck_session_topic_version_non_negative",
        ),
    )


class QueuedSubmission(Base):
    """One accepted queued write, and the row both guarantees live on.

    **A table rather than a column, and that is the design.** § B.7
    requires a replayed ``client_mutation_id`` to return the ORIGINAL
    stored result with 200 and never write twice. A roster is MANY
    attendance rows sharing ONE mutation id, so a unique constraint on
    that column cannot live on ``attendance``: per-row it is not unique
    for the write it is meant to protect, and absent it leaves
    idempotency to application logic.

    **That is the shape D3's double-crediting defect had** -- a write
    with no natural key to conflict on. Here the key exists and is the
    constraint [reliability-design § 5].

    **It serves both queued paths**, which is what ``kind`` is for. The
    topic log is on the same device queue under the same rules [BR2.1],
    so it needs the same replay store -- and reusing this table
    unchanged could not work, because ``UNIQUE (session_id,
    resulting_version)`` is attendance-versioned and a topic write
    reaching topic version N+1 would collide with the roster write that
    reached attendance version N+1 on the same session.

    :ivar id: Surrogate key
    :ivar session_id: The session this wrote
    :ivar kind: Which queued path produced it
    :ivar submitted_by_account_id: Who submitted it
    :ivar client_mutation_id: The client's replay key
    :ivar base_version: The version this write was composed against
    :ivar resulting_version: The version after it applied; base + 1
    :ivar composed_at: Client-reported, used in NO decision [NFR24.20]
    :ivar created_at: When the server accepted it
    """

    __tablename__ = "queued_submission"

    id: Mapped[uuid.UUID] = _uuid_column()
    session_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("session.id", ondelete="CASCADE"),
        nullable=False,
    )
    # NULLABLE and SET NULL since 0007 [BR1.2]. The account it names is
    # the TEACHER who submitted, so this row only becomes reachable by
    # an account deletion once BR1.6's refusal is lifted -- but the
    # table's disposition is RETAIN_WITH_BASIS either way, and a
    # cascade against it was a contradiction whether or not any path
    # currently reaches it.
    #
    # The replay constraint `uq_queued_submission_replay` spans this
    # column. A NULL here makes that pair no longer unique-constrained
    # against other NULLs, which is correct: PostgreSQL treats NULLs as
    # distinct in a unique index, and a replay check for an account
    # that no longer exists has nothing to protect.
    submitted_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(_SUBMISSION_KIND, nullable=False)
    client_mutation_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False
    )
    base_version: Mapped[int] = mapped_column(Integer, nullable=False)
    resulting_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # A DEVICE clock, recorded for the pilot's queue-latency question
    # and never read in a decision. A device clock in a conflict rule
    # would let a wrong phone time silently reorder two writes.
    composed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        # The idempotency constraint § B.7 specifies, scoped per
        # ACCOUNT and deliberately NOT by kind: account B presenting
        # account A's id is not a duplicate at all [§ 5.2], while the
        # same account's id arriving on the other path is still the
        # same client decision and is still a replay.
        UniqueConstraint(
            "submitted_by_account_id",
            "client_mutation_id",
            name="uq_queued_submission_replay",
        ),
        # Belt and braces on the version increment: two writes of one
        # KIND cannot both produce version N+1. This is what makes
        # BR3.4's guarantee survive somebody later rewriting the
        # conditional update into a read-then-write.
        #
        # Without `kind` the two counters would collide: a topic write
        # reaching topic version N+1 would be refused by the roster
        # write that reached attendance version N+1 on the same
        # session.
        UniqueConstraint(
            "session_id",
            "kind",
            "resulting_version",
            name="uq_queued_submission_version",
        ),
        Index("ix_queued_submission_session_id", "session_id"),
        CheckConstraint(
            "base_version >= 0",
            name="ck_queued_submission_base_version_non_negative",
        ),
        CheckConstraint(
            "resulting_version >= 1",
            name="ck_queued_submission_resulting_version_positive",
        ),
    )


class Attendance(Base):
    """One enrollment's presence at one session.

    The whole roster is written in a **single atomic operation** and
    never one row per student [AC3.1.5]: a per-student write leaves
    attendance half-saved after a mid-roster connection drop, and
    nothing on screen can reconcile that.

    ``present`` has **no third value**. AC3.1.4 defaults every seat to
    present and the teacher marks only exceptions, so an unsubmitted
    roster is an ABSENT row rather than a null column.

    :ivar id: Surrogate key
    :ivar session_id: The session
    :ivar enrollment_id: The seat
    :ivar present: Whether the student attended
    :ivar recorded_at: When this was marked
    :ivar recorded_by_account_id: Who marked it
    :ivar submission_id: The accepted roster write that produced it
    """

    __tablename__ = "attendance"

    id: Mapped[uuid.UUID] = _uuid_column()
    session_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("session.id", ondelete="CASCADE"),
        nullable=False,
    )
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("enrollment.id", ondelete="CASCADE"),
        nullable=False,
    )
    present: Mapped[bool] = mapped_column(Boolean, nullable=False)
    recorded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    recorded_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True,
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("queued_submission.id", ondelete="CASCADE"),
        nullable=False,
    )

    __table_args__ = (
        # One row per seat per session. A roster re-submission REPLACES
        # rather than appends [BR3.5], which is what makes the upsert
        # expressible at all.
        UniqueConstraint(
            "session_id",
            "enrollment_id",
            name="uq_attendance_session_enrollment",
        ),
        Index("ix_attendance_enrollment_id", "enrollment_id"),
        Index("ix_attendance_submission_fk", "submission_id"),
    )


class Exam(Base):
    """One assessment in one batch and subject [AC4.1.1].

    Holds no result; results are :class:`Mark` rows.

    ``total_marks`` is an **integer count of marks and not a money
    value** -- it must never acquire a money type, for the same reason
    ``Batch.collection_number`` must not. It matches the money-name
    gate's ``total`` token and carries a per-column exemption stating
    exactly that.

    :ivar id: Surrogate key
    :ivar batch_id: The batch
    :ivar batch_subject_id: Which of that batch's subjects
    :ivar title: The teacher's name for the assessment
    :ivar date: The exam date, compared against ``joined_on`` [BR4.3]
    :ivar total_marks: The denominator, at least 1
    :ivar created_at: When the exam was created
    """

    __tablename__ = "exam"

    id: Mapped[uuid.UUID] = _uuid_column()
    batch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("batch.id", ondelete="CASCADE"),
        nullable=False,
    )
    # RESTRICT, not CASCADE or SET NULL: deleting a subject must not
    # silently destroy the exams and marks recorded under it, and an
    # exam with no subject cannot satisfy AC4.1.1.
    batch_subject_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("batch_subject.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    total_marks: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_exam_batch_id", "batch_id"),
        Index("ix_exam_batch_subject_id", "batch_subject_id"),
        # At least 1: a total of zero makes every percentage undefined
        # and every band degenerate.
        CheckConstraint("total_marks >= 1", name="ck_exam_total_marks_positive"),
    )


class Mark(Base):
    """One enrollment's result in one exam, append-only.

    **A supersession chain, the same shape** :class:`LedgerEntryRow`
    **uses and for the same reason**: AC3.1.7 and FR9.2 require a
    correction to be visible, and an UPDATE destroys the fact that a
    mark changed. A correction appends a new row and sets the old row's
    ``superseded_by_id`` in the same transaction [BR4.4].

    :ivar id: Surrogate key
    :ivar exam_id: The exam
    :ivar enrollment_id: The seat
    :ivar result_state: One of the four states [BR4.3]
    :ivar marks: Non-null if and only if ``result_state`` is ``marked``
    :ivar recorded_at: When this was entered
    :ivar recorded_by_account_id: Who entered it
    :ivar superseded_by_id: NULL on the live row [BR4.5]
    :ivar created_at: When the row was created
    """

    __tablename__ = "mark"

    id: Mapped[uuid.UUID] = _uuid_column()
    exam_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("exam.id", ondelete="CASCADE"),
        nullable=False,
    )
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("enrollment.id", ondelete="CASCADE"),
        nullable=False,
    )
    result_state: Mapped[str] = mapped_column(_RESULT_STATE, nullable=False)
    # Nullable because the other three states have no number, and
    # storing zero for them is exactly the conflation FR4.3 forbids.
    marks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    recorded_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True,
    )
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("mark.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        # A DATABASE constraint rather than a validator, because this is
        # the invariant the four-state requirement reduces to and a
        # validator is bypassed by every write path that forgets it.
        CheckConstraint(
            "(result_state = 'marked') = (marks IS NOT NULL)",
            name="ck_mark_state_marks_biconditional",
        ),
        CheckConstraint(
            "marks IS NULL OR marks >= 0",
            name="ck_mark_marks_non_negative",
        ),
        # A PARTIAL unique index, the same shape as the built
        # uq_enrollment_batch_student. Without it a correction that
        # fails to set the old row's pointer leaves two live marks and
        # the marksheet silently counts one student twice [BR4.5].
        Index(
            "uq_mark_live_per_seat",
            "exam_id",
            "enrollment_id",
            unique=True,
            postgresql_where=text("superseded_by_id IS NULL"),
        ),
        Index("ix_mark_exam_id", "exam_id"),
        Index("ix_mark_enrollment_id", "enrollment_id"),
    )


class Announcement(Base):
    """One note a teacher posted to a batch [FR3.8].

    **Soft-deleted rather than removed**, because AC3.3.3 requires it to
    disappear from student and guardian views while FR9.2's correction
    history and the governance manifest's "stays with the batch's
    history" basis both require the fact of it to survive.

    **No expiry column and no expiry job** [AC3.3.4]. Stated as an
    absence because the obvious implementation of "announcements" adds
    one, and a silently expiring announcement is a message the teacher
    believes was delivered.

    :ivar id: Surrogate key
    :ivar batch_id: The batch it was posted to
    :ivar body: The note
    :ivar created_at: When it was posted
    :ivar edited_at: NULL until edited; its non-null-ness IS the
        "shows as edited" flag [AC3.3.2]
    :ivar deleted_at: NULL while visible [AC3.3.3]
    :ivar posted_by_account_id: Who posted it
    """

    __tablename__ = "announcement"

    id: Mapped[uuid.UUID] = _uuid_column()
    batch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("batch.id", ondelete="CASCADE"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(String(4000), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # A separate boolean would be a second source of truth that can
    # disagree with the timestamp.
    edited_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    posted_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (Index("ix_announcement_batch_id", "batch_id"),)


class Notification(Base):
    """A message in one account's in-app inbox.

    **Addressed to an account, read only by that account.** Every read is
    scoped by the authenticated caller's id, never by an id taken from a
    request, so there is no lens to resolve [0009].

    ``batch_name`` is copied at send time rather than joined, so the
    message reads the same after the batch is renamed or the seat is
    removed -- it is a record of what was said.

    :ivar id: Surrogate key
    :ivar account_id: Whose inbox it sits in
    :ivar enrollment_id: The seat it is about, if any
    :ivar kind: What produced it, such as ``fee_reminder``
    :ivar batch_name: The batch it concerns, as named when sent
    :ivar period: The period it concerns, as ``YYYY-MM``, if any
    :ivar amount: The money it concerns, if any
    :ivar created_at: When it was sent
    :ivar read_at: When its owner opened the inbox after it arrived
    """

    __tablename__ = "notification"

    id: Mapped[uuid.UUID] = _uuid_column()
    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
    )
    enrollment_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("enrollment.id", ondelete="SET NULL"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    batch_name: Mapped[str] = mapped_column(Text, nullable=False)
    period: Mapped[str | None] = mapped_column(String(7), nullable=True)
    amount: Mapped[Money | None] = mapped_column(MoneyColumn, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    read_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_notification_account_created", "account_id", "created_at"),
    )
