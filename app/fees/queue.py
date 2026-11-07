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
from typing import Final, Literal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session, aliased

from app.analytics.seats import any_of, owing_ledger_for_seats
from app.authz.lenses import TeacherLens
from app.db.models import (
    Batch,
    Enrollment,
    LedgerEntryRow,
    PaymentClaim,
    PaymentSubmission,
)
from app.fees.extra_ledger import charge_entries, extra_decision_relief
from app.fees.purposes import (
    FeeRef,
    Purpose,
    Target,
    fee_refs,
    fees_charging_each,
    owed_for_target,
    resolve_target,
)
from app.fees.status import SubmissionStatus
from app.fees.submissions import child_order
from app.fees.verification import shortfall_of
from app.fees.views import owned_submission, submission_status
from app.money import LedgerEntry, LedgerEntryKind, Money, derive, relief_of

__all__ = [
    "RECENT_WINDOW",
    "DuplicatePayment",
    "PaymentReview",
    "RecentDecision",
    "ReviewChild",
    "VerificationQueue",
    "covered_children",
    "payment_review",
    "pending_count",
    "pending_preview",
    "verification_queue",
]

Comparison = Literal["matches", "short", "over"]
Submitter = Literal["student", "guardian"]

#: How far back "decided today" reaches.
RECENT_WINDOW = dt.timedelta(hours=24)

#: A ``text[]`` parameter, for matching references with ``= ANY``.
_TEXTS: Final = ARRAY(sa.Text())


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
    :ivar extra_fee_options: The extra fees it could be applied to instead
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
    extra_fee_options: tuple[FeeRef, ...] = ()


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
        .where(PaymentClaim.payment_submission_id == any_of(submission_ids))
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


#: The ASCII whitespace ``str.split()`` drops from a reference, besides
#: the space itself.
_CONTROL_SPACE: Final = "\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f"


def _reference_candidates(references: set[str]) -> sa.ColumnElement[bool]:
    """Match every stored reference :func:`_reference` could map to one of these.

    A superset, cheap per row and exact where it decides: for a stored
    reference of printable ASCII, ``upper`` under the ``C`` collation
    maps exactly a-z to A-Z, as ``str.upper`` does to ASCII, and the
    spaces are dropped as ``str.split`` drops them, so the comparison IS
    :func:`_reference`'s. A reference holding any other character -- a
    control whitespace, or anything outside ASCII, whose case rules the
    database need not share with Python -- is returned as a candidate
    regardless, and :func:`_reference` decides it in Python.

    :param references: Normalised references, from :func:`_reference`
    :return: The condition on ``payment_submission.transaction_id``
    """
    stored = PaymentSubmission.transaction_id
    key = sa.func.replace(sa.func.upper(stored.collate("C")), " ", "")
    return sa.or_(
        key == sa.any_(sa.bindparam("references", sorted(references), type_=_TEXTS)),
        sa.func.octet_length(stored) != sa.func.length(stored),
        *[sa.func.strpos(stored, char) > 0 for char in _CONTROL_SPACE],
    )


