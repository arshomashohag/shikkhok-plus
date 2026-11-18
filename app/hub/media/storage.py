"""The photo bucket: the one module that talks to S3.

Everything else in the media service reaches the bucket through the
:class:`MediaStore` protocol, so the services are tested against an
in-memory fake and **boto3 is imported here and nowhere else**, which
``tests/gates/test_boto3_confined.py`` asserts [H3 global constraints].

**The bucket's layout** [0043, H3 deviation 3]. An upload lands at
``quarantine/{media_id}``; the sanitiser Lambda writes WebP variants and a
``result.json`` under ``staged/{media_id}/``; approval copies the variants
to ``public/{public_key}/`` (the only prefix CloudFront serves) and
``archive/{media_id}/``. The four helpers below build those names, and
:data:`OBJECT_PREFIX` is the one shape check, mirroring
``ck_media_object_task_prefix``: no prefix wider than one photo's objects is
ever deleted.

**Credentials are re-read when the host rewrites them** [Task 2 review].
The container holds no AWS credentials of its own: a host job assumes the
media role every 15 minutes and writes one-hour credentials to the file at
``AWS_SHARED_CREDENTIALS_FILE``, mounted read-only. botocore's own
shared-file provider reads that file once per session and never again, so a
long-lived client would sign with expired keys an hour after start-up. This
store reads the file on every operation -- it is a few hundred bytes -- and
builds a new client whenever its content differs from the last one's, with
the keys passed explicitly so no other provider in the chain is consulted.
A missing or unreadable file is a :class:`~app.errors.TransientError` at
once: the container sets ``AWS_EC2_METADATA_DISABLED``, and nothing here
falls back to the instance metadata service, which hop limit 1 would make
hang rather than refuse.

**Signed for the regional endpoint, virtual-hosted.** Presigned POST and
GET URLs are ``https://{bucket}.s3.{region}.amazonaws.com/...``, the one
host the web and admin CSPs admit (``web/vite.config.ts``,
``web/vite.admin.config.ts``). The upload is a CORS simple request -- a
plain ``fetch`` of ``FormData`` -- so the POST policy asks for no header.

**No bucket configured** (local development, the rehearsal host): an upload
answers a transient error, and a delete is logged and skipped, so the drain
does not fail forever on a host that has no bucket to delete from.
"""

from __future__ import annotations

import configparser
import datetime as dt
import json
import logging
import os
import re
import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol, TypeVar

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.errors import TransientError

__all__ = [
    "MAX_UPLOAD_BYTES",
    "OBJECT_PREFIX",
    "PREVIEW_TTL",
    "UPLOAD_TTL",
    "UPLOAD_TYPES",
    "VARIANT_WIDTHS",
    "MediaStore",
    "S3MediaStore",
    "SanitiseResult",
    "UploadTicket",
    "archive_prefix",
    "parse_result",
    "public_prefix",
    "quarantine_key",
    "staged_prefix",
]

log = logging.getLogger(__name__)

#: The three upload types; the sanitiser checks magic bytes against them.
UPLOAD_TYPES: Final[frozenset[str]] = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)

#: The largest upload, 8 MiB, enforced by S3 through the POST policy.
MAX_UPLOAD_BYTES: Final[int] = 8_388_608

#: How long a presigned POST stays valid.
UPLOAD_TTL: Final[dt.timedelta] = dt.timedelta(minutes=10)

#: How long a presigned preview GET stays valid.
PREVIEW_TTL: Final[dt.timedelta] = dt.timedelta(minutes=5)

#: The WebP variant widths the sanitiser may write.
VARIANT_WIDTHS: Final[tuple[int, ...]] = (320, 960, 1600)

#: The largest ``result.json`` read; the sanitiser's is under 100 bytes.
_MAX_RESULT_BYTES: Final[int] = 4096

_UUID: Final[str] = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

#: The four deletable shapes, exactly ``ck_media_object_task_prefix``.
OBJECT_PREFIX: Final = re.compile(
    rf"quarantine/{_UUID}|(?:staged|archive)/{_UUID}/|public/[0-9a-f]{{32}}/"
)

