"""Request and response bodies for fees, claims and verification.

**Every money value is a JSON string, never a number** [BR6.2, TC-7,
D-20], through the shared ``Money`` component rather than a per-field
pattern. A JSON number is an IEEE 754 double in most parsers, so
emitting one converts the value to a float on the client -- reintroducing
the exact representation error the money module exists to prevent, on
the far side of the wire where none of its controls reach.

**Every response carries a server-computed DECISION, not the inputs to
one** [TC-9, D-31]. A fee cycle carries ``status`` as an enum, because
``if (balance > 0) "Due" else "Paid"`` is a business rule about what
counts as due wearing presentation's clothes -- and it diverges the first
time a waiver is involved, since a fully waived cycle has a zero balance
and is not "Paid".

**No schema here carries a payment method's number or account fields**;
``app.schemas.payment_methods`` holds them, and a test over the generated
document asserts which routes carry them [BR6.4, NFR14.32].
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import MoneyField

__all__ = [
    "ClaimQueueItemResponse",
    "ClaimResponse",
    "FeeCycleResponse",
    "FeeHistoryResponse",
    "OwedChildResponse",
    "OwedTogetherResponse",
    "PayableResponse",
    "PayablesResponse",
    "PaymentSubmitRequest",
    "PaymentSubmittedResponse",
    "RecentDecisionResponse",
    "ReminderRequest",
    "ReminderResponse",
    "RosterFeeRowResponse",
    "ShortfallPreviewRequest",
    "ShortfallPreviewResponse",
    "SubmittedClaimResponse",
    "VerificationQueueResponse",
    "VerificationRequest",
    "WaitingPaymentResponse",
]

#: The four statuses a cycle reports [BR6.1]. A ``Literal`` rather than
#: a free ``str`` so the generated document publishes the closed set and
#: a client author reads the contract rather than guessing it.
FeeStatus = Literal["paid", "partly_paid", "unpaid", "waived"]

#: The four a claim reports [BR6.3].
ClaimStatus = Literal["pending", "approved_full", "approved_partial", "rejected"]

#: The teacher's choice on approving less than was charged [BR5.4].
ShortfallDisposition = Literal["carried", "waived"]


class FeeCycleResponse(BaseModel):
    """One period's fee, for any lens entitled to read it.

    ``status`` is the decision; ``outstanding`` is reported for display
    and is never what the client computes a status from.

    :ivar period: The period, as ``YYYY-MM``
    :ivar due_date: The due date, after the short-month clamp
    :ivar charged: What was charged for this period
    :ivar outstanding: What is still owed, floored at zero
    :ivar status: The server-computed status
    """

    model_config = ConfigDict(extra="forbid")

    period: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    due_date: dt.date
    charged: MoneyField
    outstanding: MoneyField
    status: FeeStatus


class FeeHistoryResponse(BaseModel):
    """One seat's periods, with the total the server computed.

    **A wrapper rather than a bare array, and the total is why.** The
    client must not sum the rows: that is money arithmetic on the
    Android side, which [D-20] forbids, and it would be wrong the
    moment the history paginates — a page of three periods would
    report a total that is not the balance.

    The value is the ledger fold's own ``total_outstanding``, floored
    at zero inside the money module, not a second sum computed beside
    the rows.

    :ivar cycles: One row per generated period, oldest first
    :ivar total_outstanding: What this seat still owes in total
    """

    model_config = ConfigDict(extra="forbid")

    cycles: list[FeeCycleResponse]
    total_outstanding: MoneyField


class RosterFeeRowResponse(BaseModel):
    """One seat's fee position, as its teacher sees it.

    The key is ``enrollment_id`` and never an account id [ADR-001],
    asserted schema-wide by the built privacy gate.

    **No payment-method details.** They are carried only by the
    payment-method routes and this is not one [NFR14.33].

    :ivar enrollment_id: The teacher-facing key
    :ivar display_name: The teacher-typed name
    :ivar outstanding: What this seat owes across every period
    :ivar current_period: The latest generated period, or null
    :ivar current_status: That period's status, or null
    :ivar due_date: That period's due date, or null
    :ivar days_overdue: How late the oldest unpaid period is, decided by
        the server against Bangladesh's date, or null
    :ivar verifying: The total of claims still waiting for the teacher
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_id: uuid.UUID
    display_name: str
    outstanding: MoneyField
    current_period: str | None = None
    current_status: FeeStatus | None = None
    due_date: dt.date | None = None
    days_overdue: int | None = None
    verifying: MoneyField | None = None


