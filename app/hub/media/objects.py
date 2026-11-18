"""The bucket's deletion outbox, ``media_object_task``.

**Enqueued in the takedown's own transaction** [0043]. :func:`enqueue` adds
rows to the caller's transaction and commits nothing, as the CDN outbox
does: a withdrawal that rolls back leaves no row, and one that commits
cannot lose its row.

**Every prefix names one photo's objects.** :func:`enqueue` refuses any
prefix outside the four shapes the table's CHECK allows, before the
database would, so the error names the caller rather than a constraint.

**A row is due at its ``requested_at``.** The drain takes only rows whose
``requested_at`` has passed, which is how :func:`enqueue_upload_window`
defers a delete: a photo withdrawn (or its account deleted) while its upload
is still in flight can have its file land, and the sanitiser write
``staged/``, after the first drain found nothing -- the presigned POST stays
valid for ten minutes. So ``quarantine/`` and ``staged/`` are enqueued a
second time, due when the upload window closes.

**The drain** is :func:`app.hub.media.commands.drain`, the module the
host's cron entry runs, which also records the job's heartbeat.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import MediaObjectTask
from app.hub.media.storage import (
    OBJECT_PREFIX,
    RESULT_DEADLINE,
    quarantine_key,
    staged_prefix,
)

__all__ = ["IN_FLIGHT", "UPLOAD_WINDOW", "enqueue", "enqueue_upload_window"]

#: How long after an upload is signed its objects may still appear.
UPLOAD_WINDOW: Final[dt.timedelta] = RESULT_DEADLINE

#: The statuses whose upload may still be landing.
IN_FLIGHT: Final[tuple[str, ...]] = ("awaiting_upload", "processing")


def enqueue(session: Session, prefixes: Sequence[str], now: dt.datetime) -> None:
    """Add prefixes to delete to the caller's transaction.

    Commits nothing: the rows commit or roll back with the takedown.

    :param session: The takedown's session, inside its transaction
    :param prefixes: Each one photo's objects; duplicates are written once
    :param now: The moment of the takedown
    :return: None
    :raises ValueError: A prefix wider than one photo's objects
    """
    _insert(session, prefixes, now)


def _insert(session: Session, prefixes: Sequence[str], due: dt.datetime) -> None:
    """Write delete rows, each due at ``due``.

    :param session: The caller's session
    :param prefixes: The prefixes; duplicates are written once
    :param due: When the drain may take them
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
            [{"op": "delete", "prefix": p, "requested_at": due} for p in wanted],
        )


def enqueue_upload_window(
    session: Session,
    media_id: uuid.UUID,
    created_at: dt.datetime,
    now: dt.datetime,
) -> None:
    """Delete an in-flight upload's objects again once its window closes.

    For a photo leaving the system while its status is in :data:`IN_FLIGHT`
    -- a withdrawal, an account deletion. The caller still enqueues the
    immediate deletes; this adds ``quarantine/{id}`` and ``staged/{id}/``
    due at ``created_at + UPLOAD_WINDOW``, so a file that lands after the
    first drain is deleted all the same. Nothing is added once the window
    has closed. Commits nothing.

    :param session: The caller's session, inside its transaction
    :param media_id: The photo
    :param created_at: When its upload was signed
    :param now: The moment of the takedown
    :return: None
    """
    due = created_at + UPLOAD_WINDOW
    if due > now:
        _insert(session, [quarantine_key(media_id), staged_prefix(media_id)], due)
