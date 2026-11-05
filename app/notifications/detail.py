"""What one inbox item opens to, read as the source stands now.

**The item is a pointer and the source is the truth.** A notice that was
edited opens to its current body, and a notice that was deleted, an exam
that was removed, or a seat the caller no longer reaches opens to
*nothing* rather than to a refusal: the item is the caller's own, so its
existence is no secret, but the content behind it is only theirs while
their lens still reaches the seat.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import Lens, TeacherLens
from app.authz.resolve import available_lenses
from app.db.models import (
    Announcement,
    BatchSubject,
    Exam,
    PaymentClaim,
    PaymentSubmission,
)
from app.errors import AuthorizationError
from app.money import Money
from app.notifications.inbox import (
    CLAIM_TO_VERIFY,
    EXAM_SCHEDULED,
    NOTICE,
    PAYMENT_APPROVED,
    PAYMENT_PARTIAL,
    PAYMENT_RECORDED,
    PAYMENT_REJECTED,
    InboxItem,
    owned_item,
)
from app.teaching.roster import readable_enrollment

__all__ = [
    "ExamDetail",
    "ItemDetail",
    "NoticeDetail",
    "PaymentDetail",
    "open_item",
]

PaymentOutcome = Literal["approved", "partial", "rejected", "pending"]

_PAYMENT_KINDS = frozenset(
    {PAYMENT_APPROVED, PAYMENT_PARTIAL, PAYMENT_RECORDED, PAYMENT_REJECTED}
)


@dataclass(frozen=True, slots=True)
class NoticeDetail:
    """A notice as it reads now.

    :ivar body: The current text
    :ivar posted_at: When it was posted
    :ivar edited_at: When it was last edited, if ever
    """

    body: str
    posted_at: dt.datetime
    edited_at: dt.datetime | None


@dataclass(frozen=True, slots=True)
class ExamDetail:
    """An exam as it stands now.

    :ivar exam_id: The exam
    :ivar title: The teacher's name for it
    :ivar date: When it is held
    :ivar subject_name: The subject
    :ivar total_marks: The denominator
    :ivar topics: What it covers
    """

    exam_id: uuid.UUID
    title: str
    date: dt.date
    subject_name: str
    total_marks: int
    topics: list[str]


@dataclass(frozen=True, slots=True)
class PaymentDetail:
    """A payment and how it was decided.

    :ivar claim_id: The claim for the item's seat
    :ivar period: The period it paid toward
    :ivar claimed: What was claimed
    :ivar approved: What the teacher accepted, once decided
    :ivar outcome: Where the decision stands
    :ivar reason: Why it was rejected, if it was
    """

    claim_id: uuid.UUID
    period: str
    claimed: Money
    approved: Money | None
    outcome: PaymentOutcome
    reason: str | None


@dataclass(frozen=True, slots=True)
class ItemDetail:
    """One inbox item and, when it still can, what it opens to.

    :ivar item: The item itself
    :ivar available: Whether the source still exists and the caller reaches it
    :ivar notice: Set for an available notice
    :ivar exam: Set for an available exam
    :ivar payment: Set for an available payment result
    """

    item: InboxItem
    available: bool
    notice: NoticeDetail | None = None
    exam: ExamDetail | None = None
    payment: PaymentDetail | None = None


def _reaches(
    session: Session,
    *,
    account_id: uuid.UUID,
    enrollment_id: uuid.UUID | None,
    kind: str,
) -> bool:
    """Whether the caller still has a lens onto the item's seat.

    A claim awaiting verification is the teacher's; every other kind is
    the family's, so a teacher lens does not stand in for a lost seat.

    :param session: The session to read through
    :param account_id: The caller
    :param enrollment_id: The seat the item is about
    :param kind: The item's kind
    :return: True if a fitting lens reaches the seat
    """
    if enrollment_id is None:
        return False
    for lens in available_lenses(session, account_id):
        if _fits(lens, kind) and _reads(session, lens, enrollment_id):
            return True
    return False


def _fits(lens: Lens, kind: str) -> bool:
    """Whether this lens is the sort of reader the kind is addressed to.

    :param lens: A lens the caller holds
    :param kind: The item's kind
    :return: True if the lens fits
    """
    return isinstance(lens, TeacherLens) == (kind == CLAIM_TO_VERIFY)


def _reads(session: Session, lens: Lens, enrollment_id: uuid.UUID) -> bool:
    """Whether the lens reaches the seat.

    :param session: The session to read through
    :param lens: The lens
    :param enrollment_id: The seat
    :return: True if it does
    """
    try:
        readable_enrollment(session, lens=lens, enrollment_id=enrollment_id)
    except AuthorizationError:
        return False
    return True


def _notice(session: Session, source_id: uuid.UUID) -> NoticeDetail | None:
    """Read a notice that has not been deleted.

    :param session: The session to read through
    :param source_id: The announcement
    :return: Its current text, or None
    """
    row = session.get(Announcement, source_id)
    if row is None or row.deleted_at is not None:
        return None
    return NoticeDetail(
        body=row.body, posted_at=row.created_at, edited_at=row.edited_at
    )


def _exam(session: Session, source_id: uuid.UUID) -> ExamDetail | None:
    """Read an exam.

    :param session: The session to read through
    :param source_id: The exam
    :return: Its current state, or None
    """
    row = session.get(Exam, source_id)
    if row is None:
        return None
    subject = session.scalars(
        sa.select(BatchSubject.name).where(BatchSubject.id == row.batch_subject_id)
    ).one()
    return ExamDetail(
        exam_id=row.id,
        title=row.title,
        date=row.date,
        subject_name=subject,
        total_marks=row.total_marks,
        topics=list(row.topics),
    )


def _outcome(claim: PaymentClaim) -> PaymentOutcome:
    """Read where a claim's stored decision leaves it.

    :param claim: The claim
    :return: pending, rejected, partial (approved below claimed) or approved
    """
    if claim.status == "rejected":
        return "rejected"
    if claim.status == "pending" or claim.approved_amount is None:
        return "pending"
    if claim.approved_amount < claim.claimed_amount:
        return "partial"
    return "approved"


def _submission_outcome(submission: PaymentSubmission) -> PaymentOutcome:
    """Read where a submission's decision leaves it.

    :param submission: The submission
    :return: pending, rejected or approved
    """
    if submission.status == "rejected":
        return "rejected"
    if submission.status == "pending":
        return "pending"
    return "approved"


def _submission_payment(
    session: Session, submission: PaymentSubmission, enrollment_id: uuid.UUID | None
) -> PaymentDetail | None:
    """Read a submission's decision as the item's seat sees it.

    The block names that seat's claim and period, and carries the whole
    payment's figures and the teacher's note.

    :param session: The session to read through
    :param submission: The submission
    :param enrollment_id: The seat the item is about
    :return: The decision, or None when the seat's claim is gone
    """
    claims = list(
        session.scalars(
            sa.select(PaymentClaim).where(
                PaymentClaim.payment_submission_id == submission.id
            )
        )
    )
    mine = [claim for claim in claims if claim.enrollment_id == enrollment_id]
    if not mine:
        return None
    outcome = _submission_outcome(submission)
    approved = (
        Money.sum([claim.approved_amount or Money.ZERO for claim in claims])
        if outcome == "approved"
        else None
    )
    if approved is not None and approved < submission.total_amount:
        outcome = "partial"
    return PaymentDetail(
        claim_id=mine[0].id,
        period=mine[0].period,
        claimed=submission.total_amount,
        approved=approved,
        outcome=outcome,
        reason=submission.decision_note,
    )


def _payment(session: Session, item: InboxItem) -> PaymentDetail | None:
    """Read the decision an item points at: a submission, or a lone claim.

    :param session: The session to read through
    :param item: The item, whose source is the submission or the claim
    :return: The decision as it stands now, or None
    """
    source_id = item.source_id
    if source_id is None:
        return None
    submission = session.get(PaymentSubmission, source_id)
    if submission is not None:
        return _submission_payment(session, submission, item.enrollment_id)
    claim = session.get(PaymentClaim, source_id)
    if claim is None:
        return None
    return PaymentDetail(
        claim_id=claim.id,
        period=claim.period,
        claimed=claim.claimed_amount,
        approved=claim.approved_amount,
        outcome=_outcome(claim),
        reason=claim.rejection_reason,
    )


def _awaits_verification(session: Session, source_id: uuid.UUID) -> bool:
    """Whether the payment a teacher's item points at still exists.

    The item's source is the submission; items written before payments
    had submissions point at the claim, and both are honoured.

    :param session: The session to read through
    :param source_id: The submission or claim
    :return: True when either is present
    """
    return (
        session.get(PaymentSubmission, source_id) is not None
        or session.get(PaymentClaim, source_id) is not None
    )


def _source(
    session: Session, item: InboxItem
) -> tuple[NoticeDetail | None, ExamDetail | None, PaymentDetail | None, bool]:
    """Read whatever the item's source is.

    :param session: The session to read through
    :param item: The item
    :return: The notice, exam and payment blocks, and whether the source
        is present (kinds with no block are present when they have no
        source to lose)
    """
    source = item.source_id
    if item.kind == NOTICE and source is not None:
        notice = _notice(session, source)
        return notice, None, None, notice is not None
    if item.kind == EXAM_SCHEDULED and source is not None:
        exam = _exam(session, source)
        return None, exam, None, exam is not None
    if item.kind in _PAYMENT_KINDS and source is not None:
        payment = _payment(session, item)
        return None, None, payment, payment is not None
    if item.kind == CLAIM_TO_VERIFY and source is not None:
        return None, None, None, _awaits_verification(session, source)
    return None, None, None, True


def open_item(
    session: Session, *, account_id: uuid.UUID, notification_id: uuid.UUID
) -> ItemDetail:
    """Open one of the caller's own items as its source stands now.

    :param session: The session to read through
    :param account_id: The authenticated caller
    :param notification_id: The item to open
    :return: The item, with a block only while it is still available
    :raises AuthorizationError: The id is missing or another account's
    """
    item = owned_item(session, account_id=account_id, notification_id=notification_id)
    if not _reaches(
        session, account_id=account_id, enrollment_id=item.enrollment_id, kind=item.kind
    ):
        return ItemDetail(item=item, available=False)
    notice, exam, payment, present = _source(session, item)
    if not present:
        return ItemDetail(item=item, available=False)
    return ItemDetail(
        item=item, available=True, notice=notice, exam=exam, payment=payment
    )