class VerificationRequest(BaseModel):
    """Record a teacher's decision on a claim [AC6.3.x].

    ``shortfall_disposition`` is **required where the approval is below
    the charge and forbidden where it is not** [BR5.4]. It carries no
    default: the two choices have opposite consequences for the student,
    so a default silently chooses for the teacher. The requirement
    cannot be expressed in the schema alone -- it depends on what the
    cycle was charged -- so the server enforces it and this field stays
    optional here.

    ``correcting`` is **the teacher saying "I know this claim is already
    decided and I am revising it"** [BR5.7, FR9.2]. It defaults to
    ``False``, so an ordinary verification of an undecided claim needs no
    flag and a *concurrent* second verification is refused rather than
    silently double-crediting the payment.

    It cannot be inferred from the claim's state. A decided claim with a
    second request arriving is exactly the shape of both the race this
    guard exists to stop and the correction FR9.2 requires, and the
    server cannot tell them apart -- only the teacher knows which one
    they meant. Inferring it would mean choosing to let the race through.

    :ivar approved_amount: What the teacher accepts
    :ivar shortfall_disposition: Carried or waived, where one applies
    :ivar correcting: True when deliberately revising a decided claim
    """

    model_config = ConfigDict(extra="forbid")

    approved_amount: MoneyField
    shortfall_disposition: ShortfallDisposition | None = None
    correcting: bool = False


class RejectionRequest(BaseModel):
    """Reject a claim, optionally as a correction [BR5.6, BR5.7].

    A body with one optional field rather than no body at all, because
    rejection is correctable for the same reason approval is: a teacher
    who rejected the wrong claim must be able to say so, and FR9.2 makes
    no exception for the rejection path.

    Every field defaults, so an ordinary rejection may still send no
    body.

    :ivar correcting: True when deliberately revising a decided claim
    :ivar reason: Why the claim is rejected, shown to the family
    """

    model_config = ConfigDict(extra="forbid")

    correcting: bool = False
    reason: str | None = Field(default=None, max_length=500)


class ClaimResponse(BaseModel):
    """A claim and its decision, as its submitter sees it.

    ``previous_decision`` is carried deliberately: a corrected
    verification is visible to the teacher **and** to that student and
    guardian, never hidden from either party [BR5.7, FR9.2]. It is typed
    as a map of strings because every value in it -- including the
    amount -- is a string, so a money value inside it crosses the wire
    under the same rule as every other [BR6.2].

    :ivar claim_id: The claim
    :ivar period: The period it resolved to at submission
    :ivar claimed_amount: What was claimed
    :ivar approved_amount: What was accepted, or null while pending
    :ivar status: One of the four server-set values
    :ivar shortfall_disposition: Carried or waived, where one applies
    :ivar channel: Which service the money moved through
    :ivar submitted_at: When it was submitted
    :ivar verified_at: When it was decided, or null
    :ivar previous_decision: The prior decision, on a correction
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: uuid.UUID
    period: str
    claimed_amount: MoneyField
    approved_amount: MoneyField | None = None
    status: ClaimStatus
    shortfall_disposition: ShortfallDisposition | None = None
    channel: str
    submitted_at: dt.datetime
    verified_at: dt.datetime | None = None
    previous_decision: dict[str, str | None] | None = None


#: How a claim stands against what its period charged.
ClaimComparison = Literal["matches", "short", "over"]

#: Who sent a claim.
Submitter = Literal["student", "guardian"]


class DuplicateClaimResponse(BaseModel):
    """The earlier claim that quoted the same transaction id.

    :ivar claim_id: That claim
    :ivar display_name: Whose seat it was on, as the teacher typed it
    :ivar status: How it was decided
    :ivar amount: What was approved, else what was claimed
    :ivar decided_at: When it was decided, or null
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: uuid.UUID
    display_name: str
    status: ClaimStatus
    amount: MoneyField
    decided_at: dt.datetime | None = None