#: A folder variants are copied from or to.
_VARIANT_FOLDER: Final = re.compile(
    rf"(?:staged|archive)/{_UUID}/|public/[0-9a-f]{{32}}/"
)

#: An object an administrator or owner may preview: one variant, unpublished.
_PREVIEW_KEY: Final = re.compile(rf"(?:staged|archive)/{_UUID}/(?:320|960|1600)\.webp")

#: An AWS region name.
_REGION: Final = re.compile(r"[a-z]{2}(?:-[a-z]+)+-[0-9]")

_T = TypeVar("_T")


def quarantine_key(media_id: uuid.UUID) -> str:
    """Name an upload's quarantined object.

    :param media_id: The photo
    :return: ``quarantine/{media_id}``
    """
    return f"quarantine/{media_id}"


def staged_prefix(media_id: uuid.UUID) -> str:
    """Name the folder the sanitiser writes.

    :param media_id: The photo
    :return: ``staged/{media_id}/``
    """
    return f"staged/{media_id}/"


def archive_prefix(media_id: uuid.UUID) -> str:
    """Name the folder approval archives the variants in.

    :param media_id: The photo
    :return: ``archive/{media_id}/``
    """
    return f"archive/{media_id}/"


def public_prefix(public_key: str) -> str:
    """Name the folder CloudFront serves at ``/m/{public_key}/``.

    :param public_key: The photo's public key
    :return: ``public/{public_key}/``
    """
    return f"public/{public_key}/"


@dataclass(frozen=True, slots=True)
class UploadTicket:
    """What the client needs to upload straight to the bucket.

    :ivar media_id: The photo the upload is for
    :ivar url: The bucket's regional endpoint, the POST target
    :ivar fields: The form fields to send, in order, before the file
    :ivar expires_at: When the signature stops being accepted
    """

    media_id: uuid.UUID
    url: str
    fields: dict[str, str]
    expires_at: dt.datetime


@dataclass(frozen=True, slots=True)
class SanitiseResult:
    """The sanitiser's verdict on one upload, from its ``result.json``.

    :ivar ok: Whether the upload decoded and its variants were written
    :ivar width: The decoded width in pixels, when ok
    :ivar height: The decoded height in pixels, when ok
    :ivar widths: The variant widths written, when ok
    :ivar reason: Why not, when not ok
    """

    ok: bool
    width: int | None
    height: int | None
    widths: tuple[int, ...]
    reason: str | None


def _unreadable(reason: str) -> SanitiseResult:
    """Build a not-ok result.

    :param reason: Why
    :return: The result
    """
    return SanitiseResult(ok=False, width=None, height=None, widths=(), reason=reason)


def _positive(value: object) -> int | None:
    """Return a positive integer, refusing booleans and everything else.

    :param value: A decoded JSON value
    :return: The integer, or None
    """
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def parse_result(raw: bytes) -> SanitiseResult:
    """Read a ``result.json`` strictly.

    Anything but the two shapes the sanitiser writes is a malformed result,
    which the upload service treats as unreadable: a photo is never sent to
    review with a size or a variant list nobody can trust.

    :param raw: The object's bytes
    :return: The result
    """
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, ValueError):
        return _unreadable("malformed")
    if not isinstance(data, dict):
        return _unreadable("malformed")
    if data.get("ok") is False:
        reason = data.get("reason")
        return _unreadable(reason if reason == "unreadable" else "malformed")
    if data.get("ok") is not True:
        return _unreadable("malformed")
    width = _positive(data.get("width"))
    height = _positive(data.get("height"))
    widths = data.get("widths")
    if (
        width is None
        or height is None
        or not isinstance(widths, list)
        or not widths
        or not all(_positive(w) in VARIANT_WIDTHS for w in widths)
    ):
        return _unreadable("malformed")
    return SanitiseResult(
        ok=True,
        width=width,
        height=height,
        widths=tuple(sorted(set(widths))),
        reason=None,
    )


