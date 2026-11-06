"""The teacher's payment queue and review (R1, R2): one payment at a time.

**One item per submission, not per child.** A guardian who pays for two
children sent one payment, and the teacher checks it once: the item
lists the children, what they owe together, what was sent and where.

**Every figure on the card is the server's.** What the children owe,
the comparison (``matches``, ``short`` or ``over``) and the difference
are computed here, so the app shows "৳500 short of ৳2,000" without
subtracting anything.

**A decided payment is measured against what was owed before it.**
Measured after, a payment that settled everything reads as entirely
over, and a correction sheet built on that asks the wrong question.
Each child's figure is what they owe now plus the relief this payment's
live entries gave -- those written by the current decision, not the
superseded originals or the compensations a correction wrote.

**Scoped to the batches this lens owns**, in the query rather than after
it: another teacher's submission is never loaded, so it cannot leak
through a forgotten filter.

**A reused transaction id is flagged, not refused.** Two submissions
quoting the same reference is either a mistake or a second report of
one payment; the teacher decides, and the item names the earlier one.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session, aliased

from app.authz.lenses import TeacherLens
from app.db.models import (
    Batch,
    Enrollment,
    LedgerEntryRow,
    PaymentClaim,
    PaymentSubmission,
)
from app.fees.extra_ledger import extra_decision_relief
from app.fees.purposes import FeeRef, Purpose, fee_refs, owed_for_claim
from app.fees.status import SubmissionStatus
from app.fees.submissions import child_order
from app.fees.verification import shortfall_of
from app.fees.views import owned_submission, submission_status
from app.money import LedgerEntry, LedgerEntryKind, Money, relief_of

__all__ = [
    "RECENT_WINDOW",
    "DuplicatePayment",
    "PaymentReview",
    "RecentDecision",
    "ReviewChild",
    "VerificationQueue",
    "covered_children",
    "payment_review",
    "verification_queue",
]

Comparison = Literal["matches", "short", "over"]
Submitter = Literal["student", "guardian"]

#: How far back "decided today" reaches.
RECENT_WINDOW = dt.timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class ReviewChild:
    """One child a payment covers, as the teacher reviews it.

    :ivar claim_id: The child's claim
    :ivar enrollment_id: The child's seat
    :ivar display_name: The teacher-typed name
    :ivar period: The period the claim resolved to
    :ivar owed: What the seat owes now, never negative; for a decided
        payment, what it owed before this decision
    :ivar approved_amount: What the decision approved, or None
    """

    claim_id: uuid.UUID
    enrollment_id: uuid.UUID
    display_name: str
    period: str
    owed: Money
    approved_amount: Money | None


@dataclass(frozen=True, slots=True)
class DuplicatePayment:
    """The earlier submission that quoted the same reference.

    :ivar submission_id: That submission
    :ivar display_name: The children it covered
    :ivar status: How it was decided, or pending
    :ivar amount: What it reported as sent
    :ivar decided_at: When it was decided, or None
    """

    submission_id: uuid.UUID
    display_name: str
    status: SubmissionStatus
    amount: Money
    decided_at: dt.datetime | None


@dataclass(frozen=True, slots=True)
class PaymentReview:
    """One payment as the teacher reviews it.

    :ivar submission_id: The submission
    :ivar batch_name: The batch
    :ivar children: The children covered, in child order
    :ivar owed_together: What they owe together now, or before this
        decision for a decided payment
    :ivar total_amount: What the payer says they sent
    :ivar comparison: ``matches``, ``short`` or ``over``
    :ivar difference: How far from what is owed, never negative
    :ivar method: The destination as the family was shown it
    :ivar transaction_id: The mobile reference, if any
    :ivar from_account: The paying bank account, if any
    :ivar paid_on: The day the money moved
    :ivar submitted_at: When it was reported
    :ivar submitted_by: ``student`` or ``guardian``, or None
    :ivar submitter_phone: The number the teacher holds for them
    :ivar payer_note: The payer's note
    :ivar status: ``pending``, ``approved`` or ``rejected``
    :ivar decision_note: The teacher's note on the decision
    :ivar decided_at: When it was decided, or None
    :ivar duplicate_of: The earlier submission quoting the same reference
    :ivar purpose: What the teacher applies it to, ``monthly`` or ``extra``
    :ivar extra_fee: The fee it is applied to, when ``extra``
    :ivar requested_purpose: What the family chose
    :ivar requested_extra_fee: The fee the family chose, if any
    """

    submission_id: uuid.UUID
    batch_name: str
    children: list[ReviewChild]
    owed_together: Money
    total_amount: Money
    comparison: Comparison
    difference: Money
    method: dict[str, object]
    transaction_id: str | None
    from_account: str | None
    paid_on: dt.date
    submitted_at: dt.datetime
    submitted_by: Submitter | None
    submitter_phone: str | None
    payer_note: str | None
    status: SubmissionStatus
    decision_note: str | None
    decided_at: dt.datetime | None
    duplicate_of: DuplicatePayment | None
    purpose: Purpose = "monthly"
    extra_fee: FeeRef | None = None
    requested_purpose: Purpose = "monthly"
    requested_extra_fee: FeeRef | None = None


@dataclass(frozen=True, slots=True)
class RecentDecision:
    """A payment decided in the last day, for "Approved today".

    :ivar submission_id: The submission
    :ivar display_name: The children it covered
    :ivar batch_name: The batch
    :ivar status: How it was decided
    :ivar amount: What was approved, else what was sent
    :ivar decided_at: When
    """

    submission_id: uuid.UUID
    display_name: str
    batch_name: str
    status: SubmissionStatus
    amount: Money
    decided_at: dt.datetime


@dataclass(frozen=True, slots=True)
class VerificationQueue:
    """What R1 shows: waiting payments, and what was decided recently.

    :ivar pending: Oldest first, so nobody waits longest unseen
    :ivar decided_recently: Newest first
    """

    pending: list[PaymentReview]
    decided_recently: list[RecentDecision]


def _compare(sent: Money, owed: Money) -> tuple[Comparison, Money]:
    """Say how a payment stands against what is owed.

    :param sent: What was sent
    :param owed: What the children owe together
    :return: The comparison and the distance, never negative
    """
    if sent < owed:
        return "short", shortfall_of(owed, sent)
    if sent > owed:
        return "over", shortfall_of(sent, owed)
    return "matches", Money.ZERO


def _reference(transaction_id: str | None) -> str | None:
    """Normalise a quoted reference for comparison.

    People retype an SMS reference with stray spaces and in whatever
    case their keyboard offers; the service does not distinguish them.

    :param transaction_id: The reference as quoted
    :return: The comparable form, or None when there is none
    """
    if transaction_id is None:
        return None
    cleaned = "".join(transaction_id.split()).upper()
    return cleaned or None


def covered_children(
    session: Session, submission_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[PaymentClaim, Enrollment]]]:
    """Read each submission's claims with their seats, in child order.

    :param session: The session to read through
    :param submission_ids: The submissions
    :return: Submission id to its claims and seats
    """
    found: dict[uuid.UUID, list[tuple[PaymentClaim, Enrollment]]] = defaultdict(list)
    if not submission_ids:
        return found
    rows = session.execute(
        sa.select(PaymentClaim, Enrollment)
        .join(Enrollment, Enrollment.id == PaymentClaim.enrollment_id)
        .where(PaymentClaim.payment_submission_id.in_(submission_ids))
    ).all()
    for claim, seat in rows:
        if claim.payment_submission_id is not None:
            found[claim.payment_submission_id].append((claim, seat))
    for pairs in found.values():
        pairs.sort(key=lambda pair: child_order(pair[1]))
    return found


def _names(pairs: list[tuple[PaymentClaim, Enrollment]]) -> str:
    """Join the covered children's names for one line.

    :param pairs: The claims and seats, in child order
    :return: The names, comma separated
    """
    return ", ".join(seat.display_name for _claim, seat in pairs)


def _submitter(
    submission: PaymentSubmission, seats: list[Enrollment]
) -> tuple[Submitter | None, str | None]:
    """Who sent a payment, and the number the teacher holds for them.

    :param submission: The submission
    :param seats: The seats it covers
    :return: The role and phone, or Nones when it cannot be said
    """
    sender = submission.submitted_by_account_id
    if sender is None:
        return None, None
    for seat in seats:
        if sender == seat.guardian_account_id:
            return "guardian", seat.guardian_phone
    for seat in seats:
        if sender == seat.student_account_id:
            return "student", seat.student_phone
    return None, None


def _approved_total(
    submission: PaymentSubmission, pairs: list[tuple[PaymentClaim, Enrollment]]
) -> Money:
    """Give the figure a decided payment stands for.

    :param submission: The submission
    :param pairs: Its claims and seats
    :return: What was approved across the children, else what was sent
    """
    if submission.status != "approved":
        return submission.total_amount
    return Money.sum([claim.approved_amount or Money.ZERO for claim, _seat in pairs])


def _duplicates(
    submissions: list[PaymentSubmission],
    children: dict[uuid.UUID, list[tuple[PaymentClaim, Enrollment]]],
) -> dict[uuid.UUID, DuplicatePayment]:
    """For each submission, the earliest other one quoting its reference.

    :param submissions: The teacher's submissions, oldest first
    :param children: Each submission's claims and seats
    :return: Submission id to the earlier submission it repeats
    """
    first: dict[str, PaymentSubmission] = {}
    found: dict[uuid.UUID, DuplicatePayment] = {}
    for submission in submissions:
        reference = _reference(submission.transaction_id)
        if reference is None:
            continue
        earlier = first.get(reference)
        if earlier is None:
            first[reference] = submission
            continue
        found[submission.id] = DuplicatePayment(
            submission_id=earlier.id,
            display_name=_names(children[earlier.id]),
            status=submission_status(earlier.status),
            amount=earlier.total_amount,
            decided_at=earlier.decided_at,
        )
    return found


def _decision_relief(
    session: Session, claims: list[PaymentClaim]
) -> dict[uuid.UUID, Money]:
    """Measure what the current decision took off each child's balance.

    Only the decision's live entries count: an entry a correction
    superseded, and every compensation the correction wrote against it,
    belong to a decision no longer in force. A claim-linked ``charge``
    is only ever such a compensation, so it is left out with them.

    :param session: The session to read through
    :param claims: The payment's claims
    :return: Claim id to the relief its live entries give
    """
    compensating = aliased(LedgerEntryRow)
    rows = session.scalars(
        sa.select(LedgerEntryRow).where(
            LedgerEntryRow.payment_claim_id.in_([claim.id for claim in claims]),
            LedgerEntryRow.superseded_by_id.is_(None),
            LedgerEntryRow.kind != "charge",
            ~sa.exists().where(compensating.superseded_by_id == LedgerEntryRow.id),
        )
    )
    live: defaultdict[uuid.UUID, list[LedgerEntry]] = defaultdict(list)
    for row in rows:
        if row.payment_claim_id is not None:
            live[row.payment_claim_id].append(
                LedgerEntry(
                    kind=LedgerEntryKind(row.kind),
                    period=row.period,
                    amount=row.amount,
                )
            )
    return {claim.id: relief_of(live[claim.id]) for claim in claims}


def _review(
    session: Session,
    submission: PaymentSubmission,
    pairs: list[tuple[PaymentClaim, Enrollment]],
    batch_name: str,
    duplicate_of: DuplicatePayment | None,
) -> PaymentReview:
    """Assemble one payment's review from its rows.

    :param session: The session to read through
    :param submission: The submission
    :param pairs: Its claims and seats, in child order
    :param batch_name: The batch's name
    :param duplicate_of: The earlier submission it repeats, if any
    :return: The review
    """
    # A decided payment is measured against what was owed before it, in
    # whichever ledger its current decision lives: a claim re-pointed by
    # a correction has no live entries left in the other one.
    claims = [claim for claim, _seat in pairs]
    relief = {} if submission.status == "pending" else _decision_relief(session, claims)
    extra_relief = (
        {}
        if submission.status == "pending"
        else extra_decision_relief(session, [claim.id for claim in claims])
    )
    fees = fee_refs(
        session, [submission.extra_fee_id, submission.requested_extra_fee_id]
    )
    children = [
        ReviewChild(
            claim_id=claim.id,
            enrollment_id=seat.id,
            display_name=seat.display_name,
            period=claim.period,
            owed=owed_for_claim(session, claim)
            + relief.get(claim.id, Money.ZERO)
            + extra_relief.get(claim.id, Money.ZERO),
            approved_amount=claim.approved_amount,
        )
        for claim, seat in pairs
    ]
    owed_together = Money.sum([child.owed for child in children])
    comparison, difference = _compare(submission.total_amount, owed_together)
    submitted_by, phone = _submitter(submission, [seat for _claim, seat in pairs])
    return PaymentReview(
        submission_id=submission.id,
        batch_name=batch_name,
        children=children,
        owed_together=owed_together,
        total_amount=submission.total_amount,
        comparison=comparison,
        difference=difference,
        method=dict(submission.destination_snapshot),
        transaction_id=submission.transaction_id,
        from_account=submission.from_account,
        paid_on=submission.paid_on,
        submitted_at=submission.submitted_at,
        submitted_by=submitted_by,
        submitter_phone=phone,
        payer_note=submission.payer_note,
        status=submission_status(submission.status),
        decision_note=submission.decision_note,
        decided_at=submission.decided_at,
        duplicate_of=duplicate_of,
        purpose="extra" if submission.purpose == "extra" else "monthly",
        extra_fee=(
            None if submission.extra_fee_id is None else fees[submission.extra_fee_id]
        ),
        requested_purpose=(
            "extra" if submission.requested_purpose == "extra" else "monthly"
        ),
        requested_extra_fee=(
            None
            if submission.requested_extra_fee_id is None
            else fees[submission.requested_extra_fee_id]
        ),
    )


def _owned_submissions(
    session: Session, lens: TeacherLens
) -> list[tuple[PaymentSubmission, str]]:
    """Every submission on this teacher's batches, with the batch name.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :return: Submission and batch name, oldest first
    """
    rows = session.execute(
        sa.select(PaymentSubmission, Batch.name)
        .join(Batch, Batch.id == PaymentSubmission.batch_id)
        .where(Batch.owner_id == lens.owner_id)
        .order_by(PaymentSubmission.submitted_at, PaymentSubmission.id)
    ).all()
    return [(row[0], row[1]) for row in rows]


def verification_queue(
    session: Session,
    *,
    lens: TeacherLens,
    now: dt.datetime | None = None,
) -> VerificationQueue:
    """Read this teacher's waiting payments and recent decisions.

    :param session: The session to read through
    :param lens: The teacher lens
    :param now: The moment "recent" is measured from; now by default
    :return: The queue
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    rows = _owned_submissions(session, lens)
    submissions = [submission for submission, _name in rows]
    children = covered_children(session, [s.id for s in submissions])
    duplicates = _duplicates(submissions, children)

    pending: list[PaymentReview] = []
    recent: list[RecentDecision] = []
    for submission, batch_name in rows:
        pairs = children[submission.id]
        if submission.status == "pending":
            pending.append(
                _review(
                    session,
                    submission,
                    pairs,
                    batch_name,
                    duplicates.get(submission.id),
                )
            )
        elif (
            submission.decided_at is not None
            and moment - submission.decided_at <= RECENT_WINDOW
        ):
            recent.append(
                RecentDecision(
                    submission_id=submission.id,
                    display_name=_names(pairs),
                    batch_name=batch_name,
                    status=submission_status(submission.status),
                    amount=_approved_total(submission, pairs),
                    decided_at=submission.decided_at,
                )
            )
    recent.sort(key=lambda decision: decision.decided_at, reverse=True)
    return VerificationQueue(pending=pending, decided_recently=recent)