class ClaimQueueItemResponse(BaseModel):
    """One claim waiting for the teacher (T4).

    **The comparison is the server's.** ``comparison`` and
    ``difference`` are measured against what the period CHARGED
    [BR5.3]; the client shows them and never subtracts.

    :ivar claim_id: The claim
    :ivar enrollment_id: The seat it is against
    :ivar display_name: The student, as the teacher typed the name
    :ivar batch_name: The batch
    :ivar period: The period the claim resolved to
    :ivar claimed_amount: What the payer says they sent
    :ivar charged: What that period charged
    :ivar comparison: ``matches``, ``short`` or ``over``
    :ivar difference: How far from the charge, never negative
    :ivar channel: The service the money moved through
    :ivar transaction_id: The reference quoted, if any
    :ivar submitted_at: When it was sent
    :ivar submitted_by: ``student`` or ``guardian``, or null
    :ivar submitter_phone: The number the teacher holds for them
    :ivar duplicate_of: The earlier claim quoting the same reference
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: uuid.UUID
    enrollment_id: uuid.UUID
    display_name: str
    batch_name: str
    period: str
    claimed_amount: MoneyField
    charged: MoneyField
    comparison: ClaimComparison
    difference: MoneyField
    channel: str
    transaction_id: str | None = None
    submitted_at: dt.datetime
    submitted_by: Submitter | None = None
    submitter_phone: str | None = None
    duplicate_of: DuplicateClaimResponse | None = None


class RecentDecisionResponse(BaseModel):
    """A claim decided in the last day.

    :ivar claim_id: The claim
    :ivar display_name: The student
    :ivar batch_name: The batch
    :ivar status: How it was decided
    :ivar amount: What was approved, else what was claimed
    :ivar decided_at: When
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: uuid.UUID
    display_name: str
    batch_name: str
    status: ClaimStatus
    amount: MoneyField
    decided_at: dt.datetime


class VerificationQueueResponse(BaseModel):
    """The teacher's payment queue.

    :ivar pending: Waiting claims, oldest first
    :ivar decided_recently: Claims decided in the last day, newest first
    """

    model_config = ConfigDict(extra="forbid")

    pending: list[ClaimQueueItemResponse]
    decided_recently: list[RecentDecisionResponse]


class ShortfallPreviewRequest(BaseModel):
    """An amount the teacher is about to approve.

    :ivar approved_amount: The amount being considered
    """

    model_config = ConfigDict(extra="forbid")

    approved_amount: MoneyField


class ShortfallPreviewResponse(BaseModel):
    """What that approval would leave short, and whether to ask about it.

    :ivar shortfall: ``charged - approved``, floored at zero
    :ivar disposition_required: Whether the teacher must choose carry or
        waive, which the decision itself will insist on
    """

    model_config = ConfigDict(extra="forbid")

    shortfall: MoneyField
    disposition_required: bool


class ReminderRequest(BaseModel):
    """The seats a teacher wants reminded about what they owe.

    :ivar enrollment_ids: The seats; every one must be this teacher's
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class ReminderResponse(BaseModel):
    """What the reminder did.

    :ivar sent: Seats whose student or guardian was reminded in the app
    :ivar skipped: Seats left alone -- owing nothing, already reminded
        today, or with nobody who has accepted the seat
    """

    model_config = ConfigDict(extra="forbid")

    sent: int = Field(ge=0)
    skipped: int = Field(ge=0)


class PayableResponse(BaseModel):
    """One month a student can pay for (S3).

    :ivar enrollment_id: Their seat; the claim is posted against it
    :ivar batch_name: The batch
    :ivar period: The month a claim would be recorded against
    :ivar amount_due: What is still owed on it
    :ivar due_date: When it was due, or null
    :ivar total_due: Everything the seat owes, that month included
    :ivar later_periods: How many later months also owe
    :ivar days_late: Days past the oldest late due date, or null
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_id: uuid.UUID
    batch_name: str
    period: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    amount_due: MoneyField
    due_date: dt.date | None = None
    total_due: MoneyField
    later_periods: int = Field(ge=0)
    days_late: int | None = Field(default=None, ge=1)


