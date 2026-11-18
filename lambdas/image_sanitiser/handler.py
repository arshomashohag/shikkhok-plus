"""The image sanitiser: untrusted uploads in, re-encoded WebP out.

Triggered by S3 ``ObjectCreated`` under ``quarantine/`` in the hub's photo
bucket (infra/modules/media/lambda.tf). For each ``quarantine/{media_id}``:

1. read the object, refusing anything over the POST policy's 8 MiB;
2. check its magic bytes against the type its presigned POST declared
   (``x-amz-meta-declared-type``), and that the container ends where its
   own structure says it does -- so a JPEG with a page appended is refused,
   although Pillow would decode the JPEG and ignore the tail. A phone's
   "motion photo", which stores a video after the JPEG's end, is refused
   for the same reason;
3. decode it under ``MAX_IMAGE_PIXELS = 40_000_000``, with Pillow's
   ``DecompressionBombWarning`` raised as an error, opening only the
   declared format's decoder;
4. apply the EXIF orientation, keep the first frame, convert to RGB (RGBA
   when it has alpha) and drop every metadata field;
5. write ``staged/{media_id}/{w}.webp`` for each target width, never
   upscaled, then ``result.json``; and only then
6. delete the quarantine object.

Anything that fails to decode writes ``{"ok": false, "reason":
"unreadable"}`` and nothing else, and the upload is deleted all the same.
A failure to READ or WRITE storage is not an unreadable image: it is
raised, so Lambda retries the event, and the upload stays where it is.

**No original byte is ever published.** Every variant is an encoder's
output from decoded pixels; no EXIF, ICC profile or XMP is passed to it.

Only this file is packaged (``make lambda-image``), with Pillow beside it.
boto3 is the Lambda runtime's own and is imported only when the handler
first runs there, so the tests, which replace ``client_factory``, never
need it.
"""

from __future__ import annotations

import importlib
import io
import json
import logging
import re
import urllib.parse
import warnings
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Protocol

from PIL import Image, ImageOps

#: The decoder's pixel ceiling. Pillow raises over twice this and warns
#: over it; the warning is raised as an error below, so this is the cap.
Image.MAX_IMAGE_PIXELS = 40_000_000

#: The variant widths, in order. Each is written at min(width, source).
WIDTHS: tuple[int, ...] = (320, 960, 1600)
WEBP_QUALITY = 82
WEBP_METHOD = 6

#: The presigned POST's content-length-range ceiling.
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

#: ``quarantine/{media_id}``, the id in the canonical lowercase form the
#: API generates. Anything else under the prefix is not ours to touch.
QUARANTINE_KEY = re.compile(
    r"quarantine/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)

#: The three declarable types: Pillow's format name for each.
FORMATS: dict[str, str] = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}

UNREADABLE: dict[str, object] = {"ok": False, "reason": "unreadable"}

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class S3Client(Protocol):
    """The three calls the handler makes, as boto3's S3 client spells them."""

    def get_object(self, *, Bucket: str, Key: str) -> Any:
        """Read an object."""

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
    ) -> Any:
        """Write an object."""

    def delete_object(self, *, Bucket: str, Key: str) -> Any:
        """Delete an object."""


def _runtime_client() -> S3Client:
    """Return boto3's S3 client, from the Lambda runtime.

    Imported by name, so neither the package nor the tests carry boto3.

    :return: A client in the function's own region
    """
    boto3 = importlib.import_module("boto3")
    client: S3Client = boto3.client("s3")
    return client


#: Where the handler gets its client. The tests replace it with a
#: dict-backed stand-in; nothing else should.
client_factory: Callable[[], S3Client] = _runtime_client


class Unreadable(Exception):
    """The upload is not the image it was declared to be."""


@dataclass(frozen=True)
class Variant:
    """One encoded width.

    :ivar name: The target width it is named for, e.g. 960
    :ivar body: The WebP bytes
    """

    name: int
    body: bytes


@dataclass(frozen=True)
class Sanitised:
    """What a readable upload became.

    :ivar width: The source's width, after orientation
    :ivar height: The source's height, after orientation
    :ivar variants: The encoded widths, smallest first
    """

    width: int
    height: int
    variants: tuple[Variant, ...]


# ---------------------------------------------------------------------------
# The container: is it what was declared, and does it end where it says?
# ---------------------------------------------------------------------------


