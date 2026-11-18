"""The daily refresh of the stored hub badge, and its heartbeat.

The public views cannot read ``enrollment``, so the "Runs classes" badge
is stored on ``owner_listing.runs_classes`` [0040]. A save or a publish
sets it, but the rule moves with the calendar -- attendance ages out of
its thirty-day window and seats leave -- while a listing nobody edits is
never saved. This job recomputes the column for every published listing
from :func:`~app.hub.listings.badge.runs_classes`, the one place the rule
lives, so the view and the editor can never disagree by more than a day.

**One verb, no required arguments**, like the other jobs: it is also what
a person runs by hand after the freshness alert fires.

**The heartbeat is stamped after the work commits**, under the job's own
name, and whatever the outcome: a run that changes nothing is the normal
case and must still register as fresh.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import HUB_BADGE_JOB, OwnerListing
from app.db.session import build_engine, session_scope
from app.fees.commands import stamp_heartbeat
from app.fees.generation import GenerationResult as HeartbeatCounts
from app.hub.listings.badge import runs_classes
from app.local_time import bangladesh_today

__all__ = ["RefreshResult", "main", "main_refresh", "refresh_all", "run_refresh"]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RefreshResult:
    """What one refresh run did.

    :ivar changed: Published listings whose stored badge flipped
    :ivar unchanged: Published listings whose stored badge already held
    """

    changed: int
    unchanged: int


def refresh_all(session: Session, *, today: dt.date | None = None) -> RefreshResult:
    """Recompute the stored badge of every published listing, in one transaction.

    Only published listings are refreshed: nothing else is public, and a
    listing that is published again is recomputed by
    :func:`~app.hub.listings.owner.publish` itself.

    :param session: The session to work through
    :param today: The day to count back from; Bangladesh's today by default
    :return: How many stored values flipped and how many held
    """
    day = today or bangladesh_today()
    rows = session.execute(
        sa.select(OwnerListing.owner_id, OwnerListing.runs_classes)
        .where(OwnerListing.status == "published")
        .order_by(OwnerListing.owner_id)
    ).all()
    changed = 0
    for owner_id, stored in rows:
        earned = runs_classes(session, owner_id, day)
        if earned == stored:
            continue
        session.execute(
            sa.update(OwnerListing)
            .where(OwnerListing.owner_id == owner_id)
            .values(runs_classes=earned)
        )
        changed += 1
    session.commit()
    return RefreshResult(changed=changed, unchanged=len(rows) - changed)


def run_refresh(
    session: Session,
    *,
    today: dt.date | None = None,
    now: dt.datetime | None = None,
) -> RefreshResult:
    """Run one refresh and stamp this job's heartbeat.

    The heartbeat's three counts reuse the fee job's columns, as every job
    does: changed, unchanged, and zero failures -- a failing refresh raises
    rather than counting.

    :param session: The session to work through
    :param today: The day to count back from; Bangladesh's today by default
    :param now: The heartbeat timestamp; the real clock by default
    :return: The run's counts
    """
    result = refresh_all(session, today=today)
    stamp_heartbeat(
        session,
        result=HeartbeatCounts(
            cycles_created=result.changed,
            cycles_skipped=result.unchanged,
            periods_failed=0,
        ),
        job_name=HUB_BADGE_JOB,
        now=now,
    )
    return result


def main_refresh() -> int:
    """Entry point for ``refresh``.

    :return: 0 on completion
    """
    with session_scope(build_engine()) as session:
        result = run_refresh(session)

    # Counts only; no owner, name or slug reaches this line.
    log.info(
        "hub badge refresh complete",
        extra={"changed": result.changed, "unchanged": result.unchanged},
    )
    return 0


def main() -> int:
    """Dispatch the one verb this module carries.

    :return: The command's exit status, or 2 for an unknown verb
    """
    verb = sys.argv[1] if len(sys.argv) > 1 else "refresh"
    if verb == "refresh":
        return main_refresh()

    log.error("unknown command", extra={"verb": verb, "known": "refresh"})
    return 2


if __name__ == "__main__":  # pragma: no cover - a process entry point
    sys.exit(main())
