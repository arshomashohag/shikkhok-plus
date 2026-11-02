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

**No schema here declares a payment method's number or account fields**;
``app.schemas.payment_methods`` holds them, the payment review embeds its
destination snapshot from there, and a test over the generated document
asserts which routes carry them [BR6.4, NFR14.32].
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import MoneyField
from app.schemas.payment_methods import PaymentDestinationResponse

__all__ = [
    "BatchFeesResponse",
    "ClaimResponse",
    "DuplicatePaymentResponse",
    "FeeCycleResponse",
    "FeeHistoryResponse",
    "HistoryLineResponse",
    "MonthCountsResponse",
    "MonthStateResponse",
    "OwedChildResponse",
    "OwedTogetherResponse",
    "PayableResponse",
    "PayablesResponse",
    "PaymentApprovalRequest",
    "PaymentRejectionRequest",
    "PaymentReviewResponse",
    "PaymentSubmitRequest",
    "PaymentSubmittedResponse",
    "RecentDecisionResponse",
    "ReminderRequest",
    "ReminderResponse",
    "ReviewChildResponse",
    "RosterFeeRowResponse",
    "SubmittedClaimResponse",
    "VerificationQueueResponse",
    "WaitingPaymentResponse",
]

#: The four statuses a cycle reports [BR6.1]. A ``Literal`` rather than
#: a free ``str`` so the generated document publishes the closed set and
#: a client author reads the contract rather than guessing it.
FeeStatus = Literal["paid", "partly_paid", "unpaid", "waived"]

#: The five states a month reports: the four above plus ``checking``.
MonthState = Literal["paid", "partly_paid", "unpaid", "waived", "checking"]

#: The four a claim reports [BR6.3].
ClaimStatus = Literal["pending", "approved_full", "approved_partial", "rejected"]

#: The teacher's choice on approving less than was charged [BR5.4].
ShortfallDisposition = Literal["carried", "waived"]

#: The three a payment submission reports.
SubmissionStatus = Literal["pending", "approved", "rejected"]


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


class HistoryLineResponse(BaseModel):
    """The latest payment claim for one month, as data to localize.

    :ivar amount: What was approved for the child once approved;
        otherwise the whole payment as sent, covering ``covered_names``
    :ivar channel: Which service the money moved through
    :ivar paid_on: When the money was sent
    :ivar status: The claim's server-set status
    :ivar decision_note: The teacher's note on the decision, or null
    :ivar covered_names: The children the sent amount covered, in child
        order; empty when the amount is the child's approved figure
    """

    model_config = ConfigDict(extra="forbid")

    amount: MoneyField
    channel: str
    paid_on: dt.date
    status: ClaimStatus
    decision_note: str | None = None
    covered_names: list[str] = Field(default_factory=list)


class MonthStateResponse(BaseModel):
    """One month on a seat's strip.

    :ivar period: The month, as ``YYYY-MM``
    :ivar state: The server-computed state
    :ivar history_line: The latest claim for the month, or null
    """

    model_config = ConfigDict(extra="forbid")

    period: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    state: MonthState
    history_line: HistoryLineResponse | None = None


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
    :ivar month_states: The last months that have a state, oldest first
    """

    model_config = ConfigDict(extra="forbid")

    cycles: list[FeeCycleResponse]
    total_outstanding: MoneyField
    month_states: list[MonthStateResponse] = Field(default_factory=list)


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
    :ivar state: The seat's state in the requested month, or null when
        nothing was charged
    :ivar history_line: The latest claim for that month, or null
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
    state: MonthState | None = None
    history_line: HistoryLineResponse | None = None


class MonthCountsResponse(BaseModel):
    """How many seats fall under each filter for the month.

    :ivar paid: Settled seats, including waived ones
    :ivar checking: Seats with a payment waiting for the teacher
    :ivar owed: Seats still owing
    """

    model_config = ConfigDict(extra="forbid")

    paid: int
    checking: int
    owed: int


class BatchFeesResponse(BaseModel):
    """One batch in one month.

    :ivar period: The month, as ``YYYY-MM``
    :ivar collected: Cash in for the month after corrections
    :ivar charged: What the month was billed
    :ivar counts: Seats per filter
    :ivar seats: One row per seat
    """

    model_config = ConfigDict(extra="forbid")

    period: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    collected: MoneyField
    charged: MoneyField
    counts: MonthCountsResponse
    seats: list[RosterFeeRowResponse]


class PaymentApprovalRequest(BaseModel):
    """Approve a payment, saying what was received and how to split it (R4).

    ``shortfall_disposition`` is required when less than the children
    owe together was received, and refused otherwise; it carries no
    default, because carrying and waiving have opposite consequences for
    the family [BR5.4]. For more than one child a short payment also
    names who carries it and an over payment names who gets the credit.
    The server enforces both, because only it knows what is owed.

    ``correcting`` is the teacher saying "I know this payment is already
    decided and I am revising it" [BR5.7, FR9.2]; without it a second
    decision is refused, so a concurrent repeat cannot credit twice.

    :ivar received_amount: What the teacher received; more than zero,
        since a payment nothing came in for is rejected rather than
        approved
    :ivar shortfall_disposition: Carried or waived, when short
    :ivar carried_by_enrollment_id: The child who carries a shortfall
    :ivar credit_to_enrollment_id: The child who gets an excess as credit
    :ivar note: Shown to the family with the decision
    :ivar correcting: True when deliberately revising a decided payment
    """

    model_config = ConfigDict(extra="forbid")

    received_amount: MoneyField
    shortfall_disposition: Literal["carried", "waived"] | None = None
    carried_by_enrollment_id: uuid.UUID | None = None
    credit_to_enrollment_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=500)
    correcting: bool = False


class PaymentRejectionRequest(BaseModel):
    """Reject a payment, optionally as a correction [BR5.6, BR5.7].

    :ivar note: Why it was rejected, shown to the family
    :ivar correcting: True when deliberately revising a decided payment
    """

    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=500)
    correcting: bool = False


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
    :ivar decision_note: The teacher's note on the decision, or null
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
    decision_note: str | None = None


#: How a claim stands against what its period charged.
ClaimComparison = Literal["matches", "short", "over"]

#: Who sent a claim.
Submitter = Literal["student", "guardian"]


class DuplicatePaymentResponse(BaseModel):
    """The earlier payment that quoted the same reference.

    :ivar submission_id: That submission
    :ivar display_name: The children it covered, comma separated
    :ivar status: How it was decided
    :ivar amount: What it reported as sent
    :ivar decided_at: When it was decided, or null
    """

    model_config = ConfigDict(extra="forbid")

    submission_id: uuid.UUID
    display_name: str
    status: SubmissionStatus
    amount: MoneyField
    decided_at: dt.datetime | None = None


class ReviewChildResponse(BaseModel):
    """One child a payment covers, in child order.

    :ivar claim_id: The child's claim
    :ivar enrollment_id: The child's seat
    :ivar display_name: The teacher-typed name
    :ivar period: The period the claim resolved to
    :ivar owed: What the seat owes now
    :ivar approved_amount: What the decision approved, or null
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: uuid.UUID
    enrollment_id: uuid.UUID
    display_name: str
    period: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    owed: MoneyField
    approved_amount: MoneyField | None = None


