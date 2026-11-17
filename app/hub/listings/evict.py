"""Turning a listing takedown into the edge-cache paths it must evict.

Each takedown in this package calls one of these inside its own transaction,
so the invalidation rows commit with it or not at all. The paths come from
:mod:`app.hub.public.invalidation`; nothing here writes one by hand.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import OwnerListing
from app.hub.public import invalidation

__all__ = ["evict_batch", "evict_owner", "owner_slug"]


def owner_slug(session: Session, owner_id: uuid.UUID) -> str | None:
    """Read an owner's listing slug.

    :param session: The session
    :param owner_id: The owner
    :return: The slug, or None when the owner has no listing or no slug
    """
    return session.execute(
        sa.select(OwnerListing.slug).where(OwnerListing.owner_id == owner_id)
    ).scalar_one_or_none()


def evict_owner(session: Session, slug: str | None, now: dt.datetime) -> None:
    """Enqueue an owner's page and every batch page under it.

    :param session: The takedown's session
    :param slug: The owner's slug as the edge knows it; None evicts nothing
    :param now: The moment of the takedown
    :return: None
    """
    if slug:
        invalidation.enqueue(session, invalidation.owner_paths(slug), now)


def evict_batch(
    session: Session, owner_id: uuid.UUID, batch_slug: str | None, now: dt.datetime
) -> None:
    """Enqueue one batch's page, under its owner's current slug.

    :param session: The takedown's session
    :param owner_id: The batch's owner
    :param batch_slug: The batch's slug as the edge knows it; None evicts
        nothing
    :param now: The moment of the takedown
    :return: None
    """
    owner = owner_slug(session, owner_id)
    if owner and batch_slug:
        invalidation.enqueue(session, invalidation.batch_paths(owner, batch_slug), now)
