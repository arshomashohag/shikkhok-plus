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
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens, StudentLens
from app.db.models import (
    Batch,
    Enrollment,
    PaymentClaim,
    PaymentMethod,
    PaymentSubmission,
)
from app.errors import AuthorizationError, ValidationError
from app.fees.balances import derive_for_enrollment
from app.fees.claims import CASH, record_claim
from app.local_time import DHAKA, bangladesh_today
from app.money import Money, allocate_payment
from app.notifications.inbox import CLAIM_TO_VERIFY, deliver
from app.notifications.recipients import teacher_recipient
from app.teaching.roster import readable_enrollment

__all__ = [
    "EARLIEST_DAYS_BEFORE_JOINING",
    "FamilyLens",
    "OwedChild",
    "PaymentDraft",
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
    """

    enrollment_ids: tuple[uuid.UUID, ...]
    payment_method_id: uuid.UUID | None
    cash: bool
    amount: Money
    paid_on: dt.date
    transaction_id: str | None
    from_account: str | None
    note: str | None

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
    return sorted(seats, key=lambda seat: (seat.display_name, str(seat.id)))


def owed_children(
    session: Session, *, lens: FamilyLens, enrollment_ids: Sequence[uuid.UUID]
) -> list[OwedChild]:
    """Read what each covered child owes, in child order.

    :param session: The session to read through
    :param lens: The student or guardian lens
    :param enrollment_ids: The children named
    :return: Each child's seat and outstanding
    :raises AuthorizationError: A seat is out of reach
    :raises ValidationError: None named, or they span two batches
    """
    return [
        OwedChild(
            seat=seat,
            owed=derive_for_enrollment(session, seat.id).total_outstanding,
        )
        for seat in _covered_seats(session, lens=lens, enrollment_ids=enrollment_ids)
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
    """
    children = owed_children(session, lens=lens, enrollment_ids=draft.enrollment_ids)
    batch_id = children[0].seat.batch_id
    method = _offered_method(session, batch_id=batch_id, draft=draft)
    draft.check_reference(None if method is None else method.kind)
    day = today or bangladesh_today()
    draft.check_paid_on(
        today=day, earliest_joined=min(_joined(child.seat) for child in children)
    )
    draft.check_amount()

    transaction_id = _blank_to_none(draft.transaction_id)
    submission = PaymentSubmission(
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
    )
    session.add(submission)
    session.flush()

    channel = CASH if method is None else (method.provider or method.kind)
    shares = _shares(draft.amount, [child.owed for child in children])
    claims = [
        record_claim(
            session,
            enrollment_id=child.seat.id,
            submitted_by_account_id=lens.account_id,
            claimed_amount=share,
            channel=channel,
            transaction_id=transaction_id,
            submission_id=submission.id,
            today=day,
        )
        for child, share in zip(children, shares, strict=True)
    ]
    _tell_the_teacher(session, submission, claims, [c.seat for c in children])
    session.commit()
    return submission


def _tell_the_teacher(
    session: Session,
    submission: PaymentSubmission,
    claims: list[PaymentClaim],
    seats: list[Enrollment],
) -> None:
    """Put one item for the whole submission in the teacher's inbox.

    The item points at the first child's claim, which the current
    verification and detail paths read. Adds to the transaction and
    does not commit.

    :param session: The session the submission is written through
    :param submission: The new submission
    :param claims: Its claims, in child order
    :param seats: The covered seats, in child order
    :return: None
    """
    teacher = teacher_recipient(session, batch_id=submission.batch_id)
    if teacher is None:
        return
    batch = session.get(Batch, submission.batch_id)
    deliver(
        session,
        account_ids=[teacher],
        kind=CLAIM_TO_VERIFY,
        batch_name=batch.name if batch is not None else "",
        now=dt.datetime.now(tz=dt.UTC),
        enrollment_id=seats[0].id,
        period=claims[0].period,
        amount=submission.total_amount,
        source_id=claims[0].id,
        child_names={teacher: ", ".join(seat.display_name for seat in seats)},
    )
