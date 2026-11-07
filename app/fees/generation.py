"""The daily generation job: the most consequential code with no user.

**The idempotency guarantee is the database constraint, not this
module** [BR1.3]. The insert is ``ON CONFLICT DO NOTHING`` on
``(enrollment_id, period)`` and the conflict is the SUCCESS path. There
is deliberately no application-level "has this already run?" guard:
that shape passes a sequential test and double-charges under two
workers, which Phase 1 has. The built precedent is
``RateLimitCounter``'s unique constraint, whose comment already
explains why -- "the second one conflicts instead of reading a stale
value" -- and this is the same shape with DO NOTHING in place of DO
UPDATE.

**The charge is appended only when the insert created a row.** That
ordering is what prevents a double charge: the row's creation is the
idempotency token, so the conflict path appends nothing. An
implementation that inserted the cycle and then unconditionally charged
would pass every single-run test and double-charge on the second day.

**Commits per enrollment-period** [NFR19.8], so one bad row cannot
abort a run. A run that generated 2,900 of 3,000 did succeed at the
2,900, and the heartbeat is written afterwards in its own transaction
precisely so it does not roll back with the 2,901st.

**Runs daily, and a missed day self-heals** [BR1.4]. Every period from
the enrollment's first generating one through the current one is
considered, and only those with no existing cycle are inserted -- which
is what makes the job safe to run any number of times on any number of
days. Which ones have no cycle is found set-based, by an anti-join, so
the considering costs a few statements rather than one insert per
seat-month [C-28]; the inserting still goes through the constraint.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import Batch, Enrollment, FeeCycle
from app.fees.balances import derive_for_enrollment
from app.fees.ledger_writer import append_entry, apply_available_credit
from app.fees.periods import Period, due_date_for, periods_from_through
from app.fees.resolution import FeeNotResolvable, resolve_fee
from app.local_time import bangladesh_today
from app.money import Money

__all__ = ["GenerationResult", "generate_due_cycles"]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """What one run of the job did.

    The three per-run counts [NFR25.13], carried to the heartbeat row
    because they are in hand at the moment it is written and are then
    queryable without a metrics backend.

    A sustained non-zero ``cycles_skipped`` is a double-scheduling bug
    rather than normal operation, which is the signal that count exists
    to give.

    :ivar cycles_created: Cycles inserted
    :ivar cycles_skipped: Inserts that conflicted and did nothing
    :ivar periods_failed: Enrollment-periods that raised and were
        skipped, leaving the rest of the run to continue
    """

    cycles_created: int
    cycles_skipped: int
    periods_failed: int


@dataclass(frozen=True, slots=True)
class _Candidate:
    """One seat the job may generate for, with the columns it needs.

    :ivar enrollment_id: The seat
    :ivar fee_amount: The seat's own fee, or None to inherit
    :ivar batch_default: The batch's default fee, or None
    :ivar anchor_day: The batch's billing anchor, or None
    :ivar joined_on: When the seat starts generating, or None
    :ivar inactive_from: The date after which it stops, or None
    :ivar created_at: The seat's creation, the fallback start
    """

    enrollment_id: uuid.UUID
    fee_amount: Money | None
    batch_default: Money | None
    anchor_day: int | None
    joined_on: dt.date | None
    inactive_from: dt.date | None
    created_at: dt.datetime


def _candidates(session: Session) -> list[_Candidate]:
    """Select every seat that may generate.

    **A ``declined`` STUDENT link is a filter; a ``declined`` GUARDIAN
    link is explicitly NOT** [BR1.6, BR1.7]. The asymmetry is the whole
    point: if a guardian's refusal stopped generation, any student could
    clear their own fees by having a guardian refuse.

    A ``pending`` seat generates [BR1.9]. Pending is the normal state of
    a new seat, not a withheld one -- a teacher who adds twenty students
    on Monday must see their fees without each installing the app.

    :param session: The session to read through
    :return: One candidate per seat on an active batch
    """
    rows = session.execute(
        sa.select(
            Enrollment.id,
            Enrollment.fee_amount,
            Batch.default_fee,
            Batch.fee_due_day,
            Enrollment.joined_on,
            Enrollment.inactive_from,
            Enrollment.created_at,
        )
        .join(Batch, Batch.id == Enrollment.batch_id)
        .where(
            Batch.active.is_(True),
            # The student link only. The guardian column is deliberately
            # absent from this predicate [BR1.7].
            Enrollment.student_decision != "declined",
        )
        .order_by(Enrollment.created_at, Enrollment.id)
    ).all()

    return [
        _Candidate(
            enrollment_id=row[0],
            fee_amount=row[1],
            batch_default=row[2],
            anchor_day=row[3],
            joined_on=row[4],
            inactive_from=row[5],
            created_at=row[6],
        )
        for row in rows
    ]


def seat_start(joined_on: dt.date | None, created_at: dt.datetime) -> dt.date:
    """Return the date a seat starts: ``joined_on``, else its creation date.

    :param joined_on: When the teacher recorded the seat as starting
    :param created_at: The seat's creation, the fallback start
    :return: The seat's first day
    """
    # The Bangladesh date: a seat created after Dhaka midnight on the 1st
    # starts that month, not the UTC date's previous one [audit C-23].
    return joined_on or bangladesh_today(created_at)


def _first_period(candidate: _Candidate) -> Period:
    """Return the earliest period this seat could generate for.

    ``joined_on`` when the teacher recorded one, else the seat's
    creation date. Falling back to creation rather than to "this month"
    is what makes a seat added mid-month bill for that month.

    :param candidate: The seat
    :return: Its first generating period
    """
    return Period.containing(seat_start(candidate.joined_on, candidate.created_at))


def _generates(candidate: _Candidate, period: Period) -> bool:
    """Decide whether this seat generates for this period [BR1.5].

    A seat generates for the period CONTAINING ``inactive_from`` and
    stops only for periods beginning strictly after it. The period
    containing the date generates **in full** -- never prorated. A
    student leaving on the 1st must not escape the month's fee, and one
    leaving on the 28th must not be billed for the next month too.

    :param candidate: The seat
    :param period: The period under consideration
    :return: True if a cycle should exist for it
    """
    if candidate.inactive_from is None:
        return True
    return candidate.inactive_from >= period.first_day()


def _insert_cycle(
    session: Session,
    *,
    enrollment_id: uuid.UUID,
    period: Period,
    due_date: dt.date,
) -> bool:
    """Insert a cycle, treating a conflict as success [BR1.3].

    ``ON CONFLICT DO NOTHING`` with ``RETURNING id``: the returned row
    is present exactly when this call created it, which is the
    idempotency token the charge is conditioned on. Reading the result
    rather than counting rows is what makes "did I create it" an answer
    from the database instead of a guess.

    :param session: The session to write through
    :param enrollment_id: The seat
    :param period: The period
    :param due_date: The clamped due date
    :return: True if this call created the row, False if it conflicted
    """
    statement = (
        pg_insert(FeeCycle)
        .values(
            id=uuid.uuid4(),
            enrollment_id=enrollment_id,
            period=str(period),
            due_date=due_date,
            created_at=dt.datetime.now(tz=dt.UTC),
        )
        .on_conflict_do_nothing(constraint="uq_fee_cycle_enrollment_period")
        .returning(FeeCycle.id)
    )
    return session.execute(statement).scalar_one_or_none() is not None


#: Seats per anti-join statement, so one run's parameters stay bounded.
_SEATS_PER_LOOKUP = 2000


def _wanted_periods(candidate: _Candidate, current: Period) -> list[Period]:
    """List every period this seat should have a cycle for, oldest first.

    :param candidate: The seat
    :param current: The period containing today
    :return: The generating periods from the seat's first through today's
    """
    return [
        period
        for period in periods_from_through(_first_period(candidate), current)
        if _generates(candidate, period)
    ]


def _missing_cycles(
    session: Session, wanted: dict[uuid.UUID, list[Period]]
) -> set[tuple[uuid.UUID, str]]:
    """Find which wanted (seat, period) pairs have no cycle yet, set-based.

    **One anti-join per chunk of seats, not one insert per pair** [C-28]:
    the pairs travel as two arrays, and only those with no ``fee_cycle``
    row come back. On a normal day that is nothing at all, or one new
    month per seat on the 1st.

    This is a READ, and only decides which pairs are worth attempting.
    The guarantee is still the unique constraint and ``ON CONFLICT DO
    NOTHING`` in :func:`_insert_cycle`: a pair a concurrent run inserts
    after this read conflicts there, does nothing, and is counted skipped.

    :param session: The session to read through
    :param wanted: Each seat's generating periods
    :return: The pairs with no cycle, as (seat, period key)
    """
    missing: set[tuple[uuid.UUID, str]] = set()
    seats = [seat for seat, periods in wanted.items() if periods]
    for start in range(0, len(seats), _SEATS_PER_LOOKUP):
        pairs = [
            (seat, str(period))
            for seat in seats[start : start + _SEATS_PER_LOOKUP]
            for period in wanted[seat]
        ]
        pair = (
            sa.func.unnest(
                sa.bindparam(
                    None, [p[0] for p in pairs], type_=ARRAY(PgUUID(as_uuid=True))
                ),
                sa.bindparam(None, [p[1] for p in pairs], type_=ARRAY(sa.Text())),
            )
            .table_valued("enrollment_id", "period")
            .render_derived()
        )
        missing.update(
            (row[0], row[1])
            for row in session.execute(
                sa.select(pair.c.enrollment_id, pair.c.period).where(
                    ~sa.exists().where(
                        FeeCycle.enrollment_id == pair.c.enrollment_id,
                        FeeCycle.period == pair.c.period,
                    )
                )
            )
        )
    # No commit here: a read ends no unit of work, and the caller's
    # transaction is left exactly as the per-pair loop always found it.
    return missing


def generate_due_cycles(
    session: Session,
    *,
    today: dt.date | None = None,
) -> GenerationResult:
    """Generate every cycle due at or before `today`.

    **The clock is a parameter, not a module global.** The across-days
    obligation [BR1.4, AC5.1.3] needs the job run as though it were a
    different day, and a patched global is both wider than the caller
    and invisible at the call site.

    **Set-based, then one transaction per created cycle** [C-28]. The
    wanted (seat, period) pairs are computed here, the ones that already
    have a cycle are found by one anti-join per chunk of seats, and only
    the rest are attempted -- each, as before, its own insert, charge
    and credit application committed together. A run on a day with
    nothing new issues a handful of statements, not one per seat-month.

    The counts mean what they meant when every pair was attempted: a
    pair whose cycle already exists is ``skipped`` whether this run saw
    it in the anti-join or a concurrent run won its insert, and a seat
    with no fee anywhere fails once per wanted period, logged each time.

    Safe to run any number of times on any number of days.

    :param session: The session to work through
    :param today: The date to generate up to; defaults to the real one
    :return: The three per-run counts
    """
    current = Period.containing(today or bangladesh_today())
    candidates = _candidates(session)
    wanted = {
        candidate.enrollment_id: _wanted_periods(candidate, current)
        for candidate in candidates
    }
    missing = _missing_cycles(session, wanted)
    created = skipped = failed = 0

    for candidate in candidates:
        periods = wanted[candidate.enrollment_id]
        if not periods:
            continue
        try:
            fee = resolve_fee(
                enrollment_fee=candidate.fee_amount,
                batch_default=candidate.batch_default,
            )
        except FeeNotResolvable:
            # Every wanted period fails, existing cycle or not, exactly as
            # when each was attempted: the fee is resolved before anything
            # else is looked at.
            for period in periods:
                _log_unresolvable(candidate, period)
            failed += len(periods)
            continue
        for period in periods:
            if (candidate.enrollment_id, str(period)) not in missing:
                skipped += 1
                continue
            outcome = _generate_one(session, candidate, period, fee)
            created += outcome[0]
            skipped += outcome[1]
            failed += outcome[2]

    return GenerationResult(
        cycles_created=created,
        cycles_skipped=skipped,
        periods_failed=failed,
    )


def _log_unresolvable(candidate: _Candidate, period: Period) -> None:
    """Log one enrollment-period skipped for want of a fee.

    :param candidate: The seat
    :param period: The period
    :return: None
    """
    log.warning(
        "fee not resolvable; skipping enrollment-period",
        extra={
            "enrollment_id": str(candidate.enrollment_id),
            "period": str(period),
        },
    )


def _generate_one(
    session: Session,
    candidate: _Candidate,
    period: Period,
    fee: Money,
) -> tuple[int, int, int]:
    """Generate one enrollment-period, committing it alone.

    **The whole enrollment-period is one transaction** [BR4.5]: the
    cycle row, its charge, and any credit applied against it commit
    together or not at all. Splitting them could leave a charge with no
    application after a crash.

    A failure is **logged, counted and swallowed** so the run continues
    [NFR19.8] -- one seat whose write fails must not cost every other
    seat its cycle. Nothing identifying reaches the log line: an
    enrollment id and a period, never a name, a number or an amount
    [NFR24.6].

    :param session: The session to work through
    :param candidate: The seat
    :param period: The period
    :param fee: The seat's resolved fee
    :return: The created, skipped and failed counts for this one
    """
    try:
        due_date = due_date_for(period, anchor_day=candidate.anchor_day)

        if not _insert_cycle(
            session,
            enrollment_id=candidate.enrollment_id,
            period=period,
            due_date=due_date,
        ):
            # The conflict path appends NOTHING. This is the branch
            # that makes a concurrent run free [BR1.3].
            session.commit()
            return (0, 1, 0)

        append_entry(
            session,
            enrollment_id=candidate.enrollment_id,
            period=str(period),
            kind="charge",
            amount=fee,
        )
        # AFTER the charge, in the same transaction [BR4.5]. Applying
        # first computes min(available, 0) and spends nothing.
        apply_available_credit(
            session,
            enrollment_id=candidate.enrollment_id,
            period=str(period),
        )
        session.commit()
    except sa.exc.SQLAlchemyError:
        session.rollback()
        log.exception(
            "generation failed for an enrollment-period",
            extra={
                "enrollment_id": str(candidate.enrollment_id),
                "period": str(period),
            },
        )
        return (0, 0, 1)
    return (1, 0, 0)


def void_declined_seats(session: Session) -> int:
    """Void the accrued balance of every declined student seat [BR1.6].

    Separate from :func:`generate_due_cycles` because it is the mirror
    operation: generation walks seats that are NOT declined, and this
    walks the ones that are. Running it from the same daily job is what
    makes the reversal self-healing too -- a decline recorded while the
    job was down is still reversed on the next run.

    Idempotent: ``void_accrued_cycles`` finds nothing outstanding on a
    second call and writes nothing.

    :param session: The session to write through
    :return: How many seats had a balance voided
    """
    from app.fees.ledger_writer import void_accrued_cycles

    declined = session.scalars(
        sa.select(Enrollment.id).where(Enrollment.student_decision == "declined")
    ).all()

    voided = 0
    for enrollment_id in declined:
        if derive_for_enrollment(
            session, enrollment_id
        ).total_outstanding.is_positive():
            void_accrued_cycles(session, enrollment_id=enrollment_id)
            voided += 1
    return voided
