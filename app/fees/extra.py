"""Raising exam and other fees, and reading them [0020].

**Raising a fee is one transaction**: the fee, one charge per student
and each charge's ``charge`` entry commit together or not at all.

**Who is charged is the monthly rule's seats**, so a teacher never has
to wonder why one list differs from the other: every seat on the batch
whose student link is not ``declined`` and who has not left
(``inactive_from`` today or later, or never set). A pending seat is
charged, exactly as it is for a month [BR1.9]. The teacher may leave
students out, or give a student a different amount; zero is a real fee
of zero, which reads ``waived``.

**A resend is a replay, and the constraint makes it one.** The client
sends one ``client_mutation_id`` per fee it is raising and reuses it on
every resend; ``UNIQUE (created_by_account_id, client_mutation_id)``
decides with ``ON CONFLICT DO NOTHING``, and the loser reads the winner
back. A lookup alone would let two simultaneous resends both pass it.

**Every figure a reader sees is folded here**, from the fee's own
ledger, and each student's status comes from the same function the
monthly ledger uses, so "waived" means the same thing in both places.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.authz.lenses import Lens, TeacherLens
from app.db.models import Batch, Enrollment, Exam, ExtraFee, ExtraFeeCharge
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.errors.codes import NOT_AVAILABLE
from app.fees.extra_ledger import append_extra_entry, live_charge_entries
from app.fees.status import FeeStatus, status_from_entries
from app.local_time import bangladesh_today
from app.money import Money, derive
from app.teaching.roster import readable_enrollment

__all__ = [
    "RAISE_REPLAY_CONSTRAINT",
    "ExtraFeeSummary",
    "FeeDraft",
    "SeatFee",
    "StudentRow",
    "batch_extra_fees",
    "extra_fee_detail",
    "raise_extra_fee",
    "seat_extra_fees",
]

#: The constraint a raise inserts against, created by ``0020``.
RAISE_REPLAY_CONSTRAINT = "uq_extra_fee_account_mutation"

#: The longest name a fee may carry, as the column allows.
_LABEL_MAX = 80

ExtraFeePurpose = Literal["exam", "other"]


@dataclass(frozen=True, slots=True)
class FeeDraft:
    """What the teacher typed when raising a fee.

    :ivar purpose: ``exam`` or ``other``
    :ivar label: The name families see
    :ivar exam_id: The exam an exam fee is for, if linked
    :ivar amount: The per-student default
    :ivar due_on: When it is due
    :ivar seat_amounts: Students given a different amount, zero included
    :ivar excluded: Students left out of the fee
    :ivar client_mutation_id: The app's retry key, or None
    """

    purpose: str
    label: str
    exam_id: uuid.UUID | None
    amount: Money
    due_on: dt.date
    seat_amounts: Mapping[uuid.UUID, Money]
    excluded: frozenset[uuid.UUID]
    client_mutation_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class StudentRow:
    """One student under one fee, as the teacher sees it.

    :ivar enrollment_id: The seat
    :ivar display_name: The teacher-typed name
    :ivar charged: What the student was charged
    :ivar paid: What arrived against it
    :ivar owed: What is still owed, never negative
    :ivar status: ``paid``, ``partly_paid``, ``unpaid`` or ``waived``
    """

    enrollment_id: uuid.UUID
    display_name: str
    charged: Money
    paid: Money
    owed: Money
    status: FeeStatus


@dataclass(frozen=True, slots=True)
class ExtraFeeSummary:
    """One fee with its totals, for the teacher's list.

    :ivar extra_fee_id: The fee
    :ivar purpose: ``exam`` or ``other``
    :ivar label: The name families see
    :ivar exam_id: The linked exam, if any
    :ivar exam_title: That exam's title, if any
    :ivar amount: The per-student default it was raised with
    :ivar due_on: When it is due
    :ivar created_at: When it was raised
    :ivar student_count: How many students were charged
    :ivar paid_count: Students whose charge is paid
    :ivar waived_count: Students whose charge is waived
    :ivar owing_count: Students still owing something
    :ivar charged_total: Everything charged
    :ivar collected_total: Everything that arrived
    :ivar owed_total: Everything still owed
    """

    extra_fee_id: uuid.UUID
    purpose: ExtraFeePurpose
    label: str
    exam_id: uuid.UUID | None
    exam_title: str | None
    amount: Money
    due_on: dt.date
    created_at: dt.datetime
    student_count: int
    paid_count: int
    waived_count: int
    owing_count: int
    charged_total: Money
    collected_total: Money
    owed_total: Money


@dataclass(frozen=True, slots=True)
class SeatFee:
    """One extra fee as a student or guardian sees it.

    :ivar extra_fee_id: The fee
    :ivar purpose: ``exam`` or ``other``
    :ivar label: The name
    :ivar due_on: When it is due
    :ivar charged: What was charged
    :ivar paid: What arrived
    :ivar owed: What is still owed
    :ivar status: The server's status
    """

    extra_fee_id: uuid.UUID
    purpose: ExtraFeePurpose
    label: str
    due_on: dt.date
    charged: Money
    paid: Money
    owed: Money
    status: FeeStatus


def _refuse() -> AuthorizationError:
    """Build the shared refusal: an absent fee and another teacher's alike.

    :return: The refusal
    """
    return AuthorizationError(code=NOT_AVAILABLE, message_key="fees.not_available")


def _owned_batch(session: Session, *, lens: TeacherLens, batch_id: uuid.UUID) -> Batch:
    """Load a batch this lens owns, or refuse indistinguishably.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param batch_id: The batch
    :return: The batch
    :raises AuthorizationError: Not this lens's batch, or none at all
    """
    batch = session.scalars(
        sa.select(Batch).where(Batch.id == batch_id, Batch.owner_id == lens.owner_id)
    ).one_or_none()
    if batch is None:
        raise _refuse()
    return batch


def _chargeable_seats(
    session: Session, *, batch_id: uuid.UUID, today: dt.date
) -> list[Enrollment]:
    """Select the seats a fee raised today charges: the monthly rule's.

    :param session: The session to read through
    :param batch_id: The batch
    :param today: Bangladesh's date
    :return: The seats, by display name then id
    """
    return list(
        session.scalars(
            sa.select(Enrollment)
            .where(
                Enrollment.batch_id == batch_id,
                Enrollment.student_decision != "declined",
                sa.or_(
                    Enrollment.inactive_from.is_(None),
                    Enrollment.inactive_from >= today,
                ),
            )
            .order_by(Enrollment.display_name, Enrollment.id)
        )
    )


def _check(
    session: Session, draft: FeeDraft, *, batch: Batch, seats: list[Enrollment]
) -> str:
    """Refuse a fee that cannot be raised, and return its trimmed name.

    :param session: The session to read through
    :param draft: The teacher's form
    :param batch: The batch it is raised on
    :param seats: The seats it would charge
    :return: The label, trimmed
    :raises ValidationError: An unknown kind, a blank or long name, a
        negative amount, an exam that is not this batch's or is cancelled,
        an inactive batch, a named student who is not one of the seats,
        or no student left to charge
    """
    if draft.purpose not in ("exam", "other"):
        raise ValidationError(
            code="EXTRA_FEE_PURPOSE_UNKNOWN", message_key="fees.extra.kind_unknown"
        )
    label = draft.label.strip()
    if not label:
        raise ValidationError(
            code="EXTRA_FEE_LABEL_REQUIRED", message_key="fees.extra.label_required"
        )
    if len(label) > _LABEL_MAX:
        raise ValidationError(
            code="EXTRA_FEE_LABEL_TOO_LONG", message_key="fees.extra.label_too_long"
        )
    amounts = [draft.amount, *draft.seat_amounts.values()]
    if any(amount.is_negative() for amount in amounts):
        raise ValidationError(
            code="EXTRA_FEE_AMOUNT_NEGATIVE", message_key="fees.extra.amount_negative"
        )
    if not batch.active:
        raise ValidationError(
            code="EXTRA_FEE_BATCH_INACTIVE", message_key="fees.extra.batch_inactive"
        )
    if draft.exam_id is not None:
        if draft.purpose != "exam":
            raise ValidationError(
                code="EXTRA_FEE_EXAM_NOT_APPLICABLE",
                message_key="fees.extra.exam_not_applicable",
            )
        exam = session.get(Exam, draft.exam_id)
        if exam is None or exam.batch_id != batch.id or exam.cancelled_at is not None:
            raise ValidationError(
                code="EXTRA_FEE_EXAM_NOT_FOUND", message_key="fees.extra.exam_not_found"
            )
    seat_ids = {seat.id for seat in seats}
    named = set(draft.seat_amounts) | set(draft.excluded)
    if not named <= seat_ids:
        raise ValidationError(
            code="EXTRA_FEE_STUDENT_NOT_IN_BATCH",
            message_key="fees.extra.student_not_in_batch",
        )
    if not seat_ids - set(draft.excluded):
        raise ValidationError(
            code="EXTRA_FEE_NO_STUDENTS", message_key="fees.extra.no_students"
        )
    return label


def _same_fee(
    session: Session, prior: ExtraFee, draft: FeeDraft, *, batch_id: uuid.UUID
) -> bool:
    """Decide whether a resend describes the fee already raised.

    Compares what the teacher typed, after the same trimming, and the
    students charged and their amounts.

    :param session: The session to read through
    :param prior: The fee raised under the same key
    :param draft: The resend
    :param batch_id: The batch the resend names
    :return: True when it is the same fee
    """
    charges = session.scalars(
        sa.select(ExtraFeeCharge.enrollment_id).where(
            ExtraFeeCharge.extra_fee_id == prior.id
        )
    ).all()
    return (
        prior.batch_id == batch_id
        and prior.purpose == draft.purpose
        and prior.label == draft.label.strip()
        and prior.exam_id == draft.exam_id
        and prior.amount == draft.amount
        and prior.due_on == draft.due_on
        and not set(charges) & set(draft.excluded)
    )


def _prior(
    session: Session, *, account_id: uuid.UUID, key: uuid.UUID | None
) -> ExtraFee | None:
    """Find this ACCOUNT's fee under a retry key.

    :param session: The session to read through
    :param account_id: The raising account
    :param key: The retry key
    :return: The fee, or None (always, without a key)
    """
    if key is None:
        return None
    return session.scalars(
        sa.select(ExtraFee).where(
            ExtraFee.created_by_account_id == account_id,
            ExtraFee.client_mutation_id == key,
        )
    ).one_or_none()


def _replayed(
    session: Session, prior: ExtraFee, draft: FeeDraft, *, batch_id: uuid.UUID
) -> ExtraFee:
    """Answer a resend with the fee it repeats, writing nothing.

    :param session: The session to read through
    :param prior: The fee raised under the same key
    :param draft: The resend
    :param batch_id: The batch the resend names
    :return: The fee, unchanged
    :raises ConflictError: The resend describes a different fee
    """
    if not _same_fee(session, prior, draft, batch_id=batch_id):
        raise ConflictError(
            code="MUTATION_ID_ALREADY_USED",
            message_key="fees.extra.mutation_id_already_used",
        )
    return prior


def raise_extra_fee(
    session: Session,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
    draft: FeeDraft,
    today: dt.date | None = None,
) -> ExtraFee:
    """Raise one fee on a batch and charge its students, in one transaction.

    Commits.

    :param session: The session to write through
    :param lens: The teacher lens
    :param batch_id: The batch
    :param draft: The teacher's form
    :param today: Bangladesh's date; the real clock by default
    :return: The fee, new or replayed
    :raises AuthorizationError: The batch is absent or not this lens's
    :raises ValidationError: The fee cannot be raised as typed
    :raises ConflictError: The retry key already names a different fee
    """
    batch = _owned_batch(session, lens=lens, batch_id=batch_id)
    prior = _prior(session, account_id=lens.account_id, key=draft.client_mutation_id)
    if prior is not None:
        return _replayed(session, prior, draft, batch_id=batch_id)

    day = today or bangladesh_today()
    seats = _chargeable_seats(session, batch_id=batch_id, today=day)
    label = _check(session, draft, batch=batch, seats=seats)

    now = dt.datetime.now(tz=dt.UTC)
    inserted: uuid.UUID | None = session.execute(
        pg_insert(ExtraFee)
        .values(
            id=uuid.uuid4(),
            batch_id=batch_id,
            purpose=draft.purpose,
            label=label,
            exam_id=draft.exam_id,
            amount=draft.amount,
            due_on=draft.due_on,
            created_by_account_id=lens.account_id,
            client_mutation_id=draft.client_mutation_id,
            created_at=now,
        )
        .on_conflict_do_nothing(constraint=RAISE_REPLAY_CONSTRAINT)
        .returning(ExtraFee.id)
    ).scalar_one_or_none()
    if inserted is None:
        # A concurrent resend won. READ COMMITTED gives this statement a
        # fresh snapshot after the winner's commit, so it is visible.
        session.rollback()
        winner = _prior(
            session, account_id=lens.account_id, key=draft.client_mutation_id
        )
        if winner is None:
            raise ConflictError(
                code="MUTATION_ID_ALREADY_USED",
                message_key="fees.extra.mutation_id_already_used",
            )
        return _replayed(session, winner, draft, batch_id=batch_id)

    for seat in seats:
        if seat.id in draft.excluded:
            continue
        charge_id: uuid.UUID | None = session.execute(
            pg_insert(ExtraFeeCharge)
            .values(
                id=uuid.uuid4(),
                extra_fee_id=inserted,
                enrollment_id=seat.id,
                created_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_extra_fee_charge_fee_enrollment")
            .returning(ExtraFeeCharge.id)
        ).scalar_one_or_none()
        if charge_id is None:
            continue
        append_extra_entry(
            session,
            charge_id=charge_id,
            kind="charge",
            amount=draft.seat_amounts.get(seat.id, draft.amount),
            created_by_account_id=lens.account_id,
        )
    session.commit()
    return session.get_one(ExtraFee, inserted)


def _rows_for(
    session: Session, fee_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[StudentRow]]:
    """Fold every charge of several fees, two statements in all.

    :param session: The session to read through
    :param fee_ids: The fees
    :return: Fee id to its students' rows, by display name then id
    """
    found: dict[uuid.UUID, list[StudentRow]] = {fee_id: [] for fee_id in fee_ids}
    if not fee_ids:
        return found
    pairs = session.execute(
        sa.select(ExtraFeeCharge, Enrollment)
        .join(Enrollment, Enrollment.id == ExtraFeeCharge.enrollment_id)
        .where(ExtraFeeCharge.extra_fee_id.in_(fee_ids))
        .order_by(Enrollment.display_name, Enrollment.id)
    ).all()
    entries = live_charge_entries(session, [charge.id for charge, _seat in pairs])
    for charge, seat in pairs:
        own = entries[charge.id]
        totals = derive(own)
        found[charge.extra_fee_id].append(
            StudentRow(
                enrollment_id=seat.id,
                display_name=seat.display_name,
                charged=totals.total_charged,
                paid=totals.total_receipt,
                owed=totals.total_outstanding,
                status=status_from_entries(own, str(charge.id)),
            )
        )
    return found


def _summary(
    fee: ExtraFee, rows: list[StudentRow], exam_title: str | None
) -> ExtraFeeSummary:
    """Total one fee's rows.

    :param fee: The fee
    :param rows: Its students' rows
    :param exam_title: The linked exam's title, if any
    :return: The summary
    """
    return ExtraFeeSummary(
        extra_fee_id=fee.id,
        purpose="exam" if fee.purpose == "exam" else "other",
        label=fee.label,
        exam_id=fee.exam_id,
        exam_title=exam_title,
        amount=fee.amount,
        due_on=fee.due_on,
        created_at=fee.created_at,
        student_count=len(rows),
        paid_count=sum(1 for row in rows if row.status == "paid"),
        waived_count=sum(1 for row in rows if row.status == "waived"),
        owing_count=sum(1 for row in rows if row.owed.is_positive()),
        charged_total=Money.sum([row.charged for row in rows]),
        collected_total=Money.sum([row.paid for row in rows]),
        owed_total=Money.sum([row.owed for row in rows]),
    )


def _exam_titles(session: Session, fees: list[ExtraFee]) -> dict[uuid.UUID, str]:
    """Title every linked exam in one statement.

    :param session: The session to read through
    :param fees: The fees
    :return: Exam id to title
    """
    wanted = {fee.exam_id for fee in fees if fee.exam_id is not None}
    if not wanted:
        return {}
    return dict(
        session.execute(
            sa.select(Exam.id, Exam.title).where(Exam.id.in_(wanted))
        ).tuples()
    )


def batch_extra_fees(
    session: Session, *, lens: TeacherLens, batch_id: uuid.UUID
) -> list[ExtraFeeSummary]:
    """Every fee raised on one of this teacher's batches, newest first.

    :param session: The session to read through
    :param lens: The teacher lens
    :param batch_id: The batch
    :return: Each fee with its totals
    :raises AuthorizationError: The batch is absent or not this lens's
    """
    _owned_batch(session, lens=lens, batch_id=batch_id)
    fees = list(
        session.scalars(
            sa.select(ExtraFee)
            .where(ExtraFee.batch_id == batch_id)
            .order_by(ExtraFee.created_at.desc(), ExtraFee.id)
        )
    )
    rows = _rows_for(session, [fee.id for fee in fees])
    titles = _exam_titles(session, fees)
    return [
        _summary(fee, rows[fee.id], titles.get(fee.exam_id) if fee.exam_id else None)
        for fee in fees
    ]


def extra_fee_detail(
    session: Session, *, lens: TeacherLens, extra_fee_id: uuid.UUID
) -> tuple[ExtraFeeSummary, list[StudentRow]]:
    """One fee on this teacher's batches, with every student's row.

    :param session: The session to read through
    :param lens: The teacher lens
    :param extra_fee_id: The fee
    :return: Its summary and students
    :raises AuthorizationError: The fee is absent or not this lens's
    """
    fee = session.scalars(
        sa.select(ExtraFee)
        .join(Batch, Batch.id == ExtraFee.batch_id)
        .where(ExtraFee.id == extra_fee_id, Batch.owner_id == lens.owner_id)
    ).one_or_none()
    if fee is None:
        raise _refuse()
    rows = _rows_for(session, [fee.id])[fee.id]
    titles = _exam_titles(session, [fee])
    return _summary(fee, rows, titles.get(fee.exam_id) if fee.exam_id else None), rows


def seat_extra_fees(
    session: Session, *, lens: Lens, enrollment_id: uuid.UUID
) -> list[SeatFee]:
    """Every extra fee one seat was charged, as its family reads them.

    Reach is the family rule: a student reaches only their own accepted
    seat and a guardian only an accepted child, checked by the same
    function every family read uses.

    :param session: The session to read through
    :param lens: The student or guardian lens
    :param enrollment_id: The seat
    :return: The fees, soonest due first
    :raises AuthorizationError: The seat is not this lens's
    """
    readable_enrollment(session, lens=lens, enrollment_id=enrollment_id)
    pairs = session.execute(
        sa.select(ExtraFeeCharge, ExtraFee)
        .join(ExtraFee, ExtraFee.id == ExtraFeeCharge.extra_fee_id)
        .where(ExtraFeeCharge.enrollment_id == enrollment_id)
        .order_by(ExtraFee.due_on, ExtraFee.created_at, ExtraFee.id)
    ).all()
    entries = live_charge_entries(session, [charge.id for charge, _fee in pairs])
    fees: list[SeatFee] = []
    for charge, fee in pairs:
        own = entries[charge.id]
        totals = derive(own)
        fees.append(
            SeatFee(
                extra_fee_id=fee.id,
                purpose="exam" if fee.purpose == "exam" else "other",
                label=fee.label,
                due_on=fee.due_on,
                charged=totals.total_charged,
                paid=totals.total_receipt,
                owed=totals.total_outstanding,
                status=status_from_entries(own, str(charge.id)),
            )
        )
    return fees
