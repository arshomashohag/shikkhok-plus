"""Submitting one payment for one or several children [F1-F5].

**One submission per payment, one pending claim per child.** What the
payer sent is held once on ``payment_submission``; the ledger stays
enrollment-level, so each child gets a claim carrying a provisional
share the teacher's decision later replaces.

**Reach is the family rule, checked per seat** through
``readable_enrollment``: a student reaches only their own accepted seat
and a guardian only an accepted child. Every seat must sit in one batch,
and the method must be a live one of that batch's owner.

**Children are ordered by display name, then id**, everywhere a split
or a list is made, so the provisional split and the teacher's review
agree on who is "last".

**A resend is a replay, and the unique constraint is what makes it one**
[PA-DB-1]. The app sends one ``client_mutation_id`` per payment draft
and reuses it on every resend, because a submit can commit and then
lose its response on a flaky connection. ``UNIQUE
(submitted_by_account_id, client_mutation_id)`` decides: the insert is
``ON CONFLICT DO NOTHING`` against it and the loser reads the winner
back. The lookup before validation is a fast path only -- two
simultaneous resends both pass it, and only the constraint stops the
second -- so a test blinds it and replays anyway.

The replay is answered **before** the payment is re-validated. The
original was valid when it was recorded; a resend arriving after the
teacher retired the method, or after the teacher approved it, must
return that payment rather than be refused into the family sending it
again. Scoped by account, it can only ever return the caller's own
submission, so answering it first discloses nothing.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens, StudentLens
from app.db.models import (
    Batch,
    Enrollment,
    PaymentClaim,
    PaymentMethod,
    PaymentSubmission,
)
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.fees.claims import CASH, record_claim
from app.fees.purposes import MONTHLY, Target, owed_for_target, resolve_target
from app.local_time import DHAKA, bangladesh_today
from app.money import Money, allocate_payment
from app.notifications.inbox import CLAIM_TO_VERIFY, deliver
from app.notifications.recipients import teacher_recipients
from app.teaching.roster import readable_enrollment

__all__ = [
    "EARLIEST_DAYS_BEFORE_JOINING",
    "REPLAY_CONSTRAINT",
    "FamilyLens",
    "OwedChild",
    "PaymentDraft",
    "child_order",
    "lens_reaching",
    "owed_children",
    "owed_together",
    "submit_payment",
]

type FamilyLens = StudentLens | GuardianLens

#: How far before the earliest covered seat's joining a payment may be dated.
EARLIEST_DAYS_BEFORE_JOINING = 60

_MOBILE = "mobile"
_BANK = "bank"

#: The constraint the replay insert names. Created by migration ``0015``
#: and declared on the model; a rename there is a failed insert here
#: rather than a replay that silently stops matching.
REPLAY_CONSTRAINT = "uq_payment_submission_account_mutation"


def _invalid(*, code: str, message_key: str) -> ValidationError:
    """Build a submission refusal.

    :param code: The machine code
    :param message_key: The client string key
    :return: The refusal
    """
    return ValidationError(code=code, message_key=message_key)


def _blank_to_none(value: str | None) -> str | None:
    """Treat a blank field as absent.

    :param value: The text as typed
    :return: The trimmed text, or None when empty
    """
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


@dataclass(frozen=True, slots=True)
class PaymentDraft:
    """What the payer typed on the form, before it is checked.

    :ivar enrollment_ids: The children covered
    :ivar payment_method_id: The teacher's method paid to, or None
    :ivar cash: Whether the money was handed over in person
    :ivar amount: The whole amount sent
    :ivar paid_on: The day the money moved
    :ivar transaction_id: The mobile reference, if any
    :ivar from_account: The paying bank account, if any
    :ivar note: Free text for the teacher
    :ivar client_mutation_id: The app's retry key, or None from a build
        that sends none
    :ivar purpose: ``monthly`` or ``extra``, or None from a build that
        sends none, which pays the months as every payment did before
    :ivar extra_fee_id: The fee, when the purpose is ``extra``
    """

    enrollment_ids: tuple[uuid.UUID, ...]
    payment_method_id: uuid.UUID | None
    cash: bool
    amount: Money
    paid_on: dt.date
    transaction_id: str | None
    from_account: str | None
    note: str | None
    client_mutation_id: uuid.UUID | None = None
    purpose: str | None = None
    extra_fee_id: uuid.UUID | None = None

    def check_amount(self) -> None:
        """Refuse a payment of nothing.

        :raises ValidationError: The amount is not strictly positive
        """
        if not self.amount.is_positive():
            raise _invalid(
                code="PAYMENT_AMOUNT_NOT_POSITIVE",
                message_key="fees.payment.amount_not_positive",
            )

    def check_reference(self, kind: str | None) -> None:
        """Require exactly the reference the method's kind takes.

        A mobile payment quotes a transaction id, a bank payment names
        the paying account, and cash in hand quotes neither.

        :param kind: ``mobile``, ``bank``, or None for cash
        :raises ValidationError: The reference does not match the kind
        """
        has_transaction = _blank_to_none(self.transaction_id) is not None
        has_account = _blank_to_none(self.from_account) is not None
        expected = (kind == _MOBILE, kind == _BANK)
        if (has_transaction, has_account) != expected:
            raise _invalid(
                code="PAYMENT_REFERENCE_MISMATCH",
                message_key="fees.payment.reference_mismatch",
            )

    def check_paid_on(self, *, today: dt.date, earliest_joined: dt.date) -> None:
        """Keep the payment date between joining's window and today.

        :param today: Bangladesh's date
        :param earliest_joined: The earliest covered seat's joining date
        :raises ValidationError: The date is after today or too early
        """
        if self.paid_on > today:
            raise _invalid(
                code="PAYMENT_DATE_IN_FUTURE", message_key="fees.payment.date_in_future"
            )
        window = dt.timedelta(days=EARLIEST_DAYS_BEFORE_JOINING)
        if self.paid_on < earliest_joined - window:
            raise _invalid(
                code="PAYMENT_DATE_TOO_EARLY", message_key="fees.payment.date_too_early"
            )


@dataclass(frozen=True, slots=True)
class OwedChild:
    """One covered child and what their seat owes now.

    :ivar seat: The enrollment
    :ivar owed: The seat's outstanding, never negative
    """

    seat: Enrollment
    owed: Money


def lens_reaching(
    session: Session,
    lenses: Sequence[FamilyLens],
    enrollment_id: uuid.UUID | None,
) -> FamilyLens:
    """Choose which of an account's family lenses reaches a seat.

    An account may hold both a student and a guardian lens. The seat
    decides which one applies; the reach check itself still runs later,
    so a lens that reaches nothing is refused there.

    :param session: The session to read through
    :param lenses: The account's student and guardian lenses
    :param enrollment_id: The first covered seat, if any
    :return: The lens reaching that seat, else the first lens
    """
    if enrollment_id is not None:
        for lens in lenses:
            try:
                readable_enrollment(session, lens=lens, enrollment_id=enrollment_id)
            except AuthorizationError:
                continue
            return lens
    return lenses[0]


def child_order(seat: Enrollment) -> tuple[str, str]:
    """Give the key every list of a payment's children is sorted by.

    Display name, then id, so the payer's split, the teacher's review
    and the allocation all agree on who is first and who is last.

    :param seat: A covered seat
    :return: The sort key
    """
    return seat.display_name, str(seat.id)


def _covered_seats(
    session: Session, *, lens: FamilyLens, enrollment_ids: Sequence[uuid.UUID]
) -> list[Enrollment]:
    """Load the covered seats in child order, refusing any out of reach.

    :param session: The session to read through
    :param lens: The student or guardian lens
    :param enrollment_ids: The children named
    :return: The seats, by display name then id
    :raises AuthorizationError: A seat is not this lens's accepted seat
    :raises ValidationError: None named, or they span two batches
    """
    unique = list(dict.fromkeys(enrollment_ids))
    if not unique:
        raise _invalid(
            code="PAYMENT_CHILDREN_REQUIRED",
            message_key="fees.payment.children_required",
        )
    seats = [
        readable_enrollment(session, lens=lens, enrollment_id=seat_id)
        for seat_id in unique
    ]
    if len({seat.batch_id for seat in seats}) > 1:
        raise _invalid(
            code="PAYMENT_CHILDREN_ACROSS_BATCHES",
            message_key="fees.payment.children_across_batches",
        )
    return sorted(seats, key=child_order)


def owed_children(
    session: Session,
    *,
    lens: FamilyLens,
    enrollment_ids: Sequence[uuid.UUID],
    purpose: str | None = None,
    extra_fee_id: uuid.UUID | None = None,
) -> list[OwedChild]:
    """Read what each covered child owes for one purpose, in child order.

    :param session: The session to read through
    :param lens: The student or guardian lens
    :param enrollment_ids: The children named
    :param purpose: ``monthly`` or ``extra``; None means the months
    :param extra_fee_id: The fee, when ``extra``
    :return: Each child's seat and outstanding
    :raises AuthorizationError: A seat is out of reach
    :raises ValidationError: None named, they span two batches, the
        purpose names no fee of their batch, or a child was not charged it
    """
    return _owed_for(
        session,
        lens=lens,
        enrollment_ids=enrollment_ids,
        purpose=purpose,
        extra_fee_id=extra_fee_id,
    )[1]


def _owed_for(
    session: Session,
    *,
    lens: FamilyLens,
    enrollment_ids: Sequence[uuid.UUID],
    purpose: str | None,
    extra_fee_id: uuid.UUID | None,
) -> tuple[Target, list[OwedChild]]:
    """Check the purpose against the covered seats and read what each owes.

    :param session: The session to read through
    :param lens: The student or guardian lens
    :param enrollment_ids: The children named
    :param purpose: ``monthly``, ``extra`` or None
    :param extra_fee_id: The fee, if any
    :return: The checked target, and each child's seat and outstanding
    :raises AuthorizationError: A seat is out of reach
    :raises ValidationError: As :func:`owed_children`
    """
    seats = _covered_seats(session, lens=lens, enrollment_ids=enrollment_ids)
    target = resolve_target(
        session,
        purpose=purpose,
        extra_fee_id=extra_fee_id,
        batch_id=seats[0].batch_id,
    )
    return target, [
        OwedChild(
            seat=seat,
            owed=owed_for_target(session, target=target, enrollment_id=seat.id),
        )
        for seat in seats
    ]


def owed_together(
    session: Session, *, lens: FamilyLens, enrollment_ids: Sequence[uuid.UUID]
) -> tuple[Money, list[Money]]:
    """Total what the covered children owe, for the form's owed line.

    :param session: The session to read through
    :param lens: The student or guardian lens
    :param enrollment_ids: The children named
    :return: The total, and each child's figure in child order
    :raises AuthorizationError: A seat is out of reach
    :raises ValidationError: None named, or they span two batches
    """
    owed = [
        child.owed
        for child in owed_children(session, lens=lens, enrollment_ids=enrollment_ids)
    ]
    return Money.sum(owed), owed


def _offered_method(
    session: Session, *, batch_id: uuid.UUID, draft: PaymentDraft
) -> PaymentMethod | None:
    """Resolve the method paid to, or None for cash in hand.

    :param session: The session to read through
    :param batch_id: The batch every covered seat sits in
    :param draft: The payer's form
    :return: The live method of the batch's owner, or None for cash
    :raises ValidationError: Neither or both of method and cash, or the
        method is absent, retired or another owner's
    """
    if draft.cash == (draft.payment_method_id is not None):
        raise _invalid(
            code="PAYMENT_METHOD_NOT_OFFERED",
            message_key="fees.payment.method_not_offered",
        )
    if draft.cash:
        return None
    method = session.scalars(
        sa.select(PaymentMethod)
        .join(Batch, Batch.owner_id == PaymentMethod.owner_id)
        .where(
            Batch.id == batch_id,
            PaymentMethod.id == draft.payment_method_id,
            PaymentMethod.retired_at.is_(None),
        )
    ).one_or_none()
    if method is None:
        raise _invalid(
            code="PAYMENT_METHOD_NOT_OFFERED",
            message_key="fees.payment.method_not_offered",
        )
    return method


def _snapshot(method: PaymentMethod | None) -> dict[str, object]:
    """Copy the destination as the family was shown it.

    :param method: The method, or None for cash
    :return: The method's shown fields, or the cash marker
    """
    if method is None:
        return {"kind": CASH}
    return {
        "method_id": str(method.id),
        "kind": method.kind,
        "provider": method.provider,
        "mobile_number": method.mobile_number,
        "account_number": method.account_number,
        "account_name": method.account_name,
        "branch_name": method.branch_name,
        "note": method.note,
    }


def _joined(seat: Enrollment) -> dt.date:
    """Give the day a seat started, falling back to its creation.

    :param seat: The enrollment
    :return: Its joining date in Bangladesh
    """
    return seat.joined_on or seat.created_at.astimezone(DHAKA).date()


def _shares(amount: Money, owed: list[Money]) -> tuple[Money, ...]:
    """Split the amount provisionally across the children.

    A shortfall is carried by the last child and an excess credited to
    them; with one child or an exact payment no choice applies.

    :param amount: The whole amount sent
    :param owed: Each child's outstanding, in child order
    :return: Each child's share, in child order
    """
    total = Money.sum(owed)
    several = len(owed) > 1
    last = len(owed) - 1
    short = amount < total
    over = total < amount
    return allocate_payment(
        amount,
        owed,
        disposition="carried" if short else None,
        bearer_index=last if short and several else None,
        credit_index=last if over and several else None,
    ).approved


def submit_payment(
    session: Session,
    *,
    lens: FamilyLens,
    draft: PaymentDraft,
    today: dt.date | None = None,
) -> PaymentSubmission:
    """Record one payment and a pending claim per child it covers.

    Commits, and puts one item in the teacher's inbox.

    :param session: The session to write through
    :param lens: The student or guardian lens
    :param draft: The payer's form
    :param today: Bangladesh's date; the real clock by default
    :return: The pending submission
    :raises AuthorizationError: A seat is not this lens's accepted seat
    :raises ValidationError: The children span batches, the method is
        not offered, the reference does not match, the date is out of
        range, or the amount is not positive
    :raises ConflictError: The draft's ``client_mutation_id`` already
        names a different payment from this account
    """
    # 1. REPLAY, fast path. Not the guarantee -- see step 2.
    prior = _fast_path_prior(session, account_id=lens.account_id, draft=draft)
    if prior is not None:
        return _replayed(session, prior, draft)

    target, children = _owed_for(
        session,
        lens=lens,
        enrollment_ids=draft.enrollment_ids,
        purpose=draft.purpose,
        extra_fee_id=draft.extra_fee_id,
    )
    batch_id = children[0].seat.batch_id
    method = _offered_method(session, batch_id=batch_id, draft=draft)
    draft.check_reference(None if method is None else method.kind)
    day = today or bangladesh_today()
    draft.check_paid_on(
        today=day, earliest_joined=min(_joined(child.seat) for child in children)
    )
    draft.check_amount()

    transaction_id = _blank_to_none(draft.transaction_id)

    # 2. THE GUARANTEE. Everything above only read, so a conflict here
    #    leaves nothing of this request to undo. A concurrent resend
    #    blocks on the winner's uncommitted row, and on its commit gets
    #    no row back; READ COMMITTED gives the next statement a fresh
    #    snapshot, so the read-back sees the committed winner. NULL keys
    #    never conflict, so a build sending none inserts as before.
    inserted: uuid.UUID | None = session.execute(
        pg_insert(PaymentSubmission)
        .values(
            id=uuid.uuid4(),
            batch_id=batch_id,
            payment_method_id=None if method is None else method.id,
            destination_snapshot=_snapshot(method),
            total_amount=draft.amount,
            paid_on=draft.paid_on,
            transaction_id=transaction_id,
            from_account=_blank_to_none(draft.from_account),
            payer_note=_blank_to_none(draft.note),
            submitted_by_account_id=lens.account_id,
            submitted_at=dt.datetime.now(tz=dt.UTC),
            status="pending",
            client_mutation_id=draft.client_mutation_id,
            purpose=target.purpose,
            extra_fee_id=target.extra_fee_id,
            requested_purpose=target.purpose,
            requested_extra_fee_id=target.extra_fee_id,
        )
        .on_conflict_do_nothing(constraint=REPLAY_CONSTRAINT)
        .returning(PaymentSubmission.id)
    ).scalar_one_or_none()

    if inserted is None:
        winner = (
            None
            if draft.client_mutation_id is None
            else _prior_submission(
                session,
                account_id=lens.account_id,
                client_mutation_id=draft.client_mutation_id,
            )
        )
        if winner is None:
            # Unreachable for a NULL key, which never conflicts; for a
            # real one, the winner was committed and then removed (its
            # batch deleted) between the two statements. Not a payment
            # to return, and not one to record blind.
            raise _mutation_id_spent()
        return _replayed(session, winner, draft)

    submission = session.get_one(PaymentSubmission, inserted)

    channel = CASH if method is None else (method.provider or method.kind)
    shares = _shares(draft.amount, [child.owed for child in children])
    claims = [
        record_claim(
            session,
            enrollment_id=child.seat.id,
            submitted_by_account_id=lens.account_id,
            claimed_amount=share,
            channel=channel,
            target=target,
            transaction_id=transaction_id,
            submission_id=submission.id,
            today=day,
        )
        for child, share in zip(children, shares, strict=True)
    ]
    _tell_the_teacher(session, submission, claims[0], [c.seat for c in children])
    session.commit()
    return submission


def _mutation_id_spent() -> ConflictError:
    """Build the refusal for a retry key already naming another payment.

    The code is the one the queued teaching writes use for the same
    semantic; the message key is the payment's own, because the
    teaching string tells the person to reload a class.

    :return: The conflict
    """
    return ConflictError(
        code="MUTATION_ID_ALREADY_USED",
        message_key="fees.payment.mutation_id_already_used",
    )


def _fast_path_prior(
    session: Session, *, account_id: uuid.UUID, draft: PaymentDraft
) -> PaymentSubmission | None:
    """Look a resend up before doing any of the payment's work.

    A separate function from the read-back after a conflicted insert
    only so a test can blind THIS lookup and leave that one working,
    which is how it proves the constraint rather than the lookup is
    what stops a second payment.

    :param session: The session to read through
    :param account_id: The submitting account
    :param draft: The payer's form
    :return: The recorded submission, or None (always, without a key)
    """
    if draft.client_mutation_id is None:
        return None
    return _prior_submission(
        session, account_id=account_id, client_mutation_id=draft.client_mutation_id
    )


def _prior_submission(
    session: Session, *, account_id: uuid.UUID, client_mutation_id: uuid.UUID
) -> PaymentSubmission | None:
    """Find this ACCOUNT's submission under a retry key.

    **Scoped by both columns of the constraint.** A lookup on the key
    alone would find another account's submission and return it -- a
    silent success that discloses another family's payment.

    :param session: The session to read through
    :param account_id: The submitting account
    :param client_mutation_id: The app's retry key
    :return: The submission, or None
    """
    return session.scalars(
        sa.select(PaymentSubmission).where(
            PaymentSubmission.submitted_by_account_id == account_id,
            PaymentSubmission.client_mutation_id == client_mutation_id,
        )
    ).one_or_none()


def _same_payment(
    session: Session, prior: PaymentSubmission, draft: PaymentDraft
) -> bool:
    """Decide whether a resend describes the payment already recorded.

    Compared **as stored**, after the same blank-to-None normalisation
    the original went through, so a resend is not refused for a
    trailing space the first send also had. The destination is read
    from the snapshot rather than ``payment_method_id``, which becomes
    NULL if the method is later deleted.

    :param session: The session to read the claims through
    :param prior: The recorded submission
    :param draft: The resend
    :return: True when every field the payer typed matches
    """
    snapshot = prior.destination_snapshot
    if draft.cash:
        same_destination = (
            snapshot.get("kind") == CASH and draft.payment_method_id is None
        )
    else:
        same_destination = draft.payment_method_id is not None and snapshot.get(
            "method_id"
        ) == str(draft.payment_method_id)
    children = set(
        session.scalars(
            sa.select(PaymentClaim.enrollment_id).where(
                PaymentClaim.payment_submission_id == prior.id
            )
        ).all()
    )
    asked = (
        (MONTHLY.purpose, None)
        if draft.purpose in (None, MONTHLY.purpose)
        else (draft.purpose, draft.extra_fee_id)
    )
    return (
        same_destination
        and (prior.requested_purpose, prior.requested_extra_fee_id) == asked
        and children == set(draft.enrollment_ids)
        and prior.total_amount == draft.amount
        and prior.paid_on == draft.paid_on
        and prior.transaction_id == _blank_to_none(draft.transaction_id)
        and prior.from_account == _blank_to_none(draft.from_account)
        and prior.payer_note == _blank_to_none(draft.note)
    )


def _replayed(
    session: Session, prior: PaymentSubmission, draft: PaymentDraft
) -> PaymentSubmission:
    """Answer a resend with the submission it repeats, writing nothing.

    :param session: The session to read through
    :param prior: The submission recorded under the same key
    :param draft: The resend
    :return: The recorded submission, unchanged
    :raises ConflictError: The resend describes a different payment
    """
    if not _same_payment(session, prior, draft):
        raise _mutation_id_spent()
    return prior


def _tell_the_teacher(
    session: Session,
    submission: PaymentSubmission,
    first_claim: PaymentClaim,
    seats: list[Enrollment],
) -> None:
    """Put one item for the whole submission in the teacher's inbox.

    The item's source is the submission, which the review and the
    inbox detail both resolve. Adds to the transaction and does not
    commit.

    :param session: The session the submission is written through
    :param submission: The new submission
    :param first_claim: The first child's claim, for the period shown
    :param seats: The covered seats, in child order
    :return: None
    """
    teachers = teacher_recipients(session, batch_id=submission.batch_id)
    if not teachers:
        return
    batch = session.get(Batch, submission.batch_id)
    deliver(
        session,
        account_ids=teachers,
        kind=CLAIM_TO_VERIFY,
        batch_name=batch.name if batch is not None else "",
        now=dt.datetime.now(tz=dt.UTC),
        enrollment_id=seats[0].id,
        period=first_claim.period,
        amount=submission.total_amount,
        source_id=submission.id,
        child_names=dict.fromkeys(
            teachers, ", ".join(seat.display_name for seat in seats)
        ),
    )
