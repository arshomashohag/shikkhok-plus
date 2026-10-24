"""The two management commands: generate, and check that it ran.

**``generate-fee-cycles`` takes no required arguments and is safe to run
at any time.** That is a requirement rather than a convenience: it is
the recovery procedure for NFR25.9, so a person who sees the alert must
be able to run the job by hand with no flags to get wrong.

**``check-generation-freshness`` is a SEPARATE command, and the
separation is the point** [observability-design § 1.4]. A freshness
check that runs only when the job runs is circular: if the job is not
running, neither is its own self-check. The check must be triggered by
something other than the thing it is checking, which is why the
infrastructure wires the job to cron and this check to something else.

**The heartbeat is written in its own transaction, after the run's last
enrollment-period has committed** -- never inside one. A run that
generated 2,900 of 3,000 did succeed at the 2,900, and its heartbeat
must not roll back with the 2,901st.

**A run that finds nothing due still writes the row.** Generation is
monthly, so on most days of most months there is nothing to create. A
heartbeat written only when ``cycles_created > 0`` would leave the row
stale for weeks during correct operation, fire the 48-hour alert
constantly, and get it muted -- reaching the alert's own failure mode by
the opposite route. The write is unconditional on OUTCOME and
conditional only on COMPLETION.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import FEE_GENERATION_JOB, JobHeartbeat
from app.db.session import build_engine, session_scope
from app.fees.generation import (
    GenerationResult,
    generate_due_cycles,
    void_declined_seats,
)

__all__ = [
    "STALENESS_THRESHOLD",
    "FreshnessVerdict",
    "check_generation_freshness",
    "main",
    "main_check_freshness",
    "main_generate",
    "run_generation",
    "stamp_heartbeat",
]

log = logging.getLogger(__name__)

#: **48 hours, derived as two missed daily runs** [NFR26.3] -- the
#: shortest window that does not page on a single transient failure the
#: next run would heal. The job runs daily, so one missed run is 24
#: hours of staleness at the moment the next would have fired, and two
#: is 48. Alerting at 24 would page on every single-run failure, which
#: NFR25.8 already covers loudly.
#:
#: The requirement records this threshold as open and the human's. A
#: monthly billing cycle would tolerate longer; a teacher watching for
#: a fee to appear would not.
STALENESS_THRESHOLD = dt.timedelta(hours=48)


@dataclass(frozen=True, slots=True)
class FreshnessVerdict:
    """What the freshness check found.

    :ivar healthy: True only when a row exists and is fresh
    :ivar reason: ``fresh``, ``stale`` or ``never_ran``
    :ivar staleness: How long since the last success, or None if never
    """

    healthy: bool
    reason: str
    staleness: dt.timedelta | None


def stamp_heartbeat(
    session: Session,
    *,
    result: GenerationResult,
    job_name: str = FEE_GENERATION_JOB,
    now: dt.datetime | None = None,
) -> None:
    """Record that the job completed, whatever it did.

    An upsert on ``job_name``: one row per job, updated in place. The
    question is "when did this last succeed", which is a single value;
    an append-only run log would answer the same question and grow
    unboundedly for a value only ever read as its maximum.

    **Called after the run's last enrollment-period has committed**, in
    its own transaction, so a heartbeat cannot roll back with work that
    actually succeeded.

    :param session: The session to write through
    :param result: The run's three counts
    :param job_name: Which job this row describes
    :param now: The success timestamp; the real clock by default
    :return: None
    """
    stamped = now or dt.datetime.now(tz=dt.UTC)
    statement = (
        pg_insert(JobHeartbeat)
        .values(
            job_name=job_name,
            last_success_at=stamped,
            cycles_created=result.cycles_created,
            cycles_skipped=result.cycles_skipped,
            periods_failed=result.periods_failed,
        )
        .on_conflict_do_update(
            index_elements=[JobHeartbeat.job_name],
            set_={
                "last_success_at": stamped,
                "cycles_created": result.cycles_created,
                "cycles_skipped": result.cycles_skipped,
                "periods_failed": result.periods_failed,
            },
        )
    )
    session.execute(statement)
    session.commit()


def run_generation(
    session: Session,
    *,
    today: dt.date | None = None,
    now: dt.datetime | None = None,
) -> GenerationResult:
    """Run one generation pass and stamp the heartbeat.

    The order is the requirement: generate, void the declined seats,
    then stamp. Stamping first would record a success before the work,
    which is the timer-level heartbeat § 1.1 rejects.

    :param session: The session to work through
    :param today: The date to generate up to; the real one by default
    :param now: The heartbeat timestamp; the real clock by default
    :return: The run's three counts
    """
    result = generate_due_cycles(session, today=today)
    # The mirror operation: seats whose student link declined have
    # their accrued balance voided, so a decline recorded while the job
    # was down is reversed on the next run rather than never.
    void_declined_seats(session)

    # UNCONDITIONAL ON OUTCOME. A run finding nothing due stamps with
    # cycles_created = 0, which is the honest count -- "nothing was
    # due" and "nothing ran" are different facts and the row
    # distinguishes them.
    stamp_heartbeat(session, result=result, now=now)
    return result


def check_generation_freshness(
    session: Session,
    *,
    job_name: str = FEE_GENERATION_JOB,
    now: dt.datetime | None = None,
) -> FreshnessVerdict:
    """Report whether the job has succeeded recently enough.

    **Written as "alert unless a row exists and is fresh", never as
    "alert if a row is stale"** [observability-design § 1.2]. The
    no-row case is the one a naive query silently swallows: a
    ``SELECT ... WHERE job_name = ...`` returning zero rows is falsy in
    most shapes a developer would write, so "if staleness > 48 hours
    then alert" treats *never ran* as *fine* -- and never-ran is
    precisely the scheduler-was-never-wired failure.

    :param session: The session to read through
    :param job_name: Which job to check
    :param now: The comparison time; the real clock by default
    :return: The verdict, with its reason
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    row = session.scalars(
        sa.select(JobHeartbeat).where(JobHeartbeat.job_name == job_name)
    ).one_or_none()

    if row is None:
        return FreshnessVerdict(healthy=False, reason="never_ran", staleness=None)

    staleness = moment - row.last_success_at
    if staleness >= STALENESS_THRESHOLD:
        return FreshnessVerdict(healthy=False, reason="stale", staleness=staleness)
    return FreshnessVerdict(healthy=True, reason="fresh", staleness=staleness)