class MediaStore(Protocol):
    """The bucket operations the media service needs."""

    def presign_upload(self, media_id: uuid.UUID, content_type: str) -> UploadTicket:
        """Sign a POST that may write only ``quarantine/{media_id}``.

        :param media_id: The photo
        :param content_type: The declared type, one of :data:`UPLOAD_TYPES`
        :return: The ticket, valid for :data:`UPLOAD_TTL`
        """
        ...

    def read_result(self, media_id: uuid.UUID) -> SanitiseResult | None:
        """Read the sanitiser's ``result.json``.

        :param media_id: The photo
        :return: The result, or None when it has not been written
        """
        ...

    def copy_variants(
        self, src_prefix: str, dst_prefix: str, widths: list[int]
    ) -> None:
        """Copy each ``{w}.webp`` from one photo folder to another.

        :param src_prefix: The source folder
        :param dst_prefix: The destination folder
        :param widths: The variant widths
        :return: None
        """
        ...

    def delete_prefix(self, prefix: str) -> None:
        """Delete every object under one photo's prefix.

        :param prefix: One of the :data:`OBJECT_PREFIX` shapes
        :return: None
        """
        ...

    def presign_get(self, key: str) -> str:
        """Sign a preview GET of one unpublished variant.

        :param key: A ``staged/`` or ``archive/`` variant
        :return: A URL valid for :data:`PREVIEW_TTL`
        """
        ...


def _unavailable() -> TransientError:
    """Build the refusal for a bucket that cannot be reached right now.

    :return: The error
    """
    return TransientError(
        code="SERVICE_UNAVAILABLE", message_key="error.temporarily_unavailable"
    )


def _error_code(error: ClientError) -> str:
    """Read S3's error code from a client error.

    :param error: The error
    :return: The code, or an empty string
    """
    return str(error.response.get("Error", {}).get("Code", ""))


