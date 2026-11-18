"""Photo moderation: an administrator's decision, and a report's hold.

**Every photo is seen before it is public** [hub spec D7]. An upload waits
in ``pending_review`` until an administrator decides it (:func:`decide`),
previewing it through five-minute signed URLs (:func:`detail`) that name
no account.

**What is reviewed is what is published** [I1]. ``complete`` froze the
sanitised variants into ``archive/{id}/``, pinned to the ETags it read, and
recorded ``archived_at`` (:func:`app.hub.media.uploads.complete`). The
preview and every approval read ``archive/`` only; nothing here reads
``staged/``, so a post to the same form after completion reaches neither
the administrator nor the public. A photo with no freeze recorded is never
published: an approval rejects it as ``unreadable``, in the decision's own
transaction and under its locks.

**Approval publishes from the archive.** It mints a fresh 128-bit key and
copies the frozen variants to ``public/{key}/``, the only prefix CloudFront
serves -- the first time and after an alt-text edit or a hold alike [H3
deviation 3]. A copy that fails changes nothing, and the key it was
copying to is enqueued for deletion, so a partial public copy cannot
linger; so is the key of a copy that succeeded when the commit recording
it then fails (:func:`commit_releasing`).

**And not before its upload window closes** [I1]. Until ``created_at +
UPLOAD_WINDOW`` -- the ten-minute signature, at most five minutes in the
sanitiser's event queue, its thirty seconds and a margin, all pinned by
``tests/gates/test_image_sanitiser.py`` -- a photo is left out of the queue
and an approval is refused. The freeze above is what keeps a re-staged
variant from being published; the window is kept as a second, independent
bound. A rejection is not held back by the window; inside it, it also deletes, once
the window closes, whatever lands after it.

**Rejection deletes everything the photo has**: the quarantined original
(which may not have expired yet), the staged variants and the archive. A
photo waiting or held has no public copy -- a hold already enqueued the
public objects' deletion and the edge invalidation -- and an approved one
is unpublished first, so a rejected photo never keeps a public copy [I2].

**A child-safety or personal-information report holds a photo at once**
[H3 deviation 2, Review Focus 3]. :func:`hold` runs in the report's own
transaction: the photo goes to ``held``, its key is cleared, ``public/{key}/``
is enqueued for deletion and ``/m/{key}/{w}.webp`` and its page for
invalidation, all through :func:`app.hub.media.library.unpublish`. A report that rolls
back leaves the photo approved.

**A decision on a photo report carries to the photo** [R11]
(:func:`settle_report`, in the decision's own transaction). Upholding a
report removes the photo -- approved, held or back in review -- as a
rejection does, with the code mapped from the report reason, and an
approved photo's public copy and paths go with it. Dismissing the report
that holds a photo restores it from the archive under a fresh key, unless
another open child-safety or personal-information report still stands.

**Every act is a closed-vocabulary moderation event** with
``target_kind = 'media'``: ``media_approved``, ``media_rejected`` (its code),
``media_held`` (the report's reason, no actor) and ``media_restored``.
"""

from __future__ import annotations

import datetime as dt
import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.authz.lenses import PlatformAdminLens
from app.db.models import (
    Batch,
    BatchListing,
    HubModerationEvent,
    HubReport,
    ListingMedia,
    OwnerListing,
)
from app.errors import ConflictError, TransientError, ValidationError
from app.hub.media import library, objects
from app.hub.media.objects import UPLOAD_WINDOW
from app.hub.media.quota import lock_owner
from app.hub.media.storage import (
    MediaStore,
    archive_prefix,
    public_prefix,
    quarantine_key,
    staged_prefix,
)
from app.moderation.refusals import admin_not_found
from app.moderation.vocab import (
    HOLD_REASONS,
    MEDIA_REJECTION_CODES,
    REPORT_REJECTION_CODES,
)