def main_generate() -> int:
    """Entry point for ``generate-fee-cycles``.

    Takes no arguments, by requirement: this is the recovery procedure
    a person runs by hand after the alert fires.

    :return: 0 on completion, 1 on an unhandled failure
    """
    with session_scope(build_engine()) as session:
        result = run_generation(session)

    log.info(
        "fee cycle generation complete",
        extra={
            "cycles_created": result.cycles_created,
            "cycles_skipped": result.cycles_skipped,
            "periods_failed": result.periods_failed,
        },
    )
    return 0


def main_check_freshness() -> int:
    """Entry point for ``check-generation-freshness``.

    Emits ``log.critical`` on an unhealthy verdict, which is this
    product's existing alert channel: there is no CloudWatch alarm, no
    SNS topic and no ``alarm_actions`` anywhere in ``app/`` or
    ``infra/``, and the two alerting sites today are
    ``app/auth/ceilings.py`` and ``app/audit/log.py``, both
    ``log.critical`` on the host's standard output. D3 adds no alerting
    infrastructure and no recurring cost [NFR7.6].

    **Nothing automated proves the alert reaches a person.** That is a
    once-performed skipped-run rehearsal in staging before the first
    production generation, and until it is performed the delivery path
    is unproven. Stated plainly here because a manual check described
    without that sentence reads, to the next person, as a verifier.

    :return: 0 when healthy, 1 when not
    """
    with session_scope(build_engine()) as session:
        verdict = check_generation_freshness(session)

    if verdict.healthy:
        return 0

    log.critical(
        "fee cycle generation has not succeeded recently",
        extra={"reason": verdict.reason, "job_name": FEE_GENERATION_JOB},
    )
    return 1


def main() -> int:
    """Dispatch to one of the two commands by argument.

    One module with a verb rather than two modules, so the cron entry
    and the hand-run recovery command are spelled the same way and a
    person reading the crontab sees which is which.

    The default with no argument is **generate**, because that is the
    one a person runs by hand after an alert and the one whose
    requirement is "no required arguments".

    :return: The command's exit status, or 2 for an unknown verb
    """
    verb = sys.argv[1] if len(sys.argv) > 1 else "generate"
    if verb == "generate":
        return main_generate()
    if verb == "check-freshness":
        return main_check_freshness()

    log.error(
        "unknown command",
        extra={"verb": verb, "known": "generate, check-freshness"},
    )
    return 2


if __name__ == "__main__":  # pragma: no cover - a process entry point
    sys.exit(main())
