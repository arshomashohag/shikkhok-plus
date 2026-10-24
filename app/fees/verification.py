"""Verifying a claim: the calculation easiest to get wrong.

**The shortfall is ``charged - approved``, never ``claimed -
approved``** [BR5.3]. The separating case, computed: a cycle charged
1000, a claim of 1500, approved at 600 leaves **400.00** -- not 900.00.
A claim is an *assertion*; a charge is the *obligation*. Measuring
against the claim would let a payer change what they owe by changing
what they assert, and a test using a claim equal to the charge cannot
tell the two formulas apart.

**Approving less than was charged requires an explicit choice** between
carrying the shortfall forward and waiving it [BR5.4]. Neither may be a
default: the two have opposite consequences for the student, and a
default silently chooses for the teacher.

**The decision and its entries commit in ONE transaction** [BR5.5]. A
partial commit leaves a claim marked approved with no money recorded,
or money recorded against a claim still showing pending -- and the
ledger is append-only, so the second cannot be tidied away.

**A correction compensates; it never rewrites** [BR3.3, BR5.7]. The
prior decision is retained with its actor and timestamp and is visible
to the teacher AND to that student and guardian, which is the asymmetry
FR9.2 forbids.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import DISPOSITION_VALUES, LedgerEntryRow, PaymentClaim
from app.errors import ConflictError, ValidationError
from app.fees.balances import derive_for_enrollment
from app.fees.ledger_writer import append_carry_pair, append_entry, supersede
from app.fees.periods import Period
from app.money import Money

__all__ = ["VerificationOutcome", "reject_claim", "verify_claim"]


@dataclass(frozen=True, slots=True)
class VerificationOutcome:
    """What one verification decided and produced.

    :ivar claim: The claim, with its decision written
    :ivar shortfall: ``charged - approved``, floored at zero
    """

    claim: PaymentClaim
    shortfall: Money


def _load(session: Session, claim_id: uuid.UUID) -> PaymentClaim:
    """Load a claim or refuse.

    :param session: The session to read through
    :param claim_id: The claim
    :return: The claim record
    :raises ValidationError: No such claim
    """
    claim = session.get(PaymentClaim, claim_id)
    if claim is None:
        raise ValidationError(
            code="CLAIM_NOT_FOUND",
            message_key="fees.claim.not_found",
        )
    return claim


#: The only status from which a claim may be decided for the first
#: time. Any other value means a verification already landed, so a
#: second one is either a conflict or a declared correction.
_UNDECIDED = "pending"


def _claim_the_decision(
    session: Session,
    claim: PaymentClaim,
    *,
    correcting: bool,
) -> None:
    """Win the right to decide this claim, or refuse [NFR6.35].

    **A locking read, not a plain check.** The design names a
    conditional ``UPDATE ... WHERE status = 'pending'``; this is the
    same guarantee reached by locking the row instead, which fits a
    path that then writes the status through the ORM rather than in
    that statement. Both make the winner's commit visible to every
    loser before it reads; a bare ``if claim.status == 'pending'``
    makes neither, because all N workers read ``pending`` at the same
    moment and all proceed.

    The property is the one the fee-cycle constraint gives generation:
    an application-level "is it still pending?" test passes a
    sequential test and fails with two workers.

    A declared correction skips the guard. FR9.2 makes every
    verification correctable, so refusing every decision on a decided
    claim would settle the race and break correction with it.

    :param session: The session to write through
    :param claim: The claim being decided
    :param correcting: True when this is a deliberate revision
    :return: None
    :raises ConflictError: Another verification decided this claim
        first, and this one is not a declared correction
    """
    if correcting:
        return

    # **The row lock is what makes this a race and not a check.**
    # `FOR UPDATE` serializes the contenders on this claim: the first
    # holds the lock until it commits its decision, and each of the
    # others then reads the status it committed rather than the stale
    # `pending` they all started from. Without the lock every worker
    # reads `pending` simultaneously and all of them proceed.
    current = session.execute(
        sa.select(PaymentClaim.status)
        .where(PaymentClaim.id == claim.id)
        .with_for_update()
    ).scalar_one_or_none()

    if current != _UNDECIDED:
        raise ConflictError(
            code="CLAIM_ALREADY_VERIFIED",
            message_key="fees.verification.already_decided",
        )


def _previous_decision(claim: PaymentClaim) -> dict[str, object] | None:
    """Capture a decided claim's current decision before replacing it.

    Returns None for a claim still pending: there is no previous
    decision to retain, and writing an all-null record would make
    "was this corrected" unanswerable by presence.

    Amounts are stored as canonical strings, never numbers, so the
    retained record crosses the API under the same rule as every other
    money value [BR6.2].

    :param claim: The claim about to be re-decided
    :return: The prior decision, or None if it had none
    """
    if claim.status == "pending":
        return None
    return {
        "status": claim.status,
        "approved_amount": (
            None if claim.approved_amount is None else str(claim.approved_amount)
        ),
        "shortfall_disposition": claim.shortfall_disposition,
        "verified_by_account_id": (
            None
            if claim.verified_by_account_id is None
            else str(claim.verified_by_account_id)
        ),
        "verified_at": (
            None if claim.verified_at is None else claim.verified_at.isoformat()
        ),
    }


def _reverse_prior_entries(
    session: Session,
    claim: PaymentClaim,
    *,
    verified_by_account_id: uuid.UUID,
) -> None:
    """Compensate every entry a prior decision produced [BR3.3].

    **Append-only**: each prior entry keeps its amount and gains a
    ``superseded_by_id`` pointing at the entry that compensates it. The
    fold reads both, and a compensating pair sums to zero, so the
    balance returns to what it was before the prior decision while the
    audit trail stays complete.

    The compensating kind is the one sitting opposite the original on
    the balance identity, so the two cancel exactly: a ``receipt`` or a
    ``forgiveness`` relieved an obligation and is cancelled by a
    ``charge`` of the same amount, a ``credit_grant`` by a
    ``credit_apply``, and either half of a carry by the other -- which
    reverses the whole pair and keeps
    ``sum(carry_forward) == sum(carried_out)`` true throughout.

    :param session: The session to write through
    :param claim: The claim whose prior entries are being undone
    :param verified_by_account_id: Who is correcting
    :return: None
    """
    prior = list(
        session.scalars(
            # Only entries this claim produced, and only those not
            # already compensated -- a second correction must not
            # reverse the first correction's reversals.
            sa.select(LedgerEntryRow)
            .where(
                LedgerEntryRow.payment_claim_id == claim.id,
                LedgerEntryRow.superseded_by_id.is_(None),
            )
            .order_by(LedgerEntryRow.created_at)
        )
    )

    # Each kind is cancelled by the kind that sits opposite it on the
    # identity. carried_out/carry_forward are a pair and cancel each
    # other, so reversing one reverses both halves of the carry.
    opposite = {
        "receipt": "charge",
        "forgiveness": "charge",
        "credit_grant": "credit_apply",
        "credit_apply": "credit_grant",
        "carry_forward": "carried_out",
        "carried_out": "carry_forward",
    }

    for entry in prior:
        mirror = opposite.get(entry.kind)
        if mirror is None:
            continue
        compensation = append_entry(
            session,
            enrollment_id=claim.enrollment_id,
            period=entry.period,
            kind=mirror,
            amount=entry.amount,
            payment_claim_id=claim.id,
            created_by_account_id=verified_by_account_id,
        )
        supersede(session, original=entry, compensation=compensation)


def verify_claim(
    session: Session,
    *,
    claim_id: uuid.UUID,
    approved_amount: Money,
    shortfall_disposition: str | None,
    verified_by_account_id: uuid.UUID,
    correcting: bool = False,
) -> VerificationOutcome:
    """Approve a claim, writing its decision and entries together.

    One transaction for the claim's status, approved amount,
    disposition, verifier and timestamp together with every ledger entry
    the decision produced [BR5.5].

    **Deciding an already-decided claim is a ``ConflictError`` unless
    the caller says it is a correction** [NFR6.35, NFR14.45]. Two
    teachers approving the same claim at the same moment would
    otherwise each append a full set of entries and credit the payment
    twice, which is a money error — and a claim has no
    ``(enrollment, period)`` uniqueness for the database to conflict
    on, so this is the one concurrent path the fee-cycle constraint does
    not already cover.

    The guard is a **conditional update** rather than a read-then-write:
    ``_claim_the_decision`` moves the status only ``WHERE`` it still
    holds the value this caller read, so zero rows updated means another
    verification won. A check-then-act would pass a sequential test and
    lose the race it exists to settle.

    ``correcting`` separates the two cases that look identical from the
    database's point of view. FR9.2 makes every verification
    correctable, so a guard reading "refuse any verification of a
    decided claim" would pass the race test and break correction
    entirely.

    :param session: The session to write through
    :param claim_id: The claim to decide
    :param approved_amount: What the teacher accepted
    :param shortfall_disposition: ``carried`` or ``waived``, required
        where the approval is below the charge and None where it is not
    :param verified_by_account_id: Who decided
    :param correcting: True when the teacher is deliberately revising a
        decision already on record, which retains the prior one
    :return: The decided claim and the computed shortfall
    :raises ValidationError: The amount is negative, the disposition is
        missing where one is required or supplied where none applies,
        or the disposition is not a representable value
    :raises ConflictError: The claim was already decided and this is not
        a declared correction
    """
    if approved_amount.is_negative():
        raise ValidationError(
            code="APPROVED_AMOUNT_NEGATIVE",
            message_key="fees.verification.amount_negative",
        )

    claim = _load(session, claim_id)
    _claim_the_decision(session, claim, correcting=correcting)
    previous = _previous_decision(claim)

    # A correction: undo the prior decision's entries before writing
    # the new ones, so the balance reflects one decision at a time.
    if previous is not None:
        _reverse_prior_entries(
            session, claim, verified_by_account_id=verified_by_account_id
        )

    period = claim.period
    derived = derive_for_enrollment(session, claim.enrollment_id)
    charged = derived.per_cycle.get(period, Money.ZERO)

    # THE FORMULA. `charged`, never `claim.claimed_amount`.
    raw_shortfall = charged - approved_amount
    shortfall = Money.ZERO if raw_shortfall.is_negative() else raw_shortfall

    if shortfall.is_positive():
        if shortfall_disposition is None:
            raise ValidationError(
                code="SHORTFALL_DISPOSITION_REQUIRED",
                message_key="fees.verification.disposition_required",
            )
        if shortfall_disposition not in DISPOSITION_VALUES:
            raise ValidationError(
                code="SHORTFALL_DISPOSITION_UNKNOWN",
                message_key="fees.verification.disposition_unknown",
            )
    elif shortfall_disposition is not None:
        raise ValidationError(
            code="SHORTFALL_DISPOSITION_NOT_APPLICABLE",
            message_key="fees.verification.disposition_not_applicable",
        )

    # The receipt is capped at what the cycle owed; the excess is
    # credit, never a negative balance [BR4.2]. Cash in is
    # receipt + credit_grant, which is where ADR-002's first correction
    # attempt went wrong.
    receipted = approved_amount if approved_amount < charged else charged
    if receipted.is_positive():
        append_entry(
            session,
            enrollment_id=claim.enrollment_id,
            period=period,
            kind="receipt",
            amount=receipted,
            payment_claim_id=claim.id,
            created_by_account_id=verified_by_account_id,
        )

    excess = approved_amount - receipted
    if excess.is_positive():
        append_entry(
            session,
            enrollment_id=claim.enrollment_id,
            period=period,
            kind="credit_grant",
            amount=excess,
            payment_claim_id=claim.id,
            created_by_account_id=verified_by_account_id,
        )

    if shortfall.is_positive():
        if shortfall_disposition == "carried":
            append_carry_pair(
                session,
                enrollment_id=claim.enrollment_id,
                amount=shortfall,
                origin=period,
                receiver=str(Period.parse(period).next()),
                payment_claim_id=claim.id,
                created_by_account_id=verified_by_account_id,
            )
        else:
            append_entry(
                session,
                enrollment_id=claim.enrollment_id,
                period=period,
                kind="forgiveness",
                amount=shortfall,
                payment_claim_id=claim.id,
                created_by_account_id=verified_by_account_id,
            )

    claim.status = "approved_full" if shortfall.is_zero() else "approved_partial"
    claim.approved_amount = approved_amount
    claim.shortfall_disposition = shortfall_disposition
    claim.verified_by_account_id = verified_by_account_id
    claim.verified_at = dt.datetime.now(tz=dt.UTC)
    if previous is not None:
        claim.previous_decision = previous

    session.commit()
    return VerificationOutcome(claim=claim, shortfall=shortfall)


def reject_claim(
    session: Session,
    *,
    claim_id: uuid.UUID,
    verified_by_account_id: uuid.UUID,
    correcting: bool = False,
) -> PaymentClaim:
    """Reject a claim, recording nothing as received [BR5.6].

    **No ledger entry of any kind is appended**, and the outstanding
    balance is unchanged. A rejected claim that still moved money, or a
    rejection the submitter never sees, are the two failures this
    answers; the second is the response schema's job and the first is
    this function's.

    Rejecting a previously approved claim is a correction and reverses
    the entries that approval produced.

    :param session: The session to write through
    :param claim_id: The claim to reject
    :param verified_by_account_id: Who rejected it
    :param correcting: True when deliberately revising a decision
    :return: The rejected claim
    :raises ValidationError: No such claim
    :raises ConflictError: Already decided and not a declared correction
    """
    claim = _load(session, claim_id)
    _claim_the_decision(session, claim, correcting=correcting)
    previous = _previous_decision(claim)

    if previous is not None:
        _reverse_prior_entries(
            session, claim, verified_by_account_id=verified_by_account_id
        )

    claim.status = "rejected"
    claim.approved_amount = None
    claim.shortfall_disposition = None
    claim.verified_by_account_id = verified_by_account_id
    claim.verified_at = dt.datetime.now(tz=dt.UTC)
    if previous is not None:
        claim.previous_decision = previous

    session.commit()
    return claim
