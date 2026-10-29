"""The teacher's payment queue (T4): claims waiting to be checked.

**Every figure on the card is the server's.** The charge, the comparison
(``matches``, ``short`` or ``over``) and the difference are computed here,
against what the cycle CHARGED rather than what was claimed [BR5.3], so
the app shows "৳400 short of ৳1,200" without subtracting anything.

**Scoped to the batches this lens owns**, in the query rather than after
it: a claim from another teacher's batch is never loaded, so it cannot
leak through a forgotten filter.

**A reused transaction id is flagged, not refused.** Two claims quoting
the same bKash or Nagad reference is either a mistake or a second claim
for one payment; the teacher decides, and the card names the earlier
claim so they can.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.db.models import Batch, Enrollment, PaymentClaim
from app.fees.balances import derive_for_enrollment
from app.fees.status import ClaimStatus
from app.fees.verification import shortfall_of
from app.fees.views import assert_claim_is_verifiable, claim_status
from app.money import Money

__all__ = [
    "DuplicateClaim",
    "QueueItem",
    "RecentDecision",
    "VerificationQueue",
    "shortfall_preview",
    "verification_queue",
]

Comparison = Literal["matches", "short", "over"]
Submitter = Literal["student", "guardian"]

#: How far back "decided today" reaches.
RECENT_WINDOW = dt.timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class DuplicateClaim:
    """The earlier claim that quoted the same transaction id.

    :ivar claim_id: That claim
    :ivar display_name: Whose seat it was on, as the teacher typed it
    :ivar status: How it was decided, or pending
    :ivar amount: What was approved, else what was claimed
    :ivar decided_at: When it was decided, or None
    """

    claim_id: uuid.UUID
    display_name: str
    status: ClaimStatus
    amount: Money
    decided_at: dt.datetime | None


@dataclass(frozen=True, slots=True)
class QueueItem:
    """One claim waiting for the teacher.

    :ivar claim_id: The claim
    :ivar enrollment_id: The seat it is against
    :ivar display_name: The student, as the teacher typed the name
    :ivar batch_name: The batch
    :ivar period: The period the claim resolved to, ``YYYY-MM``
    :ivar claimed_amount: What the payer says they sent
    :ivar charged: What that period charged
    :ivar comparison: ``matches``, ``short`` or ``over``
    :ivar difference: How far from the charge, never negative
    :ivar channel: bKash, Nagad and so on
    :ivar transaction_id: The reference quoted, if any
    :ivar submitted_at: When it was sent
    :ivar submitted_by: ``student`` or ``guardian``, or None if the
        submitter's account has since been deleted
    :ivar submitter_phone: The number the teacher has on record for
        that person, or None
    :ivar duplicate_of: The earlier claim quoting the same reference
    """

    claim_id: uuid.UUID
    enrollment_id: uuid.UUID
    display_name: str
    batch_name: str
    period: str
    claimed_amount: Money
    charged: Money
    comparison: Comparison
    difference: Money
    channel: str
    transaction_id: str | None
    submitted_at: dt.datetime
    submitted_by: Submitter | None
    submitter_phone: str | None
    duplicate_of: DuplicateClaim | None


@dataclass(frozen=True, slots=True)
class RecentDecision:
    """A claim decided in the last day, for "Approved today".

    :ivar claim_id: The claim
    :ivar display_name: The student
    :ivar batch_name: The batch
    :ivar status: How it was decided
    :ivar amount: What was approved, else what was claimed
    :ivar decided_at: When
    """

    claim_id: uuid.UUID
    display_name: str
    batch_name: str
    status: ClaimStatus
    amount: Money
    decided_at: dt.datetime


@dataclass(frozen=True, slots=True)
class VerificationQueue:
    """What T4 shows: waiting claims, and what was decided recently.

    :ivar pending: Oldest first, so nobody waits longest unseen
    :ivar decided_recently: Newest first
    """

    pending: list[QueueItem]
    decided_recently: list[RecentDecision]


def _compare(claimed: Money, charged: Money) -> tuple[Comparison, Money]:
    """Say how a claim stands against its charge.

    :param claimed: What was claimed
    :param charged: What the period charged
    :return: The comparison and the distance, never negative
    """
    if claimed < charged:
        return "short", shortfall_of(charged, claimed)
    if claimed > charged:
        return "over", shortfall_of(claimed, charged)
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


def _submitter(
    claim: PaymentClaim, seat: Enrollment
) -> tuple[Submitter | None, str | None]:
    """Who sent a claim, and the number the teacher holds for them.

    :param claim: The claim
    :param seat: The seat it is against
    :return: The role and phone, or Nones when it cannot be said
    """
    submitter = claim.submitted_by_account_id
    if submitter is not None and submitter == seat.guardian_account_id:
        return "guardian", seat.guardian_phone
    if submitter is not None and submitter == seat.student_account_id:
        return "student", seat.student_phone
    return None, None


def _amount(claim: PaymentClaim) -> Money:
    """Give the figure a decided claim stands for.

    :param claim: The claim
    :return: The approved amount where there is one, else the claimed
    """
    return (
        claim.approved_amount
        if claim.approved_amount is not None
        else claim.claimed_amount
    )


def _owned_claims(
    session: Session, lens: TeacherLens
) -> list[tuple[PaymentClaim, Enrollment, str]]:
    """Every claim on this teacher's batches, with its seat and batch.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :return: Claim, seat and batch name, oldest submission first
    """
    rows = session.execute(
        sa.select(PaymentClaim, Enrollment, Batch.name)
        .join(Enrollment, Enrollment.id == PaymentClaim.enrollment_id)
        .join(Batch, Batch.id == Enrollment.batch_id)
        .where(Batch.owner_id == lens.owner_id)
        .order_by(PaymentClaim.submitted_at, PaymentClaim.id)
    ).all()
    return [(row[0], row[1], row[2]) for row in rows]


def _duplicates(
    rows: list[tuple[PaymentClaim, Enrollment, str]],
) -> dict[uuid.UUID, DuplicateClaim]:
    """For each claim, the earliest other claim quoting its reference.

    :param rows: The teacher's claims, oldest first
    :return: Claim id to the earlier claim it repeats
    """
    first_by_reference: dict[str, tuple[PaymentClaim, Enrollment]] = {}
    found: dict[uuid.UUID, DuplicateClaim] = {}
    for claim, seat, _batch in rows:
        reference = _reference(claim.transaction_id)
        if reference is None:
            continue
        earlier = first_by_reference.get(reference)
        if earlier is None:
            first_by_reference[reference] = (claim, seat)
            continue
        found[claim.id] = DuplicateClaim(
            claim_id=earlier[0].id,
            display_name=earlier[1].display_name,
            status=claim_status(earlier[0].status),
            amount=_amount(earlier[0]),
            decided_at=earlier[0].verified_at,
        )
    return found


def verification_queue(
    session: Session,
    *,
    lens: TeacherLens,
    now: dt.datetime | None = None,
) -> VerificationQueue:
    """Read this teacher's waiting claims and recent decisions.

    :param session: The session to read through
    :param lens: The teacher lens
    :param now: The moment "recent" is measured from; now by default
    :return: The queue
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    rows = _owned_claims(session, lens)
    duplicates = _duplicates(rows)

    pending: list[QueueItem] = []
    recent: list[RecentDecision] = []
    for claim, seat, batch_name in rows:
        if claim.status == "pending":
            charged = derive_for_enrollment(session, seat.id).per_cycle.get(
                claim.period, Money.ZERO
            )
            comparison, difference = _compare(claim.claimed_amount, charged)
            submitted_by, phone = _submitter(claim, seat)
            pending.append(
                QueueItem(
                    claim_id=claim.id,
                    enrollment_id=seat.id,
                    display_name=seat.display_name,
                    batch_name=batch_name,
                    period=claim.period,
                    claimed_amount=claim.claimed_amount,
                    charged=charged,
                    comparison=comparison,
                    difference=difference,
                    channel=claim.channel,
                    transaction_id=claim.transaction_id,
                    submitted_at=claim.submitted_at,
                    submitted_by=submitted_by,
                    submitter_phone=phone,
                    duplicate_of=duplicates.get(claim.id),
                )
            )
        elif (
            claim.verified_at is not None
            and moment - claim.verified_at <= RECENT_WINDOW
        ):
            recent.append(
                RecentDecision(
                    claim_id=claim.id,
                    display_name=seat.display_name,
                    batch_name=batch_name,
                    status=claim_status(claim.status),
                    amount=_amount(claim),
                    decided_at=claim.verified_at,
                )
            )
    recent.sort(key=lambda decision: decision.decided_at, reverse=True)
    return VerificationQueue(pending=pending, decided_recently=recent)


def shortfall_preview(
    session: Session,
    *,
    lens: TeacherLens,
    claim_id: uuid.UUID,
    approved_amount: Money,
) -> Money:
    """Preview what approving this amount would leave short.

    The partial sheet asks "what happens to the other ৳400?"; the 400
    comes from here, through the same formula the decision uses.

    :param session: The session to read through
    :param lens: The teacher lens
    :param claim_id: The claim
    :param approved_amount: The amount the teacher is about to accept
    :return: The shortfall, never negative
    :raises AuthorizationError: The claim is not on this lens's batches
    """
    claim = assert_claim_is_verifiable(session, lens=lens, claim_id=claim_id)
    charged = derive_for_enrollment(session, claim.enrollment_id).per_cycle.get(
        claim.period, Money.ZERO
    )
    return shortfall_of(charged, approved_amount)