def _duplicates(
    session: Session,
    lens: TeacherLens,
    submissions: list[PaymentSubmission],
) -> dict[uuid.UUID, DuplicatePayment]:
    """For each submission, the earliest of this teacher's quoting its reference.

    **A targeted read, not every submission ever** [C-13]: the
    candidates are the teacher's submissions whose normalised reference
    is one of these submissions' references. Earliest means first by
    ``(submitted_at, id)``, the order the queue lists in, and a
    submission that is itself the earliest repeats nothing.

    The SQL condition (:func:`_reference_candidates`) is a superset and
    every candidate is decided here by :func:`_reference` itself, so the
    result is exactly what comparing every submission ever would give.
    It is scoped to this teacher's batches by id, so its cost follows
    the teacher's submissions, never the platform's.

    :param session: The session to read through
    :param lens: The teacher lens; candidates are this lens's only
    :param submissions: The submissions to check
    :return: Submission id to the earlier submission it repeats
    """
    wanted = {
        reference
        for reference in (_reference(s.transaction_id) for s in submissions)
        if reference is not None
    }
    if not wanted:
        return {}
    first: dict[str, uuid.UUID] = {}
    for candidate_id, transaction_id in session.execute(
        sa.select(PaymentSubmission.id, PaymentSubmission.transaction_id)
        .where(
            PaymentSubmission.batch_id
            == sa.any_(
                sa.func.array(
                    sa.select(Batch.id)
                    .where(Batch.owner_id == lens.owner_id)
                    .scalar_subquery()
                )
            ),
            PaymentSubmission.transaction_id.is_not(None),
            _reference_candidates(wanted),
        )
        .order_by(PaymentSubmission.submitted_at, PaymentSubmission.id)
    ).all():
        reference = _reference(transaction_id)
        if reference in wanted and reference not in first:
            first[reference] = candidate_id

    repeats: dict[uuid.UUID, uuid.UUID] = {}
    for submission in submissions:
        reference = _reference(submission.transaction_id)
        earliest = None if reference is None else first.get(reference)
        if earliest is not None and earliest != submission.id:
            repeats[submission.id] = earliest
    if not repeats:
        return {}

    earlier_ids = set(repeats.values())
    earlier = {
        row.id: row
        for row in session.scalars(
            sa.select(PaymentSubmission).where(
                PaymentSubmission.id == any_of(earlier_ids)
            )
        )
    }
    names = covered_children(session, list(earlier_ids))
    return {
        submission_id: DuplicatePayment(
            submission_id=earliest,
            display_name=_names(names[earliest]),
            status=submission_status(earlier[earliest].status),
            amount=earlier[earliest].total_amount,
            decided_at=earlier[earliest].decided_at,
        )
        for submission_id, earliest in repeats.items()
    }


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


@dataclass(frozen=True, slots=True)
class _Prefetched:
    """What several reviews need, read once for all of them [C-13].

    :ivar monthly_owed: Seat to what it owes in months now
    :ivar extra_owed: Extra-fee charge to what is owed on it now
    :ivar fees: Fee id to its label
    :ivar options: Submission id to the extra fees it could go to
    """

    monthly_owed: dict[uuid.UUID, Money]
    extra_owed: dict[uuid.UUID, Money]
    fees: dict[uuid.UUID, FeeRef]
    options: dict[uuid.UUID, list[FeeRef]]


def _target(submission: PaymentSubmission) -> Target:
    """Say what a submission is applied to now.

    :param submission: The submission
    :return: Its current target
    """
    return Target(
        purpose="extra" if submission.purpose == "extra" else "monthly",
        extra_fee_id=submission.extra_fee_id,
    )


def _prefetch(
    session: Session,
    items: list[tuple[PaymentSubmission, list[tuple[PaymentClaim, Enrollment]]]],
    preview: Target | None = None,
) -> _Prefetched:
    """Read everything a set of reviews needs, in a constant number of statements.

    The same figures :func:`~app.fees.purposes.owed_for_claim`,
    :func:`fee_refs` and :func:`~app.fees.purposes.fees_charging_all`
    give one review at a time, read for every review at once: one summed
    ledger read for every covered seat, one read for every extra-fee
    charge a claim points at, one for the fee labels and one for the fee
    options.

    :param session: The session to read through
    :param items: Each submission with its claims and seats
    :param preview: The preview target, when one review is previewed
    :return: The figures, keyed for :func:`_review`
    """
    claims = [claim for _submission, pairs in items for claim, _seat in pairs]
    seats = sorted(
        {claim.enrollment_id for claim in claims if claim.extra_fee_charge_id is None}
    )
    charges = sorted(
        {
            claim.extra_fee_charge_id
            for claim in claims
            if claim.extra_fee_charge_id is not None
        }
    )
    # A review shows what each child owes, so months settled long ago
    # need not reach the fold.
    ledger = owing_ledger_for_seats(session, seats)
    charge_ledger = charge_entries(session, charges)
    fee_ids: list[uuid.UUID | None] = [] if preview is None else [preview.extra_fee_id]
    for submission, _pairs in items:
        fee_ids += [submission.extra_fee_id, submission.requested_extra_fee_id]
    return _Prefetched(
        monthly_owed={
            seat: derive(entries).total_outstanding for seat, entries in ledger.items()
        },
        extra_owed={
            charge: derive(entries).total_outstanding
            for charge, entries in charge_ledger.items()
        },
        fees=fee_refs(session, fee_ids),
        options=fees_charging_each(
            session,
            {
                submission.id: (
                    submission.batch_id,
                    [seat.id for _claim, seat in pairs],
                )
                for submission, pairs in items
            },
        ),
    )


