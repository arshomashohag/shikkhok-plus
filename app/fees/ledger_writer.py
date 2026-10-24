"""Writing ledger rows: the persistence half of the arithmetic.

**Calls ``app.money``'s ``carry_forward`` and ``apply_credit``;
implements neither.** The module returns a carry as an inseparable pair
from one call, so a one-sided carry is unrepresentable in the
*arithmetic*. This module is the PERSISTENCE counterpart: the two rows
must also be committed together, which is a transaction property the
fold cannot enforce [BR3.1].

Computed, and the reason the pairing is not optional: carrying 1000 into
a second 1000 charge reads **2000.00** owed two-sided and **3000.00**
one-sided, and the gap grows with every period.

**Rows are append-only** [BR3.3]. Nothing here updates an ``amount``, a
``kind``, a ``period`` or an ``enrollment_id``, and nothing deletes. The
only column ever written after insert is ``superseded_by_id``, which
records that a correction compensated an entry -- and it drives what a
teacher SEES rather than what the balance IS, because a compensating
pair sums to zero and the fold reads both rows.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import Enrollment, LedgerEntryRow
from app.fees.balances import derive_for_enrollment
from app.money import Money, apply_credit, carry_forward

__all__ = [
    "append_carry_pair",
    "append_entry",
    "apply_available_credit",
    "supersede",
    "void_accrued_cycles",
]


def append_entry(
    session: Session,
    *,
    enrollment_id: uuid.UUID,
    period: str,
    kind: str,
    amount: Money,
    payment_claim_id: uuid.UUID | None = None,
    created_by_account_id: uuid.UUID | None = None,
) -> LedgerEntryRow:
    """Append one entry. Does **not** commit.

    The caller owns the transaction boundary, because the entries a
    decision produces must commit together with that decision [BR5.5]
    and a commit here would split them.

    ``created_by_account_id`` is NULL for entries the generation job
    created, which is the honest value: nobody did.

    :param session: The session to write through
    :param enrollment_id: The seat the entry is against
    :param period: The period the entry sits in, as ``YYYY-MM``
    :param kind: One of the seven closed kinds
    :param amount: A non-negative amount
    :param payment_claim_id: The verification that produced this entry
    :param created_by_account_id: Who caused it, or None for the job
    :return: The appended row, flushed so its id is available
    """
    row = LedgerEntryRow(
        enrollment_id=enrollment_id,
        period=period,
        kind=kind,
        amount=amount,
        payment_claim_id=payment_claim_id,
        created_by_account_id=created_by_account_id,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(row)
    session.flush()
    return row


def append_carry_pair(
    session: Session,
    *,
    enrollment_id: uuid.UUID,
    amount: Money,
    origin: str,
    receiver: str,
    payment_claim_id: uuid.UUID | None = None,
    created_by_account_id: uuid.UUID | None = None,
) -> tuple[LedgerEntryRow, LedgerEntryRow]:
    """Append both halves of a carry, or neither.

    **The pair comes from ``app.money.carry_forward``**, which returns
    both entries from one call and refuses an amount exceeding what the
    origin owes [BR3.2]. The origin balance is read here and always
    supplied: D3 can always supply it, since every carry the system has
    is produced from a computed balance.

    Does not commit. Both rows are added in one flush, so a caller that
    commits once writes both or neither -- which is what makes
    ``sum(carry_forward) == sum(carried_out)`` hold structurally rather
    than by anyone remembering.

    :param session: The session to write through
    :param enrollment_id: The seat
    :param amount: The balance to carry
    :param origin: The period being relieved
    :param receiver: The period being charged
    :param payment_claim_id: The verification that produced the pair
    :param created_by_account_id: Who decided
    :return: The ``carried_out`` row, then the ``carry_forward`` row
    :raises MoneyValidationError: The amount exceeds the origin's
        balance, which would manufacture debt
    """
    origin_balance = derive_for_enrollment(session, enrollment_id).per_cycle.get(
        origin, Money.ZERO
    )
    out_value, in_value = carry_forward(
        amount,
        origin=origin,
        receiver=receiver,
        origin_balance=origin_balance,
    )

    out_row = append_entry(
        session,
        enrollment_id=enrollment_id,
        period=out_value.period,
        kind=out_value.kind.value,
        amount=out_value.amount,
        payment_claim_id=payment_claim_id,
        created_by_account_id=created_by_account_id,
    )
    in_row = append_entry(
        session,
        enrollment_id=enrollment_id,
        period=in_value.period,
        kind=in_value.kind.value,
        amount=in_value.amount,
        payment_claim_id=payment_claim_id,
        created_by_account_id=created_by_account_id,
    )
    return out_row, in_row


def apply_available_credit(
    session: Session,
    *,
    enrollment_id: uuid.UUID,
    period: str,
) -> LedgerEntryRow | None:
    """Spend held credit against what a period owes, if any.

    **The amount is COMPUTED, never supplied** [BR4.4]. It comes from
    ``app.money.apply_credit`` as ``min(available, owed)``, which is why
    over-application is unrepresentable rather than refused -- no caller
    may pass an amount of their own choosing, and in particular none may
    be read from a request body.

    **Called after the charge is appended** [BR4.5]. Applying before it
    computes ``min(available, 0)`` and spends nothing, so the credit is
    never used.

    :param session: The session to write through
    :param enrollment_id: The seat
    :param period: The period to apply against
    :return: The ``credit_apply`` row, or None where nothing applied
    """
    derived = derive_for_enrollment(session, enrollment_id)
    available = derived.available_credit
    owed = derived.per_cycle.get(period, Money.ZERO)

    applied = apply_credit(available, owed)
    if not applied.is_positive():
        return None

    return append_entry(
        session,
        enrollment_id=enrollment_id,
        period=period,
        kind="credit_apply",
        amount=applied,
    )


def void_accrued_cycles(
    session: Session,
    *,
    enrollment_id: uuid.UUID,
    created_by_account_id: uuid.UUID | None = None,
) -> list[LedgerEntryRow]:
    """Relieve every outstanding balance by a reversal entry [BR1.6].

    **A reversal, never a deletion.** The original ``charge`` rows stay
    and a ``forgiveness`` is appended for what each period still owes,
    which takes the balance to zero while leaving the audit trail FR9.2
    requires intact.

    ``forgiveness`` is the correct kind rather than an eighth: it is the
    term the identity already carries for an obligation relieved without
    cash, and ADR-002 is explicit that a new kind is for a quantity no
    existing one expresses.

    **Forgives the OUTSTANDING balance, not the charge.** A seat charged
    1500 with 500 already received is forgiven 1000; forgiving the
    charge would record a relief that never happened and take the
    balance below zero. Idempotent for the same reason -- a second call
    finds nothing outstanding and writes nothing, which matters because
    the daily job reaches every declined seat again tomorrow.

    **The STUDENT link is re-read here and the guardian link is not**
    [BR1.7]. The caller has already decided to void; this function
    refuses anyway, because the asymmetry is the rule most likely to be
    got wrong in this unit and has already produced one defect in this
    project on the presentation side. A guardian's refusal to oversee an
    enrollment does not cancel the student's obligation, and making that
    mechanical here means a future caller cannot reach the wrong
    outcome by passing the wrong seat. Checking the condition where the
    write happens is the same reasoning the lens query uses: a check
    above a query is one the next query can bypass.

    Commits, because this is a complete operation rather than a step in
    a larger decision.

    :param session: The session to write through
    :param enrollment_id: The seat whose accrued cycles are voided
    :param created_by_account_id: Who declined, if a person did
    :return: The forgiveness rows appended, possibly none
    """
    decision = session.execute(
        sa.select(Enrollment.student_decision).where(Enrollment.id == enrollment_id)
    ).scalar_one_or_none()
    if decision != "declined":
        # Not a refusal to report: there is simply nothing to void. A
        # guardian decline reaches here and must leave the ledger
        # untouched.
        return []

    per_cycle = derive_for_enrollment(session, enrollment_id).per_cycle
    written: list[LedgerEntryRow] = []

    for period in sorted(per_cycle):
        owed = per_cycle[period]
        if not owed.is_positive():
            continue
        written.append(
            append_entry(
                session,
                enrollment_id=enrollment_id,
                period=period,
                kind="forgiveness",
                amount=owed,
                created_by_account_id=created_by_account_id,
            )
        )

    session.commit()
    return written


def supersede(
    session: Session,
    *,
    original: LedgerEntryRow,
    compensation: LedgerEntryRow,
) -> None:
    """Mark an entry as corrected by a compensating one [BR3.3].

    The only column ever written to a ledger row after insert. Does not
    commit: a correction's entries and its claim decision move together.

    :param session: The session to write through
    :param original: The entry that was wrong
    :param compensation: The entry that compensates it
    :return: None
    """
    original.superseded_by_id = compensation.id
    session.flush()
