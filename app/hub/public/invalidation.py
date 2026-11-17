"""The CloudFront invalidation outbox: which paths a takedown evicts, and sending them.

Public owner and batch pages are cached at the edge for up to ten minutes. A
takedown -- a suspension, an unpublish, a retired batch, a withdrawn name
consent, a solo owner's account deletion, a slug change -- changes rows the
pages are read from, and without an invalidation the edge goes on serving
the page until its TTL ends.

**Enqueued in the takedown's own transaction.** :func:`enqueue` adds rows to
the caller's transaction and commits nothing, so a takedown that rolls back
leaves no row and one that commits cannot lose its row [Review Focus 2].

**Drained after commit, best-effort, with a cron backstop.** :func:`drain`
sends every unsent row in one ``CreateInvalidation`` batch and stamps it; a
failure counts an attempt and leaves the row for the next drain. The request
that enqueued drains once its transaction has committed (``app.main``), and
``app.hub.public.commands`` drains every ten minutes.

**No caller writes a path by hand.** CloudFront accepts ``*`` only as a
path's last character, so the paths come from :func:`owner_paths` and
:func:`batch_paths`, one per locale, and :func:`enqueue` refuses anything
else. Every enqueue also carries :data:`SITEMAP_PATH`, which lists what the
takedown removed. A path holds only public slugs.

The outbox is written through a lightweight table construct rather than the
ORM model: this package may not import ``app.db.models``.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import uuid
from collections.abc import Sequence
from typing import Final, Protocol

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.hub.public.messages import LOCALES

__all__ = [
    "MAX_PATH",
    "PENDING_INFO_KEY",
    "SITEMAP_PATH",
    "InvalidationClient",
    "batch_paths",
    "drain",
    "enqueue",
    "has_pending",
    "owner_paths",
    "unsent_count",
]

log = logging.getLogger(__name__)

#: The sitemap, which every takedown changes.
SITEMAP_PATH: Final[str] = "/hub/sitemap.xml"

#: The ``path`` column's width.
MAX_PATH: Final[int] = 300

#: Set on ``Session.info`` by :func:`enqueue`, so the request scope knows
#: this request has rows to drain once it commits.
PENDING_INFO_KEY: Final[str] = "hub_cdn_invalidation_pending"

_OUTBOX: Final = sa.table(
    "cdn_invalidation",
    sa.column("id"),
    sa.column("path"),
    sa.column("requested_at"),
    sa.column("sent_at"),
    sa.column("aws_id"),
    sa.column("attempts"),
)


class InvalidationClient(Protocol):
    """Whatever sends one invalidation batch to the site's distribution."""

    def create_invalidation(self, paths: list[str], caller_reference: str) -> str:
        """Ask the edge to evict paths.

        :param paths: The paths, each valid for CloudFront
        :param caller_reference: The batch's idempotency key: the same key
            with the same paths is the same invalidation
        :return: The invalidation's id
        """
        ...


def owner_paths(slug: str) -> list[str]:
    """Build the paths that evict an owner's page and every batch page under it.

    :param slug: The owner's slug
    :return: One prefix path per locale, each ending in ``*``
    """
    return [f"/hub/{locale}/t/{slug}*" for locale in LOCALES]


def batch_paths(owner_slug: str, batch_slug: str) -> list[str]:
    """Build the paths that evict one batch's page.

    :param owner_slug: The owner's slug
    :param batch_slug: The batch's slug
    :return: One exact path per locale
    """
    return [f"/hub/{locale}/t/{owner_slug}/{batch_slug}" for locale in LOCALES]


def _require_valid(path: str) -> None:
    """Refuse a path CloudFront would reject or the column cannot hold.

    :param path: The path
    :raises ValueError: It is relative, too long, or has an inner wildcard
    """
    if not path.startswith("/"):
        raise ValueError(f"an invalidation path must be absolute: {path!r}")
    if "*" in path[:-1]:
        raise ValueError(
            f"an invalidation path may carry a wildcard only at its end: {path!r}"
        )
    if len(path) > MAX_PATH:
        raise ValueError(f"an invalidation path exceeds {MAX_PATH} characters")


def enqueue(session: Session, paths: Sequence[str], now: dt.datetime) -> None:
    """Add paths, and the sitemap, to the caller's transaction.

    Commits nothing: the rows commit or roll back with the takedown.

    :param session: The takedown's session, inside its transaction
    :param paths: The paths to evict, from :func:`owner_paths` or
        :func:`batch_paths`
    :param now: The moment of the takedown
    :return: None
    :raises ValueError: A path CloudFront would reject
    """
    wanted = list(dict.fromkeys([*paths, SITEMAP_PATH]))
    for path in wanted:
        _require_valid(path)
    session.execute(
        sa.insert(_OUTBOX),
        [{"id": uuid.uuid4(), "path": path, "requested_at": now} for path in wanted],
    )
    session.info[PENDING_INFO_KEY] = True


def has_pending(session: Session) -> bool:
    """Say whether this session enqueued anything.

    :param session: The session
    :return: True once :func:`enqueue` has run in it
    """
    return bool(session.info.get(PENDING_INFO_KEY))


def unsent_count(session: Session) -> int:
    """Count the rows still waiting to be sent.

    :param session: The session
    :return: The count
    """
    count = session.execute(
        sa.select(sa.func.count())
        .select_from(_OUTBOX)
        .where(_OUTBOX.c.sent_at.is_(None))
    ).scalar_one()
    return int(count)


def _caller_reference(ids: Sequence[uuid.UUID]) -> str:
    """Derive a batch's idempotency key from its rows.

    The same rows retried give the same key, so a request CloudFront
    accepted but whose answer was lost is not created twice.

    :param ids: The batch's row ids
    :return: A hex digest
    """
    joined = ",".join(sorted(str(i) for i in ids))
    return hashlib.sha256(joined.encode("ascii")).hexdigest()[:32]


def drain(
    session: Session, client: InvalidationClient, now: dt.datetime, limit: int = 50
) -> int:
    """Send up to ``limit`` unsent rows in one batch and stamp them.

    The rows are locked ``SKIP LOCKED``, so the request's drain and the
    cron's never send the same row twice. On failure each row's ``attempts``
    grows and the row stays for the next drain; the failure is logged by
    class and row count, never raised. Commits either way.

    :param session: A session with no open work of its own
    :param client: Where the batch is sent
    :param now: The timestamp stamped on sent rows
    :param limit: The most rows one batch carries
    :return: How many rows were sent
    """
    rows = session.execute(
        sa.select(_OUTBOX.c.id, _OUTBOX.c.path)
        .where(_OUTBOX.c.sent_at.is_(None))
        .order_by(_OUTBOX.c.requested_at, _OUTBOX.c.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    if not rows:
        session.commit()
        return 0
    ids = [row.id for row in rows]
    paths = list(dict.fromkeys(str(row.path) for row in rows))
    selected = _OUTBOX.c.id.in_(ids)
    try:
        aws_id = client.create_invalidation(paths, _caller_reference(ids))
    except Exception as error:  # noqa: BLE001  best-effort by rule: the row is the retry
        session.execute(
            sa.update(_OUTBOX).where(selected).values(attempts=_OUTBOX.c.attempts + 1)
        )
        session.commit()
        # Counts and the error's class only; the paths stay in the table.
        log.warning(
            "cdn invalidation failed; rows kept for the next drain",
            extra={"rows": len(rows), "error": type(error).__name__},
        )
        return 0
    session.execute(
        sa.update(_OUTBOX).where(selected).values(sent_at=now, aws_id=aws_id)
    )
    session.commit()
    return len(rows)