def _review(
    session: Session,
    submission: PaymentSubmission,
    pairs: list[tuple[PaymentClaim, Enrollment]],
    batch_name: str,
    duplicate_of: DuplicatePayment | None,
    known: _Prefetched,
    preview: Target | None = None,
) -> PaymentReview:
    """Assemble one payment's review from its rows.

    **A preview measures the payment against something else it could be
    applied to** [0020], so the teacher sees "matches" or "৳200 short"
    for the exam fee before approving it there, and the client compares
    nothing. Nothing is written. A decided payment's own relief counts
    only when the preview is what it is applied to now.

    :param session: The session to read through
    :param submission: The submission
    :param pairs: Its claims and seats, in child order
    :param batch_name: The batch's name
    :param duplicate_of: The earlier submission it repeats, if any
    :param known: What :func:`_prefetch` read for it
    :param preview: Another purpose to measure it against, or None
    :return: The review
    """
    current = _target(submission)
    target = current if preview is None else preview
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
    fees = known.fees

    def owed(claim: PaymentClaim, seat: Enrollment) -> Money:
        """Measure one child against the target, before this decision.

        :param claim: The child's claim
        :param seat: The child's seat
        :return: What they owe for the target
        """
        if target != current:
            return owed_for_target(session, target=target, enrollment_id=seat.id)
        # What ``owed_for_claim`` reads, taken from the prefetched folds.
        now = (
            known.monthly_owed[claim.enrollment_id]
            if claim.extra_fee_charge_id is None
            else known.extra_owed[claim.extra_fee_charge_id]
        )
        return (
            now
            + relief.get(claim.id, Money.ZERO)
            + extra_relief.get(claim.id, Money.ZERO)
        )

    children = [
        ReviewChild(
            claim_id=claim.id,
            enrollment_id=seat.id,
            display_name=seat.display_name,
            period=claim.period,
            owed=owed(claim, seat),
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
        purpose=target.purpose,
        extra_fee=None if target.extra_fee_id is None else fees[target.extra_fee_id],
        requested_purpose=(
            "extra" if submission.requested_purpose == "extra" else "monthly"
        ),
        requested_extra_fee=(
            None
            if submission.requested_extra_fee_id is None
            else fees[submission.requested_extra_fee_id]
        ),
        extra_fee_options=tuple(known.options[submission.id]),
    )


def _owned_submissions(
    session: Session,
    lens: TeacherLens,
    *,
    decided_since: dt.datetime | None,
    limit: int | None = None,
) -> list[tuple[PaymentSubmission, str]]:
    """List this teacher's waiting submissions, and those decided since a moment.

    **Filtered in the query, not after it** [C-13]: a centre's history
    of decided payments grows every month and the queue shows none of
    it older than :data:`RECENT_WINDOW`, so loading it to discard it was
    the whole cost of the screen.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param decided_since: Also return submissions decided at or after
        this moment; None for waiting ones only
    :param limit: At most this many, oldest first; None for all
    :return: Submission and batch name, oldest first
    """
    wanted: sa.ColumnElement[bool] = PaymentSubmission.status == "pending"
    if decided_since is not None:
        wanted = sa.or_(wanted, PaymentSubmission.decided_at >= decided_since)
    statement = (
        sa.select(PaymentSubmission, Batch.name)
        .join(Batch, Batch.id == PaymentSubmission.batch_id)
        .where(Batch.owner_id == lens.owner_id, wanted)
        .order_by(PaymentSubmission.submitted_at, PaymentSubmission.id)
    )
    if limit is not None:
        statement = statement.limit(limit)
    return [(row[0], row[1]) for row in session.execute(statement).all()]


def _pending_reviews(
    session: Session,
    lens: TeacherLens,
    rows: list[tuple[PaymentSubmission, str]],
    children: dict[uuid.UUID, list[tuple[PaymentClaim, Enrollment]]],
) -> list[PaymentReview]:
    """Review every waiting submission among these rows, in their order.

    :param session: The session to read through
    :param lens: The teacher lens
    :param rows: Submissions with batch names, oldest first
    :param children: Each submission's claims and seats
    :return: One review per waiting submission
    """
    waiting = [(s, name) for s, name in rows if s.status == "pending"]
    if not waiting:
        return []
    duplicates = _duplicates(session, lens, [s for s, _name in waiting])
    known = _prefetch(session, [(s, children[s.id]) for s, _name in waiting])
    return [
        _review(
            session,
            submission,
            children[submission.id],
            batch_name,
            duplicates.get(submission.id),
            known,
        )
        for submission, batch_name in waiting
    ]


def verification_queue(
    session: Session,
    *,
    lens: TeacherLens,
    now: dt.datetime | None = None,
) -> VerificationQueue:
    """Read this teacher's waiting payments and recent decisions.

    A constant number of statements whatever the queue's length or the
    centre's history [C-13].

    :param session: The session to read through
    :param lens: The teacher lens
    :param now: The moment "recent" is measured from; now by default
    :return: The queue
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    rows = _owned_submissions(session, lens, decided_since=moment - RECENT_WINDOW)
    children = covered_children(session, [s.id for s, _name in rows])
    pending = _pending_reviews(session, lens, rows, children)

    recent: list[RecentDecision] = []
    for submission, batch_name in rows:
        if (
            submission.status != "pending"
            and submission.decided_at is not None
            and moment - submission.decided_at <= RECENT_WINDOW
        ):
            pairs = children[submission.id]
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


def pending_count(session: Session, *, lens: TeacherLens) -> int:
    """Count this teacher's waiting payments, in one statement.

    The figure the queue's length gives, without building a review of
    each: what a badge or a "To check" heading needs.

    :param session: The session to read through
    :param lens: The teacher lens
    :return: How many submissions wait to be checked
    """
    return session.execute(
        sa.select(sa.func.count())
        .select_from(PaymentSubmission)
        .join(Batch, Batch.id == PaymentSubmission.batch_id)
        .where(Batch.owner_id == lens.owner_id, PaymentSubmission.status == "pending")
    ).scalar_one()


def pending_preview(
    session: Session, *, lens: TeacherLens, limit: int
) -> list[PaymentReview]:
    """Review only the oldest few waiting payments.

    Exactly the first ``limit`` items of :func:`verification_queue`'s
    ``pending``, reviewing no others.

    :param session: The session to read through
    :param lens: The teacher lens
    :param limit: How many
    :return: The oldest waiting payments' reviews, oldest first
    """
    rows = _owned_submissions(session, lens, decided_since=None, limit=limit)
    children = covered_children(session, [s.id for s, _name in rows])
    return _pending_reviews(session, lens, rows, children)


def payment_review(
    session: Session,
    *,
    lens: TeacherLens,
    submission_id: uuid.UUID,
    preview_purpose: str | None = None,
    preview_extra_fee_id: uuid.UUID | None = None,
) -> PaymentReview:
    """Read one payment on this teacher's batches, decided or not (R2).

    :param session: The session to read through
    :param lens: The teacher lens
    :param submission_id: The submission
    :param preview_purpose: Measure it against ``monthly`` or ``extra``
        instead of what it is applied to now; None for no preview
    :param preview_extra_fee_id: The fee, when previewing ``extra``
    :return: The review
    :raises AuthorizationError: It is absent or not this lens's
    :raises ValidationError: The preview names no fee of this batch, or
        one a covered child was not charged
    """
    submission = owned_submission(session, lens=lens, submission_id=submission_id)
    batch_name = session.scalars(
        sa.select(Batch.name).where(Batch.id == submission.batch_id)
    ).one()
    duplicate = _duplicates(session, lens, [submission]).get(submission.id)
    pairs = covered_children(session, [submission.id])[submission.id]
    preview = (
        None
        if preview_purpose is None
        else resolve_target(
            session,
            purpose=preview_purpose,
            extra_fee_id=preview_extra_fee_id,
            batch_id=submission.batch_id,
        )
    )
    return _review(
        session,
        submission,
        pairs,
        batch_name,
        duplicate,
        _prefetch(session, [(submission, pairs)], preview),
        preview=preview,
    )
