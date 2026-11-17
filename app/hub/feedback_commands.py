"""The daily demand question, and its heartbeat [0042].

Asks "Did the hub bring you a student?" of every owner whose first publish
is now 60 or 90 Dhaka days back, through :func:`~app.hub.feedback.ask_due`,
the one place the rule lives.

**One verb, no required arguments**, like the other jobs: it is also what
a person runs by hand after the freshness alert fires. A late run is safe:
the job asks up to seven days late and never asks twice.

**The heartbeat is stamped after the work commits**, under the job's own
name, and whatever the outcome: a day on which nobody is due is the normal
case and must still register as fresh.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import HUB_FEEDBACK_JOB
from app.db.session import build_engine, session_scope
from app.fees.commands import stamp_heartbeat
from app.fees.generation import GenerationResult as HeartbeatCounts
from app.hub.feedback import ask_due
from app.local_time import bangladesh_today

__all__ = ["AskResult", "main", "main_ask", "run_ask"]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AskResult:
    """What one run did.

    :ivar asked: ``(owner, day)`` questions newly asked
    """

    asked: int


def run_ask(
    session: Session,
    *,
    today: dt.date | None = None,
    now: dt.datetime | None = None,
) -> AskResult:
    """Ask everyone due and stamp this job's heartbeat.

    The heartbeat's three counts reuse the fee job's columns, as every job
    does: questions asked, none skipped, and zero failures -- a failing run
    raises rather than counting.

    :param session: The session to work through
    :param today: The Dhaka date to ask for; Bangladesh's today by default
    :param now: When the messages are sent and the heartbeat's timestamp;
        the real clock by default
    :return: The run's count
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    asked = ask_due(session, today or bangladesh_today(moment), now=moment)
    stamp_heartbeat(
        session,
        result=HeartbeatCounts(
            cycles_created=asked, cycles_skipped=0, periods_failed=0
        ),
        job_name=HUB_FEEDBACK_JOB,
        now=now,
    )
    return AskResult(asked=asked)


def main_ask() -> int:
    """Entry point for ``ask``.

    :return: 0 on completion
    """
    with session_scope(build_engine()) as session:
        result = run_ask(session)

    # A count only; no owner, name or slug reaches this line.
    log.info("hub feedback question complete", extra={"asked": result.asked})
    return 0


def main() -> int:
    """Dispatch the one verb this module carries.

    :return: The command's exit status, or 2 for an unknown verb
    """
    verb = sys.argv[1] if len(sys.argv) > 1 else "ask"
    if verb == "ask":
        return main_ask()

    log.error("unknown command", extra={"verb": verb, "known": "ask"})
    return 2


if __name__ == "__main__":  # pragma: no cover - a process entry point
    sys.exit(main())