class PaymentReviewResponse(BaseModel):
    """One payment as its teacher reviews it (R1, R2, R3).

    ``method`` is the destination as the family was shown it when they
    paid, so a later edit of the method does not change what the
    teacher checks against.

    :ivar submission_id: The submission
    :ivar batch_name: The batch
    :ivar children: The children covered, in child order
    :ivar owed_together: What they owe together now
    :ivar total_amount: What the payer says they sent
    :ivar comparison: ``matches``, ``short`` or ``over``
    :ivar difference: How far from what is owed, never negative
    :ivar method: The destination snapshot
    :ivar transaction_id: The mobile reference, if any
    :ivar from_account: The paying bank account, if any
    :ivar paid_on: The day the money moved
    :ivar submitted_at: When it was reported
    :ivar submitted_by: ``student`` or ``guardian``, or null
    :ivar submitter_phone: The number the teacher holds for them
    :ivar payer_note: The payer's note
    :ivar status: ``pending``, ``approved`` or ``rejected``
    :ivar decision_note: The teacher's note on the decision
    :ivar decided_at: When it was decided, or null
    :ivar duplicate_of: The earlier payment quoting the same reference
    """

    model_config = ConfigDict(extra="forbid")

    submission_id: uuid.UUID
    batch_name: str
    children: list[ReviewChildResponse]
    owed_together: MoneyField
    total_amount: MoneyField
    comparison: ClaimComparison
    difference: MoneyField
    method: PaymentDestinationResponse
    transaction_id: str | None = None
    from_account: str | None = None
    paid_on: dt.date
    submitted_at: dt.datetime
    submitted_by: Submitter | None = None
    submitter_phone: str | None = None
    payer_note: str | None = None
    status: SubmissionStatus
    decision_note: str | None = None
    decided_at: dt.datetime | None = None
    duplicate_of: DuplicatePaymentResponse | None = None


class RecentDecisionResponse(BaseModel):
    """A payment decided in the last day.

    :ivar submission_id: The submission
    :ivar display_name: The children it covered, comma separated
    :ivar batch_name: The batch
    :ivar status: How it was decided
    :ivar amount: What was approved, else what was sent
    :ivar decided_at: When
    """

    model_config = ConfigDict(extra="forbid")

    submission_id: uuid.UUID
    display_name: str
    batch_name: str
    status: SubmissionStatus
    amount: MoneyField
    decided_at: dt.datetime


class VerificationQueueResponse(BaseModel):
    """The teacher's payment queue.

    :ivar pending: Waiting payments, oldest first
    :ivar decided_recently: Payments decided in the last day, newest first
    """

    model_config = ConfigDict(extra="forbid")

    pending: list[PaymentReviewResponse]
    decided_recently: list[RecentDecisionResponse]


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
