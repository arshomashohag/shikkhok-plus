"""Deciding a payment: approve it with a split, or reject it with a note.

**The decision is claimed on the submission row.** A conditional
``UPDATE payment_submission SET status = :new WHERE id = :id AND
status = :read`` moves the status only while it still holds the value
this caller read. Two teachers approving at once both read ``pending``;
the second update waits on the first's row lock, then matches nothing,
and is refused before it writes a single entry. The per-claim work runs
inside that one transaction and never re-runs a guard of its own.

**The split is the money module's.** ``allocate_payment`` takes what was
received and each child's owed figure in child order, and returns each
child's approved amount. Each claim is then verified at that amount; the
teacher's carry-or-waive reaches only a child approved below their
period's charge, so a child paid in full gets no disposition.

**A correction withdraws every child's decision first**, compensating
its entries, then writes the new one, so the allocation sees what was
owed before the decision being replaced.

**The family hears once per payment.** Each accepted student or
guardian of a covered seat gets one item carrying the teacher's note,
however many of their children it covered.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.db.models import Batch, Enrollment, PaymentClaim, PaymentSubmission
from app.errors import ConflictError, ValidationError
from app.fees.balances import derive_for_enrollment
from app.fees.queue import covered_children
from app.fees.verification import (
    reject_claim_in_transaction,
    verify_claim_in_transaction,
    withdraw_decision,
)
from app.fees.views import owned_submission
from app.money import (
    Allocation,
    Disposition,
    Money,
    MoneyValidationError,
    allocate_payment,
)
from app.notifications.inbox import (
    CLAIM_TO_VERIFY,
    PAYMENT_APPROVED,
    PAYMENT_PARTIAL,
    PAYMENT_REJECTED,
    deliver,
    mark_read_for_source,
    remove_for_source,
)
from app.notifications.recipients import seat_recipients

__all__ = ["approve_submission", "reject_submission"]

_PENDING = "pending"

type Covered = list[tuple[PaymentClaim, Enrollment]]


def _claim_the_decision(
    session: Session,
    submission: PaymentSubmission,
    *,
    decision: str,
    correcting: bool,
) -> None:
    """Win the right to decide this submission, or refuse.

    :param session: The session to write through
    :param submission: The submission, as this caller read it
    :param decision: ``approved`` or ``rejected``
    :param correcting: True when deliberately revising a decision
    :return: None
    :raises ConflictError: It was already decided and this is not a
        declared correction, or another decision landed first
    """
    read = submission.status
    if read != _PENDING and not correcting:
        raise _already_decided()
    moved = session.execute(
        sa.update(PaymentSubmission)
        .where(PaymentSubmission.id == submission.id, PaymentSubmission.status == read)
        .values(status=decision)
        .execution_options(synchronize_session=False)
    )
    if moved.rowcount != 1:  # type: ignore[attr-defined]
        raise _already_decided()


def _already_decided() -> ConflictError:
    """Build the refusal for a payment someone already decided.

    :return: The refusal
    """
    return ConflictError(
        code="PAYMENT_ALREADY_DECIDED",
        message_key="fees.verification.already_decided",
    )


def _previous(submission: PaymentSubmission) -> dict[str, object] | None:
    """Capture a decided submission's decision before replacing it.

    :param submission: The submission, as read before the decision
    :return: The prior decision, or None while it was pending
    """
    if submission.status == _PENDING:
        return None
    return {
        "status": submission.status,
        "decision_note": submission.decision_note,
        "decided_by_account_id": (
            None
            if submission.decided_by_account_id is None
            else str(submission.decided_by_account_id)
        ),
        "decided_at": (
            None if submission.decided_at is None else submission.decided_at.isoformat()
        ),
    }


def _note(note: str | None) -> str | None:
    """Treat a blank note as none.

    :param note: The note as typed
    :return: The trimmed note, or None
    """
    return (note or "").strip() or None


def _index_of(covered: Covered, enrollment_id: uuid.UUID | None) -> int | None:
    """Convert a chosen child's seat into its place in child order.

    :param covered: The submission's claims and seats, in child order
    :param enrollment_id: The chosen seat, or None
    :return: Its index, or None
    :raises ValidationError: The seat is not one the payment covers
    """
    if enrollment_id is None:
        return None
    for index, (_claim, seat) in enumerate(covered):
        if seat.id == enrollment_id:
            return index
    raise ValidationError(
        code="PAYMENT_CHILD_NOT_IN_PAYMENT",
        message_key="fees.payment.child_not_in_payment",
    )


def _allocation_refusal(error: MoneyValidationError) -> ValidationError:
    """Turn the allocation's refusal into the API's, keeping its code.

    :param error: The money module's refusal, whose message starts with
        its code
    :return: The validation error carrying that code
    """
    code = str(error).split(":", 1)[0]
    match code:
        case "ALLOCATION_DISPOSITION_REQUIRED":
            return ValidationError(
                code=code, message_key="fees.payment.allocation_disposition_required"
            )
        case "ALLOCATION_BEARER_REQUIRED":
            return ValidationError(
                code=code, message_key="fees.payment.allocation_bearer_required"
            )
        case "ALLOCATION_CREDIT_CHILD_REQUIRED":
            return ValidationError(
                code=code, message_key="fees.payment.allocation_credit_child_required"
            )
        case "ALLOCATION_DISPOSITION_NOT_APPLICABLE":
            return ValidationError(
                code=code,
                message_key="fees.payment.allocation_disposition_not_applicable",
            )
        case "ALLOCATION_INDEX_NOT_APPLICABLE":
            return ValidationError(
                code=code, message_key="fees.payment.allocation_child_not_applicable"
            )
        case _:
            return ValidationError(
                code=code, message_key="fees.payment.allocation_invalid"
            )


def _allocate(
    received: Money,
    owed: Sequence[Money],
    *,
    disposition: Disposition | None,
    bearer_index: int | None,
    credit_index: int | None,
) -> Allocation:
    """Split what was received across the children, or refuse.

    :param received: What the teacher recorded as received
    :param owed: Each child's owed figure, in child order
    :param disposition: Carry or waive, when short
    :param bearer_index: The child bearing a shortfall
    :param credit_index: The child receiving an excess
    :return: The allocation
    :raises ValidationError: The allocation refused the choices
    """
    try:
        return allocate_payment(
            received,
            owed,
            disposition=disposition,
            bearer_index=bearer_index,
            credit_index=credit_index,
        )
    except MoneyValidationError as error:
        raise _allocation_refusal(error) from error


def _discard_on_refusal(session: Session, error: ValidationError) -> ValidationError:
    """Roll back a decision already claimed, then hand back its refusal.

    The status update and any withdrawn entries are in the session by
    the time the allocation can refuse; rolling back here keeps a
    direct caller's session clean as well as the request's.

    :param session: The session the decision was being written through
    :param error: The refusal
    :return: The same refusal, to raise
    """
    session.rollback()
    return error


def _record_decision(
    submission: PaymentSubmission,
    *,
    decision: str,
    note: str | None,
    decided_by: uuid.UUID,
    previous: dict[str, object] | None,
) -> None:
    """Write the decision's own columns on the submission.

    :param submission: The submission
    :param decision: ``approved`` or ``rejected``
    :param note: The teacher's note
    :param decided_by: Who decided
    :param previous: The prior decision, on a correction
    :return: None
    """
    submission.status = decision
    submission.decision_note = _note(note)
    submission.decided_by_account_id = decided_by
    submission.decided_at = dt.datetime.now(tz=dt.UTC)
    if previous is not None:
        submission.previous_decision = previous


def _covered(session: Session, submission: PaymentSubmission) -> Covered:
    """Read the submission's claims and seats in child order.

    :param session: The session to read through
    :param submission: The submission
    :return: Its claims and seats
    """
    return covered_children(session, [submission.id])[submission.id]


def approve_submission(
    session: Session,
    *,
    lens: TeacherLens,
    submission_id: uuid.UUID,
    received: Money,
    disposition: Disposition | None,
    carried_by_enrollment_id: uuid.UUID | None,
    credit_to_enrollment_id: uuid.UUID | None,
    note: str | None,
    correcting: bool = False,
) -> PaymentSubmission:
    """Approve a payment, split across its children, in one transaction.

    :param session: The session to write through
    :param lens: The deciding teacher's lens
    :param submission_id: The submission
    :param received: What the teacher recorded as received
    :param disposition: Carry or waive a shortfall; None unless short
    :param carried_by_enrollment_id: The child bearing a shortfall
    :param credit_to_enrollment_id: The child receiving an excess
    :param note: The teacher's note to the family
    :param correcting: True when deliberately revising a decision
    :return: The approved submission
    :raises AuthorizationError: It is absent or not this lens's
    :raises ValidationError: A chosen child is not covered, or the
        allocation refused the choices
    :raises ConflictError: It was already decided and this is not a
        declared correction
    """
    submission = owned_submission(session, lens=lens, submission_id=submission_id)
    covered = _covered(session, submission)
    bearer_index = _index_of(covered, carried_by_enrollment_id)
    credit_index = _index_of(covered, credit_to_enrollment_id)
    previous = _previous(submission)
    _claim_the_decision(session, submission, decision="approved", correcting=correcting)

    for claim, _seat in covered:
        withdraw_decision(session, claim, verified_by_account_id=lens.account_id)
    try:
        allocation = _allocate(
            received,
            [
                derive_for_enrollment(session, seat.id).total_outstanding
                for _claim, seat in covered
            ],
            disposition=disposition,
            bearer_index=bearer_index,
            credit_index=credit_index,
        )
    except ValidationError as error:
        raise _discard_on_refusal(session, error) from None
    for (claim, seat), approved in zip(covered, allocation.approved, strict=True):
        charged = derive_for_enrollment(session, seat.id).per_cycle.get(
            claim.period, Money.ZERO
        )
        verify_claim_in_transaction(
            session,
            claim,
            approved_amount=approved,
            shortfall_disposition=disposition if approved < charged else None,
            verified_by_account_id=lens.account_id,
        )

    _record_decision(
        submission,
        decision="approved",
        note=note,
        decided_by=lens.account_id,
        previous=previous,
    )
    short_of_sent = received < submission.total_amount
    _tell_the_family(
        session,
        submission,
        covered,
        kind=PAYMENT_PARTIAL if short_of_sent else PAYMENT_APPROVED,
        replacing=previous is not None,
    )
    session.commit()
    return submission


def reject_submission(
    session: Session,
    *,
    lens: TeacherLens,
    submission_id: uuid.UUID,
    note: str | None,
    correcting: bool = False,
) -> PaymentSubmission:
    """Reject a payment: every child's claim rejected, nothing received.

    :param session: The session to write through
    :param lens: The deciding teacher's lens
    :param submission_id: The submission
    :param note: Why, shown to the family
    :param correcting: True when deliberately revising a decision
    :return: The rejected submission
    :raises AuthorizationError: It is absent or not this lens's
    :raises ConflictError: It was already decided and this is not a
        declared correction
    """
    submission = owned_submission(session, lens=lens, submission_id=submission_id)
    covered = _covered(session, submission)
    previous = _previous(submission)
    _claim_the_decision(session, submission, decision="rejected", correcting=correcting)

    for claim, _seat in covered:
        reject_claim_in_transaction(
            session, claim, verified_by_account_id=lens.account_id, reason=note
        )

    _record_decision(
        submission,
        decision="rejected",
        note=note,
        decided_by=lens.account_id,
        previous=previous,
    )
    _tell_the_family(
        session,
        submission,
        covered,
        kind=PAYMENT_REJECTED,
        replacing=previous is not None,
    )
    session.commit()
    return submission


def _tell_the_family(
    session: Session,
    submission: PaymentSubmission,
    covered: Covered,
    *,
    kind: str,
    replacing: bool,
) -> None:
    """Put the decision in each family member's inbox, once per payment.

    The teacher's "to verify" item is settled in the same transaction,
    and a correction first removes the earlier decision's items.

    :param session: The session the decision is written through
    :param submission: The decided submission
    :param covered: Its claims and seats, in child order
    :param kind: Which decision
    :param replacing: True when an earlier decision's items exist
    :return: None
    """
    mark_read_for_source(session, kind=CLAIM_TO_VERIFY, source_id=submission.id)
    for claim, _seat in covered:
        mark_read_for_source(session, kind=CLAIM_TO_VERIFY, source_id=claim.id)
    if replacing:
        for earlier in (PAYMENT_APPROVED, PAYMENT_PARTIAL, PAYMENT_REJECTED):
            remove_for_source(session, kind=earlier, source_id=submission.id)

    reached: dict[uuid.UUID, list[tuple[PaymentClaim, str | None]]] = {}
    for claim, seat in covered:
        for recipient in seat_recipients(session, enrollment_id=seat.id):
            reached.setdefault(recipient.account_id, []).append(
                (claim, recipient.child_name)
            )
    if not reached:
        return

    batch_name = session.scalars(
        sa.select(Batch.name).where(Batch.id == submission.batch_id)
    ).one()
    now = dt.datetime.now(tz=dt.UTC)
    for account_id, shares in reached.items():
        first = shares[0][0]
        names = [name for _claim, name in shares if name is not None]
        amount = (
            submission.total_amount
            if kind == PAYMENT_REJECTED
            else Money.sum([claim.approved_amount or Money.ZERO for claim, _ in shares])
        )
        deliver(
            session,
            account_ids=[account_id],
            kind=kind,
            batch_name=batch_name,
            now=now,
            enrollment_id=first.enrollment_id,
            period=first.period,
            amount=amount,
            source_id=submission.id,
            preview=submission.decision_note,
            child_names={account_id: ", ".join(names)} if names else None,
        )