__all__ = [
    "DECIDABLE",
    "MEDIA_FIELDS",
    "MediaDetail",
    "MediaPreview",
    "WaitingMedia",
    "commit_releasing",
    "decide",
    "describe",
    "detail",
    "hold",
    "is_public",
    "settle_report",
    "settled",
    "waiting",
]

#: The rejection code for a photo with no frozen variants [I1], as an
#: upload the sanitiser could not read is coded.
UNREADABLE: Final[str] = "unreadable"

#: The statuses an administrator decides: waiting for review, or held.
DECIDABLE: Final[tuple[str, ...]] = ("pending_review", "held")

#: The statuses whose variants exist to preview.
_PREVIEWABLE: Final[tuple[str, ...]] = ("pending_review", "held", "approved")

#: The statuses an upheld report removes a photo from.
_REMOVABLE: Final[tuple[str, ...]] = ("pending_review", "approved", "held")

#: The statuses a decision has already settled.
_DECIDED: Final[tuple[str, ...]] = ("approved", "rejected")

#: What an owner submitted for display with a photo, in queue order.
MEDIA_FIELDS: Final[tuple[str, ...]] = ("alt_en", "alt_bn")

#: A photo's submitted fields: ``(key, value)`` pairs, empty ones left out.
Fields = tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class MediaPreview:
    """One variant an administrator can look at.

    :ivar width: The variant's width in pixels
    :ivar url: A signed GET of the variant, valid for five minutes
    """

    width: int
    url: str


@dataclass(frozen=True, slots=True)
class MediaDetail:
    """One photo as an administrator reviews it, with no account in it.

    :ivar media_id: The photo
    :ivar status: ``pending_review``, ``held`` or ``approved``
    :ivar width: The decoded width in pixels
    :ivar height: The decoded height in pixels
    :ivar previews: One signed URL per variant written
    :ivar alt_en: English alt text
    :ivar alt_bn: Bangla alt text
    :ivar public_name: The owner listing's public name, if it has one
    :ivar public_title: The batch listing's public title, for a batch photo
    :ivar report_count: How many reports name this photo
    """

    media_id: uuid.UUID
    status: str
    width: int | None
    height: int | None
    previews: tuple[MediaPreview, ...]
    alt_en: str | None
    alt_bn: str | None
    public_name: str | None
    public_title: str | None
    report_count: int


@dataclass(frozen=True, slots=True)
class WaitingMedia:
    """One photo waiting for an administrator.

    :ivar media_id: The photo
    :ivar owner_id: Its owner
    :ivar title: Its page's public name or title
    :ivar fields: Its alt texts
    :ivar held_reason: The report reason that held it, when held
    :ivar since: When the wait began: the hold, else the upload
    """

    media_id: uuid.UUID
    owner_id: uuid.UUID
    title: str | None
    fields: Fields
    held_reason: str | None
    since: dt.datetime


def is_public(session: Session, media_id: uuid.UUID) -> bool:
    """Say whether a photo is on a public page, as ``hub_public_media`` does.

    The same predicates as the view, written against the tables because
    the view is the hub reader's alone: approved, under a published owner
    listing, and for a batch photo under that owner's published listing of
    an active batch [0040, 0043].

    :param session: The session
    :param media_id: The photo
    :return: True exactly when the public view shows it
    """
    owner_live = sa.select(OwnerListing.owner_id).where(
        OwnerListing.owner_id == ListingMedia.owner_id,
        OwnerListing.status == "published",
    )
    batch_live = (
        sa.select(BatchListing.batch_id)
        .join(Batch, Batch.id == BatchListing.batch_id)
        .where(
            BatchListing.batch_id == ListingMedia.batch_id,
            BatchListing.owner_id == ListingMedia.owner_id,
            BatchListing.status == "published",
            Batch.active.is_(True),
        )
    )
    found = session.scalar(
        sa.select(ListingMedia.id).where(
            ListingMedia.id == media_id,
            ListingMedia.status == "approved",
            sa.exists(owner_live),
            sa.or_(ListingMedia.batch_id.is_(None), sa.exists(batch_live)),
        )
    )
    return found is not None