class S3MediaStore:
    """The real bucket, through boto3.

    :ivar bucket: The bucket name; empty when none is configured
    """

    def __init__(
        self,
        *,
        bucket: str | None = None,
        region: str | None = None,
        credentials_file: str | None = None,
    ) -> None:
        """Bind to a bucket, by default the one the environment names.

        :param bucket: The bucket; ``SHIKKHOKPLUS_MEDIA_BUCKET`` by default
        :param region: Its region; ``AWS_REGION`` by default
        :param credentials_file: The host-refreshed credentials file;
            ``AWS_SHARED_CREDENTIALS_FILE`` by default. Empty means the SDK's
            default chain, for local development against a real bucket.
        """
        env = os.environ
        self.bucket = (
            env.get("SHIKKHOKPLUS_MEDIA_BUCKET", "") if bucket is None else bucket
        )
        self._region = env.get("AWS_REGION", "") if region is None else region
        self._credentials_file = (
            env.get("AWS_SHARED_CREDENTIALS_FILE", "")
            if credentials_file is None
            else credentials_file
        )
        self._lock = threading.Lock()
        self._cached: tuple[bytes | None, Any] | None = None

    def _read_credentials(self) -> bytes | None:
        """Read the credentials file afresh.

        :return: Its bytes, or None when no file is configured
        :raises TransientError: The file is configured but unreadable
        """
        if not self._credentials_file:
            return None
        try:
            with open(self._credentials_file, "rb") as handle:
                return handle.read(65536)
        except OSError:
            log.warning("media credentials file unreadable; uploads refused")
            raise _unavailable() from None

    @staticmethod
    def _keys(content: bytes) -> dict[str, str]:
        """Parse the ``[default]`` profile the host job writes.

        :param content: The file's bytes
        :return: boto3 session keyword arguments
        :raises TransientError: The profile is missing or incomplete
        """
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read_string(content.decode())
            profile = parser["default"]
            keys = {
                "aws_access_key_id": profile["aws_access_key_id"].strip(),
                "aws_secret_access_key": profile["aws_secret_access_key"].strip(),
            }
        except (UnicodeDecodeError, configparser.Error, KeyError):
            log.warning("media credentials file incomplete; uploads refused")
            raise _unavailable() from None
        token = profile.get("aws_session_token", "").strip()
        if token:
            keys["aws_session_token"] = token
        if not all(keys.values()):
            log.warning("media credentials file incomplete; uploads refused")
            raise _unavailable()
        return keys

    def _client(self) -> Any:
        """Return an S3 client signing with the file's current credentials.

        :return: The client; rebuilt whenever the file's content changed
        :raises TransientError: No region, or no usable credentials
        """
        if not _REGION.fullmatch(self._region):
            log.warning("no AWS region for the media bucket; uploads refused")
            raise _unavailable()
        content = self._read_credentials()
        with self._lock:
            if self._cached is not None and self._cached[0] == content:
                return self._cached[1]
            keys = {} if content is None else self._keys(content)
            session = boto3.session.Session(region_name=self._region, **keys)
            client = session.client(
                "s3",
                region_name=self._region,
                endpoint_url=f"https://s3.{self._region}.amazonaws.com",
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "virtual"},
                    retries={"mode": "standard", "max_attempts": 3},
                    connect_timeout=5,
                    read_timeout=15,
                ),
            )
            self._cached = (content, client)
            return client

    def _require_bucket(self) -> str:
        """Return the bucket, refusing when none is configured.

        :return: The bucket name
        :raises TransientError: No bucket
        """
        if not self.bucket:
            log.warning("no media bucket configured; photo storage unavailable")
            raise _unavailable()
        return self.bucket

    @staticmethod
    def _call(operation: Callable[..., _T], **params: object) -> _T:
        """Run one S3 call, turning the SDK's failures into a transient error.

        :param operation: The client method
        :param params: Its keyword arguments
        :return: Its result
        :raises TransientError: S3 or the network failed
        """
        try:
            return operation(**params)
        except ClientError as error:
            log.warning("media bucket call failed", extra={"code": _error_code(error)})
            raise _unavailable() from error
        except BotoCoreError as error:
            log.warning(
                "media bucket unreachable", extra={"error": type(error).__name__}
            )
            raise _unavailable() from error

    def presign_upload(self, media_id: uuid.UUID, content_type: str) -> UploadTicket:
        """Sign a POST that may write only ``quarantine/{media_id}``.

        The policy pins the key, the exact ``Content-Type``, the
        ``x-amz-meta-declared-type`` the sanitiser checks magic bytes
        against, and a body of 1 byte to 8 MiB.

        :param media_id: The photo
        :param content_type: The declared type
        :return: The ticket, valid for ten minutes
        :raises ValueError: The type is not one of :data:`UPLOAD_TYPES`
        :raises TransientError: No bucket, region or credentials
        """
        if content_type not in UPLOAD_TYPES:
            raise ValueError(f"not an upload type: {content_type!r}")
        bucket = self._require_bucket()
        client = self._client()
        expires_at = dt.datetime.now(tz=dt.UTC) + UPLOAD_TTL
        post = self._call(
            client.generate_presigned_post,
            Bucket=bucket,
            Key=quarantine_key(media_id),
            Fields={
                "Content-Type": content_type,
                "x-amz-meta-declared-type": content_type,
            },
            Conditions=[
                {"Content-Type": content_type},
                {"x-amz-meta-declared-type": content_type},
                ["content-length-range", 1, MAX_UPLOAD_BYTES],
            ],
            ExpiresIn=int(UPLOAD_TTL.total_seconds()),
        )
        return UploadTicket(
            media_id=media_id,
            url=str(post["url"]),
            fields={str(k): str(v) for k, v in post["fields"].items()},
            expires_at=expires_at,
        )

    def read_result(self, media_id: uuid.UUID) -> SanitiseResult | None:
        """Read the sanitiser's ``result.json``.

        S3 answers a missing key with 404 to a caller that may list the
        bucket and 403 to one that may not; a 403 is told apart from a real
        refusal by listing exactly that key.

        :param media_id: The photo
        :return: The result, or None when it has not been written
        :raises TransientError: S3 failed or refused
        """
        bucket = self._require_bucket()
        client = self._client()
        key = f"{staged_prefix(media_id)}result.json"
        try:
            response = client.get_object(Bucket=bucket, Key=key)
            body = response["Body"].read(_MAX_RESULT_BYTES)
        except ClientError as error:
            code = _error_code(error)
            if code in ("NoSuchKey", "404"):
                return None
            if code in ("AccessDenied", "403"):
                listed = self._call(
                    client.list_objects_v2, Bucket=bucket, Prefix=key, MaxKeys=1
                )
                if int(listed.get("KeyCount", 0)) == 0:
                    return None
            log.warning("media result unreadable from the bucket", extra={"code": code})
            raise _unavailable() from error
        except BotoCoreError as error:
            log.warning(
                "media bucket unreachable", extra={"error": type(error).__name__}
            )
            raise _unavailable() from error
        return parse_result(body)

    def copy_variants(
        self, src_prefix: str, dst_prefix: str, widths: list[int]
    ) -> None:
        """Copy each ``{w}.webp`` between two photo folders.

        ``MetadataDirective=COPY`` keeps the source's ``Content-Type:
        image/webp``, which is what ``/m/*`` serves: its response headers
        policy sets no type of its own [Task 2 ruling].

        :param src_prefix: The source folder
        :param dst_prefix: The destination folder
        :param widths: The variant widths
        :return: None
        :raises ValueError: A folder or a width outside the layout
        :raises TransientError: S3 failed
        """
        if not (
            _VARIANT_FOLDER.fullmatch(src_prefix)
            and _VARIANT_FOLDER.fullmatch(dst_prefix)
        ):
            raise ValueError("variants are copied between photo folders only")
        if not set(widths) <= set(VARIANT_WIDTHS):
            raise ValueError(f"not variant widths: {widths!r}")
        bucket = self._require_bucket()
        client = self._client()
        for width in widths:
            name = f"{width}.webp"
            self._call(
                client.copy_object,
                Bucket=bucket,
                Key=f"{dst_prefix}{name}",
                CopySource={"Bucket": bucket, "Key": f"{src_prefix}{name}"},
                MetadataDirective="COPY",
            )

    def delete_prefix(self, prefix: str) -> None:
        """Delete every object under one photo's prefix.

        Lists the prefix and deletes what it found, a thousand keys a call.
        A key S3 reports it could not delete fails the whole call, so the
        outbox retries it.

        :param prefix: One of the :data:`OBJECT_PREFIX` shapes
        :return: None
        :raises ValueError: The prefix is wider than one photo
        :raises TransientError: S3 failed
        """
        if not OBJECT_PREFIX.fullmatch(prefix):
            raise ValueError(f"not a photo prefix: {prefix!r}")
        if not self.bucket:
            log.warning("no media bucket configured; delete skipped")
            return
        bucket = self.bucket
        client = self._client()
        keys = self._list(client, bucket, prefix)
        for start in range(0, len(keys), 1000):
            batch = keys[start : start + 1000]
            response = self._call(
                client.delete_objects,
                Bucket=bucket,
                Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
            )
            if response.get("Errors"):
                log.warning(
                    "media bucket refused some deletes",
                    extra={"count": len(response["Errors"])},
                )
                raise _unavailable()

    def _list(self, client: Any, bucket: str, prefix: str) -> Sequence[str]:
        """List every key under a prefix.

        :param client: The S3 client
        :param bucket: The bucket
        :param prefix: The prefix
        :return: The keys
        """
        keys: list[str] = []
        token: str | None = None
        while True:
            params: dict[str, str] = {"Bucket": bucket, "Prefix": prefix}
            if token:
                params["ContinuationToken"] = token
            page = self._call(client.list_objects_v2, **params)
            keys.extend(str(item["Key"]) for item in page.get("Contents", []))
            token = page.get("NextContinuationToken")
            if not page.get("IsTruncated") or not token:
                return keys

    def presign_get(self, key: str) -> str:
        """Sign a five-minute preview GET of one unpublished variant.

        :param key: A ``staged/`` or ``archive/`` variant
        :return: The URL
        :raises ValueError: Any other key
        :raises TransientError: No bucket, region or credentials
        """
        if not _PREVIEW_KEY.fullmatch(key):
            raise ValueError("only an unpublished variant may be previewed")
        bucket = self._require_bucket()
        client = self._client()
        return str(
            self._call(
                client.generate_presigned_url,
                ClientMethod="get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=int(PREVIEW_TTL.total_seconds()),
            )
        )