def payment_review(
    session: Session,
    *,
    lens: TeacherLens,
    submission_id: uuid.UUID,
) -> PaymentReview:
    """Read one payment on this teacher's batches, decided or not (R2).

    :param session: The session to read through
    :param lens: The teacher lens
    :param submission_id: The submission
    :return: The review
    :raises AuthorizationError: It is absent or not this lens's
    """
    submission = owned_submission(session, lens=lens, submission_id=submission_id)
    batch_name = session.scalars(
        sa.select(Batch.name).where(Batch.id == submission.batch_id)
    ).one()
    earlier = [
        row
        for row in session.scalars(
            sa.select(PaymentSubmission)
            .join(Batch, Batch.id == PaymentSubmission.batch_id)
            .where(
                Batch.owner_id == lens.owner_id,
                PaymentSubmission.transaction_id.is_not(None),
                PaymentSubmission.submitted_at <= submission.submitted_at,
            )
            .order_by(PaymentSubmission.submitted_at, PaymentSubmission.id)
        )
        if (row.submitted_at, str(row.id))
        < (submission.submitted_at, str(submission.id))
    ]
    candidates = [*earlier, submission]
    children = covered_children(session, [s.id for s in candidates])
    duplicate = _duplicates(candidates, children).get(submission.id)
    return _review(session, submission, children[submission.id], batch_name, duplicate)
