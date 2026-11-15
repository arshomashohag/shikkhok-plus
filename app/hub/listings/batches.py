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
from app.batches.service import _owned_batch
from app.db.models import (
    HUB_ADMISSIONS_VALUES,
    HUB_CLASS_LEVELS,
    HUB_CURRICULA,
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
from app.hub.listings.hide import hide_for_inactive_batch
from app.hub.listings.shared import (
    flush_slug_unique,
    refuse_phone_in,
    refuse_suspended,
    require_slug_shape,
)

__all__ = [
    "BatchListingUpdate",
    "BatchListingView",
    "hide_for_inactive_batch",
    "list_for_owner",
    "publish",
    "unpublish",
    "upsert",
]

#: Nullable text columns, where an empty string clears the value.
_CLEARABLE = ("description_en", "description_bn", "syllabus_en", "syllabus_bn")

_UNIQUE_SLUG = "uq_batch_listing_owner_slug"


@dataclass(frozen=True, slots=True)
class BatchListingUpdate:
    """The columns an owner may edit; ``None`` leaves a column unchanged.

    An empty string clears a nullable text column or the mode/curriculum.

    :ivar slug: The public path segment, unique per owner
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
    """

    slug: str | None = None
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


@dataclass(frozen=True, slots=True)
class BatchListingView:
    """One active batch as the owner's hub page shows it.

    :ivar batch_id: The batch
    :ivar batch_name: Its name
    :ivar subjects: Its subject names
    :ivar listing: Its listing, or None before one is drafted
    :ivar checklist: What the listing still needs
    """

    batch_id: uuid.UUID
    batch_name: str
    subjects: list[str]
    listing: BatchListing | None
    checklist: list[ChecklistItem]


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
    views = []
    for batch, listing in rows:
        subjects = _subjects(session, batch.id)
        views.append(
            BatchListingView(
                batch_id=batch.id,
                batch_name=batch.name,
                subjects=subjects,
                listing=listing,
                checklist=batch_checklist(listing, len(subjects)),
            )
        )
    return views


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
        the first save omits ``show_fee`` or ``show_schedule``, or an edit
        would leave a live listing incomplete
    """
    _owned_batch(session, lens=lens, batch_id=batch_id)
    listing = _locked(session, batch_id)
    if listing is not None:
        refuse_suspended(listing)
    elif changes.show_fee is None or changes.show_schedule is None:
        raise ValidationError(
            code="HUB_BATCH_FLAGS_REQUIRED", message_key="hub.batch_flags_required"
        )

    refuse_phone_in((n, getattr(changes, n)) for n in (*_CLEARABLE, "slug"))
    if changes.slug is not None:
        require_slug_shape(changes.slug)
    _check_vocabulary(changes)

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
    if listing.status != "draft":
        _require_complete(session, listing)
    flush_slug_unique(session, _UNIQUE_SLUG)
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
    batch = _owned_batch(session, lens=lens, batch_id=batch_id)
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
    refuse_phone_in((n, getattr(listing, n)) for n in (*_CLEARABLE, "slug"))
    _require_complete(session, listing)
    listing.status = "published"
    listing.published_at = now
    listing.updated_at = now
    session.commit()
    return listing


def unpublish(
    session: Session, lens: TeacherLens, batch_id: uuid.UUID, now: dt.datetime
) -> BatchListing:
    """Hide a published batch listing; a draft stays a draft.

    :param session: The session
    :param lens: The owner's lens
    :param batch_id: The batch
    :param now: The moment of the change
    :return: The listing
    :raises BatchNotFound: No such batch, or another owner's
    :raises ConflictError: The listing is suspended
    :raises ValidationError: The batch has no listing
    """
    _owned_batch(session, lens=lens, batch_id=batch_id)
    listing = _locked(session, batch_id)
    if listing is None:
        raise ValidationError(
            code="HUB_LISTING_INCOMPLETE",
            message_key="hub.listing_incomplete",
            details={"missing": ",".join(BATCH_REQUIRED)},
        )
    refuse_suspended(listing)
    if listing.status == "published":
        listing.status = "hidden"
        listing.updated_at = now
        session.commit()
    return listing
