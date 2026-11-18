"""The owner's photo editor routes [H3].

**Every route resolves a** :class:`~app.authz.lenses.TeacherLens`, so the
route-enumeration gate needs no allowlist entry and the owner id always
comes from the lens, never from the request.

**Transactions.** Each route runs in the request-scoped session, which the
application rolls back on any exception and on any 4xx/5xx response. The
services commit on their own success paths and roll back on the refusals
that follow a write, so a validation failure leaves no row behind.

**Writes** (upload, complete, edit, reorder) are refused for an owner
whose listing is suspended, with the refusal H1 uses for its edits, and
each consumes the owner's daily listing-edit allowance. **A delete is never
refused for a suspension** [I2]: it only removes content, and a suspension
leaves an approved photo's ``/m/`` URL live, so its owner must still be
able to take it down. It still consumes the allowance. Starting an
upload consumes the daily *upload* allowance instead, inside the service,
so it is counted once. Reading the library is never refused.
"""

from __future__ import annotations

import datetime as dt
import functools
import logging
import uuid
from typing import Annotated, Final

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_session, teacher_lens
from app.auth.ceilings import CeilingChecker
from app.authz.lenses import TeacherLens
from app.db.models import ListingMedia, OwnerListing
from app.errors import TransientError
from app.hub.listings.shared import refuse_suspended
from app.hub.media import library, uploads
from app.hub.media.storage import MediaStore, S3MediaStore, staged_prefix
from app.hub.public.settings import site_url
from app.schemas.errors import ErrorEnvelope
from app.schemas.media import (
    MediaComplete,
    MediaOrder,
    MediaResponse,
    MediaUpdate,
    MediaUploadInit,
    MediaUploadTicket,
)

__all__ = ["media_store", "router"]

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/hub/media", tags=["hub"])

_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    401: {"model": ErrorEnvelope, "description": "No credential, or an expired one."},
    403: {
        "model": ErrorEnvelope,
        "description": "No lens reaches this; absence reads the same.",
    },
    400: {
        "model": ErrorEnvelope,
        "description": "The request is wrong. Fix and resubmit; never retry as-is.",
    },
    404: {"model": ErrorEnvelope, "description": "No such photo or batch of yours."},
    409: {
        "model": ErrorEnvelope,
        "description": "Valid request; current state forbids it. Refetch and decide.",
    },
}

_READ_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    code: _ERRORS[code] for code in (401, 403, 404)
}


@functools.lru_cache(maxsize=1)
def media_store() -> MediaStore:
    """Provide the photo bucket; tests override this dependency.

    One store per process: it caches its client and re-reads the host's
    credentials file itself.

    :return: The real bucket, as the environment configures it
    """
    return S3MediaStore()


def _refuse_suspended_owner(session: Session, lens: TeacherLens) -> None:
    """Refuse a media write while the owner's listing is suspended.

    :param session: The session
    :param lens: The owner's lens
    :raises ConflictError: The listing is suspended (``HUB_LISTING_SUSPENDED``)
    """
    listing = session.execute(
        sa.select(OwnerListing).where(OwnerListing.owner_id == lens.owner_id)
    ).scalar_one_or_none()
    if listing is not None:
        refuse_suspended(listing)


def _begin_write(session: Session, lens: TeacherLens) -> None:
    """Run the checks every non-upload media write starts with.

    :param session: The session
    :param lens: The owner's lens
    :raises ConflictError: The listing is suspended
    :raises CeilingBreach: The owner has used today's edits
    """
    _refuse_suspended_owner(session, lens)
    CeilingChecker(session).check_and_consume_hub_listing(lens.owner_id)


def _thumb_url(store: MediaStore, media: ListingMedia) -> str | None:
    """Build a photo's 320-pixel preview URL.

    :param store: The bucket
    :param media: The photo
    :return: The absolute public URL when approved; a five-minute signed URL
        while pending review; otherwise None. A bucket that cannot sign
        right now costs the preview, not the list.
    """
    if media.status == "approved" and media.public_key:
        return f"{site_url()}/m/{media.public_key}/320.webp"
    if media.status == "pending_review":
        try:
            return store.presign_get(f"{staged_prefix(media.id)}320.webp")
        except TransientError:
            log.warning("media preview unavailable", extra={"media_id": str(media.id)})
    return None


def _response(store: MediaStore, media: ListingMedia) -> MediaResponse:
    """Render one photo.

    :param store: The bucket
    :param media: The photo
    :return: The response
    """
    return MediaResponse(
        id=media.id,
        batch_id=media.batch_id,
        status=media.status,  # type: ignore[arg-type]
        alt_en=media.alt_en,
        alt_bn=media.alt_bn,
        position=media.position,
        width=media.width,
        height=media.height,
        rejection_code=media.rejection_code,
        thumb_url=_thumb_url(store, media),
    )


