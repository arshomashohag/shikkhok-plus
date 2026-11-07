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
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.analytics.collections import (
    DEFAULT_MONTHS,
    LedgerFact,
    carried_in_by_period,
    charged_by_period,
    clamp_months,
    collected_by_period,
    facts_for_seats,
    months_ending,
)
from app.authz.lenses import GuardianLens, Lens, StudentLens, TeacherLens
from app.db.models import (
    Batch,
    Enrollment,
    FeeCycle,
    LedgerEntryRow,
    PaymentClaim,
    PaymentSubmission,
)
from app.errors import AuthorizationError
from app.errors.codes import NOT_AVAILABLE
from app.fees.balances import entries_for_enrollment
from app.fees.overdue import days_overdue
from app.fees.status import (
    CLAIM_STATUS_VALUES,
    DISPOSITION_VALUES,
    SUBMISSION_STATUS_VALUES,
    ClaimStatus,
    FeeStatus,
    MonthState,
    ShortfallDisposition,
    SubmissionStatus,
    month_state,
    status_from_entries,
    statuses_from_entries,
)
from app.fees.submissions import child_order
from app.local_time import bangladesh_today
from app.money import LedgerEntry, LedgerEntryKind, Money, derive

__all__ = [
    "BatchMonth",
    "ClaimDetail",
    "FeeCycleRow",
    "HistoryLine",
    "MonthCounts",
    "MonthStateRow",
    "RosterFeeRow",
    "assert_claim_is_verifiable",
    "batch_fee_overview",
    "batch_month",
    "claim_detail",
    "claim_status",
    "claims_by_month",
    "enrollment_fee_history",
    "month_strip",
    "owned_submission",
    "submission_status",
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


def submission_status(stored: str) -> SubmissionStatus:
    """Narrow a stored submission status onto the closed set, checking it.

    :param stored: The value read from the column
    :return: The same value, narrowed
    :raises ValueError: The stored value is outside the closed set
    """
    if stored not in SUBMISSION_STATUS_VALUES:
        raise ValueError(
            f"{stored!r} is not a submission status. The database enum and "
            "app.fees.status.SUBMISSION_STATUS_VALUES have diverged."
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
    :ivar days_overdue: How late the oldest unpaid period is, or None
    :ivar verifying: The total of this seat's claims still waiting for
        the teacher, or None when none waits
    """

    enrollment_id: uuid.UUID
    display_name: str
    outstanding: Money
    current_period: str | None
    current_status: FeeStatus | None
    due_date: dt.date | None
    days_overdue: int | None = None
    verifying: Money | None = None
    state: MonthState | None = None
    history_line: HistoryLine | None = None


@dataclass(frozen=True, slots=True)
class HistoryLine:
    """The latest payment claim for one seat in one month, as data.

    Structured fields rather than a sentence, so the client localizes it.

    **The amount is one a person can recognise.** Once approved it is
    what the teacher approved for this child. While a payment waits, or
    once it is rejected, it is the whole payment as sent, with the
    children it covered named: the child's provisional share is a split
    nobody made, and for a child with a zero share it reads as nothing
    sent at all.

    :ivar amount: What was approved for the child; otherwise what was
        sent, for every child in ``covered_names``
    :ivar channel: Which service the money moved through
    :ivar paid_on: When the money was sent
    :ivar status: One of the four server-set claim values
    :ivar decision_note: The teacher's note on the decision, or None
    :ivar covered_names: The children the sent amount covered, in child
        order; empty once the amount is the child's approved figure, and
        for a claim made before payments covered several children
    """

    amount: Money
    channel: str
    paid_on: dt.date
    status: ClaimStatus
    decision_note: str | None
    covered_names: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MonthClaims:
    """What the claims of one seat say about one month.

    :ivar checking: A claim for the month still waits for the teacher
    :ivar latest: The most recently submitted claim
    """

    checking: bool
    latest: HistoryLine


@dataclass(frozen=True, slots=True)
class MonthStateRow:
    """One month on a seat's strip.

    :ivar period: The month, as ``YYYY-MM``
    :ivar state: The month's state
    :ivar history_line: The latest claim for it, or None
    """

    period: str
    state: MonthState
    history_line: HistoryLine | None


@dataclass(frozen=True, slots=True)
class MonthCounts:
    """How many seats fall under each filter for one month.

    :ivar paid: Settled seats, including waived ones
    :ivar checking: Seats with a payment waiting for the teacher
    :ivar owed: Seats still owing, wholly or partly
    """

    paid: int
    checking: int
    owed: int


@dataclass(frozen=True, slots=True)
class BatchMonth:
    """One batch in one month.

    :ivar period: The month, as ``YYYY-MM``
    :ivar collected: Cash in for the month after corrections
    :ivar charged: What the month was billed
    :ivar counts: Seats per filter
    :ivar seats: One row per seat
    """

    period: str
    collected: Money
    charged: Money
    counts: MonthCounts
    seats: list[RosterFeeRow]


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
    :ivar decision_note: The teacher's note on the decision, or None
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
    decision_note: str | None = None


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
    today: dt.date | None = None,
    period: str | None = None,
) -> list[RosterFeeRow]:
    """List every seat's fee position on one of this teacher's batches.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param batch_id: The batch
    :param today: The date overdue is measured on; Bangladesh's by default
    :param period: The month each row's state and history line describe;
        the current month by default
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
    due_by_seat: dict[uuid.UUID, dict[str, dt.date]] = {}
    for cycle in session.scalars(
        sa.select(FeeCycle)
        .where(FeeCycle.enrollment_id.in_(seat_ids))
        .order_by(FeeCycle.period)
    ):
        latest[cycle.enrollment_id] = cycle
        due_by_seat.setdefault(cycle.enrollment_id, {})[cycle.period] = cycle.due_date

    # Claims waiting for the teacher, summed per seat in one statement:
    # the "Verifying ৳800" chip.
    verifying: dict[uuid.UUID, Money] = {}
    for seat_id, claimed in session.execute(
        sa.select(PaymentClaim.enrollment_id, PaymentClaim.claimed_amount).where(
            PaymentClaim.enrollment_id.in_(seat_ids),
            PaymentClaim.status == "pending",
        )
    ).all():
        verifying[seat_id] = verifying.get(seat_id, Money.ZERO) + claimed

    on = today or bangladesh_today()
    month = period or months_ending(on, 1)[0]
    claims = claims_by_month(session, seat_ids, [month])

    rows: list[RosterFeeRow] = []
    for seat in seats:
        month_claims = claims.get((seat.id, month))
        entries = ledger[seat.id]
        newest = latest.get(seat.id)
        derived = derive(entries)
        rows.append(
            RosterFeeRow(
                enrollment_id=seat.id,
                display_name=seat.display_name,
                outstanding=derived.total_outstanding,
                current_period=None if newest is None else newest.period,
                current_status=(
                    None
                    if newest is None
                    else status_from_entries(entries, newest.period)
                ),
                due_date=None if newest is None else newest.due_date,
                days_overdue=days_overdue(
                    derived.per_cycle, due_by_seat.get(seat.id, {}), on
                ),
                verifying=verifying.get(seat.id),
                state=month_state(
                    entries,
                    month,
                    checking=month_claims is not None and month_claims.checking,
                ),
                history_line=None if month_claims is None else month_claims.latest,
            )
        )
    return rows


def claims_by_month(
    session: Session,
    seat_ids: list[uuid.UUID],
    periods: list[str],
) -> dict[tuple[uuid.UUID, str], MonthClaims]:
    """Read what the claims say about these seats in these months, in ONE statement.

    :param session: The session to read through
    :param seat_ids: The seats
    :param periods: The months
    :return: Per ``(seat, period)``, whether one waits and the latest one;
        a pair with no claim is absent
    """
    if not seat_ids:
        return {}
    rows = session.execute(
        sa.select(PaymentClaim, PaymentSubmission)
        .outerjoin(
            PaymentSubmission,
            PaymentSubmission.id == PaymentClaim.payment_submission_id,
        )
        .where(
            PaymentClaim.enrollment_id.in_(seat_ids), PaymentClaim.period.in_(periods)
        )
        .order_by(PaymentClaim.submitted_at, PaymentClaim.id)
    ).all()
    names = _covered_names(
        session, [submission.id for _claim, submission in rows if submission]
    )
    result: dict[tuple[uuid.UUID, str], MonthClaims] = {}
    for claim, submission in rows:
        key = (claim.enrollment_id, claim.period)
        waiting = claim.status == "pending" or (key in result and result[key].checking)
        result[key] = MonthClaims(
            checking=waiting,
            latest=_history_line(claim, submission, names),
        )
    return result


def _covered_names(
    session: Session, submission_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """Name each submission's children, in child order, in one statement.

    :param session: The session to read through
    :param submission_ids: The submissions
    :return: Submission id to its children's teacher-typed names
    """
    if not submission_ids:
        return {}
    seats: dict[uuid.UUID, list[Enrollment]] = {}
    for submission_id, seat in session.execute(
        sa.select(PaymentClaim.payment_submission_id, Enrollment)
        .join(Enrollment, Enrollment.id == PaymentClaim.enrollment_id)
        .where(PaymentClaim.payment_submission_id.in_(set(submission_ids)))
    ).all():
        if submission_id is not None:
            seats.setdefault(submission_id, []).append(seat)
    return {
        submission_id: [seat.display_name for seat in sorted(found, key=child_order)]
        for submission_id, found in seats.items()
    }


def _history_line(
    claim: PaymentClaim,
    submission: PaymentSubmission | None,
    names: dict[uuid.UUID, list[str]],
) -> HistoryLine:
    """Describe one claim for a seat's month.

    :param claim: The claim
    :param submission: The payment it is a share of, or None
    :param names: Each submission's children, in child order
    :return: The line, amount chosen as :class:`HistoryLine` explains
    """
    status = claim_status(claim.status)
    approved = status in ("approved_full", "approved_partial")
    if submission is None:
        return HistoryLine(
            amount=(
                claim.approved_amount
                if approved and claim.approved_amount is not None
                else claim.claimed_amount
            ),
            channel=claim.channel,
            paid_on=bangladesh_today(claim.submitted_at),
            status=status,
            decision_note=claim.rejection_reason,
        )
    if approved and claim.approved_amount is not None:
        amount, covered = claim.approved_amount, []
    else:
        amount, covered = submission.total_amount, names.get(submission.id, [])
    return HistoryLine(
        amount=amount,
        channel=claim.channel,
        paid_on=submission.paid_on,
        status=status,
        decision_note=submission.decision_note,
        covered_names=covered,
    )


def batch_month(
    session: Session,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
    period: str | None = None,
    today: dt.date | None = None,
) -> BatchMonth:
    """Read one batch in one month: totals, filter counts and each seat.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param batch_id: The batch
    :param period: The month, as ``YYYY-MM``; the current month by default
    :param today: Bangladesh's date by default
    :return: The month's figures and rows
    :raises AuthorizationError: The batch is not this lens's
    """
    on = today or bangladesh_today()
    month = period or months_ending(on, 1)[0]
    seats = batch_fee_overview(
        session, lens=lens, batch_id=batch_id, today=on, period=month
    )
    facts = facts_for_seats(
        session, [seat.enrollment_id for seat in seats], across_seats=True
    )
    states = [seat.state for seat in seats]
    return BatchMonth(
        period=month,
        collected=collected_by_period(facts).get(month, Money.ZERO),
        charged=charged_by_period(facts).get(month, Money.ZERO),
        counts=MonthCounts(
            paid=sum(1 for state in states if state in ("paid", "waived")),
            checking=sum(1 for state in states if state == "checking"),
            owed=sum(1 for state in states if state in ("unpaid", "partly_paid")),
        ),
        seats=seats,
    )


def month_strip(
    session: Session,
    enrollment_id: uuid.UUID,
    window: list[str],
    *,
    entries: list[LedgerEntry] | None = None,
) -> list[MonthStateRow]:
    """Give one seat's state for each month of a window that has one.

    The seat's ledger is folded ONCE for the whole window, never once
    per month [C-14].

    :param session: The session to read through
    :param enrollment_id: The seat, already authorized
    :param window: Period keys, oldest first
    :param entries: The seat's entries when the caller already read
        them, raw or summed per (period, kind); read here otherwise
    :return: The months that have a state, oldest first
    """
    if entries is None:
        entries = entries_for_enrollment(session, enrollment_id)
    statuses = statuses_from_entries(entries)
    claims = claims_by_month(session, [enrollment_id], window)
    strip: list[MonthStateRow] = []
    for month in window:
        month_claims = claims.get((enrollment_id, month))
        state = month_state(
            entries,
            month,
            checking=month_claims is not None and month_claims.checking,
            statuses=statuses,
        )
        if state is not None:
            strip.append(
                MonthStateRow(
                    period=month,
                    state=state,
                    history_line=None if month_claims is None else month_claims.latest,
                )
            )
    return strip


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
    :ivar month_states: The last months that have a state, oldest first
    """

    cycles: list[FeeCycleRow]
    total_outstanding: Money
    month_states: list[MonthStateRow] = field(default_factory=list)


def enrollment_fee_history(
    session: Session,
    *,
    lens: Lens,
    enrollment_id: uuid.UUID,
    months: int = DEFAULT_MONTHS,
    today: dt.date | None = None,
) -> FeeHistory:
    """List every generated period for one seat, with its total.

    :param session: The session to read through
    :param lens: The viewer's lens
    :param enrollment_id: The seat
    :param months: How many months the strip covers, clamped to 1 to 24
    :param today: Bangladesh's date by default
    :return: The periods, the total still owed and the strip
    :raises AuthorizationError: No path grants this lens that seat
    """
    _readable_enrollment(session, lens=lens, enrollment_id=enrollment_id)

    # ONE ledger read and ONE fold for the whole history [C-14]: the
    # balance, every cycle's status and the strip all come from the same
    # summed facts, rather than a full ledger read per cycle.
    facts = facts_for_seats(session, [enrollment_id])
    entries = [fact.entry for fact in facts]
    derived = derive(entries)
    statuses = statuses_from_entries(entries)
    charged = _charged_by_period(facts)
    cycles = list(
        session.scalars(
            sa.select(FeeCycle)
            .where(FeeCycle.enrollment_id == enrollment_id)
            .order_by(FeeCycle.period)
        )
    )

    rows: list[FeeCycleRow] = []
    for cycle in cycles:
        rows.append(
            FeeCycleRow(
                period=cycle.period,
                due_date=cycle.due_date,
                charged=charged.get(cycle.period, Money.ZERO),
                outstanding=derived.per_cycle.get(cycle.period, Money.ZERO),
                # A generated cycle always carries its charge; a cycle
                # with no entries at all is refused exactly as
                # ``fee_status`` refused it.
                status=statuses[cycle.period],
            )
        )
    window = months_ending(today or bangladesh_today(), clamp_months(months))
    strip = month_strip(session, enrollment_id, window, entries=entries)
    return FeeHistory(
        cycles=rows,
        total_outstanding=derived.total_outstanding,
        month_states=strip,
    )


def _charged_by_period(facts: list[LedgerFact]) -> dict[str, Money]:
    """Total what was charged for each period, after corrections.

    ``charge`` and ``carry_forward`` both place an obligation on a
    period, so both count: a period that received a carried balance was
    charged that balance as surely as it was charged its own fee, and
    reporting only the ``charge`` rows would show a cycle owing more
    than it was charged. The rows a correction wrote or superseded are
    left out by the collections report's own rules, so a corrected
    decision moves neither figure.

    :param facts: The seat's rows with their correction flags
    :return: The total charged per period; periods charged nothing are
        absent
    """
    totals = dict(charged_by_period(facts))
    for period, carried in carried_in_by_period(facts).items():
        totals[period] = totals.get(period, Money.ZERO) + carried
    return totals


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
        decision_note=_decision_note(session, claim),
    )


def _decision_note(session: Session, claim: PaymentClaim) -> str | None:
    """Read the note the family is shown for a claim's decision.

    A share of a submission shows the submission's note; a claim made
    on its own shows its rejection reason.

    :param session: The session to read through
    :param claim: The claim
    :return: The note, or None
    """
    if claim.payment_submission_id is None:
        return claim.rejection_reason
    submission = session.get(PaymentSubmission, claim.payment_submission_id)
    return None if submission is None else submission.decision_note


def owned_submission(
    session: Session,
    *,
    lens: TeacherLens,
    submission_id: uuid.UUID,
) -> PaymentSubmission:
    """Load a submission on one of this teacher's batches, or refuse.

    An absent submission and another teacher's are the same refusal,
    so a probe cannot tell which ids exist.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param submission_id: The submission
    :return: The submission
    :raises AuthorizationError: It is absent or not this lens's
    """
    submission = session.scalars(
        sa.select(PaymentSubmission)
        .join(Batch, Batch.id == PaymentSubmission.batch_id)
        .where(
            PaymentSubmission.id == submission_id,
            Batch.owner_id == lens.owner_id,
        )
    ).one_or_none()
    if submission is None:
        raise _refuse()
    return submission


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
