"""The image sanitiser: untrusted uploads in, re-encoded WebP out.

Triggered by S3 ``ObjectCreated`` under ``quarantine/`` in the hub's photo
bucket (infra/modules/media/lambda.tf). For each ``quarantine/{media_id}``:

1. read the object, refusing anything over the POST policy's 8 MiB;
2. check its magic bytes against the type its presigned POST declared
   (``x-amz-meta-declared-type``), so an HTML page or an SVG named as an
   image is refused before any decoder sees it;
3. decode it under ``MAX_IMAGE_PIXELS = 40_000_000``, with Pillow's
   ``DecompressionBombWarning`` raised as an error, opening only the
   declared format's decoder (a JPEG with an MPF segment opens as "MPO";
   its first frame is used) and, for a JPEG, at the smallest scale that
   still gives the widest variant its pixels;
4. apply the EXIF orientation, keep the first frame, convert to RGB (RGBA
   when it has alpha) and drop every metadata field;
5. write ``staged/{media_id}/{w}.webp`` for each target width, never
   upscaled and each resized from the next larger, then ``result.json``;
   and only then
6. delete the quarantine object.

Anything that fails to decode writes ``{"ok": false, "reason":
"unreadable"}`` and nothing else, and the upload is deleted all the same.
A failure to READ or WRITE storage is not an unreadable image: it is
raised, so the invocation fails and is logged, and the upload stays where
it is. The function is not retried (lambda.tf, R7b); an upload left with
no result.json -- a storage fault, a timeout, an out-of-memory kill -- is
settled by the API's ``complete`` as unreadable once it is 20 minutes old
[R7c].

**No original byte is ever published** [R6]. Every variant is an
encoder's output from decoded pixels; no EXIF, ICC profile or XMP is passed
to it. That is also why bytes AFTER the image's end are accepted: an
Android motion photo (a video after the JPEG), an MPO multi-picture JPEG or
a JPEG with a page appended all decode as their first image, and the tail
is never read into a variant. Refusing them would reject ordinary phone
photos to block something the re-encode already removes.

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
import math
import re
import urllib.parse
import warnings
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Protocol

from PIL import ExifTags, Image, ImageOps

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

#: What Pillow may report a decoded upload of each declared format as. A
#: JPEG carrying an MPF (APP2) segment -- multi-lens phones and many
#: cameras write one -- opens as "MPO", Pillow's JPEG subclass, even when
#: only the JPEG decoder is asked for. Its first frame is that JPEG [R7a].
DECODED_AS: dict[str, frozenset[str]] = {
    "JPEG": frozenset({"JPEG", "MPO"}),
    "PNG": frozenset({"PNG"}),
    "WEBP": frozenset({"WEBP"}),
}

#: EXIF orientations that turn the stored image a quarter turn, so its
#: stored width is the height a person sees.
QUARTER_TURNS = frozenset({5, 6, 7, 8})

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
# The signature: is it what was declared?
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


def _check_signature(data: bytes, declared_type: str | None) -> str:
    """Refuse an upload whose signature is not the declared type's.

    Bytes after the image's end are not checked: the decoder reads the
    first image and the re-encode writes only its pixels [R6].

    :param data: The upload
    :param declared_type: The type its presigned POST declared
    :return: Pillow's format name for it
    :raises Unreadable: An undeclarable type, or the wrong signature
    """
    declared_format = FORMATS.get(declared_type or "")
    if declared_format is None:
        raise Unreadable(f"declared type {declared_type!r}")
    if not _magic_matches(data, declared_format):
        raise Unreadable(f"signature is not {declared_format}")
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


def _oriented_size(image: Image.Image) -> tuple[int, int]:
    """Return the size a person sees once EXIF orientation is applied.

    :param image: The opened, not yet loaded, image
    :return: (width, height) after orientation
    """
    width, height = image.size
    orientation = image.getexif().get(ExifTags.Base.Orientation)
    return (height, width) if orientation in QUARTER_TURNS else (width, height)


def _draft(image: Image.Image, oriented: tuple[int, int]) -> None:
    """Let libjpeg decode at the smallest scale the widest variant allows.

    JPEG can decode at 1/2, 1/4 or 1/8 scale for a fraction of the work and
    memory. The request keeps the oriented width at least the widest
    variant's (and the aspect ratio), so no variant is ever drawn from
    fewer pixels than it has. A no-op for anything that is not a JPEG, or
    is too small to reduce.

    :param image: The opened, not yet loaded, image
    :param oriented: Its size after orientation
    """
    widest = WIDTHS[-1]
    stored_width, stored_height = image.size
    turned = oriented != image.size
    if turned:  # the stored height is what must stay at least `widest`
        request = (math.ceil(widest * stored_width / stored_height), widest)
    else:
        request = (widest, math.ceil(widest * stored_height / stored_width))
    # None keeps the stored mode: a CMYK or greyscale JPEG converts below.
    image.draft(None, request)


def _variants(pixels: Image.Image, source: tuple[int, int]) -> tuple[Variant, ...]:
    """Encode the variant set, each width resized from the next larger one.

    Largest first, so only the widest is resampled from the full decode
    and each smaller one from a 1600- or 960-pixel image: the work per
    upload is bounded by the widest variant, not by the source.

    :param pixels: The decoded, oriented, converted image
    :param source: The upload's own oriented size, which names the widths
    :return: The variants, smallest first
    """
    source_width, source_height = source
    current = pixels
    encoded: list[Variant] = []
    for name, target in reversed(list(_target_widths(source_width))):
        size = (target, max(1, round(source_height * target / source_width)))
        if current.size != size:
            current = current.resize(size, Image.Resampling.LANCZOS)
        encoded.append(Variant(name, _encode(current)))
    return tuple(reversed(encoded))


def sanitise(data: bytes, declared_type: str | None) -> Sanitised:
    """Decode an upload and re-encode it as the variant set.

    :param data: The upload
    :param declared_type: The type its presigned POST declared
    :return: The dimensions and the encoded variants
    :raises Unreadable: For anything that is not a decodable image of the
        declared type within the pixel cap
    """
    declared_format = _check_signature(data, declared_type)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=[declared_format]) as opened:
                if opened.format not in DECODED_AS[declared_format]:
                    raise Unreadable(f"decoded as {opened.format}")
                source = _oriented_size(opened)
                _draft(opened, source)
                opened.load()  # the first frame: open() positions there
                oriented = ImageOps.exif_transpose(opened)
                mode = "RGBA" if _has_alpha(oriented) else "RGB"
                pixels = oriented.convert(mode)
        pixels.info.clear()  # nothing of the original's metadata survives
        variants = _variants(pixels, source)
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
    return Sanitised(source[0], source[1], variants)


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
