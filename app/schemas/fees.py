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

**``collection_number`` appears in exactly one schema here**, and a test
over the generated document asserts that as an equality rather than a
membership [BR6.4, NFR14.32]. A membership test passes the moment the
field spreads to a second response.
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
    "ClaimSubmitRequest",
    "FeeCycleResponse",
    "FeeHistoryResponse",
    "PaymentDestinationResponse",
    "RecentDecisionResponse",
    "ReminderRequest",
    "ReminderResponse",
    "RosterFeeRowResponse",
    "ShortfallPreviewRequest",
    "ShortfallPreviewResponse",
    "VerificationQueueResponse",
    "VerificationRequest",
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

    **No ``collection_number``.** The teacher's payment destination is
    carried by exactly one response and this is not it [NFR14.33].

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


class ClaimSubmitRequest(BaseModel):
    """Submit a payment claim [AC6.1.x].

    ``claimed_amount`` is **not capped** at the outstanding balance
    [BR5.2]: money may genuinely have been overpaid out of band, and
    blocking that at submission makes a real overpayment unreportable.
    Zero and negative are refused, which the wire pattern already does
    for a negative since it admits no sign.

    :ivar claimed_amount: What the claimant says they paid
    :ivar channel: Which service it moved through, from the server set
    :ivar transaction_id: The reference they quote, if any
    """

    model_config = ConfigDict(extra="forbid")

    claimed_amount: MoneyField
    channel: str = Field(min_length=1, max_length=32)
    transaction_id: str | None = Field(default=None, max_length=64)


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
    """

    model_config = ConfigDict(extra="forbid")

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


class PaymentDestinationResponse(BaseModel):
    """Where to send a payment, and through what.

    **The ONE response in the product carrying the collection number**
    [BR6.4, NFR14.32]. The allowlist test asserts that as an equality
    against a one-element set, so the field spreading to a second
    response fails the build rather than passing a membership check.

    Where the teacher set no number the route returns **no object at
    all** rather than this model with a null in it [NFR14.34]: a null
    invites a client-side placeholder, and an absent object leaves the
    client nothing to render while the copy tells the person to ask the
    teacher how to pay.

    :ivar collection_number: Where payments are sent
    :ivar collection_channel: Which service that number belongs to
    :ivar channels: The channel set, server-supplied so adding one is a
        data change rather than an app release
    """

    model_config = ConfigDict(extra="forbid")

    collection_number: str
    collection_channel: str | None = None
    channels: list[str]


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
