"""The photo bucket's deletion drain, and the cron entry point that runs it.

``python -m app.hub.media.commands drain [--limit 50]`` deletes the pending
prefixes in ``media_object_task``, which takedowns fill through
:func:`app.hub.media.objects.enqueue`.
The host runs it every two minutes inside the running container with
``docker compose exec`` -- never a new container every two minutes on a
2 GB host -- from ``infra/modules/app/user_data.sh.tftpl``, under a
``flock`` so two runs never overlap. The container reaches the bucket with
the host-refreshed media-role credentials, the only AWS credentials it has.

**The drain** (:func:`drain`) deletes up to ``limit`` pending prefixes that
are due -- ``requested_at`` passed; see
:func:`~app.hub.media.objects.enqueue_upload_window` -- least-failed and
then oldest first, so a prefix that keeps failing never starves the rows
behind it. A deleted prefix is stamped ``done_at``; a failed one counts an
attempt and is logged, and the next run tries it again. Rows are claimed
``FOR UPDATE SKIP LOCKED``, so two overlapping runs never take the same
prefix.

**The heartbeat means progress** [R8a]. ``HUB_MEDIA_OBJECT_JOB`` is stamped
by a drain that found nothing to do and by one that finished at least one
deletion -- never by a run whose every deletion failed. A drain that cannot
reach the bucket therefore goes stale in thirty minutes and the freshness
check alerts, while an idle one stays fresh. The heartbeat is written here,
in the module the cron entry runs, which ``tests/gates/test_scheduled_jobs.py``
requires of every job.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import HUB_MEDIA_OBJECT_JOB, MediaObjectTask
from app.db.session import build_engine, session_scope
from app.errors import TransientError
from app.fees.commands import stamp_heartbeat
from app.fees.generation import GenerationResult as HeartbeatCounts
from app.hub.media.storage import MediaStore, S3MediaStore

__all__ = ["DEFAULT_LIMIT", "drain", "main"]

log = logging.getLogger(__name__)

#: The most prefixes one drain deletes.
DEFAULT_LIMIT: Final[int] = 50


def _stamp(session: Session, done: int, now: dt.datetime) -> None:
    """Record the heartbeat for a drain that made progress; commits.

    The counts reuse the fee job's columns, as every job does: prefixes
    deleted by this run, prefixes still waiting, and waiting prefixes that
    have failed before.

    :param session: The drain's session
    :param done: Prefixes this run deleted
    :param now: The heartbeat timestamp
    :return: None
    """
    waiting, retrying = session.execute(
        sa.select(
            sa.func.count(),
            sa.func.count().filter(MediaObjectTask.attempts > 0),
        ).where(MediaObjectTask.done_at.is_(None))
    ).one()
    stamp_heartbeat(
        session,
        result=HeartbeatCounts(
            cycles_created=done,
            cycles_skipped=int(waiting),
            periods_failed=int(retrying),
        ),
        job_name=HUB_MEDIA_OBJECT_JOB,
        now=now,
    )


def drain(
    session: Session, store: MediaStore, now: dt.datetime, limit: int = DEFAULT_LIMIT
) -> int:
    """Delete pending prefixes from the bucket.

    :param session: The drain's session
    :param store: The bucket
    :param now: The moment stamped on finished rows and the heartbeat
    :param limit: The most prefixes to try
    :return: How many prefixes were deleted
    """
    rows = session.execute(
        sa.select(MediaObjectTask.id, MediaObjectTask.prefix)
        .where(
            MediaObjectTask.done_at.is_(None),
            # A deferred row waits for its upload window to close.
            MediaObjectTask.requested_at <= now,
        )
        .order_by(MediaObjectTask.attempts, MediaObjectTask.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    if not rows:
        _stamp(session, 0, now)
        return 0
    done = 0
    for task_id, prefix in rows:
        try:
            store.delete_prefix(prefix)
        except TransientError:
            session.execute(
                sa.update(MediaObjectTask)
                .where(MediaObjectTask.id == task_id)
                .values(attempts=MediaObjectTask.attempts + 1)
            )
            # The prefix names a photo id or a public key, never a person.
            log.warning(
                "media object delete failed; kept for the next drain",
                extra={"task": task_id, "prefix": prefix},
            )
            continue
        session.execute(
            sa.update(MediaObjectTask)
            .where(MediaObjectTask.id == task_id)
            .values(done_at=now)
        )
        done += 1
    if done:
        # The heartbeat commits, so the stamps and the heartbeat land together.
        _stamp(session, done, now)
    else:
        session.commit()
    return done


def _limit(text: str) -> int:
    """Read ``--limit``: a positive integer.

    :param text: The argument
    :return: The limit
    :raises argparse.ArgumentTypeError: Anything else
    """
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("the limit is an integer") from error
    if value <= 0:
        raise argparse.ArgumentTypeError("the limit is positive")
    return value


def _parser() -> argparse.ArgumentParser:
    """Build the one verb's parser.

    :return: The parser
    """
    parser = argparse.ArgumentParser(prog="python -m app.hub.media.commands")
    verbs = parser.add_subparsers(dest="verb", required=True)
    draining = verbs.add_parser("drain")
    draining.add_argument("--limit", type=_limit, default=DEFAULT_LIMIT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one drain.

    :param argv: The arguments; ``sys.argv[1:]`` by default
    :return: 0; a failed deletion is retried by the next run and shows in
        the heartbeat, not the exit status
    """
    args = _parser().parse_args(argv)
    store = S3MediaStore()
    with session_scope(build_engine()) as session:
        done = drain(session, store, dt.datetime.now(tz=dt.UTC), limit=args.limit)
    log.info("media object drain finished", extra={"deleted": done})
    return 0


if __name__ == "__main__":  # pragma: no cover - a process entry point
    sys.exit(main())
