"""Upload sessions: sign an upload under the quotas, then complete it.

**The bytes never touch the API.** :func:`init_upload` checks the declared
type and size, holds the owner's quota, inserts an ``awaiting_upload`` row
after the last photo in its gallery, and returns a presigned POST that may
write only ``quarantine/{media_id}``.
The client posts the file straight to the bucket; the sanitiser Lambda
re-encodes it and writes ``staged/{media_id}/result.json``.

**Completing reads that result** (:func:`complete`). Before it exists the
answer is ``MEDIA_NOT_UPLOADED`` and nothing changes, so a double tap or a
slow Lambda is retried rather than lost [Review Focus 2]. An unreadable
upload is rejected with ``rejection_code='unreadable'`` and its objects are
enqueued for deletion. A readable one moves to ``pending_review`` carrying
its size and variant widths -- what an approved photo must have
(``ck_listing_media_approved_dimensions``) -- and both alt texts, which are
required, at most 200 characters and phone-scanned like every public text.

**An abandoned upload gives its slot back** [I3]. An upload whose POST
failed, whose app was closed, or whose retry asked for a fresh form is
left ``awaiting_upload`` and would hold a quota slot for ever, since
nothing would call ``complete`` for it again. :func:`init_upload`, under
the owner lock and before it counts, withdraws every one of the owner's
in-flight uploads whose window has closed -- nothing can land for them any
more -- and enqueues their quarantine, staged and archive objects for
deletion, as a withdrawal does. A ``complete`` for one then finds nothing.

**Completion freezes what it read** [I1]. The presigned POST can be
posted to again until it expires, and the sanitiser re-stages whatever
lands. So ``complete`` reads each staged variant's ETag and copies the
variants to ``archive/{id}/`` with ``CopySourceIfMatch`` on them, recording
``archived_at``. The administrator's preview and every approval read
``archive/`` only, so nothing posted after completion reaches either. A
variant that changed between the read and the copy fails closed as
unreadable. ``quarantine/`` and ``staged/`` are then enqueued for deletion,
now, when the upload window closes and at the late-upload backstop. A
result whose variant is missing -- being written again -- is not uploaded
yet.

**No result after twenty minutes is unreadable** [R7c]. The Lambda never
retries, so a timeout or an out-of-memory kill writes nothing, and the API
is the only party that can give the photo an end. Twenty minutes is the
ten-minute POST signature, the Lambda's thirty seconds, and a margin.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.auth.ceilings import CeilingChecker
from app.authz.lenses import TeacherLens
from app.batches.service import _owned_batch
from app.db.models import ListingMedia
from app.errors import ConflictError, TransientError, ValidationError
from app.hub.media import objects, quota
from app.hub.media.shared import clean_alt, media_not_found, owned_media
from app.hub.media.storage import (
    MAX_UPLOAD_BYTES,
    RESULT_DEADLINE,
    UPLOAD_TYPES,
    MediaStore,
    SourceChanged,
    UploadTicket,
    archive_prefix,
    quarantine_key,
    staged_prefix,
)

__all__ = ["RESULT_DEADLINE", "UNREADABLE", "UploadTicket", "complete", "init_upload"]

#: The rejection code for an upload the sanitiser could not decode.
UNREADABLE: Final[str] = "unreadable"

#: The statuses an upload can be completed from.
_IN_FLIGHT: Final[tuple[str, ...]] = ("awaiting_upload", "processing")


def init_upload(
    session: Session,
    store: MediaStore,
    lens: TeacherLens,
    *,
    batch_id: uuid.UUID | None,
    content_type: str,
    byte_size: int,
    now: dt.datetime,
) -> UploadTicket:
    """Start one upload: check, count, insert and sign, then commit.

    :param session: The session
    :param store: The bucket
    :param lens: The owner's lens
    :param batch_id: The batch whose page the photo is for; None for the
        owner's own page
    :param content_type: The declared type
    :param byte_size: The declared size in bytes
    :param now: The moment the upload starts
    :return: The presigned POST
    :raises ValidationError: The type or size is not allowed
    :raises BatchNotFound: The batch is absent or another owner's
    :raises AuthorizationError: ``NO_TEACHER_LENS``: the owner's account was
        deleted while this waited for the owner row [R13]; nothing written.
        Before counting, the owner's abandoned uploads are withdrawn [I3];
        a refusal rolls that back with everything else
    :raises ConflictError: The gallery is full, or today's 30 uploads are
        spent; nothing is counted or written
    :raises TransientError: The bucket cannot be signed for right now;
        nothing is counted or written
    """
    if content_type not in UPLOAD_TYPES:
        raise ValidationError(
            code="MEDIA_TYPE_NOT_ALLOWED", message_key="hub.media.type_not_allowed"
        )
    if not 1 <= byte_size <= MAX_UPLOAD_BYTES:
        raise ValidationError(code="MEDIA_TOO_LARGE", message_key="hub.media.too_large")
    if batch_id is not None:
        _owned_batch(session, lens=lens, batch_id=batch_id)

    if not quota.lock_owner(session, lens.owner_id):
        session.rollback()
        raise quota.owner_departed()
    try:
        _withdraw_abandoned(session, lens.owner_id, now)
        quota.require_room(session, lens.owner_id, batch_id)
        CeilingChecker(session).consume_hub_media(lens.owner_id, now)
        media = ListingMedia(
            id=uuid.uuid4(),
            owner_id=lens.owner_id,
            batch_id=batch_id,
            status="awaiting_upload",
            content_type=content_type,
            byte_size=byte_size,
            position=_next_position(session, lens.owner_id, batch_id),
            created_at=now,
        )
        session.add(media)
        session.flush()
        ticket = store.presign_upload(media.id, content_type)
    except (ConflictError, TransientError):
        # The count, the row and the lock go together.
        session.rollback()
        raise
    session.commit()
    return ticket


def _next_position(
    session: Session, owner_id: uuid.UUID, batch_id: uuid.UUID | None
) -> int:
    """Pick a new upload's place: after the last photo in its gallery.

    Read under the owner lock, so two uploads cannot take the same place.
    A withdrawn photo is no longer in the gallery and does not count.

    :param session: The upload's session, the owner locked
    :param owner_id: The owner
    :param batch_id: The batch, or None for the owner's own gallery
    :return: ``max(position) + 1``, or 0 for an empty gallery
    """
    gallery = (
        ListingMedia.batch_id.is_(None)
        if batch_id is None
        else ListingMedia.batch_id == batch_id
    )
    last = session.scalar(
        sa.select(sa.func.max(ListingMedia.position)).where(
            ListingMedia.owner_id == owner_id,
            gallery,
            ListingMedia.status != "withdrawn",
        )
    )
    return 0 if last is None else int(last) + 1


def _withdraw_abandoned(
    session: Session, owner_id: uuid.UUID, now: dt.datetime
) -> None:
    """Withdraw the owner's uploads that can no longer land [I3].

    Every in-flight row of the owner's, in any gallery, signed at least
    :data:`~app.hub.media.objects.UPLOAD_WINDOW` ago. Call with the owner
    row locked: the photo rows are locked after it, the order every photo
    write takes [R13]. Commits nothing.

    :param session: The upload's session
    :param owner_id: The owner, locked
    :param now: The moment of the upload
    :return: None
    """
    abandoned = list(
        session.scalars(
            sa.select(ListingMedia)
            .where(
                ListingMedia.owner_id == owner_id,
                ListingMedia.status.in_(objects.IN_FLIGHT),
                ListingMedia.created_at <= now - objects.UPLOAD_WINDOW,
            )
            .order_by(ListingMedia.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    for media in abandoned:
        media.status = "withdrawn"
    objects.enqueue(
        session,
        [
            prefix
            for media in abandoned
            for prefix in (
                quarantine_key(media.id),
                staged_prefix(media.id),
                # A completion whose freeze failed part-way may have left one.
                archive_prefix(media.id),
            )
        ],
        now,
    )
    session.flush()


def _reject_unreadable(
    session: Session,
    media: ListingMedia,
    now: dt.datetime,
    spend: Callable[[], None] | None,
) -> ValidationError:
    """Reject an upload the sanitiser could not decode, and commit.

    Its quarantined original, anything staged and any partial archive are
    enqueued for deletion in the same commit, again when the upload window
    closes and at the late-upload backstop.

    :param session: The session
    :param media: The locked photo
    :param now: The moment of the decision
    :param spend: Called before the commit, to count the change; or None
    :return: The refusal for the caller to raise
    """
    if spend is not None:
        spend()
    media.status = "rejected"
    media.rejection_code = UNREADABLE
    objects.enqueue(session, [archive_prefix(media.id)], now)
    _release_staged(session, media, now)
    session.commit()
    return _unreadable()


def _unreadable() -> ValidationError:
    """Build the refusal for an upload that is not a readable image.

    :return: The error
    """
    return ValidationError(code="MEDIA_UNREADABLE", message_key="hub.media.unreadable")


def complete(
    session: Session,
    store: MediaStore,
    lens: TeacherLens,
    media_id: uuid.UUID,
    *,
    alt_en: str,
    alt_bn: str,
    now: dt.datetime,
    spend: Callable[[], None] | None = None,
) -> ListingMedia:
    """Submit an uploaded photo for review once the sanitiser has read it.

    Idempotent: a photo already past upload is returned unchanged, and one
    already found unreadable is refused again without a second enqueue.

    :param session: The session
    :param store: The bucket
    :param lens: The owner's lens
    :param media_id: The photo
    :param alt_en: English alt text
    :param alt_bn: Bangla alt text
    :param now: The moment of the call, measured against the upload's start
    :param spend: Called in the transaction of a call that changes the photo's
        state (to review, or to rejected-unreadable), just before the commit,
        so the count and the change stand or fall together. A refusal that
        changes nothing, and a repeat, never call it.
    :return: The photo
    :raises ValidationError: An alt text is blank, too long or carries a
        phone number; or the upload is unreadable (``MEDIA_UNREADABLE``)
    :raises AuthorizationError: No such photo, another owner's, withdrawn, or
        its solo owner's account deleted [R13]
    :raises ConflictError: The sanitiser has not written its result yet
    :raises TransientError: The bucket cannot be read right now
    """
    texts = clean_alt("alt_en", alt_en), clean_alt("alt_bn", alt_bn)
    # The owner first, then the photo, as an upload, an approval and an
    # account deletion take them [R13].
    if not quota.lock_owner(session, lens.owner_id):
        session.rollback()
        raise media_not_found()
    media = owned_media(session, lens, media_id)
    if media.status == "rejected" and media.rejection_code == UNREADABLE:
        session.rollback()
        raise _unreadable()
    if media.status not in _IN_FLIGHT:
        session.commit()
        return media

    result = store.read_result(media.id)
    if result is None:
        if now - media.created_at > RESULT_DEADLINE:
            raise _reject_unreadable(session, media, now, spend)
        session.rollback()
        raise ConflictError(
            code="MEDIA_NOT_UPLOADED", message_key="hub.media.not_uploaded"
        )
    if not result.ok:
        raise _reject_unreadable(session, media, now, spend)
    widths = list(result.widths)
    pins = store.staged_etags(media.id, widths)
    if pins is None:
        # A variant is missing: the sanitiser is writing this upload again,
        # or -- past the deadline, when nothing can write it -- never will.
        if now - media.created_at > RESULT_DEADLINE:
            raise _reject_unreadable(session, media, now, spend)
        session.rollback()
        raise ConflictError(
            code="MEDIA_NOT_UPLOADED", message_key="hub.media.not_uploaded"
        )

    try:
        # Freeze: archive/ now holds exactly the variants read above.
        store.copy_variants(
            staged_prefix(media.id), archive_prefix(media.id), widths, if_match=pins
        )
    except SourceChanged:
        # The form was posted to again between the reads and the copy.
        raise _reject_unreadable(session, media, now, spend) from None
    except TransientError:
        session.rollback()
        raise

    if spend is not None:
        spend()
    media.status = "pending_review"
    media.width = result.width
    media.height = result.height
    media.widths = widths
    media.archived_at = now
    media.alt_en, media.alt_bn = texts
    _release_staged(session, media, now)
    session.commit()
    return media


def _release_staged(session: Session, media: ListingMedia, now: dt.datetime) -> None:
    """Enqueue an upload's quarantine and staged objects for deletion.

    Now, when its upload window closes, and at the late-upload backstop
    (:func:`~app.hub.media.objects.enqueue_upload_window`): nothing reads
    them after completion, and a post to the same form that lands later
    must not keep private bytes for ``staged/``'s thirty days. Commits
    nothing.

    :param session: The caller's session
    :param media: The photo
    :param now: The moment of the decision
    :return: None
    """
    objects.enqueue(session, [quarantine_key(media.id), staged_prefix(media.id)], now)
    objects.enqueue_upload_window(session, media.id, media.created_at, now)
