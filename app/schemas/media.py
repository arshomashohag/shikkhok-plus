"""Request and response bodies for the owner's photo editor [H3].

Every response here is the owner's own view of their own photos. The
public pages read approved photos through ``hub_public_media`` and their own
view model, so nothing in this module is served to an anonymous reader, and
nothing in it carries an account id, a phone number or a name.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

__all__ = [
    "MediaComplete",
    "MediaOrder",
    "MediaResponse",
    "MediaUpdate",
    "MediaUploadInit",
    "MediaUploadTicket",
]

MediaStatus = Literal[
    "awaiting_upload",
    "processing",
    "pending_review",
    "approved",
    "rejected",
    "withdrawn",
    "held",
]

#: The three upload types, published in the contract as an enum.
_UPLOAD_TYPES: Final[list[JsonValue]] = ["image/jpeg", "image/png", "image/webp"]

#: The most photos an order may name: the larger gallery's quota, the owner's
#: 12 (a batch holds 8). Clients name the photos that count, never the
#: rejected ones still listed; any left out keep their order after the named.
#: ``tests/hub/media/test_media_routes.py`` asserts it equals ``OWNER_LIMIT``.
_MAX_ORDER: Final[int] = 12


class MediaUploadInit(BaseModel):
    """Start an upload.

    ``content_type`` and ``byte_size`` are checked by the service, not the
    schema, so a disallowed type or size answers ``MEDIA_TYPE_NOT_ALLOWED``
    or ``MEDIA_TOO_LARGE`` -- a message key the client can localize -- and
    not a generic 422. The type set is still published as an enum.

    :ivar batch_id: The batch the photo is for; None for the owner's page
    :ivar content_type: ``image/jpeg``, ``image/png`` or ``image/webp``
    :ivar byte_size: The file's size in bytes, at most 8 MiB
    """

    model_config = ConfigDict(extra="forbid")

    batch_id: uuid.UUID | None = None
    content_type: str = Field(max_length=32, json_schema_extra={"enum": _UPLOAD_TYPES})
    byte_size: int = Field(le=2_147_483_647)


class MediaUploadTicket(BaseModel):
    """What the client needs to post the file straight to the bucket.

    :ivar media_id: The photo the upload is for
    :ivar url: The POST target
    :ivar fields: The form fields to send, in order, before the file
    :ivar expires_at: When the signature stops being accepted
    """

    media_id: uuid.UUID
    url: str
    fields: dict[str, str]
    expires_at: dt.datetime


class MediaComplete(BaseModel):
    """Submit an uploaded photo for review.

    :ivar alt_en: English alt text, at most 200 characters
    :ivar alt_bn: Bangla alt text, at most 200 characters
    """

    model_config = ConfigDict(extra="forbid")

    alt_en: str = Field(max_length=200)
    alt_bn: str = Field(max_length=200)


class MediaUpdate(BaseModel):
    """Change a photo's alt text; an omitted field is left alone.

    :ivar alt_en: New English alt text
    :ivar alt_bn: New Bangla alt text
    """

    model_config = ConfigDict(extra="forbid")

    alt_en: str | None = Field(default=None, max_length=200)
    alt_bn: str | None = Field(default=None, max_length=200)


class MediaOrder(BaseModel):
    """Put one gallery's photos in order.

    :ivar batch_id: The batch; None for the owner's own gallery
    :ivar ids: The photos in their new order, at most 12: the ones that
        count against the quota; any left out follow them in their order
    """

    model_config = ConfigDict(extra="forbid")

    batch_id: uuid.UUID | None = None
    ids: list[uuid.UUID] = Field(max_length=_MAX_ORDER)


class MediaResponse(BaseModel):
    """One of the owner's photos.

    :ivar id: The photo
    :ivar batch_id: The batch it is for; None for the owner's own page
    :ivar status: Where it is in upload and review
    :ivar alt_en: English alt text
    :ivar alt_bn: Bangla alt text
    :ivar position: Its place in its gallery
    :ivar width: The decoded width in pixels
    :ivar height: The decoded height in pixels
    :ivar rejection_code: Why it was rejected, if it was
    :ivar thumb_url: A 320-pixel preview: the public URL once approved, a
        five-minute signed URL while it awaits review, otherwise None
    """

    id: uuid.UUID
    batch_id: uuid.UUID | None
    status: MediaStatus
    alt_en: str | None
    alt_bn: str | None
    position: int
    width: int | None
    height: int | None
    rejection_code: str | None
    thumb_url: str | None
