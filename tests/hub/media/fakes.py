"""An in-memory :class:`~app.hub.media.storage.MediaStore` for the service tests.

It keeps objects in a dictionary keyed exactly as the bucket is, so a test
can arrange what the sanitiser Lambda would have written and read back what
an approval copied or a drain deleted. It never touches the network.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.errors import TransientError
from app.hub.media.storage import (
    PREVIEW_TTL,
    UPLOAD_TTL,
    SanitiseResult,
    SourceChanged,
    UploadTicket,
    parse_result,
    quarantine_key,
    staged_prefix,
)

__all__ = ["FakeMediaStore", "Stored"]

#: The bucket's regional endpoint, as the real store signs for it.
URL = "https://shikkhokplus-test-media-123456789012.s3.ap-south-1.amazonaws.com/"


@dataclass(frozen=True, slots=True)
class Stored:
    """One object as the fake bucket holds it.

    :ivar body: Its bytes
    :ivar content_type: Its ``Content-Type``
    """

    body: bytes
    content_type: str

    @property
    def etag(self) -> str:
        """The object's ETag as S3 reports it for a single-part PUT.

        :return: The quoted MD5 of the body
        """
        return f'"{hashlib.md5(self.body, usedforsecurity=False).hexdigest()}"'


@dataclass
class FakeMediaStore:
    """A bucket in a dictionary.

    :ivar objects: Every object, by key
    :ivar presigned: The ``(media_id, content_type)`` of each upload signed
    :ivar deleted: Every prefix deleted, in order
    :ivar failing: Prefixes whose deletion raises a transient error
    :ivar delay: Seconds each presign sleeps, to widen a race window
    :ivar copy_delay: Seconds each copy sleeps, to widen a race window
    """

    objects: dict[str, Stored] = field(default_factory=dict)
    presigned: list[tuple[uuid.UUID, str]] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    failing: set[str] = field(default_factory=set)
    delay: float = 0.0
    copy_delay: float = 0.0

    def put_result(self, media_id: uuid.UUID, payload: dict[str, object]) -> None:
        """Arrange what the sanitiser writes, variants first, then the result.

        :param media_id: The photo
        :param payload: The ``result.json`` content
        :return: None
        """
        prefix = staged_prefix(media_id)
        widths = payload.get("widths")
        if payload.get("ok") is True and isinstance(widths, list):
            for width in widths:
                self.objects[f"{prefix}{width}.webp"] = Stored(
                    f"RIFF{width}".encode(), "image/webp"
                )
        self.objects[f"{prefix}result.json"] = Stored(
            json.dumps(payload).encode(), "application/json"
        )

    def restage(self, media_id: uuid.UUID, width: int, body: bytes) -> None:
        """Overwrite one staged variant, as a second post to the form would.

        :param media_id: The photo
        :param width: The variant
        :param body: Its new bytes
        :return: None
        """
        self.objects[f"{staged_prefix(media_id)}{width}.webp"] = Stored(
            body, "image/webp"
        )

    def staged_etags(
        self, media_id: uuid.UUID, widths: Sequence[int]
    ) -> dict[int, str] | None:
        """Read each staged variant's ETag.

        :param media_id: The photo
        :param widths: The variants
        :return: ``{width: etag}``, or None when one is missing
        """
        found: dict[int, str] = {}
        for width in widths:
            stored = self.objects.get(f"{staged_prefix(media_id)}{width}.webp")
            if stored is None:
                return None
            found[width] = stored.etag
        return found

    def presign_upload(self, media_id: uuid.UUID, content_type: str) -> UploadTicket:
        """Sign an upload, recording it.

        :param media_id: The photo
        :param content_type: The declared type
        :return: The ticket
        """
        if self.delay:
            time.sleep(self.delay)
        self.presigned.append((media_id, content_type))
        return UploadTicket(
            media_id=media_id,
            url=URL,
            fields={
                "key": quarantine_key(media_id),
                "Content-Type": content_type,
                "x-amz-meta-declared-type": content_type,
            },
            expires_at=dt.datetime.now(tz=dt.UTC) + UPLOAD_TTL,
        )

    def read_result(self, media_id: uuid.UUID) -> SanitiseResult | None:
        """Read the sanitiser's result, if written.

        :param media_id: The photo
        :return: The result, or None
        """
        stored = self.objects.get(f"{staged_prefix(media_id)}result.json")
        return None if stored is None else parse_result(stored.body)

    def copy_variants(
        self,
        src_prefix: str,
        dst_prefix: str,
        widths: list[int],
        *,
        if_match: Mapping[int, str] | None = None,
    ) -> None:
        """Copy each variant, keeping its content type as CopyObject does.

        :param src_prefix: The source folder
        :param dst_prefix: The destination folder
        :param widths: The variants to copy
        :param if_match: Each width's pinned ETag, or None
        :return: None
        :raises TransientError: A source object is missing
        :raises SourceChanged: A pinned source's ETag differs
        """
        if self.copy_delay:
            time.sleep(self.copy_delay)
        for width in widths:
            source = self.objects.get(f"{src_prefix}{width}.webp")
            if source is None:
                raise TransientError(
                    code="SERVICE_UNAVAILABLE",
                    message_key="error.temporarily_unavailable",
                )
            if if_match is not None and if_match[width] != source.etag:
                raise SourceChanged(f"{src_prefix}{width}.webp")
            self.objects[f"{dst_prefix}{width}.webp"] = source

    def delete_prefix(self, prefix: str) -> None:
        """Delete every object under a prefix, or fail as configured.

        :param prefix: The prefix
        :return: None
        :raises TransientError: The prefix is in :attr:`failing`
        """
        if prefix in self.failing:
            raise TransientError(
                code="SERVICE_UNAVAILABLE", message_key="error.temporarily_unavailable"
            )
        for key in [k for k in self.objects if k.startswith(prefix)]:
            del self.objects[key]
        self.deleted.append(prefix)

    def presign_get(self, key: str) -> str:
        """Sign a preview URL.

        :param key: The object
        :return: A URL naming the key and the five-minute expiry
        """
        return f"{URL}{key}?X-Amz-Expires={int(PREVIEW_TTL.total_seconds())}"
