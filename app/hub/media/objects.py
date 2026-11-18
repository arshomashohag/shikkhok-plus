"""The bucket's deletion outbox, ``media_object_task``.

**Enqueued in the takedown's own transaction** [0043]. :func:`enqueue` adds
rows to the caller's transaction and commits nothing, as the CDN outbox
does: a withdrawal that rolls back leaves no row, and one that commits
cannot lose its row.

**Every prefix names one photo's objects.** :func:`enqueue` refuses any
prefix outside the four shapes the table's CHECK allows, before the
database would, so the error names the caller rather than a constraint.

**The drain** is :func:`app.hub.media.commands.drain`, the module the
host's cron entry runs, which also records the job's heartbeat.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import MediaObjectTask
from app.hub.media.storage import OBJECT_PREFIX

__all__ = ["enqueue"]


def enqueue(session: Session, prefixes: Sequence[str], now: dt.datetime) -> None:
    """Add prefixes to delete to the caller's transaction.

    Commits nothing: the rows commit or roll back with the takedown.

    :param session: The takedown's session, inside its transaction
    :param prefixes: Each one photo's objects; duplicates are written once
    :param now: The moment of the takedown
    :return: None
    :raises ValueError: A prefix wider than one photo's objects
    """
    wanted = list(dict.fromkeys(prefixes))
    for prefix in wanted:
        if not OBJECT_PREFIX.fullmatch(prefix):
            raise ValueError(f"not a photo prefix: {prefix!r}")
    if wanted:
        session.execute(
            sa.insert(MediaObjectTask),
            [{"op": "delete", "prefix": p, "requested_at": now} for p in wanted],
        )