@router.post("/uploads", response_model=MediaUploadTicket, responses=_ERRORS)
def start_upload(
    body: MediaUploadInit,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[MediaStore, Depends(media_store)],
) -> MediaUploadTicket:
    """Start an upload and sign it.

    Counts against the owner's daily uploads, not their daily edits.

    :param body: The declared type, size and the batch
    :param lens: The owner's lens
    :param session: The request-scoped session
    :param store: The bucket
    :return: The presigned POST
    """
    _refuse_suspended_owner(session, lens)
    ticket = uploads.init_upload(
        session,
        store,
        lens,
        batch_id=body.batch_id,
        content_type=body.content_type,
        byte_size=body.byte_size,
        now=dt.datetime.now(tz=dt.UTC),
    )
    return MediaUploadTicket(
        media_id=ticket.media_id,
        url=ticket.url,
        fields=ticket.fields,
        expires_at=ticket.expires_at,
    )


@router.post("/{media_id}/complete", response_model=MediaResponse, responses=_ERRORS)
def complete_upload(
    media_id: uuid.UUID,
    body: MediaComplete,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[MediaStore, Depends(media_store)],
) -> MediaResponse:
    """Submit an uploaded photo for review once the file has been read.

    Safe to repeat, and safe to poll: before the file has been processed the
    answer is 409 ``MEDIA_NOT_UPLOADED``, and a repeat on a photo already in
    review changes nothing. Neither spends the daily edit allowance; only a
    call that moves the photo to review or rejects it as unreadable does, in
    that call's own transaction.

    :param media_id: The photo
    :param body: Both alt texts
    :param lens: The owner's lens
    :param session: The request-scoped session
    :param store: The bucket
    :return: The photo
    """
    _refuse_suspended_owner(session, lens)
    media = uploads.complete(
        session,
        store,
        lens,
        media_id,
        alt_en=body.alt_en,
        alt_bn=body.alt_bn,
        now=dt.datetime.now(tz=dt.UTC),
        spend=lambda: CeilingChecker(session).consume_hub_listing_in_transaction(
            lens.owner_id
        ),
    )
    return _response(store, media)


@router.get("", response_model=list[MediaResponse], responses=_READ_ERRORS)
def list_photos(
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[MediaStore, Depends(media_store)],
    batch_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[MediaResponse]:
    """List one gallery: the owner's own, or one batch's.

    :param lens: The owner's lens
    :param session: The request-scoped session
    :param store: The bucket
    :param batch_id: The batch; omit for the owner's own gallery
    :return: The photos in gallery order; withdrawn ones, and uploads
        abandoned past their window, excluded
    """
    listed = library.list_media(session, lens, batch_id, dt.datetime.now(tz=dt.UTC))
    return [_response(store, m) for m in listed]


@router.put("/order", response_model=list[MediaResponse], responses=_ERRORS)
def put_order(
    body: MediaOrder,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[MediaStore, Depends(media_store)],
) -> list[MediaResponse]:
    """Put a gallery's photos in the given order.

    :param body: The gallery and the photo ids, first to last
    :param lens: The owner's lens
    :param session: The request-scoped session
    :param store: The bucket
    :return: The gallery in its new order
    """
    _begin_write(session, lens)
    ordered = library.reorder(session, lens, body.batch_id, body.ids)
    return [_response(store, m) for m in ordered]


@router.patch("/{media_id}", response_model=MediaResponse, responses=_ERRORS)
def patch_photo(
    media_id: uuid.UUID,
    body: MediaUpdate,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[MediaStore, Depends(media_store)],
) -> MediaResponse:
    """Change a photo's alt text.

    Changing an approved photo's text sends it back to review, because the
    new text has not been moderated.

    :param media_id: The photo
    :param body: The new text; an omitted field is left alone
    :param lens: The owner's lens
    :param session: The request-scoped session
    :param store: The bucket
    :return: The photo
    """
    _begin_write(session, lens)
    media = library.update_alt(
        session,
        lens,
        media_id,
        alt_en=body.alt_en,
        alt_bn=body.alt_bn,
        now=dt.datetime.now(tz=dt.UTC),
    )
    return _response(store, media)


@router.delete(
    "/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=_ERRORS,
)
def delete_photo(
    media_id: uuid.UUID,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Withdraw a photo; its stored files are deleted, even while suspended.

    :param media_id: The photo
    :param lens: The owner's lens
    :param session: The request-scoped session
    :return: An empty 204
    """
    # No suspension check [I2]: taking a photo down is always allowed.
    CeilingChecker(session).check_and_consume_hub_listing(lens.owner_id)
    library.withdraw(session, lens, media_id, now=dt.datetime.now(tz=dt.UTC))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
