"""The ten-minute drain of the CloudFront invalidation outbox, and its heartbeat.

Every takedown enqueues its paths in its own transaction and the request
drains them after commit (:mod:`app.hub.public.cloudfront`). That drain is
best-effort: CloudFront may be unreachable, the process may stop between the
commit and the send. This job is the backstop, so a taken-down page is
evicted within ten minutes whatever happened to the request.

**One verb, no required arguments**, like the other jobs:
``python -m app.hub.public.commands drain``.

**The heartbeat is stamped whatever the outcome**, under
:data:`~app.db.models.HUB_INVALIDATION_JOB`: an empty outbox is the normal
case, and a host with no site distribution has nowhere to send and must not
alert for it. Unsent rows are visible in the heartbeat's counts.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import HUB_INVALIDATION_JOB
from app.db.session import build_engine, session_scope
from app.fees.commands import stamp_heartbeat
from app.fees.generation import GenerationResult as HeartbeatCounts
from app.hub.public import cloudfront, invalidation
from app.hub.public.invalidation import InvalidationClient

__all__ = ["DrainResult", "main", "main_drain", "run_drain"]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DrainResult:
    """What one drain run did.

    :ivar sent: Rows CloudFront accepted
    :ivar pending: Rows still unsent when the run ended
    :ivar failed: Rows a failed batch left unsent
    """

    sent: int
    pending: int
    failed: int


def run_drain(
    session: Session,
    *,
    now: dt.datetime | None = None,
    client: InvalidationClient | None = None,
) -> DrainResult:
    """Send every unsent row, batch by batch, and stamp this job's heartbeat.

    Stops at the first batch that sends nothing while rows wait, so a
    CloudFront outage costs one failed request per run, not one per batch.

    :param session: The session to work through
    :param now: The timestamp for sent rows and the heartbeat; now by default
    :param client: Where batches go; the configured distribution by default
    :return: The run's counts
    """
    stamped = now or dt.datetime.now(tz=dt.UTC)
    target = client or cloudfront.client_from_environment()
    sent = 0
    failed = 0
    if target is None:
        log.info("no site distribution configured; invalidations left unsent")
    else:
        while waiting := invalidation.unsent_count(session):
            batch = invalidation.drain(session, target, stamped)
            if batch == 0:
                failed = waiting
                break
            sent += batch
    result = DrainResult(
        sent=sent, pending=invalidation.unsent_count(session), failed=failed
    )
    stamp_heartbeat(
        session,
        result=HeartbeatCounts(
            cycles_created=result.sent,
            cycles_skipped=result.pending,
            periods_failed=result.failed,
        ),
        job_name=HUB_INVALIDATION_JOB,
        now=stamped,
    )
    return result


def main_drain() -> int:
    """Entry point for ``drain``.

    :return: 0 on completion
    """
    with session_scope(build_engine()) as session:
        result = run_drain(session)

    # Counts only; the paths stay in the table.
    log.info(
        "hub cdn invalidation drain complete",
        extra={"sent": result.sent, "pending": result.pending, "failed": result.failed},
    )
    return 0


def main() -> int:
    """Dispatch the one verb this module carries.

    :return: The command's exit status, or 2 for an unknown verb
    """
    verb = sys.argv[1] if len(sys.argv) > 1 else "drain"
    if verb == "drain":
        return main_drain()

    log.error("unknown command", extra={"verb": verb, "known": "drain"})
    return 2


if __name__ == "__main__":  # pragma: no cover - a process entry point
    sys.exit(main())
