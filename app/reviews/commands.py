"""The review publication job's cron entry point, and its heartbeat.

``python -m app.reviews.commands publish`` runs
:func:`~app.reviews.publication.publish_due` once, commits, and stamps
``HUB_REVIEW_PUBLISH_JOB``. The host runs it daily at 21:10 UTC (03:10 in
Dhaka) from ``infra/modules/app/user_data.sh.tftpl``; the first run after a
Friday midnight in Dhaka publishes that week's approvals and the rest find
nothing, so a missed run is made good by the next.

**The heartbeat is stamped on every completed run**, after the work
commits and whatever it did -- a run with nothing due, and a run while
reviews are switched off, are both healthy. A run that fails raises before
stamping, and the freshness check alerts once the job goes stale.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.db.models import HUB_REVIEW_PUBLISH_JOB
from app.db.session import build_engine, session_scope
from app.fees.commands import stamp_heartbeat
from app.fees.generation import GenerationResult as HeartbeatCounts
from app.reviews.publication import publish_due

__all__ = ["main", "run_publish"]

log = logging.getLogger(__name__)


def run_publish(session: Session, now: dt.datetime) -> int:
    """Publish what is due, commit it, then stamp this job's heartbeat.

    The heartbeat's counts reuse the fee job's columns, as every job does:
    reviews published, none skipped, and zero failures -- a failing run
    raises rather than counting.

    :param session: The session to work through
    :param now: The moment of the run and the heartbeat's timestamp
    :return: How many reviews were published
    """
    published = publish_due(session, now)
    session.commit()
    stamp_heartbeat(
        session,
        result=HeartbeatCounts(
            cycles_created=published, cycles_skipped=0, periods_failed=0
        ),
        job_name=HUB_REVIEW_PUBLISH_JOB,
        now=now,
    )
    return published


def _parser() -> argparse.ArgumentParser:
    """Build the one verb's parser.

    :return: The parser
    """
    parser = argparse.ArgumentParser(prog="python -m app.reviews.commands")
    verbs = parser.add_subparsers(dest="verb", required=True)
    verbs.add_parser("publish")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one publication.

    :param argv: The arguments; ``sys.argv[1:]`` by default
    :return: 0 on completion
    """
    _parser().parse_args(argv)
    with session_scope(build_engine()) as session:
        published = run_publish(session, dt.datetime.now(tz=dt.UTC))
    # A count only; no review, author or batch reaches this line.
    log.info("hub review publication complete", extra={"published": published})
    return 0


if __name__ == "__main__":  # pragma: no cover - a process entry point
    sys.exit(main())
