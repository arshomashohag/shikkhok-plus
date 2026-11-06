"""A teacher records money they received by hand [BR5.3, BR5.4, BR5.5].

**A record is a claim the teacher submits and approves in one
transaction.** It is written as a ``payment_submission`` with one
``payment_claim``, both carrying the teacher as submitter and decider,
and decided through :func:`settle_claim_in_transaction` -- the same
function that decides a family's payment. Every reader of the ledger
(balances, the month strip, collections, earnings, the payment history)
therefore sees a cash record exactly as it sees an approved family
payment, because it IS one; nothing downstream needs to know the path.

**The shortfall rule is the verification rule** [BR5.3, BR5.4]. What the
seat owes is its outstanding across every unpaid month, settled oldest
first. Recording less than that requires an explicit ``carried`` or
``waived``, and a disposition on a payment that leaves nothing short is
refused rather than ignored -- :func:`check_disposition` decides both,
and it runs **before** anything is written. More than is owed becomes
credit; a balance is never negative [BR4.2].

**One transaction** [BR5.5]: the submission, the claim, its decision,
every ledger entry and the family's inbox items commit together or not
at all.

**Replay-safe on the family path's key.** ``UNIQUE
(submitted_by_account_id, client_mutation_id)`` already exists on
``payment_submission`` and is per account, so the teacher's retry key
cannot collide with a family's. The insert is ``ON CONFLICT DO NOTHING``
and the loser reads the winner back, exactly as
:mod:`app.fees.submissions` does; a resend describing a different
payment is a ``ConflictError``.

**No "to verify" item.** The teacher received the money and recorded
it; there is nothing left for them to check. The family is told with
:data:`PAYMENT_RECORDED`, whose copy says the teacher recorded money
received, because "your payment was approved" would describe a report
the family never made.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.db.models import Batch, Enrollment, PaymentClaim, PaymentSubmission
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.errors.codes import NOT_AVAILABLE
from app.fees.claims import CASH, MOBILE_SERVICES, record_claim
from app.fees.purposes import owed_for_target, resolve_target
from app.fees.submissions import EARLIEST_DAYS_BEFORE_JOINING, REPLAY_CONSTRAINT
from app.fees.verification import (
    check_disposition,
    settle_claim_in_transaction,
    shortfall_of,
)
from app.local_time import DHAKA, bangladesh_today
from app.money import Money
from app.notifications.inbox import PAYMENT_RECORDED, deliver
from app.notifications.recipients import child_names, seat_recipients

__all__ = ["CHANNELS", "ReceivedPayment", "record_received_payment"]

#: Where money recorded by hand can have moved: cash in hand, or a
#: mobile service a family sent straight to the teacher's own number.
CHANNELS: tuple[str, ...] = (CASH, *MOBILE_SERVICES)


@dataclass(frozen=True, slots=True)
class ReceivedPayment:
    """What the teacher typed when recording money received.

    :ivar amount: What was received; strictly positive
    :ivar channel: ``cash``, or one of the mobile services
    :ivar reference: A transaction id or receipt number, if any
    :ivar note: Shown to the family with the record, if any
    :ivar paid_on: The day the money changed hands; today when None
    :ivar shortfall_disposition: ``carried`` or ``waived`` exactly when
        the amount is below what the seat owes, else None
    :ivar client_mutation_id: The client's retry key, or None
    :ivar purpose: ``monthly`` or ``extra``; None pays the months
    :ivar extra_fee_id: The fee, when the purpose is ``extra``
    """

    amount: Money
    channel: str = CASH
    reference: str | None = None
    note: str | None = None
    paid_on: dt.date | None = None
    shortfall_disposition: str | None = None
    client_mutation_id: uuid.UUID | None = None
    purpose: str | None = None
    extra_fee_id: uuid.UUID | None = None


def _blank_to_none(value: str | None) -> str | None:
    """Treat a blank field as absent.

    :param value: The text as typed
    :return: The trimmed text, or None when empty
    """
    trimmed = (value or "").strip()
    return trimmed or None


def _refuse() -> AuthorizationError:
    """Build the shared refusal for a seat this lens does not reach.

    :return: The refusal; an absent seat and another teacher's read alike
    """
    return AuthorizationError(code=NOT_AVAILABLE, message_key="fees.not_available")


def _owned_seat(
    session: Session, *, lens: TeacherLens, enrollment_id: uuid.UUID
) -> Enrollment:
    """Lock a seat on one of this teacher's batches, or refuse.

    **Locked, not just read.** Two records on one seat at once would
    each settle against the same outstanding and receipt the same month
    twice; the row lock makes the second wait for the first's commit and
    then derive the balance the first left.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param enrollment_id: The seat
    :return: The seat
    :raises AuthorizationError: It is absent or not this lens's
    """
    seat = session.scalars(
        sa.select(Enrollment)
        .join(Batch, Batch.id == Enrollment.batch_id)
        .where(Enrollment.id == enrollment_id, Batch.owner_id == lens.owner_id)
        .with_for_update(of=Enrollment)
    ).one_or_none()
    if seat is None:
        raise _refuse()
    return seat


def _check(payment: ReceivedPayment, *, seat: Enrollment, today: dt.date) -> None:
    """Refuse a record that could not have happened.

    :param payment: The teacher's form
    :param seat: The seat
    :param today: Bangladesh's date
    :return: None
    :raises ValidationError: The amount is not positive, the channel is
        unknown, or the date is in the future or before the seat's window
    """
    if not payment.amount.is_positive():
        raise ValidationError(
            code="PAYMENT_AMOUNT_NOT_POSITIVE",
            message_key="fees.payment.amount_not_positive",
        )
    if payment.channel not in CHANNELS:
        raise ValidationError(
            code="CLAIM_CHANNEL_UNKNOWN", message_key="fees.claim.channel_unknown"
        )
    paid_on = payment.paid_on or today
    if paid_on > today:
        raise ValidationError(
            code="PAYMENT_DATE_IN_FUTURE", message_key="fees.payment.date_in_future"
        )
    joined = seat.joined_on or seat.created_at.astimezone(DHAKA).date()
    if paid_on < joined - dt.timedelta(days=EARLIEST_DAYS_BEFORE_JOINING):
        raise ValidationError(
            code="PAYMENT_DATE_TOO_EARLY", message_key="fees.payment.date_too_early"
        )


def _snapshot(channel: str) -> dict[str, object]:
    """Describe where the money went, in the shape the review reads.

    :param channel: ``cash`` or a mobile service's name
    :return: The destination snapshot
    """
    if channel == CASH:
        return {"kind": CASH}
    return {"kind": "mobile", "provider": channel}


def _mutation_id_spent() -> ConflictError:
    """Build the refusal for a retry key already naming another payment.

    :return: The conflict
    """
    return ConflictError(
        code="MUTATION_ID_ALREADY_USED",
        message_key="fees.payment.mutation_id_already_used",
    )


def _prior(
    session: Session, *, account_id: uuid.UUID, client_mutation_id: uuid.UUID | None
) -> PaymentSubmission | None:
    """Find this account's payment under a retry key.

    Scoped by both columns of the constraint, so another account's
    identical key is never found.

    :param session: The session to read through
    :param account_id: The recording teacher's account
    :param client_mutation_id: The retry key, or None
    :return: The recorded payment, or None (always, without a key)
    """
    if client_mutation_id is None:
        return None
    return session.scalars(
        sa.select(PaymentSubmission).where(
            PaymentSubmission.submitted_by_account_id == account_id,
            PaymentSubmission.client_mutation_id == client_mutation_id,
        )
    ).one_or_none()


def _replayed(
    session: Session,
    prior: PaymentSubmission,
    *,
    enrollment_id: uuid.UUID,
    payment: ReceivedPayment,
) -> PaymentSubmission:
    """Answer a resend with the payment it repeats, writing nothing.

    Compares what the teacher typed and nothing a later correction can
    change: the decision and its disposition belong to the record and
    may since have been revised, which must not turn a resend into a
    conflict. An omitted date matches any, so a resend crossing
    midnight is still a resend.

    :param session: The session to read through
    :param prior: The payment recorded under the same key
    :param enrollment_id: The seat the resend names
    :param payment: The resend
    :return: The recorded payment, unchanged
    :raises ConflictError: The resend describes a different payment
    """
    seats = set(
        session.scalars(
            sa.select(PaymentClaim.enrollment_id).where(
                PaymentClaim.payment_submission_id == prior.id
            )
        )
    )
    same = (
        seats == {enrollment_id}
        and prior.destination_snapshot == _snapshot(payment.channel)
        and prior.total_amount == payment.amount
        and (payment.paid_on is None or prior.paid_on == payment.paid_on)
        and prior.transaction_id == _blank_to_none(payment.reference)
    )
    if not same:
        raise _mutation_id_spent()
    return prior


def record_received_payment(
    session: Session,
    *,
    lens: TeacherLens,
    enrollment_id: uuid.UUID,
    payment: ReceivedPayment,
    today: dt.date | None = None,
) -> PaymentSubmission:
    """Record money received for one seat, approved, in one transaction.

    Commits, and tells the seat's accepted student and guardian.

    :param session: The session to write through
    :param lens: The recording teacher's lens
    :param enrollment_id: The seat
    :param payment: What was received, how, and the carry-or-waive
    :param today: Bangladesh's date; the real clock by default
    :return: The approved payment
    :raises AuthorizationError: The seat is absent or not this lens's
    :raises ValidationError: The amount is not positive, the channel is
        unknown, the date is out of range, or the disposition is missing
        where one is required, unknown, or supplied where none applies
    :raises ConflictError: The retry key already names a different payment
    """
    seat = _owned_seat(session, lens=lens, enrollment_id=enrollment_id)

    # 1. REPLAY, fast path, answered before re-validating: the original
    #    was valid when it was recorded, and a resend after the month
    #    was paid must return it rather than be refused.
    prior = _prior(
        session,
        account_id=lens.account_id,
        client_mutation_id=payment.client_mutation_id,
    )
    if prior is not None:
        session.rollback()
        return _replayed(session, prior, enrollment_id=enrollment_id, payment=payment)

    day = today or bangladesh_today()
    _check(payment, seat=seat, today=day)
    target = resolve_target(
        session,
        purpose=payment.purpose,
        extra_fee_id=payment.extra_fee_id,
        batch_id=seat.batch_id,
    )
    owed = owed_for_target(session, target=target, enrollment_id=seat.id)
    if target.extra_fee_id is not None and payment.amount > owed:
        # An extra fee holds no credit [0020]: refused before anything
        # is written, rather than half-recorded and rolled back.
        raise ValidationError(
            code="EXTRA_FEE_OVERPAID", message_key="fees.extra.overpaid"
        )
    disposition = payment.shortfall_disposition
    check_disposition(shortfall_of(owed, payment.amount), disposition)

    # 2. THE GUARANTEE. Everything above only read (and locked the
    #    seat), so a conflict here leaves nothing of this request to
    #    undo. NULL keys never conflict.
    now = dt.datetime.now(tz=dt.UTC)
    reference = _blank_to_none(payment.reference)
    inserted: uuid.UUID | None = session.execute(
        pg_insert(PaymentSubmission)
        .values(
            id=uuid.uuid4(),
            batch_id=seat.batch_id,
            payment_method_id=None,
            destination_snapshot=_snapshot(payment.channel),
            total_amount=payment.amount,
            paid_on=payment.paid_on or day,
            transaction_id=reference,
            from_account=None,
            payer_note=None,
            submitted_by_account_id=lens.account_id,
            submitted_at=now,
            status="pending",
            client_mutation_id=payment.client_mutation_id,
            purpose=target.purpose,
            extra_fee_id=target.extra_fee_id,
            requested_purpose=target.purpose,
            requested_extra_fee_id=target.extra_fee_id,
        )
        .on_conflict_do_nothing(constraint=REPLAY_CONSTRAINT)
        .returning(PaymentSubmission.id)
    ).scalar_one_or_none()
    if inserted is None:
        session.rollback()
        winner = _prior(
            session,
            account_id=lens.account_id,
            client_mutation_id=payment.client_mutation_id,
        )
        if winner is None:
            raise _mutation_id_spent()
        return _replayed(session, winner, enrollment_id=enrollment_id, payment=payment)

    submission = session.get_one(PaymentSubmission, inserted)
    claim = record_claim(
        session,
        enrollment_id=seat.id,
        submitted_by_account_id=lens.account_id,
        claimed_amount=payment.amount,
        target=target,
        channel=payment.channel,
        transaction_id=reference,
        submission_id=submission.id,
        today=day,
    )
    settle_claim_in_transaction(
        session,
        claim,
        approved_amount=payment.amount,
        shortfall_disposition=disposition,
        verified_by_account_id=lens.account_id,
    )
    submission.status = "approved"
    submission.decision_note = _blank_to_none(payment.note)
    submission.decided_by_account_id = lens.account_id
    submission.decided_at = now

    _tell_the_seat(session, submission, claim, seat)
    session.commit()
    return submission


def _tell_the_seat(
    session: Session,
    submission: PaymentSubmission,
    claim: PaymentClaim,
    seat: Enrollment,
) -> None:
    """Tell the seat's accepted student and guardian what was recorded.

    The item's source is the submission, which the inbox detail already
    resolves for a family's decided payment. Adds to the transaction and
    does not commit.

    :param session: The session the record is written through
    :param submission: The recorded payment
    :param claim: Its one claim, for the period shown
    :param seat: The seat
    :return: None
    """
    recipients = seat_recipients(session, enrollment_id=seat.id)
    if not recipients:
        return
    batch_name = session.scalars(
        sa.select(Batch.name).where(Batch.id == seat.batch_id)
    ).one()
    deliver(
        session,
        account_ids=[r.account_id for r in recipients],
        kind=PAYMENT_RECORDED,
        batch_name=batch_name,
        now=dt.datetime.now(tz=dt.UTC),
        enrollment_id=seat.id,
        period=claim.period,
        amount=submission.total_amount,
        source_id=submission.id,
        preview=submission.decision_note,
        child_names=child_names(recipients),
    )
