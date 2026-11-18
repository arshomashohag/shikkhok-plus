"""Rules the upload service and the library share.

One not-found refusal, one owned-photo lookup and one alt-text check, so
completing an upload and editing a photo's description cannot drift apart.
"""

from __future__ import annotations

import uuid
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.db.models import ListingMedia
from app.errors import AuthorizationError, ValidationError
from app.hub.listings.shared import refuse_phone_in

__all__ = ["ALT_MAX", "clean_alt", "media_not_found", "owned_media"]

#: The longest alt text, in characters, per language [H3 global constraints].
ALT_MAX: Final[int] = 200


def media_not_found() -> AuthorizationError:
    """Build the refusal for a photo that is absent or another owner's.

    The two cases are one answer, a 404, as for a batch: a different
    answer for another owner's photo would let a caller probe which ids
    exist [NFR14.13].

    :return: The error
    """
    return AuthorizationError(
        code="MEDIA_NOT_FOUND", message_key="hub.media.not_found", status=404
    )


def owned_media(
    session: Session, lens: TeacherLens, media_id: uuid.UUID
) -> ListingMedia:
    """Read and lock one of the owner's photos, refusing a withdrawn one.

    :param session: The session
    :param lens: The owner's lens
    :param media_id: The photo
    :return: The photo, locked until the caller's transaction ends
    :raises AuthorizationError: No such photo, another owner's, or withdrawn
    """
    media = session.execute(
        sa.select(ListingMedia)
        .where(ListingMedia.id == media_id, ListingMedia.owner_id == lens.owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if media is None or media.status == "withdrawn":
        raise media_not_found()
    return media


def clean_alt(field: str, value: str) -> str:
    """Check one alt text: present, at most 200 characters, no phone number.

    :param field: ``alt_en`` or ``alt_bn``, named in the refusal
    :param value: The text as sent
    :return: The text, trimmed
    :raises ValidationError: It is blank, too long or carries a phone number
    """
    text = value.strip()
    if not text or len(text) > ALT_MAX:
        raise ValidationError(
            code="MEDIA_ALT_INVALID",
            message_key="hub.media.alt_invalid",
            details={"field": field},
        )
    refuse_phone_in([(field, text)])
    return text
