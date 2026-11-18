"""The owner's photo library: list, describe, reorder and withdraw.

**A photo that leaves the page is taken down in the same transaction.** An
approved photo is public twice over: at ``/m/{key}/{w}.webp`` and on its
owner's or batch's page, both cached at the edge. :func:`unpublish` clears
its key, enqueues ``public/{key}/`` for deletion and enqueues invalidations
for the ``/m/`` path and the page it was on, all in the caller's
transaction. An alt-text change to an approved photo calls it -- the new
text has not been moderated -- and so does a withdrawal; moderation's hold
(Task 6) can reuse it.

**Withdrawal deletes everything the photo has, including what has not
arrived yet.** Every prefix it might own
is enqueued -- the quarantined original, the staged and archived variants,
and the public copies while approved -- because deleting a prefix that
holds nothing costs one listing, while missing one leaves a photo of a
child in the bucket. A photo withdrawn mid-upload has its quarantine and
staged deletes enqueued a second time, due when its upload window closes
(:func:`~app.hub.media.objects.enqueue_upload_window`).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.batches.service import _owned_batch
from app.db.models import BatchListing, ListingMedia
from app.hub.listings.evict import owner_slug
from app.hub.media import objects
from app.hub.media.shared import clean_alt, media_not_found, owned_media
from app.hub.media.storage import (
    archive_prefix,
    public_prefix,
    quarantine_key,
    staged_prefix,
)
from app.hub.public import invalidation

__all__ = ["list_media", "reorder", "unpublish", "update_alt", "withdraw"]


def _gallery(owner_id: uuid.UUID, batch_id: uuid.UUID | None) -> sa.ColumnElement[bool]:
    """Select one gallery's photos, withdrawn ones excluded.

    :param owner_id: The owner
    :param batch_id: The batch, or None for the owner's own gallery
    :return: The condition
    """
    gallery = (
        ListingMedia.batch_id.is_(None)
        if batch_id is None
        else ListingMedia.batch_id == batch_id
    )
    return sa.and_(
        ListingMedia.owner_id == owner_id,
        gallery,
        ListingMedia.status != "withdrawn",
    )


def _ordered(
    session: Session, owner_id: uuid.UUID, batch_id: uuid.UUID | None
) -> list[ListingMedia]:
    """Read one gallery in its order.

    :param session: The session
    :param owner_id: The owner
    :param batch_id: The batch, or None for the owner's own gallery
    :return: The photos, by position, then age
    """
    return list(
        session.scalars(
            sa.select(ListingMedia)
            .where(_gallery(owner_id, batch_id))
            .order_by(ListingMedia.position, ListingMedia.created_at, ListingMedia.id)
            .execution_options(populate_existing=True)
        )
    )


def list_media(
    session: Session, lens: TeacherLens, batch_id: uuid.UUID | None, now: dt.datetime
) -> list[ListingMedia]:
    """List one of the owner's galleries, every status but withdrawn.

    Uploads still in flight are listed too, so one that holds a quota slot
    can be seen and withdrawn -- until its upload window closes. Then
    nothing can land for it, the next upload withdraws it and takes its
    slot [I3], and the list already leaves it out, so a client counting
    the list counts what the server will.

    :param session: The session
    :param lens: The owner's lens
    :param batch_id: The batch, or None for the owner's own gallery
    :param now: The present moment
    :return: The photos, in gallery order
    :raises BatchNotFound: The batch is absent or another owner's
    """
    if batch_id is not None:
        _owned_batch(session, lens=lens, batch_id=batch_id)
    return [
        media
        for media in _ordered(session, lens.owner_id, batch_id)
        if not _abandoned(media, now)
    ]


def _abandoned(media: ListingMedia, now: dt.datetime) -> bool:
    """Say whether an upload is in flight with its window closed.

    :param media: The photo
    :param now: The present moment
    :return: True for an upload nothing can land for any more
    """
    return (
        media.status in objects.IN_FLIGHT
        and media.created_at <= now - objects.UPLOAD_WINDOW
    )


def _page_paths(session: Session, media: ListingMedia) -> list[str]:
    """Build the paths of the page an approved photo appears on.

    :param session: The session
    :param media: The photo
    :return: The owner's page paths for an owner photo, the batch's for a
        batch photo; none when the page has no slug
    """
    owner = owner_slug(session, media.owner_id)
    if not owner:
        return []
    if media.batch_id is None:
        return invalidation.owner_paths(owner)
    batch = session.execute(
        sa.select(BatchListing.slug).where(BatchListing.batch_id == media.batch_id)
    ).scalar_one_or_none()
    return invalidation.batch_paths(owner, batch) if batch else []


def unpublish(
    session: Session, media: ListingMedia, status: str, now: dt.datetime
) -> None:
    """Take an approved photo off the edge, in the caller's transaction.

    Moves it to ``status`` and clears its key together -- the key exists
    exactly while approved -- then enqueues ``public/{key}/`` for deletion,
    and the ``/m/{key}/*`` path and its page for invalidation. The caller
    commits.

    :param session: The caller's session
    :param media: The photo, locked and approved
    :param status: Where it goes: ``pending_review``, ``withdrawn``,
        ``held`` or ``rejected``
    :param now: The moment of the takedown
    :return: None
    :raises ValueError: The photo is not approved, or ``status`` is
    """
    key = media.public_key
    if media.status != "approved" or key is None or status == "approved":
        raise ValueError("only an approved photo is unpublished")
    media.status = status
    media.public_key = None
    objects.enqueue(session, [public_prefix(key)], now)
    invalidation.enqueue(
        session, [*invalidation.media_paths(key), *_page_paths(session, media)], now
    )


def update_alt(
    session: Session,
    lens: TeacherLens,
    media_id: uuid.UUID,
    *,
    alt_en: str | None,
    alt_bn: str | None,
    now: dt.datetime,
) -> ListingMedia:
    """Change a photo's alt text; an approved photo goes back to review.

    The same text is no change, so a client re-saving an unchanged form
    never takes a public photo down.

    :param session: The session
    :param lens: The owner's lens
    :param media_id: The photo
    :param alt_en: New English alt text, or None to leave it
    :param alt_bn: New Bangla alt text, or None to leave it
    :param now: The moment of the edit
    :return: The photo
    :raises ValidationError: A text is blank, too long or carries a phone
        number
    :raises AuthorizationError: No such photo, another owner's, or withdrawn
    """
    en = None if alt_en is None else clean_alt("alt_en", alt_en)
    bn = None if alt_bn is None else clean_alt("alt_bn", alt_bn)
    media = owned_media(session, lens, media_id)
    changed = (en is not None and en != media.alt_en) or (
        bn is not None and bn != media.alt_bn
    )
    if changed:
        if en is not None:
            media.alt_en = en
        if bn is not None:
            media.alt_bn = bn
        if media.status == "approved":
            unpublish(session, media, "pending_review", now)
    session.commit()
    return media


def reorder(
    session: Session,
    lens: TeacherLens,
    batch_id: uuid.UUID | None,
    ids: Sequence[uuid.UUID],
) -> list[ListingMedia]:
    """Put a gallery's photos in the given order.

    The named photos come first, in the order given; any left out keep
    their order after them. Positions are rewritten through a negative
    detour, because the approved-slot index is checked row by row and a
    plain swap would collide halfway.

    :param session: The session
    :param lens: The owner's lens
    :param batch_id: The batch, or None for the owner's own gallery
    :param ids: The photos in their new order
    :return: The gallery, in its new order
    :raises BatchNotFound: The batch is absent or another owner's
    :raises AuthorizationError: An id is not a photo in this gallery
    """
    if batch_id is not None:
        _owned_batch(session, lens=lens, batch_id=batch_id)
    rows = list(
        session.scalars(
            sa.select(ListingMedia)
            .where(_gallery(lens.owner_id, batch_id))
            .order_by(ListingMedia.position, ListingMedia.created_at, ListingMedia.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    by_id = {media.id: media for media in rows}
    wanted = list(dict.fromkeys(ids))
    if not set(wanted) <= by_id.keys():
        session.rollback()
        raise media_not_found()
    named = set(wanted)
    order = [by_id[i] for i in wanted] + [m for m in rows if m.id not in named]
    for index, media in enumerate(order):
        media.position = -1 - index
    session.flush()
    for index, media in enumerate(order):
        media.position = index
    session.commit()
    return order


def withdraw(
    session: Session, lens: TeacherLens, media_id: uuid.UUID, *, now: dt.datetime
) -> None:
    """Withdraw a photo and enqueue the deletion of every object it has.

    Idempotent: a photo already withdrawn is left as it is.

    :param session: The session
    :param lens: The owner's lens
    :param media_id: The photo
    :param now: The moment of the withdrawal
    :return: None
    :raises AuthorizationError: No such photo, or another owner's
    """
    media = session.execute(
        sa.select(ListingMedia)
        .where(ListingMedia.id == media_id, ListingMedia.owner_id == lens.owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if media is None:
        raise media_not_found()
    if media.status == "withdrawn":
        session.commit()
        return
    in_flight = media.status in objects.IN_FLIGHT
    if media.status == "approved":
        unpublish(session, media, "withdrawn", now)
    else:
        media.status = "withdrawn"
    objects.enqueue(
        session,
        [quarantine_key(media.id), staged_prefix(media.id), archive_prefix(media.id)],
        now,
    )
    if in_flight:
        # The upload may still land after the first drain [Task 4 review].
        objects.enqueue_upload_window(session, media.id, media.created_at, now)
    session.commit()