def _locked(session: Session, media_id: uuid.UUID) -> ListingMedia | None:
    """Read and lock one photo, fresh from the database.

    :param session: The session
    :param media_id: The photo
    :return: The photo, or None
    """
    return session.execute(
        sa.select(ListingMedia)
        .where(ListingMedia.id == media_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def _event(
    media_id: uuid.UUID,
    event: str,
    *,
    actor: uuid.UUID | None,
    code: str | None,
    correlation_id: str,
    now: dt.datetime,
) -> HubModerationEvent:
    """Build one photo moderation event.

    :param media_id: The photo
    :param event: ``media_approved``, ``media_rejected``, ``media_held`` or
        ``media_restored``
    :param actor: The administrator, or None for a report's hold
    :param code: The rejection code or the report reason
    :param correlation_id: The request that caused it
    :param now: When it happened
    :return: The event, not yet added
    """
    return HubModerationEvent(
        event=event,
        target_kind="media",
        target_id=media_id,
        actor_admin_account_id=actor,
        decision_code=code,
        correlation_id=correlation_id,
        at=now,
    )


def hold(
    session: Session,
    media_id: uuid.UUID,
    *,
    reason: str,
    now: dt.datetime,
    correlation_id: str = "internal",
) -> None:
    """Take a reported photo down, in the reporting transaction.

    Commits nothing: the hold stands or falls with the report. A photo no
    longer approved by the time it is locked -- held by another report a
    moment earlier, or sent back to review -- is left as it is.

    :param session: The report's session
    :param media_id: The photo
    :param reason: The report's reason, recorded on the event
    :param now: The moment of the report
    :param correlation_id: The request that caused it
    :return: None
    """
    media = _locked(session, media_id)
    if media is None or media.status != "approved":
        return
    library.unpublish(session, media, "held", now)
    session.add(
        _event(
            media_id,
            "media_held",
            actor=None,
            code=reason,
            correlation_id=correlation_id,
            now=now,
        )
    )


def _invalid_code() -> ValidationError:
    """Build the refusal for a code that does not fit the decision.

    :return: The error
    """
    return ValidationError(
        code="MEDIA_REJECTION_CODE_INVALID", message_key="hub.report_reason_invalid"
    )


def _already_decided() -> ConflictError:
    """Build the refusal for a photo already approved or rejected.

    :return: The error
    """
    return ConflictError(
        code="MEDIA_ALREADY_DECIDED", message_key="hub.media.already_decided"
    )


def _window_open() -> ConflictError:
    """Build the refusal for approving a photo whose upload may still change.

    :return: The error
    """
    return ConflictError(
        code="MEDIA_UPLOAD_WINDOW_OPEN", message_key="hub.media.not_uploaded"
    )


def _report_open() -> ConflictError:
    """Build the refusal for approving a photo a report still holds.

    :return: The error
    """
    return ConflictError(code="MEDIA_REPORT_OPEN", message_key="hub.media.report_open")


def settled(media: ListingMedia, now: dt.datetime) -> bool:
    """Say whether nothing can write a photo's staged variants any more.

    :param media: The photo
    :param now: The present moment
    :return: True once its upload window has closed [I1]
    """
    return now >= media.created_at + UPLOAD_WINDOW


def _free_position(session: Session, media: ListingMedia) -> int:
    """Pick the photo's slot among its gallery's approved photos.

    Its own position is kept when no approved photo holds it, so an order
    the owner chose survives; otherwise it goes after the last.

    :param session: The session, with the owner row locked
    :param media: The photo being approved
    :return: A position no approved photo in the gallery holds
    """
    gallery = (
        ListingMedia.batch_id.is_(None)
        if media.batch_id is None
        else ListingMedia.batch_id == media.batch_id
    )
    taken = set(
        session.scalars(
            sa.select(ListingMedia.position).where(
                ListingMedia.owner_id == media.owner_id,
                gallery,
                ListingMedia.status == "approved",
                ListingMedia.id != media.id,
            )
        )
    )
    if media.position >= 0 and media.position not in taken:
        return media.position
    return max(taken) + 1


def _publish(
    session: Session, store: MediaStore, media: ListingMedia, now: dt.datetime
) -> str:
    """Copy a photo's frozen variants out under a fresh key; mark it approved.

    Reads ``archive/{id}/`` only [I1]. The caller has checked that the photo
    was frozen, and commits through :func:`commit_releasing` with the key, so
    a commit that fails after the copy leaves no public copy behind.

    :param session: The session, the owner and the photo locked
    :param store: The bucket
    :param media: The photo, waiting or held, frozen
    :param now: The moment of approval
    :return: The fresh key, whose ``public/{key}/`` now holds the variants
    :raises TransientError: A copy failed; the transaction is rolled back,
        and the fresh key's prefix enqueued for deletion and committed
    """
    widths = sorted(media.widths or [])
    key = secrets.token_hex(16)
    try:
        store.copy_variants(archive_prefix(media.id), public_prefix(key), widths)
    except TransientError:
        session.rollback()
        objects.enqueue(session, [public_prefix(key)], now)
        session.commit()
        raise
    media.position = _free_position(session, media)
    media.status = "approved"
    media.public_key = key
    return key


def _unreadable() -> ValidationError:
    """Build the refusal for a photo with no frozen variants [I1].

    :return: The error
    """
    return ValidationError(code="MEDIA_UNREADABLE", message_key="hub.media.unreadable")


def commit_releasing(session: Session, key: str | None, now: dt.datetime) -> None:
    """Commit; if that fails after a copy, enqueue the copy's deletion.

    A key :func:`_publish` copied to is recorded only in the transaction
    being committed. If that commit fails, no later withdrawal or account
    deletion would ever find ``public/{key}/``, so it is enqueued for
    deletion in a transaction of its own, as a failed copy's key is, and
    the commit's error is raised.

    :param session: The session, holding a decision
    :param key: The key copied to in this transaction, or None
    :param now: The moment of the decision
    :return: None
    :raises SQLAlchemyError: The commit failed; the decision is rolled back
    """
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        if key is not None:
            objects.enqueue(session, [public_prefix(key)], now)
            session.commit()
        raise


def _remove(
    session: Session, media: ListingMedia, code: str | None, now: dt.datetime
) -> None:
    """Reject a photo and enqueue the deletion of everything it has.

    An approved photo is unpublished first, which enqueues ``public/{key}/``
    and invalidates ``/m/{key}/{w}.webp`` and its page; the quarantined
    original, the staged variants and the archive follow in every case.

    :param session: The caller's session, the photo locked
    :param media: The photo, waiting, approved or held
    :param code: One of :data:`~app.moderation.vocab.MEDIA_REJECTION_CODES`,
        checked by the caller
    :param now: The moment of the removal
    :return: None
    """
    if media.status == "approved":
        library.unpublish(session, media, "rejected", now)
    else:
        media.status = "rejected"
    media.rejection_code = code
    objects.enqueue(
        session,
        [quarantine_key(media.id), staged_prefix(media.id), archive_prefix(media.id)],
        now,
    )
    # Inside the upload window a file can still land after the first drain.
    objects.enqueue_upload_window(session, media.id, media.created_at, now)


def decide(
    session: Session,
    store: MediaStore,
    lens: PlatformAdminLens,
    media_id: uuid.UUID,
    *,
    approve: bool,
    code: str | None,
    now: dt.datetime,
    correlation_id: str = "internal",
) -> ListingMedia:
    """Approve a photo waiting for review or held, or reject one, and commit.

    A rejection also takes down an approved photo [I2], on a public page or
    not: it is unpublished, its ``public/{key}/`` enqueued for deletion and
    its ``/m/`` paths and page for invalidation, as an upheld report does.

    The owner row is locked first, as an upload does, so two approvals in
    one gallery cannot both take the same free slot.

    :param session: The session
    :param store: The bucket
    :param lens: The administrator's lens
    :param media_id: The photo
    :param approve: True to publish it, False to reject it
    :param code: For a rejection, one of
        :data:`~app.moderation.vocab.MEDIA_REJECTION_CODES`; None to approve
    :param now: The moment of the decision
    :param correlation_id: The request that caused it
    :return: The photo, decided
    :raises ValidationError: A code with an approval, or a rejection without
        one of the five codes
    :raises AuthorizationError: No such photo, or nothing to review: an
        upload still in flight, or a withdrawn photo; or an approval for a
        solo owner whose account has been deleted [R13]
    :raises ConflictError: An approval of a photo already approved, or any
        decision on one already rejected; or an approval while its upload
        window is still open (``MEDIA_UPLOAD_WINDOW_OPEN``) [I1]; or of a
        held photo an open child-safety or personal-information report
        still holds (``MEDIA_REPORT_OPEN``)
    :raises TransientError: The bucket could not copy the variants; nothing
        changed
    """
    fits = code is None if approve else code in MEDIA_REJECTION_CODES
    if not fits:
        raise _invalid_code()
    owner_id = session.scalar(
        sa.select(ListingMedia.owner_id).where(ListingMedia.id == media_id)
    )
    if owner_id is None:
        raise admin_not_found()
    live = lock_owner(session, owner_id)
    media = _locked(session, media_id)
    if approve and not live:
        # A solo owner whose account was deleted while this waited [R13]:
        # nothing is copied out. A rejection still goes ahead, because it
        # only deletes.
        media = None
    # A rejection also reaches an approved photo [I2]: one a suspension or
    # an unpublished page took off the page keeps its /m/ URL live and
    # cannot be reported, so this is the takedown that reaches it.
    allowed = DECIDABLE if approve else _REMOVABLE
    if media is None or media.status not in allowed:
        session.rollback()
        if media is not None and media.status in _DECIDED:
            raise _already_decided()
        raise admin_not_found()

    if approve:
        if not settled(media, now):
            session.rollback()
            raise _window_open()
        if media.status == "held" and _still_held(session, media.id, None):
            # Dismissing the report is what restores a held photo; an
            # approval would undo the hold without anyone deciding it.
            session.rollback()
            raise _report_open()
        if media.archived_at is None:
            # Nothing froze what was completed, so nothing can be shown as
            # reviewed [I1]. Rejected here, under the locks this decision
            # already holds, so no other decision can have won meanwhile.
            _remove(session, media, UNREADABLE, now)
            media.decided_at = now
            session.add(
                _event(
                    media.id,
                    "media_rejected",
                    actor=lens.account_id,
                    code=UNREADABLE,
                    correlation_id=correlation_id,
                    now=now,
                )
            )
            session.commit()
            raise _unreadable()
        event = "media_restored" if media.status == "held" else "media_approved"
        key = _publish(session, store, media, now)
    else:
        event = "media_rejected"
        key = None
        _remove(session, media, code, now)
    media.decided_at = now
    session.add(
        _event(
            media.id,
            event,
            actor=lens.account_id,
            code=code,
            correlation_id=correlation_id,
            now=now,
        )
    )
    commit_releasing(session, key, now)
    return media


def settle_report(
    session: Session,
    store: MediaStore | None,
    lens: PlatformAdminLens,
    media_id: uuid.UUID,
    *,
    upheld: bool,
    reason: str,
    report_id: uuid.UUID,
    now: dt.datetime,
    correlation_id: str = "internal",
) -> str | None:
    """Carry an administrator's decision on a photo report to the photo.

    In the decision's transaction, committing nothing on success. Upheld: a
    photo waiting, approved or held is removed with the code mapped from
    the reason. Dismissed: a held photo is restored under a fresh key once
    no other open holding report names it, and never for a solo owner whose
    account has been deleted [R13]. Anything else is left alone.

    :param session: The decision's session, the report locked
    :param store: The bucket; needed only to restore
    :param lens: The administrator's lens
    :param media_id: The photo the report names
    :param upheld: True to uphold, False to dismiss
    :param reason: The report's reason
    :param report_id: The report being decided, already marked
    :param now: The moment of the decision
    :param correlation_id: The request that caused it
    :return: The fresh key a restore copied to, for the caller to commit
        through :func:`commit_releasing`; None when nothing was copied
    :raises ValueError: A restore is due and no bucket was given
    :raises TransientError: The restore's copy failed; the whole decision
        was rolled back, and the fresh key's prefix enqueued and committed
    """
    owner_id = session.scalar(
        sa.select(ListingMedia.owner_id).where(ListingMedia.id == media_id)
    )
    if owner_id is None:
        return None
    live = lock_owner(session, owner_id)
    media = _locked(session, media_id)
    if media is None:
        return None
    key = None
    if upheld:
        if media.status not in _REMOVABLE:
            return None
        code = REPORT_REJECTION_CODES.get(reason, "other")
        _remove(session, media, code, now)
        event = "media_rejected"
    else:
        # A departed solo owner's photo is never restored [R13]; the
        # dismissal itself still stands.
        if (
            not live
            or media.status != "held"
            or _still_held(session, media_id, report_id)
        ):
            return None
        if store is None:
            raise ValueError("restoring a held photo needs the bucket")
        code = None
        key = _publish(session, store, media, now)
        event = "media_restored"
    media.decided_at = now
    session.add(
        _event(
            media_id,
            event,
            actor=lens.account_id,
            code=code,
            correlation_id=correlation_id,
            now=now,
        )
    )
    return key


def _still_held(
    session: Session, media_id: uuid.UUID, report_id: uuid.UUID | None
) -> bool:
    """Say whether an open report keeps a photo held.

    :param session: The session
    :param media_id: The photo
    :param report_id: The report being dismissed, left out; or None to
        consider every open report
    :return: True when an open child-safety or personal-information report
        (other than ``report_id``) names the photo
    """
    query = sa.select(HubReport.id).where(
        HubReport.target_kind == "media",
        HubReport.target_id == media_id,
        HubReport.status == "open",
        HubReport.reason.in_(sorted(HOLD_REASONS)),
    )
    if report_id is not None:
        query = query.where(HubReport.id != report_id)
    return session.scalar(query.limit(1)) is not None


def _titles(
    session: Session, rows: Sequence[ListingMedia]
) -> dict[uuid.UUID, tuple[str | None, str | None]]:
    """Read the public name and title of the pages some photos are for.

    Only listing fields: an owner's ``public_name`` and a batch's
    ``public_title``, never ``batch.name``, which is the teacher's private
    label.

    :param session: The session
    :param rows: The photos
    :return: ``{media id: (public name, public title)}``
    """
    names = {
        owner_id: name
        for owner_id, name in session.execute(
            sa.select(OwnerListing.owner_id, OwnerListing.public_name).where(
                OwnerListing.owner_id.in_({m.owner_id for m in rows})
            )
        )
    }
    titles = {
        batch_id: title
        for batch_id, title in session.execute(
            sa.select(BatchListing.batch_id, BatchListing.public_title).where(
                BatchListing.batch_id.in_(
                    {m.batch_id for m in rows if m.batch_id is not None}
                )
            )
        )
    }
    return {
        m.id: (
            names.get(m.owner_id),
            titles.get(m.batch_id) if m.batch_id is not None else None,
        )
        for m in rows
    }


def _fields(media: ListingMedia) -> Fields:
    """Read a photo's submitted fields, empty ones left out.

    :param media: The photo
    :return: Its alt texts as ``(key, value)`` pairs
    """
    return tuple(
        (key, value)
        for key in MEDIA_FIELDS
        if (value := getattr(media, key)) and value.strip()
    )


def describe(
    session: Session, media_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, tuple[uuid.UUID, str | None, Fields]]:
    """Describe reported photos for the queue: owner, page title and alt text.

    A batch photo is titled by its batch's public title, an owner photo by
    the owner's public name.

    :param session: The session
    :param media_ids: The photos
    :return: ``{media id: (owner id, title, fields)}`` for those that exist
    """
    rows = list(
        session.scalars(sa.select(ListingMedia).where(ListingMedia.id.in_(media_ids)))
    )
    titles = _titles(session, rows)
    return {
        m.id: (
            m.owner_id,
            titles[m.id][1] if m.batch_id is not None else titles[m.id][0],
            _fields(m),
        )
        for m in rows
    }


def waiting(session: Session, now: dt.datetime) -> list[WaitingMedia]:
    """List the photos an administrator should decide, oldest upload first.

    A photo whose upload window is still open is left out until it closes
    [I1]: it cannot be approved yet, and its preview may still change.

    :param session: The session
    :param now: The present moment
    :return: Photos waiting for review or held after a report
    """
    rows = list(
        session.scalars(
            sa.select(ListingMedia)
            .where(
                ListingMedia.status.in_(DECIDABLE),
                ListingMedia.created_at <= now - UPLOAD_WINDOW,
            )
            .order_by(ListingMedia.created_at, ListingMedia.id)
        )
    )
    described = describe(session, [m.id for m in rows])
    holds: dict[uuid.UUID, tuple[str | None, dt.datetime]] = {}
    for target_id, code, at in session.execute(
        sa.select(
            HubModerationEvent.target_id,
            HubModerationEvent.decision_code,
            HubModerationEvent.at,
        )
        .where(
            HubModerationEvent.event == "media_held",
            HubModerationEvent.target_kind == "media",
            HubModerationEvent.target_id.in_(
                [m.id for m in rows if m.status == "held"]
            ),
        )
        .order_by(HubModerationEvent.at)
    ):
        holds[target_id] = (code, at)
    items = []
    for m in rows:
        owner_id, title, fields = described[m.id]
        reason, since = holds.get(m.id, (None, m.created_at))
        items.append(
            WaitingMedia(
                media_id=m.id,
                owner_id=owner_id,
                title=title,
                fields=fields,
                held_reason=reason,
                since=since,
            )
        )
    return items


def detail(session: Session, store: MediaStore, media_id: uuid.UUID) -> MediaDetail:
    """Read one photo for review, with five-minute previews of its variants.

    Previews come from ``archive/`` only: the variants frozen at completion,
    which are what an approval publishes [I1]. Only the widths the sanitiser
    wrote are signed.

    :param session: The session
    :param store: The bucket
    :param media_id: The photo
    :return: The photo, naming its page but no account
    :raises AuthorizationError: No such photo, or one with nothing to see
    :raises TransientError: The bucket cannot sign right now
    """
    media = session.scalar(sa.select(ListingMedia).where(ListingMedia.id == media_id))
    if media is None or media.status not in _PREVIEWABLE:
        raise admin_not_found()
    previews = tuple(
        MediaPreview(
            width=w, url=store.presign_get(f"{archive_prefix(media.id)}{w}.webp")
        )
        for w in sorted(media.widths or [])
    )
    public_name, public_title = _titles(session, [media])[media.id]
    reported = session.scalar(
        sa.select(sa.func.count())
        .select_from(HubReport)
        .where(HubReport.target_kind == "media", HubReport.target_id == media.id)
    )
    return MediaDetail(
        media_id=media.id,
        status=media.status,
        width=media.width,
        height=media.height,
        previews=previews,
        alt_en=media.alt_en,
        alt_bn=media.alt_bn,
        public_name=public_name,
        public_title=public_title,
        report_count=int(reported or 0),
    )
