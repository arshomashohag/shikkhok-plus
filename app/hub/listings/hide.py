"""Hiding a batch's listing when the batch is retired.

Kept apart from :mod:`app.hub.listings.batches` so the batch service can call
it without importing a module that imports the batch service.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import BatchListing

__all__ = ["hide_for_inactive_batch"]


def hide_for_inactive_batch(session: Session, batch_id: uuid.UUID) -> None:
    """Hide a published listing whose batch has been retired.

    Draft, hidden and suspended listings are left as they are, and bringing
    the batch back never republishes: that is the owner's act. The caller
    commits, so the hide shares the batch edit's transaction.

    :param session: The session, inside the caller's transaction
    :param batch_id: The retired batch
    :return: None
    """
    session.execute(
        sa.update(BatchListing)
        .where(BatchListing.batch_id == batch_id, BatchListing.status == "published")
        .values(status="hidden", updated_at=dt.datetime.now(tz=dt.UTC))
    )