class WaitingPaymentResponse(BaseModel):
    """A seat not offered because its payment is being checked.

    :ivar batch_name: The batch
    :ivar period: The month the waiting payment is for
    :ivar amount: What was claimed
    :ivar channel: Which app it moved through
    :ivar submitted_at: When it was sent
    """

    model_config = ConfigDict(extra="forbid")

    batch_name: str
    period: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    amount: MoneyField
    channel: str
    submitted_at: dt.datetime | None = None


class PayablesResponse(BaseModel):
    """What the "Pay a fee" screen offers, and what it explains.

    :ivar payable: Months to pay for, earliest due first
    :ivar waiting: Seats whose payment is already being checked
    """

    model_config = ConfigDict(extra="forbid")

    payable: list[PayableResponse] = Field(default_factory=list)
    waiting: list[WaitingPaymentResponse] = Field(default_factory=list)


class CurrentFeeResponse(BaseModel):
    """A seat's latest fee period, as the student sees it on S1.

    The status is the server's [TC-9]; the app renders it and decides
    nothing from the amounts.

    :ivar period: ``YYYY-MM``
    :ivar status: The period's status
    :ivar due_date: When it is due
    :ivar outstanding: What is still owed for it
    :ivar charged: What the period charged ("October fee · ৳1,200")
    :ivar verifying: Whether a payment for it is waiting to be checked
    :ivar paid_on: The day the last approved payment for it was
        decided, in Bangladesh, or null
    """

    model_config = ConfigDict(extra="forbid")

    period: str
    status: str
    due_date: dt.date
    outstanding: MoneyField
    charged: MoneyField | None = None
    verifying: bool = False
    paid_on: dt.date | None = None


class PaymentSubmitRequest(BaseModel):
    """One payment a student or guardian reports [F3, F4].

    Exactly one of ``payment_method_id`` and ``cash`` names where the
    money went, and exactly one of ``transaction_id`` and
    ``from_account`` is present, matching the method's kind; the server
    enforces both because they depend on the stored method.

    :ivar enrollment_ids: The children covered, all in one batch
    :ivar payment_method_id: The teacher's method paid to
    :ivar cash: True when the money was handed over in person
    :ivar amount: The whole amount sent
    :ivar paid_on: The day the money moved
    :ivar transaction_id: The mobile reference
    :ivar from_account: The paying bank account
    :ivar note: Free text for the teacher
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    payment_method_id: uuid.UUID | None = None
    cash: bool = False
    amount: MoneyField
    paid_on: dt.date
    transaction_id: str | None = Field(default=None, max_length=64)
    from_account: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)


class SubmittedClaimResponse(BaseModel):
    """One child's share of a submitted payment.

    :ivar claim_id: The child's pending claim
    :ivar enrollment_id: The child's seat
    :ivar display_name: The teacher-typed name
    :ivar period: The period the claim resolved to
    :ivar claimed_amount: The provisional share, which the teacher's
        decision replaces
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: uuid.UUID
    enrollment_id: uuid.UUID
    display_name: str
    period: str
    claimed_amount: MoneyField


class PaymentSubmittedResponse(BaseModel):
    """A payment as recorded, waiting for the teacher.

    :ivar submission_id: The submission
    :ivar status: Always ``pending`` when just submitted
    :ivar total_amount: The whole amount sent
    :ivar paid_on: The day the money moved
    :ivar claims: Each child's share, in child order
    """

    model_config = ConfigDict(extra="forbid")

    submission_id: uuid.UUID
    status: Literal["pending", "approved", "rejected"]
    total_amount: MoneyField
    paid_on: dt.date
    claims: list[SubmittedClaimResponse]


class OwedChildResponse(BaseModel):
    """One child in the form's owed line.

    :ivar enrollment_id: The child's seat
    :ivar display_name: The teacher-typed name
    :ivar owed: What the seat owes now, never negative
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_id: uuid.UUID
    display_name: str
    owed: MoneyField


class OwedTogetherResponse(BaseModel):
    """What the chosen children owe together, for "Owed for ...".

    :ivar owed_together: The server's total
    :ivar children: Each child, in child order
    """

    model_config = ConfigDict(extra="forbid")

    owed_together: MoneyField
    children: list[OwedChildResponse]
