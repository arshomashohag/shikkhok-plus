"""The session-generation command, and its heartbeat.

**One verb, no required arguments**, for the same reason D3's generate
command has none: this is the recovery procedure a person runs by hand
after the alert fires, so there are no flags to get wrong.

**The heartbeat is registered under this job's OWN name**, beside the
fee job's [observability-design § 4.1, NFR1.8]. A shared name would let
a healthy fee run mask a session job that has never fired -- and the
masking would be total, because session generation **self-heals**: a job
whose cron entry was never wired looks completely healthy right up to
the morning a teacher opens the app and there is no class to mark
attendance against.

That is BR1.1's ``violation_behaviour`` reached by an operational route
rather than a code one, and the concrete failure it is designed against
is named in the infrastructure specification: the ASG refreshes on every
deploy, the instance is replaced and ``user_data`` re-runs, so **a
hand-added cron entry is wiped by the next routine deploy** and nothing
looks wrong.

**The heartbeat is written after the run completes**, in its own
transaction, and is **unconditional on OUTCOME** -- a run that creates
nothing because every session already exists is the normal case over a
two-month horizon, and stamping only on ``created > 0`` would leave the
row stale during entirely correct operation.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys

from sqlalchemy.orm import Session as DbSession

from app.db.models import SESSION_GENERATION_JOB
from app.db.session import build_engine, session_scope
from app.fees.commands import stamp_heartbeat
from app.fees.generation import GenerationResult as FeeGenerationResult
from app.teaching.generation import GenerationResult, generate_sessions

__all__ = ["main", "main_generate_sessions", "run_session_generation"]

log = logging.getLogger(__name__)


def run_session_generation(
    session: DbSession,
    *,
    today: dt.date | None = None,
    now: dt.datetime | None = None,
) -> GenerationResult:
    """Run one generation pass and stamp this job's heartbeat.

    The order is the requirement: generate, then stamp. Stamping first
    would record a success before the work, which is the timer-level
    heartbeat the observability design rejects -- a scheduler firing a
    command that immediately crashes would still stamp it.

    The heartbeat row's three counts are the fee job's column names
    reused rather than a second shape: ``job_heartbeat`` is keyed by
    ``job_name`` and carries three integers, and widening it to carry
    per-job column names would be a migration for a difference that
    does not exist. The session job's counts map directly -- created,
    skipped, and the slots that failed.

    :param session: The session to work through
    :param today: The date to generate around; the real one by default
    :param now: The heartbeat timestamp; the real clock by default
    :return: The run's three counts
    """
    result = generate_sessions(session, today=today)

    stamp_heartbeat(
        session,
        result=FeeGenerationResult(
            cycles_created=result.sessions_created,
            cycles_skipped=result.sessions_skipped,
            periods_failed=result.batches_failed,
        ),
        job_name=SESSION_GENERATION_JOB,
        now=now,
    )
    return result


def main_generate_sessions() -> int:
    """Entry point for ``generate-sessions``.

    Takes no arguments, by requirement: this is the recovery procedure
    a person runs by hand after the alert fires.

    :return: 0 on completion
    """
    with session_scope(build_engine()) as session:
        result = run_session_generation(session)

    # Counts only. Nothing identifying reaches this line -- no batch
    # name, no child name, no roster [NFR24.13].
    log.info(
        "session generation complete",
        extra={
            "sessions_created": result.sessions_created,
            "sessions_skipped": result.sessions_skipped,
            "batches_failed": result.batches_failed,
        },
    )
    return 0


def main() -> int:
    """Dispatch the one verb this module carries.

    **No freshness verb here.** The freshness check enumerates every
    registered job from one entry point [infrastructure-specification
    § 3.3, option B], so this job registers a heartbeat row and adds no
    second checker -- which is the property that let ``user_data``'s
    bare ``check-freshness`` stay unchanged.

    :return: The command's exit status, or 2 for an unknown verb
    """
    verb = sys.argv[1] if len(sys.argv) > 1 else "generate"
    if verb == "generate":
        return main_generate_sessions()

    log.error("unknown command", extra={"verb": verb, "known": "generate"})
    return 2


if __name__ == "__main__":  # pragma: no cover - a process entry point
    sys.exit(main())
