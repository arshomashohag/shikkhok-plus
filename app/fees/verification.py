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
from sqlalchemy.orm import Session, aliased

from app.db.models import (
    DISPOSITION_VALUES,
    Batch,
    Enrollment,
    LedgerEntryRow,
    PaymentClaim,
)
from app.errors import ConflictError, ValidationError
from app.fees.balances import derive_for_enrollment
from app.fees.ledger_writer import append_carry_pair, append_entry, supersede
from app.fees.periods import Period
from app.money import Money, settle_oldest_first
from app.notifications.inbox import (
    CLAIM_TO_VERIFY,
    PAYMENT_APPROVED,
    PAYMENT_PARTIAL,
    PAYMENT_REJECTED,
    deliver,
    mark_read_for_source,
    remove_for_source,
)
from app.notifications.recipients import child_names, seat_recipients

__all__ = [
    "VerificationOutcome",
    "reject_claim",
    "reject_claim_in_transaction",
    "settle_claim_in_transaction",
    "shortfall_of",
    "verify_claim",
    "verify_claim_in_transaction",
    "withdraw_decision",
]


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
    ``credit_apply`` together with a ``charge`` on the same period (the
    ``credit_apply`` cancels the credit but would relieve that period, so
    the ``charge`` puts the obligation back and the period nets to zero),
    and either half of a carry by the other -- which
    reverses the whole pair and keeps
    ``sum(carry_forward) == sum(carried_out)`` true throughout.

    :param session: The session to write through
    :param claim: The claim whose prior entries are being undone
    :param verified_by_account_id: Who is correcting
    :return: None
    """
    compensating = aliased(LedgerEntryRow)
    prior = list(
        session.scalars(
            # Only entries this claim produced, and only those not
            # already compensated -- a second correction must not
            # reverse the first correction's reversals, so an entry
            # that IS a compensation is excluded as well.
            sa.select(LedgerEntryRow)
            .where(
                LedgerEntryRow.payment_claim_id == claim.id,
                LedgerEntryRow.superseded_by_id.is_(None),
                ~sa.exists().where(compensating.superseded_by_id == LedgerEntryRow.id),
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
        if entry.kind == "credit_grant":
            append_entry(
                session,
                enrollment_id=claim.enrollment_id,
                period=entry.period,
                kind="charge",
                amount=entry.amount,
                payment_claim_id=claim.id,
                created_by_account_id=verified_by_account_id,
            )


def shortfall_of(charged: Money, approved: Money) -> Money:
    """Compute what an approval leaves unpaid of a cycle's charge [BR5.3].

    **The formula, in one place**, so the teacher's preview and the
    decision itself cannot disagree: ``charged``, never the claimed
    amount, because a claim is an assertion and the charge is the
    obligation. Floored at zero; an approval above the charge leaves
    nothing short.

    :param charged: What the cycle charged
    :param approved: What the teacher accepts
    :return: The shortfall, never negative
    """
    raw = charged - approved
    return Money.ZERO if raw.is_negative() else raw


def withdraw_decision(
    session: Session,
    claim: PaymentClaim,
    *,
    verified_by_account_id: uuid.UUID,
) -> dict[str, object] | None:
    """Undo a decided claim's decision, leaving it pending again [BR3.3].

    The prior decision is retained on ``previous_decision`` and every
    entry it produced is compensated, so the next decision is written
    against the balance as it stood before. A claim still pending is
    left as it is. Adds to the transaction and does not commit.

    :param session: The session to write through
    :param claim: The claim being re-decided
    :param verified_by_account_id: Who is correcting
    :return: The prior decision, or None when there was none
    """
    previous = _previous_decision(claim)
    if previous is None:
        return None
    _reverse_prior_entries(
        session, claim, verified_by_account_id=verified_by_account_id
    )
    claim.previous_decision = previous
    claim.status = _UNDECIDED
    return previous


def verify_claim_in_transaction(
    session: Session,
    claim: PaymentClaim,
    *,
    approved_amount: Money,
    shortfall_disposition: str | None,
    verified_by_account_id: uuid.UUID,
) -> VerificationOutcome:
    """Write one claim's approval and its entries, inside a caller's decision.

    **No race guard, no notification and no commit.** The caller has
    already won the right to decide -- a submission's decision claims
    the submission row -- and commits every child's claim together. A
    claim still carrying a decision is withdrawn first, so a correction
    compensates before it writes.

    :param session: The session to write through
    :param claim: The claim to decide
    :param approved_amount: What the teacher accepted for this claim
    :param shortfall_disposition: ``carried`` or ``waived``, required
        where the approval is below the period's charge and None where
        it is not
    :param verified_by_account_id: Who decided
    :return: The decided claim and the computed shortfall
    :raises ValidationError: The amount is negative, or the disposition
        is missing, unknown or not applicable
    """
    if approved_amount.is_negative():
        raise ValidationError(
            code="APPROVED_AMOUNT_NEGATIVE",
            message_key="fees.verification.amount_negative",
        )
    withdraw_decision(session, claim, verified_by_account_id=verified_by_account_id)

    period = claim.period
    derived = derive_for_enrollment(session, claim.enrollment_id)
    charged = derived.per_cycle.get(period, Money.ZERO)

    shortfall = shortfall_of(charged, approved_amount)
    _check_disposition(shortfall, shortfall_disposition)

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
    claim.rejection_reason = None
    claim.shortfall_disposition = shortfall_disposition
    claim.verified_by_account_id = verified_by_account_id
    claim.verified_at = dt.datetime.now(tz=dt.UTC)
    return VerificationOutcome(claim=claim, shortfall=shortfall)


def _check_disposition(shortfall: Money, shortfall_disposition: str | None) -> None:
    """Require a disposition exactly when something is left short [BR5.4].

    :param shortfall: What the approval leaves unpaid
    :param shortfall_disposition: ``carried``, ``waived`` or None
    :return: None
    :raises ValidationError: Missing where required, unknown, or
        supplied where nothing is short
    """
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


def _dispose_shortfalls(
    session: Session,
    claim: PaymentClaim,
    shortfalls: list[tuple[str, Money]],
    *,
    disposition: str | None,
    verified_by_account_id: uuid.UUID,
) -> None:
    """Carry or waive what each month is still short of, oldest first.

    A carry moves the month's shortfall into the month after it. When
    that month is itself short, what was carried into it moves on with
    its own shortfall, so the whole amount ends in one month rather than
    leaving part of it behind.

    :param session: The session to write through
    :param claim: The claim the entries belong to
    :param shortfalls: Each outstanding month and what it is short of
    :param disposition: ``carried`` or ``waived``
    :param verified_by_account_id: Who decided
    :return: None
    """
    carried_into: dict[str, Money] = {}
    for period, short in shortfalls:
        if disposition == "carried":
            moving = short + carried_into.get(period, Money.ZERO)
            if not moving.is_positive():
                continue
            receiver = str(Period.parse(period).next())
            append_carry_pair(
                session,
                enrollment_id=claim.enrollment_id,
                amount=moving,
                origin=period,
                receiver=receiver,
                payment_claim_id=claim.id,
                created_by_account_id=verified_by_account_id,
            )
            carried_into[receiver] = carried_into.get(receiver, Money.ZERO) + moving
        elif short.is_positive():
            append_entry(
                session,
                enrollment_id=claim.enrollment_id,
                period=period,
                kind="forgiveness",
                amount=short,
                payment_claim_id=claim.id,
                created_by_account_id=verified_by_account_id,
            )


def settle_claim_in_transaction(
    session: Session,
    claim: PaymentClaim,
    *,
    approved_amount: Money,
    shortfall_disposition: str | None,
    verified_by_account_id: uuid.UUID,
) -> VerificationOutcome:
    """Approve one child's share of a payment across every month they owe.

    **Oldest month first.** The approved amount pays each outstanding
    month up to what it owes, one ``receipt`` per month; what is left
    after every month is paid is a ``credit_grant`` on the claim's
    period. Each month still short then gets the teacher's disposition.
    For a child owing one month this writes exactly what
    :func:`verify_claim_in_transaction` writes.

    No race guard, no notification and no commit: the caller has won the
    decision on the submission and commits every child together. A claim
    still carrying a decision is withdrawn first.

    :param session: The session to write through
    :param claim: The child's claim
    :param approved_amount: What the allocation approved for this child
    :param shortfall_disposition: ``carried`` or ``waived`` when the
        approval leaves the child short, else None
    :param verified_by_account_id: Who decided
    :return: The decided claim and the child's total shortfall
    :raises ValidationError: The amount is negative, or the disposition
        is missing, unknown or not applicable
    """
    if approved_amount.is_negative():
        raise ValidationError(
            code="APPROVED_AMOUNT_NEGATIVE",
            message_key="fees.verification.amount_negative",
        )
    withdraw_decision(session, claim, verified_by_account_id=verified_by_account_id)

    per_cycle = derive_for_enrollment(session, claim.enrollment_id).per_cycle
    periods = sorted(p for p, owed in per_cycle.items() if owed.is_positive())
    settlement = settle_oldest_first(approved_amount, [per_cycle[p] for p in periods])
    shortfall = Money.sum(settlement.shortfalls)
    _check_disposition(shortfall, shortfall_disposition)

    for period, receipt in zip(periods, settlement.receipts, strict=True):
        if receipt.is_positive():
            append_entry(
                session,
                enrollment_id=claim.enrollment_id,
                period=period,
                kind="receipt",
                amount=receipt,
                payment_claim_id=claim.id,
                created_by_account_id=verified_by_account_id,
            )
    if settlement.excess.is_positive():
        append_entry(
            session,
            enrollment_id=claim.enrollment_id,
            period=claim.period,
            kind="credit_grant",
            amount=settlement.excess,
            payment_claim_id=claim.id,
            created_by_account_id=verified_by_account_id,
        )
    if shortfall.is_positive():
        _dispose_shortfalls(
            session,
            claim,
            list(zip(periods, settlement.shortfalls, strict=True)),
            disposition=shortfall_disposition,
            verified_by_account_id=verified_by_account_id,
        )

    claim.status = "approved_full" if shortfall.is_zero() else "approved_partial"
    claim.approved_amount = approved_amount
    claim.rejection_reason = None
    claim.shortfall_disposition = shortfall_disposition
    claim.verified_by_account_id = verified_by_account_id
    claim.verified_at = dt.datetime.now(tz=dt.UTC)
    return VerificationOutcome(claim=claim, shortfall=shortfall)


def reject_claim_in_transaction(
    session: Session,
    claim: PaymentClaim,
    *,
    verified_by_account_id: uuid.UUID,
    reason: str | None,
) -> PaymentClaim:
    """Write one claim's rejection, inside a caller's decision [BR5.6].

    No race guard, no notification and no commit, as for
    :func:`verify_claim_in_transaction`. A prior approval is withdrawn
    first, which reverses its entries.

    :param session: The session to write through
    :param claim: The claim to reject
    :param verified_by_account_id: Who rejected it
    :param reason: Why it was rejected; blank is stored as none
    :return: The rejected claim
    """
    withdraw_decision(session, claim, verified_by_account_id=verified_by_account_id)
    claim.status = "rejected"
    claim.rejection_reason = (reason or "").strip() or None
    claim.approved_amount = None
    claim.shortfall_disposition = None
    claim.verified_by_account_id = verified_by_account_id
    claim.verified_at = dt.datetime.now(tz=dt.UTC)
    return claim


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
    twice, which is a money error.

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
    previous = withdraw_decision(
        session, claim, verified_by_account_id=verified_by_account_id
    )
    outcome = verify_claim_in_transaction(
        session,
        claim,
        approved_amount=approved_amount,
        shortfall_disposition=shortfall_disposition,
        verified_by_account_id=verified_by_account_id,
    )

    partial = approved_amount < claim.claimed_amount
    _tell_the_seat(
        session,
        claim,
        kind=PAYMENT_PARTIAL if partial else PAYMENT_APPROVED,
        amount=approved_amount,
        replacing=previous is not None,
    )
    session.commit()
    return outcome


def reject_claim(
    session: Session,
    *,
    claim_id: uuid.UUID,
    verified_by_account_id: uuid.UUID,
    correcting: bool = False,
    reason: str | None = None,
) -> PaymentClaim:
    """Reject a claim, recording nothing as received [BR5.6].

    **No ledger entry of any kind is appended**, and the outstanding
    balance is unchanged. Rejecting a previously approved claim is a
    correction and reverses the entries that approval produced.

    :param session: The session to write through
    :param claim_id: The claim to reject
    :param verified_by_account_id: Who rejected it
    :param correcting: True when deliberately revising a decision
    :param reason: Why it was rejected; blank is stored as none
    :return: The rejected claim
    :raises ValidationError: No such claim
    :raises ConflictError: Already decided and not a declared correction
    """
    claim = _load(session, claim_id)
    _claim_the_decision(session, claim, correcting=correcting)
    previous = withdraw_decision(
        session, claim, verified_by_account_id=verified_by_account_id
    )
    reject_claim_in_transaction(
        session, claim, verified_by_account_id=verified_by_account_id, reason=reason
    )

    _tell_the_seat(
        session,
        claim,
        kind=PAYMENT_REJECTED,
        amount=claim.claimed_amount,
        replacing=previous is not None,
    )
    session.commit()
    return claim


def _tell_the_seat(
    session: Session,
    claim: PaymentClaim,
    *,
    kind: str,
    amount: Money,
    replacing: bool,
) -> None:
    """Put the decision in every accepted seat holder's inbox.

    Runs in the decision's transaction. The teacher's own "to verify"
    item for the claim is marked read, and a correction first removes the
    earlier decision's items, so the seat ends with one item showing the
    current outcome.

    :param session: The session the decision is written through
    :param claim: The decided claim
    :param kind: Which decision
    :param amount: What was approved, or what was claimed if rejected
    :param replacing: True when an earlier decision's items exist
    :return: None
    """
    # The teacher's "to verify" item is settled by the same decision, in
    # the same transaction: a decided claim is not one still waiting.
    mark_read_for_source(session, kind=CLAIM_TO_VERIFY, source_id=claim.id)
    if replacing:
        for earlier in (PAYMENT_APPROVED, PAYMENT_PARTIAL, PAYMENT_REJECTED):
            remove_for_source(session, kind=earlier, source_id=claim.id)
    recipients = seat_recipients(session, enrollment_id=claim.enrollment_id)
    if not recipients:
        return
    batch_name = session.scalars(
        sa.select(Batch.name)
        .join(Enrollment, Enrollment.batch_id == Batch.id)
        .where(Enrollment.id == claim.enrollment_id)
    ).one()
    deliver(
        session,
        account_ids=[r.account_id for r in recipients],
        kind=kind,
        batch_name=batch_name,
        now=dt.datetime.now(tz=dt.UTC),
        enrollment_id=claim.enrollment_id,
        period=claim.period,
        amount=amount,
        source_id=claim.id,
        child_names=child_names(recipients),
    )