def _magic_matches(data: bytes, declared_format: str) -> bool:
    """Check the leading bytes against the declared format.

    :param data: The upload
    :param declared_format: ``JPEG``, ``PNG`` or ``WEBP``
    :return: Whether the signature is that format's
    """
    if declared_format == "JPEG":
        return data[:3] == b"\xff\xd8\xff"
    if declared_format == "PNG":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def _jpeg_end(data: bytes) -> int | None:
    """Return the offset just past the JPEG's end-of-image marker.

    Walks the marker segments from SOI, skipping each segment by its
    length and each scan's entropy-coded data to the next real marker.
    Embedded thumbnails live inside an APP segment's length and are
    skipped with it.

    :param data: Bytes starting with SOI
    :return: The end offset, or None when the structure does not hold
    """
    size = len(data)
    index = 2
    while index < size:
        if data[index] != 0xFF:
            return None
        while index < size and data[index] == 0xFF:  # fill bytes
            index += 1
        if index >= size:
            return None
        marker = data[index]
        index += 1
        if marker == 0xD9:  # EOI
            return index
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:  # no length
            continue
        if index + 2 > size:
            return None
        length = int.from_bytes(data[index : index + 2], "big")
        if length < 2:
            return None
        index += length
        if marker == 0xDA:  # SOS: entropy-coded data until a real marker
            while True:
                found = data.find(b"\xff", index)
                if found < 0 or found + 1 >= size:
                    return None
                following = data[found + 1]
                if following == 0x00 or 0xD0 <= following <= 0xD7:
                    index = found + 2  # a stuffed byte or a restart marker
                elif following == 0xFF:
                    index = found + 1  # fill before the next marker
                else:
                    index = found
                    break
    return None


def _png_end(data: bytes) -> int | None:
    """Return the offset just past the PNG's IEND chunk.

    :param data: Bytes starting with the PNG signature
    :return: The end offset, or None when the chunks do not hold
    """
    index = 8
    while index + 12 <= len(data):
        length = int.from_bytes(data[index : index + 4], "big")
        kind = data[index + 4 : index + 8]
        index += 12 + length
        if index > len(data):
            return None
        if kind == b"IEND":
            return index
    return None


def _webp_end(data: bytes) -> int | None:
    """Return the offset the RIFF header says the WebP ends at.

    :param data: Bytes starting with ``RIFF....WEBP``
    :return: The end offset, or None when the header overruns the data
    """
    end = 8 + int.from_bytes(data[4:8], "little")
    return end if end <= len(data) else None


_ENDS: dict[str, Callable[[bytes], int | None]] = {
    "JPEG": _jpeg_end,
    "PNG": _png_end,
    "WEBP": _webp_end,
}


def _check_container(data: bytes, declared_type: str | None) -> str:
    """Refuse an upload that is not, byte for byte, the declared type.

    :param data: The upload
    :param declared_type: The type its presigned POST declared
    :return: Pillow's format name for it
    :raises Unreadable: Wrong signature, unknown type, or bytes beyond the
        container's own end (a polyglot's appended page)
    """
    declared_format = FORMATS.get(declared_type or "")
    if declared_format is None:
        raise Unreadable(f"declared type {declared_type!r}")
    if not _magic_matches(data, declared_format):
        raise Unreadable(f"signature is not {declared_format}")
    if _ENDS[declared_format](data) != len(data):
        raise Unreadable(f"{declared_format} container does not end at the file's end")
    return declared_format


# ---------------------------------------------------------------------------
# Decoding and re-encoding: pure, no I/O
# ---------------------------------------------------------------------------


def _has_alpha(image: Image.Image) -> bool:
    """Say whether the image carries transparency worth keeping.

    :param image: The decoded first frame
    :return: True for an alpha channel or a transparency key
    """
    return image.mode in ("RGBA", "LA", "PA", "RGBa", "La") or (
        "transparency" in image.info
    )


def _target_widths(source_width: int) -> Iterator[tuple[int, int]]:
    """Yield (name, pixel width) for each variant to write.

    Each target is written at min(target, source); a target whose min
    equals the previous one's would be a duplicate and is skipped.

    :param source_width: The oriented source's width
    :return: Pairs, smallest first
    """
    previous = 0
    for target in WIDTHS:
        width = min(target, source_width)
        if width == previous:
            continue
        previous = width
        yield target, width


def _encode(image: Image.Image) -> bytes:
    """Encode one variant as WebP, passing no metadata at all.

    :param image: The pixels
    :return: The WebP bytes
    """
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
    return buffer.getvalue()


