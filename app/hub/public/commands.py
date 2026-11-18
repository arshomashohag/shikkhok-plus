"""The container's half of sending CDN invalidations: claim, ack and fail.

Every takedown enqueues the paths to evict in its own transaction
(:mod:`app.hub.public.invalidation`). **Nothing in the container calls
CloudFront** [R8, OPS-4]: the container cannot reach the instance's
credentials, and the one AWS client it builds -- the photo bucket's, in
``app/hub/media/storage.py`` -- runs as a role with no CloudFront permission.
So the host sends, and this module is what it asks:

* ``claim [--limit 50]`` prints one JSON object --
  ``{"caller_reference": ..., "ids": [...], "paths": [...]}`` -- for the
  oldest unsent rows, paths de-duplicated, ``paths`` empty when there is
  nothing to send.
* ``ack --ids 1,2,3 --aws-id <id>`` stamps the rows CloudFront accepted.
* ``fail --ids 1,2,3`` counts a failed attempt; the rows stay unsent and
  the next claim offers them again.

**At most** :data:`MAX_WILDCARDS` **distinct wildcard paths per claim.**
CloudFront refuses a request that would put more than fifteen wildcard paths
in progress on one distribution, and every owner takedown enqueues two. A
claim that offered more would be refused every run, forever, and hold every
newer row behind it. Rows are claimed whole, in id order, and the claim stops
before the row that would cross the cap; one row is one path, so no row can
cross it alone.

**The heartbeat means real progress** [R8a]. The
:data:`~app.db.models.HUB_INVALIDATION_JOB` heartbeat is stamped by a claim
that finds nothing to send and by a successful ``ack`` -- never by a claim
that hands out rows. A sender whose every send fails therefore goes stale
and the freshness check alerts, while an idle one stays fresh.

The host script is ``/usr/local/bin/shikkhokplus-hub-invalidate``, installed
by ``infra/modules/app/user_data.sh.tftpl`` and run every two minutes with
``docker compose exec``. ``claim`` locks nothing: the host script holds a
``flock`` so two runs never overlap, and a row sent twice is a harmless
second eviction.

The work is in :func:`claim`, :func:`ack` and :func:`fail`, which take a
session, so tests drive them without a process.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import HUB_INVALIDATION_JOB
from app.db.session import build_engine, session_scope
from app.fees.commands import stamp_heartbeat
from app.fees.generation import GenerationResult as HeartbeatCounts
from app.hub.public.invalidation import OUTBOX

__all__ = [
    "DEFAULT_LIMIT",
    "MAX_WILDCARDS",
    "Claim",
    "ack",
    "claim",
    "fail",
    "main",
    "parse_ids",
]

log = logging.getLogger(__name__)

#: The most rows one claim offers; well under CloudFront's per-request cap.
DEFAULT_LIMIT: Final[int] = 50

#: The most distinct wildcard paths one claim offers: one under CloudFront's
#: fifteen in progress per distribution, so a single batch always fits.
MAX_WILDCARDS: Final[int] = 14

#: A CloudFront invalidation id: upper-case letters and digits.
_AWS_ID: Final = re.compile(r"[A-Z0-9]{1,64}")


@dataclass(frozen=True, slots=True)
class Claim:
    """One batch offered to the host.

    :ivar caller_reference: A fresh idempotency key for the request
    :ivar ids: The rows the batch covers, oldest first
    :ivar paths: Their paths, each once; empty when nothing waits
    """

    caller_reference: str
    ids: list[int]
    paths: list[str]

    def to_json(self) -> str:
        """Render the line the host script reads.

        :return: One line of JSON
        """
        return json.dumps(
            {
                "caller_reference": self.caller_reference,
                "ids": self.ids,
                "paths": self.paths,
            },
            separators=(",", ":"),
        )


def _stamp(session: Session, sent: int, now: dt.datetime | None) -> None:
    """Record this job's heartbeat for a run that made progress.

    The counts reuse the fee job's columns, as every job does: rows sent by
    this run, rows still waiting, and waiting rows that have failed before.

    :param session: The session to work through
    :param sent: Rows this run stamped as sent
    :param now: The heartbeat timestamp; the real clock by default
    :return: None
    """
    waiting, retrying = session.execute(
        sa.select(
            sa.func.count(),
            sa.func.count().filter(OUTBOX.c.attempts > 0),
        ).where(OUTBOX.c.sent_at.is_(None))
    ).one()
    stamp_heartbeat(
        session,
        result=HeartbeatCounts(
            cycles_created=sent,
            cycles_skipped=int(waiting),
            periods_failed=int(retrying),
        ),
        job_name=HUB_INVALIDATION_JOB,
        now=now,
    )


def _is_wildcard(path: str) -> bool:
    """Say whether CloudFront counts a path as a wildcard path.

    :param path: The path
    :return: True when it ends in ``*``
    """
    return path.endswith("*")


def claim(
    session: Session, *, limit: int = DEFAULT_LIMIT, now: dt.datetime | None = None
) -> Claim:
    """Offer the oldest unsent rows, within the wildcard cap.

    Stamps the heartbeat only when nothing waits [R8a]: a claim that hands
    out rows has sent nothing yet.

    :param session: The session to work through
    :param limit: The most rows to offer
    :param now: The heartbeat timestamp; the real clock by default
    :return: The batch, empty when nothing waits
    """
    rows = session.execute(
        sa.select(OUTBOX.c.id, OUTBOX.c.path)
        .where(OUTBOX.c.sent_at.is_(None))
        .order_by(OUTBOX.c.id)
        .limit(limit)
    ).all()
    ids: list[int] = []
    paths: dict[str, None] = {}
    wildcards: set[str] = set()
    for row in rows:
        path = str(row.path)
        if _is_wildcard(path) and path not in wildcards:
            if len(wildcards) == MAX_WILDCARDS:
                break
            wildcards.add(path)
        ids.append(int(row.id))
        paths[path] = None
    if ids:
        session.rollback()
    else:
        _stamp(session, 0, now)
    return Claim(caller_reference=str(uuid.uuid4()), ids=ids, paths=list(paths))


def ack(
    session: Session,
    ids: Sequence[int],
    aws_id: str,
    now: dt.datetime | None = None,
) -> int:
    """Stamp rows CloudFront accepted, and record this job's heartbeat.

    A successful send is the progress the heartbeat stands for [R8a], so it
    is stamped here even when every row was already stamped by an earlier
    ack.

    :param session: The session to work through
    :param ids: The claimed rows
    :param aws_id: CloudFront's invalidation id
    :param now: The stamp; the real clock by default
    :return: How many unsent rows were stamped
    :raises ValueError: The id is not a CloudFront invalidation id
    """
    if not _AWS_ID.fullmatch(aws_id):
        raise ValueError("not a CloudFront invalidation id")
    stamped = session.execute(
        sa.update(OUTBOX)
        .where(OUTBOX.c.id.in_(list(ids)), OUTBOX.c.sent_at.is_(None))
        .values(sent_at=now or dt.datetime.now(tz=dt.UTC), aws_id=aws_id)
        .returning(OUTBOX.c.id)
    ).all()
    # The heartbeat commits, so the stamp and the heartbeat land together.
    _stamp(session, len(stamped), now)
    return len(stamped)


def fail(session: Session, ids: Sequence[int]) -> int:
    """Count a failed attempt on rows the host could not send.

    The rows stay unsent, so the next claim offers them again.

    :param session: The session to work through
    :param ids: The claimed rows
    :return: How many unsent rows were counted
    """
    counted = session.execute(
        sa.update(OUTBOX)
        .where(OUTBOX.c.id.in_(list(ids)), OUTBOX.c.sent_at.is_(None))
        .values(attempts=OUTBOX.c.attempts + 1)
        .returning(OUTBOX.c.id)
    ).all()
    session.commit()
    # Counts only; the paths stay in the table.
    log.warning(
        "cdn invalidation failed on the host; rows kept for the next claim",
        extra={"rows": len(counted)},
    )
    return len(counted)


def parse_ids(text: str) -> list[int]:
    """Read ``--ids``: positive integers, comma-separated.

    :param text: The argument
    :return: The ids
    :raises argparse.ArgumentTypeError: Anything else
    """
    try:
        ids = [int(part) for part in text.split(",") if part.strip()]
    except ValueError as error:
        raise argparse.ArgumentTypeError("ids are integers") from error
    if not ids or any(i <= 0 for i in ids):
        raise argparse.ArgumentTypeError("ids are positive integers")
    return ids


def _parser() -> argparse.ArgumentParser:
    """Build the three verbs' parser.

    :return: The parser
    """
    parser = argparse.ArgumentParser(prog="python -m app.hub.public.commands")
    verbs = parser.add_subparsers(dest="verb", required=True)
    claiming = verbs.add_parser("claim")
    claiming.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    acking = verbs.add_parser("ack")
    acking.add_argument("--ids", type=parse_ids, required=True)
    acking.add_argument("--aws-id", required=True)
    failing = verbs.add_parser("fail")
    failing.add_argument("--ids", type=parse_ids, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch one verb.

    Only ``claim`` writes to stdout, and only its one JSON line, which the
    host script parses.

    :param argv: The arguments; ``sys.argv[1:]`` by default
    :return: 0 on success, 2 for a usage error
    """
    args = _parser().parse_args(argv)
    if args.verb == "ack" and not _AWS_ID.fullmatch(args.aws_id):
        log.error("ack refused: not a CloudFront invalidation id")
        return 2
    with session_scope(build_engine()) as session:
        if args.verb == "claim":
            sys.stdout.write(claim(session, limit=args.limit).to_json() + "\n")
        elif args.verb == "ack":
            ack(session, args.ids, args.aws_id)
        else:
            fail(session, args.ids)
    return 0


if __name__ == "__main__":  # pragma: no cover - a process entry point
    sys.exit(main())
