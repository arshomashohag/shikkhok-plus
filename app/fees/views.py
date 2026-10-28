"""Lens-scoped reads: what each viewer may see, and nothing else.

**The lens is the scoping value, not a guard** [TC-11, D-2]. Every
function here takes a lens and derives its query from the value inside
it, so a caller cannot compile a scoped query without one.

**D3 adds no row-level-security policy, so these scope checks and the
adversarial probes against them ARE the mechanism** [NFR14.36]. The
built policy is on ``profile``, where ``account_id`` IS the subject; a
fee cycle's authorization is a path -- an accepted student link, an
accepted guardian link, or ownership of the batch -- which is the
three-branch join ``app.authz.resolve`` already performs. Encoding it
into a ``USING`` clause would make two implementations of one rule.

**Every pre-authorization refusal is the shared ``NOT_AVAILABLE``.** A
pair such as ``FEE_CYCLE_NOT_FOUND`` / ``FEE_CYCLE_NOT_YOURS`` is an
existence oracle even though each code reads as good practice alone: a
prober reads the difference and enumerates which ids are real. One code
covers both "there is no such thing" and "it is not yours", which is
why it is named for what the caller may do rather than for what the
server found.

**Responses carry DECISIONS, not inputs to decisions** [TC-9, D-31].
Every row here reports a server-computed status; none reports a balance
for a client to compare.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens, Lens, StudentLens, TeacherLens
from app.db.models import Batch, Enrollment, FeeCycle, LedgerEntryRow, PaymentClaim
from app.errors import AuthorizationError
from app.errors.codes import NOT_AVAILABLE
from app.fees.balances import derive_for_enrollment
from app.fees.claims import CHANNELS
from app.fees.status import (
    CLAIM_STATUS_VALUES,
    DISPOSITION_VALUES,
    ClaimStatus,
    FeeStatus,
    ShortfallDisposition,
    fee_status,
    status_from_entries,
)
from app.money import LedgerEntry, LedgerEntryKind, Money, derive

__all__ = [
    "ClaimDetail",
    "FeeCycleRow",
    "PaymentDestination",
    "RosterFeeRow",
    "assert_claim_is_verifiable",
    "batch_fee_overview",
    "claim_detail",
    "claim_status",
    "enrollment_fee_history",
    "payment_destination",
]


def _refuse() -> AuthorizationError:
    """Build the one refusal every scope check raises.

    A function rather than a constant so each raise site gets its own
    exception instance, and so there is exactly one place the code and
    message key are chosen.

    :return: The shared refusal
    """
    return AuthorizationError(
        code=NOT_AVAILABLE,
        message_key="fees.not_available",
    )


def claim_status(stored: str) -> ClaimStatus:
    """Narrow a stored status onto the closed set, checking it.

    **A real check rather than a cast, and mypy agrees it is one.**
    The column is a database enum and the ORM types it ``str``, so the
    crossing has to happen somewhere; a ``cast`` would assert the
    property while this proves it -- the membership test against the
    typed tuple narrows the value, so no cast is needed at all. A
    value outside the set means the enum was widened by a migration
    without the contract following, which is a bug the client would
    otherwise meet as an unrenderable status.

    :param stored: The value read from the column
    :return: The same value, narrowed
    :raises ValueError: The stored value is outside the closed set
    """
    if stored not in CLAIM_STATUS_VALUES:
        raise ValueError(
            f"{stored!r} is not a claim status. The database enum and "
            "app.fees.status.CLAIM_STATUS_VALUES have diverged."
        )
    return stored


def _disposition(stored: str | None) -> ShortfallDisposition | None:
    """Narrow a stored disposition onto the closed set, checking it.

    :param stored: The value read from the column, or None
    :return: The same value, narrowed, or None
    :raises ValueError: The stored value is outside the closed set
    """
    if stored is None:
        return None
    if stored not in DISPOSITION_VALUES:
        raise ValueError(
            f"{stored!r} is not a shortfall disposition. The database "
            "enum and the contract have diverged."
        )
    return stored


@dataclass(frozen=True, slots=True)
class RosterFeeRow:
    """One seat's fee position, as its teacher sees it.

    Carries the server-computed status and **no collection number**: the
    teacher's payment destination appears in exactly one response and
    this is not it [BR6.4, NFR14.33].

    :ivar enrollment_id: The teacher-facing key, never an account id
    :ivar display_name: The teacher-typed name
    :ivar outstanding: What this seat still owes across every period
    :ivar current_period: The latest generated period, or None
    :ivar current_status: That period's status, or None
    :ivar due_date: That period's due date, or None
    """

    enrollment_id: uuid.UUID
    display_name: str
    outstanding: Money
    current_period: str | None
    current_status: FeeStatus | None
    due_date: dt.date | None


@dataclass(frozen=True, slots=True)
class FeeCycleRow:
    """One period's cycle, for any lens entitled to read it.

    :ivar period: The period, as ``YYYY-MM``
    :ivar due_date: The clamped due date
    :ivar charged: What was charged for this period
    :ivar outstanding: What is still owed for it, floored at zero
    :ivar status: The server-computed status
    """

    period: str
    due_date: dt.date
    charged: Money
    outstanding: Money
    status: FeeStatus


@dataclass(frozen=True, slots=True)
class ClaimDetail:
    """One claim and its decision, as its submitter sees it.

    ``previous_decision`` is carried deliberately: a corrected
    verification is visible to the teacher **and** to that student and
    guardian, never hidden from either party [BR5.7, FR9.2].

    :ivar claim_id: The claim
    :ivar period: The period it resolved to at submission
    :ivar claimed_amount: What the claimant said they paid
    :ivar approved_amount: What the teacher accepted, or None
    :ivar status: One of the four server-set values
    :ivar shortfall_disposition: Carried or waived, where one applies
    :ivar channel: Which service the money moved through
    :ivar submitted_at: When it was submitted
    :ivar verified_at: When it was decided, or None
    :ivar previous_decision: The prior decision, on a correction
    """

    claim_id: uuid.UUID
    period: str
    claimed_amount: Money
    approved_amount: Money | None
    status: ClaimStatus
    shortfall_disposition: ShortfallDisposition | None
    channel: str
    submitted_at: dt.datetime
    verified_at: dt.datetime | None
    previous_decision: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class PaymentDestination:
    """Where to send a payment, and through what.

    **Returned as a whole object or not at all** [NFR14.34]. Where the
    teacher set no collection number the caller receives ``None`` and
    the screen omits the destination step entirely, rather than
    rendering a field with a null in it -- a null invites a client-side
    placeholder, and an absent object leaves nothing to render.

    :ivar collection_number: Where payments are sent
    :ivar collection_channel: Which service that number belongs to
    :ivar channels: The channel set, server-supplied [BR6.5]
    """

    collection_number: str
    collection_channel: str | None
    channels: tuple[str, ...]


def _owned_batch(session: Session, *, lens: TeacherLens, batch_id: uuid.UUID) -> Batch:
    """Load a batch this teacher owns, or refuse indistinguishably.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param batch_id: The batch
    :return: The batch
    :raises AuthorizationError: It is not this lens's batch, or there is
        no such batch -- the same refusal either way
    """
    batch = session.scalars(
        sa.select(Batch).where(Batch.id == batch_id, Batch.owner_id == lens.owner_id)
    ).one_or_none()
    if batch is None:
        raise _refuse()
    return batch


def _readable_enrollment(
    session: Session,
    *,
    lens: Lens,
    enrollment_id: uuid.UUID,
) -> Enrollment:
    """Load an enrollment this lens may read, or refuse.

    The three branches are the three paths authorization can take, and
    each re-reads the **accepted** predicate D1 exists to enforce
    [BR1.1, ADR-014]: naming an account on a link is not that person's
    agreement, and a teacher who mistyped one digit must not hand a
    stranger a lens over a child's records.

    A ``declined`` guardian link reaches no fee view even though the
    money is untouched [BR1.7]: the asymmetry withdraws the LENS and
    leaves the obligation standing.

    :param session: The session to read through
    :param lens: The viewer's lens
    :param enrollment_id: The seat
    :return: The enrollment
    :raises AuthorizationError: No path grants this lens that seat
    """
    record = session.get(Enrollment, enrollment_id)
    if record is None:
        raise _refuse()

    if isinstance(lens, TeacherLens):
        owned = session.scalars(
            sa.select(Batch.id).where(
                Batch.id == record.batch_id, Batch.owner_id == lens.owner_id
            )
        ).one_or_none()
        if owned is None:
            raise _refuse()
        return record

    if isinstance(lens, StudentLens):
        if (
            record.student_account_id == lens.account_id
            and record.student_decision == "accepted"
        ):
            return record
        raise _refuse()

    if isinstance(lens, GuardianLens):
        if (
            record.guardian_account_id == lens.account_id
            and record.guardian_decision == "accepted"
        ):
            return record
        raise _refuse()

    raise _refuse()


def batch_fee_overview(
    session: Session,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
) -> list[RosterFeeRow]:
    """List every seat's fee position on one of this teacher's batches.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param batch_id: The batch
    :return: One row per seat, ordered as the roster is
    :raises AuthorizationError: The batch is not this lens's
    """
    _owned_batch(session, lens=lens, batch_id=batch_id)

    seats = list(
        session.scalars(
            sa.select(Enrollment)
            .where(Enrollment.batch_id == batch_id)
            .order_by(Enrollment.created_at, Enrollment.id)
        )
    )
    if not seats:
        return []

    # **A CONSTANT number of statements, however many seats**
    # [NFR20.16, NFR20.17]. Two reads for the whole batch, then the
    # fold per enrollment in Python over rows already in hand.
    #
    # The per-seat version this replaces cost THREE statements each --
    # one fold for the balance, a second inside the status computation,
    # and a cycle lookup -- measured at 8 statements for 2 seats and 77
    # for 25. D2 left the roster's fee column open deliberately and
    # NFR20.17 is explicit that D3 must not close it with a query per
    # seat; `tests/fees/test_query_count.py` asserts the property
    # rather than a literal count, so a correct change that moves the
    # number does not retire the check.
    seat_ids = [seat.id for seat in seats]

    ledger: dict[uuid.UUID, list[LedgerEntry]] = {key: [] for key in seat_ids}
    for row in session.execute(
        sa.select(
            LedgerEntryRow.enrollment_id,
            LedgerEntryRow.kind,
            LedgerEntryRow.period,
            LedgerEntryRow.amount,
        )
        .where(LedgerEntryRow.enrollment_id.in_(seat_ids))
        .order_by(LedgerEntryRow.period, LedgerEntryRow.created_at)
    ).all():
        ledger[row[0]].append(
            LedgerEntry(kind=LedgerEntryKind(row[1]), period=row[2], amount=row[3])
        )

    # The latest cycle per seat, from one pass. Ordered ascending and
    # overwritten, so the last write per enrollment is the newest
    # period -- the period keys are fixed width, so lexical order IS
    # chronological order.
    latest: dict[uuid.UUID, FeeCycle] = {}
    for cycle in session.scalars(
        sa.select(FeeCycle)
        .where(FeeCycle.enrollment_id.in_(seat_ids))
        .order_by(FeeCycle.period)
    ):
        latest[cycle.enrollment_id] = cycle

    rows: list[RosterFeeRow] = []
    for seat in seats:
        entries = ledger[seat.id]
        newest = latest.get(seat.id)
        rows.append(
            RosterFeeRow(
                enrollment_id=seat.id,
                display_name=seat.display_name,
                outstanding=derive(entries).total_outstanding,
                current_period=None if newest is None else newest.period,
                current_status=(
                    None
                    if newest is None
                    else status_from_entries(entries, newest.period)
                ),
                due_date=None if newest is None else newest.due_date,
            )
        )
    return rows


@dataclass(frozen=True)
class FeeHistory:
    """One seat's periods, with the total the SERVER computed.

    **The total is here rather than left to the caller** [TC-9, D-31].
    Summing the rows client-side would be the Android app doing money
    arithmetic, which [D-20] forbids outright, and it would be wrong
    the moment the history paginates: a page of three periods would
    report a total that is not the balance.

    It is not a new calculation either. ``derive`` already produces
    ``total_outstanding`` as part of the ledger fold, floored at zero
    and computed inside the money module; this surfaces the value that
    already decides the number, rather than recomputing it beside the
    rows and risking the two disagreeing.

    :ivar cycles: One row per generated period, oldest first
    :ivar total_outstanding: What this seat still owes in total
    """

    cycles: list[FeeCycleRow]
    total_outstanding: Money


def enrollment_fee_history(
    session: Session,
    *,
    lens: Lens,
    enrollment_id: uuid.UUID,
) -> FeeHistory:
    """List every generated period for one seat, with its total.

    :param session: The session to read through
    :param lens: The viewer's lens
    :param enrollment_id: The seat
    :return: The periods and the total still owed
    :raises AuthorizationError: No path grants this lens that seat
    """
    _readable_enrollment(session, lens=lens, enrollment_id=enrollment_id)

    derived = derive_for_enrollment(session, enrollment_id)
    cycles = list(
        session.scalars(
            sa.select(FeeCycle)
            .where(FeeCycle.enrollment_id == enrollment_id)
            .order_by(FeeCycle.period)
        )
    )

    rows: list[FeeCycleRow] = []
    for cycle in cycles:
        charged = _charged_in(session, enrollment_id, cycle.period)
        rows.append(
            FeeCycleRow(
                period=cycle.period,
                due_date=cycle.due_date,
                charged=charged,
                outstanding=derived.per_cycle.get(cycle.period, Money.ZERO),
                status=fee_status(
                    session, enrollment_id=enrollment_id, period=cycle.period
                ),
            )
        )
    return FeeHistory(cycles=rows, total_outstanding=derived.total_outstanding)


def _charged_in(session: Session, enrollment_id: uuid.UUID, period: str) -> Money:
    """Total what was charged for one period.

    ``charge`` and ``carry_forward`` both place an obligation on a
    period, so both count: a period that received a carried balance was
    charged that balance as surely as it was charged its own fee, and
    reporting only the ``charge`` rows would show a cycle owing more
    than it was charged.

    :param session: The session to read through
    :param enrollment_id: The seat
    :param period: The period
    :return: The total charged for it
    """
    amounts = session.scalars(
        sa.select(LedgerEntryRow.amount).where(
            LedgerEntryRow.enrollment_id == enrollment_id,
            LedgerEntryRow.period == period,
            LedgerEntryRow.kind.in_(("charge", "carry_forward")),
        )
    ).all()
    return Money.sum(amounts)


def claim_detail(
    session: Session,
    *,
    lens: Lens,
    claim_id: uuid.UUID,
) -> ClaimDetail:
    """Read one claim, scoped to a viewer entitled to it.

    :param session: The session to read through
    :param lens: The viewer's lens
    :param claim_id: The claim
    :return: The claim and its decision
    :raises AuthorizationError: No path grants this lens that claim
    """
    claim = session.get(PaymentClaim, claim_id)
    if claim is None:
        raise _refuse()

    _readable_enrollment(session, lens=lens, enrollment_id=claim.enrollment_id)

    return ClaimDetail(
        claim_id=claim.id,
        period=claim.period,
        claimed_amount=claim.claimed_amount,
        approved_amount=claim.approved_amount,
        status=claim_status(claim.status),
        shortfall_disposition=_disposition(claim.shortfall_disposition),
        channel=claim.channel,
        submitted_at=claim.submitted_at,
        verified_at=claim.verified_at,
        previous_decision=claim.previous_decision,
    )


def assert_claim_is_verifiable(
    session: Session,
    *,
    lens: TeacherLens,
    claim_id: uuid.UUID,
) -> PaymentClaim:
    """Load a claim this teacher owns the batch of, or refuse.

    Separate from :func:`claim_detail` because verification is a WRITE
    and only a teacher performs it: a non-owning teacher must not learn
    the claim exists.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param claim_id: The claim
    :return: The claim
    :raises AuthorizationError: The claim's batch is not this lens's
    """
    claim = session.get(PaymentClaim, claim_id)
    if claim is None:
        raise _refuse()

    owned = session.scalars(
        sa.select(Batch.id)
        .join(Enrollment, Enrollment.batch_id == Batch.id)
        .where(Enrollment.id == claim.enrollment_id, Batch.owner_id == lens.owner_id)
    ).one_or_none()
    if owned is None:
        raise _refuse()
    return claim


def payment_destination(
    session: Session,
    *,
    lens: Lens,
    enrollment_id: uuid.UUID,
) -> PaymentDestination | None:
    """Return where to pay for this seat, if the teacher set a number.

    **The one response in the product carrying the collection number**
    [BR6.4, NFR14.32], and the allowlist asserting that is a test over
    the generated schema rather than a convention. It is the single
    teacher-authored field deliberately exposed downward, because the
    payment flow cannot work without it -- and the exposure is bounded
    to people enrolled in that teacher's batch rather than incidental.

    :param session: The session to read through
    :param lens: The viewer's lens
    :param enrollment_id: The seat being paid for
    :return: The destination, or None where the teacher set no number
    :raises AuthorizationError: No path grants this lens that seat
    """
    record = _readable_enrollment(session, lens=lens, enrollment_id=enrollment_id)

    batch = session.get(Batch, record.batch_id)
    if batch is None or batch.collection_number is None:
        return None

    return PaymentDestination(
        collection_number=batch.collection_number,
        collection_channel=batch.collection_channel,
        channels=CHANNELS,
    )