def sanitise(data: bytes, declared_type: str | None) -> Sanitised:
    """Decode an upload and re-encode it as the variant set.

    :param data: The upload
    :param declared_type: The type its presigned POST declared
    :return: The dimensions and the encoded variants
    :raises Unreadable: For anything that is not a decodable image of the
        declared type within the pixel cap
    """
    declared_format = _check_container(data, declared_type)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=[declared_format]) as opened:
                if opened.format != declared_format:
                    raise Unreadable(f"decoded as {opened.format}")
                opened.load()  # the first frame: open() positions there
                oriented = ImageOps.exif_transpose(opened)
                mode = "RGBA" if _has_alpha(oriented) else "RGB"
                pixels = oriented.convert(mode)
        pixels.info.clear()  # nothing of the original's metadata survives
        width, height = pixels.size
        variants = []
        for name, target in _target_widths(width):
            if target == width:
                resized = pixels
            else:
                resized = pixels.resize(
                    (target, max(1, round(height * target / width))),
                    Image.Resampling.LANCZOS,
                )
            variants.append(Variant(name, _encode(resized)))
    except Unreadable:
        raise
    # **Deliberately broad.** These bytes are hostile by assumption, and
    # Pillow does not report malformed input as one exception class: its
    # plugins raise SyntaxError for a bad header, the bomb checks raise
    # their own pair, and a parser walking corrupt structures can fail with
    # whatever its arithmetic hits. Every one means the same thing -- not a
    # readable image -- and no I/O happens inside this block, so nothing
    # transient is swallowed.
    except Exception as exc:
        raise Unreadable(f"{type(exc).__name__}: {exc}") from exc
    return Sanitised(width, height, tuple(variants))


# ---------------------------------------------------------------------------
# The handler: storage in and out
# ---------------------------------------------------------------------------


def _error_code(exc: BaseException) -> str | None:
    """Return botocore's error code for an exception, if it carries one.

    :param exc: Whatever the client raised
    :return: e.g. ``NoSuchKey``, or None
    """
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    code = response.get("Error", {}).get("Code")
    return str(code) if code is not None else None


@dataclass(frozen=True)
class Upload:
    """One quarantined object, as read.

    :ivar data: Its bytes, or None when it is over the upload limit (and so
        was never read into memory)
    :ivar declared_type: The type its presigned POST declared, if any
    """

    data: bytes | None
    declared_type: str | None


def _read(client: S3Client, bucket: str, key: str) -> Upload | None:
    """Read an upload and the type it was declared as.

    :param client: The S3 client
    :param bucket: The photo bucket
    :param key: ``quarantine/{media_id}``
    :return: The upload, or None when it is already gone
    """
    try:
        response = client.get_object(Bucket=bucket, Key=key)
    except Exception as exc:
        if _error_code(exc) in ("NoSuchKey", "404"):
            return None
        raise
    declared = response.get("Metadata", {}).get("declared-type")
    if int(response.get("ContentLength", 0)) > MAX_UPLOAD_BYTES:
        return Upload(None, declared)
    body: bytes = response["Body"].read(MAX_UPLOAD_BYTES + 1)
    return Upload(body if len(body) <= MAX_UPLOAD_BYTES else None, declared)


def _put_json(client: S3Client, bucket: str, key: str, value: object) -> None:
    """Write one JSON object.

    :param client: The S3 client
    :param bucket: The photo bucket
    :param key: Where
    :param value: What
    """
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(value, separators=(",", ":")).encode(),
        ContentType="application/json",
    )


def process(client: S3Client, bucket: str, key: str) -> None:
    """Sanitise one upload and empty its quarantine slot.

    :param client: The S3 client
    :param bucket: The photo bucket
    :param key: The object key, decoded
    """
    match = QUARANTINE_KEY.fullmatch(key)
    if match is None:
        logger.warning("ignored: %r is not quarantine/{media_id}", key)
        return
    media_id = match.group(1)
    staged = f"staged/{media_id}"

    upload = _read(client, bucket, key)
    if upload is None:
        logger.info("%s: already processed; nothing to do", media_id)
        return

    try:
        if upload.data is None:
            raise Unreadable(f"larger than {MAX_UPLOAD_BYTES} bytes")
        result = sanitise(upload.data, upload.declared_type)
    except Unreadable as exc:
        logger.info("%s: unreadable (%s)", media_id, exc)
        _put_json(client, bucket, f"{staged}/result.json", UNREADABLE)
    else:
        for variant in result.variants:
            client.put_object(
                Bucket=bucket,
                Key=f"{staged}/{variant.name}.webp",
                Body=variant.body,
                ContentType="image/webp",
            )
        _put_json(
            client,
            bucket,
            f"{staged}/result.json",
            {
                "ok": True,
                "width": result.width,
                "height": result.height,
                "widths": [variant.name for variant in result.variants],
            },
        )
        logger.info(
            "%s: staged %s",
            media_id,
            ",".join(str(variant.name) for variant in result.variants),
        )
    # Last, so `complete` never finds neither the upload nor a result.
    client.delete_object(Bucket=bucket, Key=key)


def handler(event: dict[str, Any], context: object) -> None:
    """Process every record of an S3 notification.

    :param event: The S3 ``ObjectCreated`` notification
    :param context: The Lambda context (unused)
    """
    client = client_factory()
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        # S3 sends keys URL-encoded, with a space as '+'.
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        process(client, bucket, key)
