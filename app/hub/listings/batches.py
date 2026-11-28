"""A batch's public listing: draft, edit, publish, hide.

The owner decides what to publish about each batch. Nothing here makes a
batch public except :func:`publish`, and only under an owner who is already
public [Review Focus 1].
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.batches.service import BatchNotFound, _owned_batch
from app.db.models import (
    HUB_ADMISSIONS_VALUES,
    HUB_CLASS_LEVELS,
    HUB_CURRICULA,
    HUB_MAX_SEATS,
    HUB_TEACHING_MODE_VALUES,
    Batch,
    BatchListing,
    BatchSubject,
    OwnerListing,
)
from app.errors import ConflictError, ValidationError
from app.hub.listings.checklist import (
    BATCH_REQUIRED,
    ChecklistItem,
    batch_checklist,
)
from app.hub.listings.evict import evict_batch
from app.hub.listings.hide import hide_for_inactive_batch
from app.hub.listings.shared import (
    flush_slug_unique,
    refuse_phone_in,
    refuse_suspended,
    require_slug_shape,
)
from app.money import Money

__all__ = [
    "BatchListingUpdate",
    "BatchListingView",
    "hide_for_inactive_batch",
    "list_for_owner",
    "publish",
    "unpublish",
    "upsert",
    "view_one",
]

#: Nullable text columns, where an empty string clears the value. Every one
#: is public text, so every one is scanned for a phone number.
_CLEARABLE = (
    "public_title",
    "description_en",
    "description_bn",
    "syllabus_en",
    "syllabus_bn",
)

_UNIQUE_SLUG = "uq_batch_listing_owner_slug"


@dataclass(frozen=True, slots=True)
class BatchListingUpdate:
    """The columns an owner may edit; ``None`` leaves a column unchanged.

    An empty string clears a nullable text column or the mode/curriculum.

    :ivar slug: The public path segment, unique per owner
    :ivar public_title: The batch's public name, never ``batch.name``
    :ivar description_en: The English description
    :ivar description_bn: The Bangla description
    :ivar syllabus_en: The English syllabus
    :ivar syllabus_bn: The Bangla syllabus
    :ivar class_levels: The class levels taught
    :ivar curriculum: The curriculum
    :ivar subject_tags: Public subject tags
    :ivar mode: How the batch is taught
    :ivar admissions: Whether admissions are open
    :ivar show_fee: Whether the fee is public; required on first save
    :ivar show_schedule: Whether the timetable is public; required on first save
    :ivar show_seats: Whether the seat counts are public; showing them needs
        both counts
    :ivar seat_capacity: How many seats the batch has, 1 to
        :data:`~app.db.models.HUB_MAX_SEATS`
    :ivar seats_free: How many of them are free, 0 to the total
    """

    slug: str | None = None
    public_title: str | None = None
    description_en: str | None = None
    description_bn: str | None = None
    syllabus_en: str | None = None
    syllabus_bn: str | None = None
    class_levels: list[str] | None = None
    curriculum: str | None = None
    subject_tags: list[str] | None = None
    mode: str | None = None
    admissions: str | None = None
    show_fee: bool | None = None
    show_schedule: bool | None = None
    show_seats: bool | None = None
    seat_capacity: int | None = None
    seats_free: int | None = None


@dataclass(frozen=True, slots=True)
class BatchListingView:
    """One active batch as the owner's hub page shows it.

    :ivar batch_id: The batch
    :ivar batch_name: Its name
    :ivar subjects: Its subject names
    :ivar listing: Its listing, or None before one is drafted
    :ivar checklist: What the listing still needs
    :ivar default_fee: The batch's fee, which the page shows only when the
        listing's ``show_fee`` is set
    """

    batch_id: uuid.UUID
    batch_name: str
    subjects: list[str]
    listing: BatchListing | None
    checklist: list[ChecklistItem]
    default_fee: Money | None = None


def _subjects(session: Session, batch_id: uuid.UUID) -> list[str]:
    """Read a batch's subject names.

    :param session: The session
    :param batch_id: The batch
    :return: The names, in a stable order
    """
    return list(
        session.scalars(
            sa.select(BatchSubject.name)
            .where(BatchSubject.batch_id == batch_id)
            .order_by(BatchSubject.name, BatchSubject.id)
        )
    )


def list_for_owner(session: Session, lens: TeacherLens) -> list[BatchListingView]:
    """List every active batch of the owner with its listing state.

    :param session: The session
    :param lens: The owner's lens
    :return: One view per active batch, oldest first
    """
    rows = session.execute(
        sa.select(Batch, BatchListing)
        .outerjoin(BatchListing, BatchListing.batch_id == Batch.id)
        .where(Batch.owner_id == lens.owner_id, Batch.active.is_(True))
        .order_by(Batch.created_at, Batch.id)
    ).all()
    return [_view(session, batch, listing) for batch, listing in rows]


def _view(
    session: Session, batch: Batch, listing: BatchListing | None
) -> BatchListingView:
    """Build one batch's view.

    :param session: The session
    :param batch: The batch
    :param listing: Its listing, or None
    :return: The view
    """
    subjects = _subjects(session, batch.id)
    return BatchListingView(
        batch_id=batch.id,
        batch_name=batch.name,
        subjects=subjects,
        listing=listing,
        checklist=batch_checklist(listing, len(subjects)),
        default_fee=batch.default_fee,
    )


def view_one(
    session: Session, lens: TeacherLens, batch_id: uuid.UUID
) -> BatchListingView:
    """Read one of the owner's batches with its listing state.

    Unlike :func:`list_for_owner` this does not require the batch to be
    active, so the answer to hiding a retired batch's listing can still be
    shown.

    :param session: The session
    :param lens: The owner's lens
    :param batch_id: The batch
    :return: The view
    :raises BatchNotFound: No such batch, or another owner's
    """
    batch = _owned_batch(session, lens=lens, batch_id=batch_id)
    listing = session.execute(
        sa.select(BatchListing)
        .where(BatchListing.batch_id == batch_id)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    return _view(session, batch, listing)


def _locked(session: Session, batch_id: uuid.UUID) -> BatchListing | None:
    """Read a batch's listing, locking it against a concurrent edit.

    :param session: The session
    :param batch_id: The batch
    :return: The listing, or None
    """
    return session.execute(
        sa.select(BatchListing)
        .where(BatchListing.batch_id == batch_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def _check_vocabulary(changes: BatchListingUpdate) -> None:
    """Refuse values outside the closed vocabularies.

    :param changes: The edits
    :raises ValidationError: A value is not in its vocabulary
    """
    bad = (
        (
            changes.class_levels is not None
            and not set(changes.class_levels) <= set(HUB_CLASS_LEVELS)
        )
        or (changes.curriculum not in (None, "", *HUB_CURRICULA))
        or (changes.mode not in (None, "", *HUB_TEACHING_MODE_VALUES))
        or (changes.admissions not in (None, *HUB_ADMISSIONS_VALUES))
    )
    if bad:
        raise ValidationError(
            code="HUB_BATCH_VALUE_INVALID", message_key="hub.batch_value_invalid"
        )


@dataclass(frozen=True, slots=True)
class _Seats:
    """The seat columns a listing will hold once an edit is applied.

    :ivar show: Whether the counts are public
    :ivar capacity: How many seats, or None
    :ivar free: How many are free, or None
    """

    show: bool
    capacity: int | None
    free: int | None


def _seats_after(listing: BatchListing | None, changes: BatchListingUpdate) -> _Seats:
    """Work out the seat columns an edit leaves, refusing counts that cannot hold.

    Called before anything is changed, so a refusal leaves the listing as
    it was. The counts are the owner's own statement and are checked only
    for shape: a total of 1 to :data:`~app.db.models.HUB_MAX_SEATS`, a free
    count from 0 to that total, and both present before they are shown.
    The database holds the same rules as CHECKs [0048].

    :param listing: The listing before the edit, or None for a first save
    :param changes: The edits
    :return: The seat columns after the edit
    :raises ValidationError: The counts are out of range or inconsistent,
        or seats would be shown without both counts
    """
    total = listing.seat_capacity if listing is not None else None
    free = listing.seats_free if listing is not None else None
    show = listing.show_seats if listing is not None else False
    if changes.seat_capacity is not None:
        total = changes.seat_capacity
    if changes.seats_free is not None:
        free = changes.seats_free
    if changes.show_seats is not None:
        show = changes.show_seats
    valid = (
        (total is None or 1 <= total <= HUB_MAX_SEATS)
        and (free is None or (total is not None and 0 <= free <= total))
        and (not show or (total is not None and free is not None))
    )
    if not valid:
        raise ValidationError(
            code="HUB_BATCH_SEATS_INVALID", message_key="hub.batch_seats_invalid"
        )
    return _Seats(show=bool(show), capacity=total, free=free)


def upsert(
    session: Session,
    lens: TeacherLens,
    batch_id: uuid.UUID,
    changes: BatchListingUpdate,
) -> BatchListing:
    """Create or edit the listing of one of this owner's batches.

    :param session: The session
    :param lens: The owner's lens
    :param batch_id: The batch
    :param changes: The edits; ``None`` fields are left alone
    :return: The listing
    :raises BatchNotFound: No such batch, or another owner's
    :raises ConflictError: The listing is suspended or the slug is taken
    :raises ValidationError: A value is malformed or carries a phone number,
        the first save omits ``show_fee`` or ``show_schedule``, the seat
        counts are out of range or inconsistent, or an edit would leave a
        live listing incomplete
    """
    _owned_batch(session, lens=lens, batch_id=batch_id)
    listing = _locked(session, batch_id)
    old_slug: str | None = None
    if listing is not None:
        refuse_suspended(listing)
        old_slug = listing.slug if listing.status == "published" else None
    elif changes.show_fee is None or changes.show_schedule is None:
        raise ValidationError(
            code="HUB_BATCH_FLAGS_REQUIRED", message_key="hub.batch_flags_required"
        )

    refuse_phone_in(
        [(n, getattr(changes, n)) for n in (*_CLEARABLE, "slug")]
        + [("subject_tags", tag) for tag in changes.subject_tags or []]
    )
    if changes.slug is not None:
        require_slug_shape(changes.slug)
    _check_vocabulary(changes)
    seats = _seats_after(listing, changes)

    if listing is None:
        listing = BatchListing(
            batch_id=batch_id,
            owner_id=lens.owner_id,
            show_fee=bool(changes.show_fee),
            show_schedule=bool(changes.show_schedule),
            class_levels=[],
            subject_tags=[],
            admissions="open",
            status="draft",
            show_seats=False,
        )
        session.add(listing)
    if changes.show_fee is not None:
        listing.show_fee = changes.show_fee
    if changes.show_schedule is not None:
        listing.show_schedule = changes.show_schedule
    if changes.slug is not None:
        listing.slug = changes.slug
    for name in _CLEARABLE:
        value = getattr(changes, name)
        if value is not None:
            setattr(listing, name, value or None)
    for name in ("curriculum", "mode"):
        value = getattr(changes, name)
        if value is not None:
            setattr(listing, name, value or None)
    if changes.class_levels is not None:
        listing.class_levels = list(changes.class_levels)
    if changes.subject_tags is not None:
        listing.subject_tags = list(changes.subject_tags)
    if changes.admissions is not None:
        listing.admissions = changes.admissions
    listing.updated_at = dt.datetime.now(tz=dt.UTC)
    # Changing either count stamps when, which the page shows as freshness.
    if (seats.capacity, seats.free) != (listing.seat_capacity, listing.seats_free):
        listing.seats_updated_at = listing.updated_at
    listing.show_seats = seats.show
    listing.seat_capacity = seats.capacity
    listing.seats_free = seats.free
    if listing.status != "draft":
        _require_complete(session, listing)
    flush_slug_unique(session, _UNIQUE_SLUG)
    # A live page's old path now 404s; evict it with the rename.
    if old_slug is not None and listing.slug != old_slug:
        evict_batch(session, lens.owner_id, old_slug, listing.updated_at)
    session.commit()
    return listing


def _require_complete(session: Session, listing: BatchListing) -> None:
    """Refuse a listing that would be live but incomplete.

    :param session: The session
    :param listing: The listing, with any edits applied
    :raises ValidationError: Something required is missing; the edits are
        rolled back
    """
    done = {
        i.key: i.done
        for i in batch_checklist(listing, len(_subjects(session, listing.batch_id)))
    }
    missing = [key for key in BATCH_REQUIRED if not done[key]]
    if missing:
        session.rollback()
        raise ValidationError(
            code="HUB_LISTING_INCOMPLETE",
            message_key="hub.listing_incomplete",
            details={"missing": ",".join(missing)},
        )


def publish(
    session: Session, lens: TeacherLens, batch_id: uuid.UUID, now: dt.datetime
) -> BatchListing:
    """Make a batch's listing public.

    :param session: The session
    :param lens: The owner's lens
    :param batch_id: The batch
    :param now: The moment of publishing
    :return: The published listing
    :raises BatchNotFound: No such batch, or another owner's
    :raises ConflictError: The listing is suspended, the batch is inactive or
        the owner's own listing is not published
    :raises ValidationError: The listing is missing or incomplete
        (``details["missing"]`` lists the keys)
    """
    _owned_batch(session, lens=lens, batch_id=batch_id)
    # Share-lock the batch row, freshly read, so a concurrent retirement
    # cannot commit between the active check and the publish.
    batch = session.execute(
        sa.select(Batch)
        .where(Batch.id == batch_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    ).scalar_one()
    listing = _locked(session, batch_id)
    if listing is None:
        raise ValidationError(
            code="HUB_LISTING_INCOMPLETE",
            message_key="hub.listing_incomplete",
            details={"missing": ",".join(BATCH_REQUIRED)},
        )
    refuse_suspended(listing)
    if not batch.active:
        raise ConflictError(code="HUB_BATCH_INACTIVE", message_key="hub.batch_inactive")
    owner_status = session.execute(
        sa.select(OwnerListing.status).where(OwnerListing.owner_id == lens.owner_id)
    ).scalar_one_or_none()
    if owner_status != "published":
        raise ConflictError(
            code="HUB_OWNER_NOT_PUBLISHED", message_key="hub.owner_not_published"
        )
    refuse_phone_in(
        [(n, getattr(listing, n)) for n in (*_CLEARABLE, "slug")]
        + [("subject_tags", tag) for tag in listing.subject_tags]
    )
    _require_complete(session, listing)
    listing.status = "published"
    listing.published_at = now
    listing.updated_at = now
    session.commit()
    return listing


def unpublish(
    session: Session, lens: TeacherLens, batch_id: uuid.UUID, now: dt.datetime
) -> BatchListing:
    """Hide a published batch listing, evicting its page; a draft stays a draft.

    The batch's photos stay as they are and leave the page through
    ``hub_public_media``; no object is deleted [H3 deviation 4].

    :param session: The session
    :param lens: The owner's lens
    :param batch_id: The batch
    :param now: The moment of the change
    :return: The listing
    :raises BatchNotFound: No such batch, another owner's, or no listing yet
    :raises ConflictError: The listing is suspended
    """
    _owned_batch(session, lens=lens, batch_id=batch_id)
    listing = _locked(session, batch_id)
    if listing is None:
        raise BatchNotFound(code="BATCH_NOT_FOUND", message_key="batch.not_found")
    refuse_suspended(listing)
    if listing.status == "published":
        listing.status = "hidden"
        listing.updated_at = now
        evict_batch(session, lens.owner_id, listing.slug, now)
        session.commit()
    return listing
