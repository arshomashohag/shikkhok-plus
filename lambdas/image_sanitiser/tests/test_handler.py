"""The image sanitiser, run against a dict-backed stand-in for S3.

Every fixture is generated here, with Pillow or by hand, so no binary is
committed and each one says in code what it is. Nothing calls AWS: the
handler takes its client from ``client_factory``, which each test replaces.
"""

from __future__ import annotations

import io
import json
import pathlib
import re
import struct
import urllib.parse
import uuid
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from PIL import ExifTags, Image, ImageCms

from image_sanitiser import handler as sanitiser

BUCKET = "shikkhokplus-staging-media-123456789012"
MEDIA_ID = "4f9c2a7e-1b3d-4e5f-8a6b-7c8d9e0f1a2b"
QUARANTINE = f"quarantine/{MEDIA_ID}"
STAGED = f"staged/{MEDIA_ID}"
UNREADABLE = {"ok": False, "reason": "unreadable"}


# ---------------------------------------------------------------------------
# The stand-in bucket
# ---------------------------------------------------------------------------


class MissingKeyError(Exception):
    """What botocore raises for a missing key, as far as the handler reads it."""

    def __init__(self, key: str) -> None:
        """Carry botocore's error shape for ``key``."""
        super().__init__(key)
        self.response = {"Error": {"Code": "NoSuchKey", "Message": key}}


@dataclass
class StoredObject:
    body: bytes
    content_type: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class FakeS3:
    objects: dict[str, StoredObject] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def upload(self, body: bytes, declared: str | None, key: str = QUARANTINE) -> None:
        """Put an object as the browser's presigned POST would."""
        metadata = {} if declared is None else {"declared-type": declared}
        self.objects[key] = StoredObject(body, declared, metadata)

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        assert Bucket == BUCKET
        self.calls.append(("get", Key))
        if Key not in self.objects:
            raise MissingKeyError(Key)
        stored = self.objects[Key]
        return {
            "Body": io.BytesIO(stored.body),
            "ContentLength": len(stored.body),
            "Metadata": dict(stored.metadata),
        }

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
    ) -> dict[str, object]:
        assert Bucket == BUCKET
        self.calls.append(("put", Key))
        self.objects[Key] = StoredObject(Body, ContentType)
        return {}

    def delete_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        assert Bucket == BUCKET
        self.calls.append(("delete", Key))
        self.objects.pop(Key, None)
        return {}

    def staged(self, media_id: str = MEDIA_ID) -> dict[str, StoredObject]:
        prefix = f"staged/{media_id}/"
        return {
            key.removeprefix(prefix): obj
            for key, obj in self.objects.items()
            if key.startswith(prefix)
        }

    def result(self, media_id: str = MEDIA_ID) -> dict[str, object]:
        loaded: dict[str, object] = json.loads(
            self.objects[f"staged/{media_id}/result.json"].body
        )
        return loaded


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeS3]:
    fake = FakeS3()
    monkeypatch.setattr(sanitiser, "client_factory", lambda: fake)
    yield fake


def _event(*keys: str) -> dict[str, object]:
    """Build an S3 ObjectCreated notification, keys URL-encoded as S3 sends them."""
    return {
        "Records": [
            {
                "eventSource": "aws:s3",
                "eventName": "ObjectCreated:Post",
                "s3": {
                    "bucket": {"name": BUCKET},
                    "object": {"key": urllib.parse.quote_plus(key, safe="/")},
                },
            }
            for key in keys
        ]
    }


def _run(*keys: str) -> None:
    sanitiser.handler(_event(*keys or (QUARANTINE,)), None)


def _pixel(image: Image.Image, xy: tuple[int, int]) -> tuple[int, ...]:
    value = image.getpixel(xy)
    assert isinstance(value, tuple)
    return value


def _open(obj: StoredObject) -> Image.Image:
    image = Image.open(io.BytesIO(obj.body))
    image.load()
    return image


# ---------------------------------------------------------------------------
# Fixtures, generated
# ---------------------------------------------------------------------------


def _jpeg(
    size: tuple[int, int] = (640, 480),
    *,
    exif: Image.Exif | None = None,
    icc: bytes | None = None,
) -> bytes:
    buffer = io.BytesIO()
    image = Image.new("RGB", size, (200, 40, 40))
    params: dict[str, object] = {"quality": 90}
    if exif is not None:
        params["exif"] = exif
    if icc is not None:
        params["icc_profile"] = icc
    image.save(buffer, "JPEG", **params)
    return buffer.getvalue()


def _png(size: tuple[int, int] = (640, 480), mode: str = "RGB") -> bytes:
    buffer = io.BytesIO()
    image = Image.new(mode, size, (30, 120, 200, 255)[: len(mode)])
    if mode == "RGBA":
        # A transparent left half, so alpha is something to keep.
        image.paste((0, 0, 0, 0), (0, 0, size[0] // 2, size[1]))
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _webp(size: tuple[int, int] = (640, 480)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (10, 200, 10)).save(buffer, "WEBP")
    return buffer.getvalue()


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _png_by_hand(width: int, height: int, *, bit_depth: int, idat: bytes) -> bytes:
    """Build a greyscale PNG whose header says exactly what the test needs."""
    header = struct.pack(">IIBBBBB", width, height, bit_depth, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def _gps_exif() -> Image.Exif:
    exif = Image.Exif()
    exif[ExifTags.Base.Make] = "PhoneMaker"
    gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps[ExifTags.GPS.GPSLatitudeRef] = "N"
    gps[ExifTags.GPS.GPSLatitude] = (23.0, 48.0, 36.0)
    gps[ExifTags.GPS.GPSLongitudeRef] = "E"
    gps[ExifTags.GPS.GPSLongitude] = (90.0, 24.0, 0.0)
    return exif


# ---------------------------------------------------------------------------
# What decodes is re-encoded, and nothing of the original survives
# ---------------------------------------------------------------------------


def test_jpeg_with_gps_exif_is_stripped(s3: FakeS3) -> None:
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    source = _jpeg((2000, 1500), exif=_gps_exif(), icc=icc)
    # The fixture really carries what must not survive.
    original = Image.open(io.BytesIO(source))
    assert original.getexif().get_ifd(ExifTags.IFD.GPSInfo)
    assert "icc_profile" in original.info
    s3.upload(source, "image/jpeg")

    _run()

    variants = {k: v for k, v in s3.staged().items() if k.endswith(".webp")}
    assert sorted(variants) == ["1600.webp", "320.webp", "960.webp"]
    for name, obj in variants.items():
        out = _open(obj)
        assert out.format == "WEBP", name
        assert len(out.getexif()) == 0, name
        assert ExifTags.IFD.GPSInfo not in out.getexif(), name
        for key in ("exif", "icc_profile", "xmp"):
            assert key not in out.info, (name, key)
        assert b"PhoneMaker" not in obj.body, name


def test_png_with_alpha_keeps_alpha(s3: FakeS3) -> None:
    s3.upload(_png((640, 480), "RGBA"), "image/png")

    _run()

    out = _open(s3.staged()["320.webp"])
    assert out.mode == "RGBA"
    assert _pixel(out, (10, 100))[3] == 0  # the transparent half
    assert _pixel(out, (out.width - 10, 100))[3] == 255


def test_opaque_png_is_rgb(s3: FakeS3) -> None:
    s3.upload(_png((640, 480), "RGB"), "image/png")

    _run()

    assert _open(s3.staged()["320.webp"]).mode == "RGB"


@pytest.mark.parametrize(
    ("source_width", "widths", "pixels"),
    [
        (500, [320, 960], {"320.webp": 320, "960.webp": 500}),
        (200, [320], {"320.webp": 200}),
        (960, [320, 960], {"320.webp": 320, "960.webp": 960}),
        (
            2000,
            [320, 960, 1600],
            {"320.webp": 320, "960.webp": 960, "1600.webp": 1600},
        ),
    ],
)
def test_variants_never_upscale(
    s3: FakeS3, source_width: int, widths: list[int], pixels: dict[str, int]
) -> None:
    s3.upload(_jpeg((source_width, source_width // 2)), "image/jpeg")

    _run()

    result = s3.result()
    assert result == {
        "ok": True,
        "width": source_width,
        "height": source_width // 2,
        "widths": widths,
    }
    staged = s3.staged()
    assert sorted(staged) == sorted([*pixels, "result.json"])
    for name, width in pixels.items():
        out = _open(staged[name])
        assert out.width == width, name
        # The aspect ratio holds, to the pixel.
        assert out.height == round(width / 2), name


def test_variants_and_result_carry_their_content_types(s3: FakeS3) -> None:
    # The /m/* edge no longer forces a Content-Type: each object must
    # carry its own, or a browser would be left to sniff it.
    s3.upload(_jpeg((2000, 1000)), "image/jpeg")

    _run()

    types = {name: obj.content_type for name, obj in s3.staged().items()}
    assert types == {
        "320.webp": "image/webp",
        "960.webp": "image/webp",
        "1600.webp": "image/webp",
        "result.json": "application/json",
    }


def test_unreadable_result_is_json_too(s3: FakeS3) -> None:
    s3.upload(b"not an image", "image/png")

    _run()

    assert s3.staged()["result.json"].content_type == "application/json"


def test_exif_orientation_is_applied(s3: FakeS3) -> None:
    # Orientation 6: the camera was turned; the stored pixels are 800 x 400
    # and the picture a person saw is 400 x 800.
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = 6
    s3.upload(_jpeg((800, 400), exif=exif), "image/jpeg")

    _run()

    result = s3.result()
    assert (result["width"], result["height"]) == (400, 800)
    out = _open(s3.staged()["320.webp"])
    assert (out.width, out.height) == (320, 640)


def test_webp_upload_is_reencoded(s3: FakeS3) -> None:
    source = _webp((1000, 500))
    s3.upload(source, "image/webp")

    _run()

    # 1600 is written at the source's 1000, which differs from 960's 960.
    assert s3.result()["widths"] == [320, 960, 1600]
    assert _open(s3.staged()["1600.webp"]).width == 1000
    assert s3.staged()["1600.webp"].body != source


def test_only_the_first_frame_is_used(s3: FakeS3) -> None:
    frames = [Image.new("RGB", (400, 200), colour) for colour in ("red", "blue")]
    buffer = io.BytesIO()
    frames[0].save(buffer, "PNG", save_all=True, append_images=frames[1:])
    source = buffer.getvalue()
    assert getattr(Image.open(io.BytesIO(source)), "n_frames", 1) == 2
    s3.upload(source, "image/png")

    _run()

    out = _open(s3.staged()["320.webp"])
    assert getattr(out, "n_frames", 1) == 1
    red, _green, blue = _pixel(out.convert("RGB"), (160, 100))
    assert red > 200 and blue < 50


def _saved(image: Image.Image, kind: str, **params: object) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, kind, **params)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("body", "declared"),
    [
        # Ten scans, each its own SOS and entropy-coded segment.
        (
            _saved(Image.new("RGB", (700, 500), "red"), "JPEG", progressive=True),
            "image/jpeg",
        ),
        # RSTn markers inside the entropy-coded data, and a DRI segment.
        (
            _saved(
                Image.radial_gradient("L").convert("RGB").resize((700, 500)),
                "JPEG",
                restart_marker_rows=1,
            ),
            "image/jpeg",
        ),
        (_saved(Image.new("CMYK", (700, 500), (0, 50, 100, 0)), "JPEG"), "image/jpeg"),
        (_saved(Image.new("L", (700, 500), 128), "JPEG"), "image/jpeg"),
        (
            _saved(Image.new("P", (700, 500), 0), "PNG", transparency=0),
            "image/png",
        ),
        (_saved(Image.new("I;16", (700, 500), 3000), "PNG"), "image/png"),
        (_saved(Image.new("RGBA", (700, 500), (1, 2, 3, 4)), "WEBP"), "image/webp"),
    ],
    ids=["progressive", "restart-markers", "cmyk", "grey", "palette", "16-bit", "webp"],
)
def test_ordinary_encodings_are_readable(
    s3: FakeS3, body: bytes, declared: str
) -> None:
    # The signature check must not refuse what real encoders write.
    s3.upload(body, declared)

    _run()

    assert s3.result()["ok"] is True
    assert s3.result()["widths"] == [320, 960]


# ---------------------------------------------------------------------------
# A file that is not the image it claims to be [Review Focus 1]
# ---------------------------------------------------------------------------


def _assert_unreadable(s3: FakeS3) -> None:
    assert s3.result() == UNREADABLE
    assert sorted(s3.staged()) == ["result.json"]  # nothing else staged
    assert QUARANTINE not in s3.objects


@pytest.mark.parametrize(
    ("body", "declared"),
    [
        # An HTML page uploaded under a .jpg name and an image type.
        (b"<html><body><script>alert(1)</script></body></html>", "image/jpeg"),
        # An SVG declared as a PNG.
        (
            b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
            b"<script>alert(1)</script></svg>",
            "image/png",
        ),
    ],
    ids=["html-as-jpeg", "svg-as-png"],
)
def test_polyglot_and_svg_are_unreadable(
    s3: FakeS3, body: bytes, declared: str
) -> None:
    # The signature is not the declared type's: no decoder is tried.
    s3.upload(body, declared)

    _run()

    _assert_unreadable(s3)


#: A page appended after an image's end: the polyglot's payload.
_PAGE = b"<html><script>alert('polyglot-marker')</script></html>"

#: Strings from the appended data that must never reach a written object.
_TAIL_MARKERS = (
    b"<html",
    b"<script>",
    b"polyglot-marker",
    b"second-image-marker",
    b"ftypmp42",
    b"motion-video-marker",
)


def _motion_photo() -> bytes:
    """Build a JPEG shaped like a phone's motion photo or an MPO.

    The primary image, then a second JPEG after its end (as an MPO stores
    its other pictures), then an MP4-shaped trailer (as a motion photo
    stores its video).
    """
    second = _saved(
        Image.new("RGB", (400, 300), (0, 0, 255)),
        "JPEG",
        comment=b"second-image-marker",
    )
    video = (
        b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
        + b"\x00\x00\x00\x20mdat"
        + b"motion-video-marker"
        + b"\x00" * 13
    )
    return _jpeg((400, 300)) + second + video


@pytest.mark.parametrize(
    ("body", "declared"),
    [
        (_jpeg((400, 300)) + _PAGE, "image/jpeg"),
        (_png((400, 300)) + _PAGE, "image/png"),
        (_webp((400, 300)) + _PAGE, "image/webp"),
        (_motion_photo(), "image/jpeg"),
    ],
    ids=["jpeg-html-polyglot", "png-tail", "webp-tail", "motion-photo"],
)
def test_trailing_data_is_accepted_and_never_written(
    s3: FakeS3, body: bytes, declared: str
) -> None:
    # [R6] The image decodes, so it is accepted; the re-encode writes only
    # its pixels, so nothing after the image's end reaches staged/.
    s3.upload(body, declared)

    _run()

    assert s3.result()["ok"] is True
    # A 400 px source: 320, and 960 written at 400.
    assert s3.result()["widths"] == [320, 960]
    written = s3.staged()
    assert sorted(written) == ["320.webp", "960.webp", "result.json"]
    for name, obj in written.items():
        for marker in _TAIL_MARKERS:
            assert marker not in obj.body, (name, marker)
    # And the variant is the FIRST image, not anything after it.
    if declared == "image/jpeg":
        red, _green, blue = _pixel(_open(written["320.webp"]).convert("RGB"), (5, 5))
        assert red > 150 and blue < 100
    assert QUARANTINE not in s3.objects


def test_decompression_bomb_is_unreadable(s3: FakeS3) -> None:
    # 30 000 x 30 000 = 900 megapixels declared by a few hundred bytes.
    s3.upload(
        _png_by_hand(30_000, 30_000, bit_depth=1, idat=zlib.compress(b"\x00" * 64)),
        "image/png",
    )

    _run()

    _assert_unreadable(s3)


def test_just_over_the_pixel_cap_is_unreadable(s3: FakeS3) -> None:
    # 8000 x 5001 = 40 008 000 pixels: over MAX_IMAGE_PIXELS but under
    # Pillow's own hard limit (twice that), where it only WARNS. A valid,
    # decodable 1-bit image, so the warning-as-error is what refuses it.
    width, height = 8000, 5001
    rows = (b"\x00" + b"\x00" * (width // 8)) * height
    s3.upload(
        _png_by_hand(width, height, bit_depth=1, idat=zlib.compress(rows, 9)),
        "image/png",
    )

    _run()

    _assert_unreadable(s3)


def test_the_pixel_cap_is_forty_megapixels() -> None:
    # Set on import of the handler, for every decode in the process.
    assert Image.MAX_IMAGE_PIXELS == 40_000_000


def test_truncated_jpeg_is_unreadable(s3: FakeS3) -> None:
    whole = _jpeg((800, 600))
    s3.upload(whole[: len(whole) // 2], "image/jpeg")

    _run()

    _assert_unreadable(s3)


def test_declared_type_mismatch_is_unreadable(s3: FakeS3) -> None:
    # PNG bytes at a key whose presigned POST declared a JPEG.
    s3.upload(_png((400, 300)), "image/jpeg")

    _run()

    _assert_unreadable(s3)


@pytest.mark.parametrize("declared", [None, "image/gif", "image/svg+xml", ""])
def test_a_missing_or_other_declared_type_is_unreadable(
    s3: FakeS3, declared: str | None
) -> None:
    s3.upload(_png((400, 300)), declared)

    _run()

    _assert_unreadable(s3)


def test_an_object_over_the_upload_limit_is_unreadable(s3: FakeS3) -> None:
    # The POST policy caps uploads at 8 MiB; anything larger did not come
    # through it and is not read into memory.
    s3.upload(_jpeg((64, 64)) + b"\x00" * (8 * 1024 * 1024), "image/jpeg")

    _run()

    _assert_unreadable(s3)


# ---------------------------------------------------------------------------
# The quarantine is always emptied; keys it does not know are left alone
# ---------------------------------------------------------------------------


def test_quarantine_object_deleted_every_time(s3: FakeS3) -> None:
    good = str(uuid.UUID(int=1))
    bad = str(uuid.UUID(int=2))
    s3.upload(_jpeg((400, 300)), "image/jpeg", key=f"quarantine/{good}")
    s3.upload(b"\xff\xd8\xff garbage", "image/jpeg", key=f"quarantine/{bad}")

    _run(f"quarantine/{good}", f"quarantine/{bad}")

    assert not [k for k in s3.objects if k.startswith("quarantine/")]
    assert s3.result(good)["ok"] is True
    assert s3.result(bad) == UNREADABLE
    # Deleted only once its result is written: `complete` must never find
    # neither the upload nor a result.
    for media_id in (good, bad):
        calls = [c for c in s3.calls if media_id in c[1]]
        assert calls[-2:] == [
            ("put", f"staged/{media_id}/result.json"),
            ("delete", f"quarantine/{media_id}"),
        ]


@pytest.mark.parametrize(
    "key",
    [
        "quarantine/not-a-uuid",
        f"quarantine/{MEDIA_ID}/extra",
        f"quarantine/{MEDIA_ID.upper()}",
        f"staged/{MEDIA_ID}/320.webp",
        f"public/{'a' * 32}/320.webp",
        f"quarantine/../staged/{MEDIA_ID}",
        "quarantine/",
    ],
)
def test_unexpected_key_ignored(
    s3: FakeS3, key: str, caplog: pytest.LogCaptureFixture
) -> None:
    s3.upload(_jpeg((400, 300)), "image/jpeg", key=key)

    _run(key)

    assert s3.calls == []  # not read, not written, not deleted
    assert key in s3.objects
    assert "ignored" in caplog.text


def test_missing_object_is_skipped(
    s3: FakeS3, caplog: pytest.LogCaptureFixture
) -> None:
    # S3 delivers at least once: a second delivery finds the upload
    # already processed and deleted, which is not an error to retry.
    _run()

    assert s3.calls == [("get", QUARANTINE)]
    assert "already processed" in caplog.text


def test_a_storage_failure_is_raised_not_reported_unreadable(
    s3: FakeS3, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A failed write is Lambda's to retry. Recording it as `unreadable`
    # would reject a good photo for a transient fault.
    s3.upload(_jpeg((400, 300)), "image/jpeg")

    def refuse(**_kwargs: object) -> dict[str, object]:
        raise ConnectionError("S3 unavailable")

    monkeypatch.setattr(s3, "put_object", refuse)

    with pytest.raises(ConnectionError):
        _run()
    assert QUARANTINE in s3.objects


# ---------------------------------------------------------------------------
# The lockfile
# ---------------------------------------------------------------------------

HERE = pathlib.Path(__file__).resolve().parents[1]


def test_the_lockfile_pins_only_pillow_with_hashes() -> None:
    # Pillow, and nothing else, goes into the package; every pin carries
    # its hashes so `--require-hashes` installs exactly what was locked.
    lines = (HERE / "requirements.txt").read_text().splitlines()
    pins = [line for line in lines if re.match(r"^[A-Za-z0-9]", line)]
    assert len(pins) == 1
    assert re.fullmatch(r"pillow==\d+\.\d+\.\d+ \\", pins[0])
    assert sum("--hash=sha256:" in line for line in lines) > 0
    floor = re.search(
        r"^pillow>=(\d+)\.(\d+)$", (HERE / "requirements.in").read_text(), re.M
    )
    assert floor is not None
    pinned = re.search(r"==(\d+)\.(\d+)", pins[0])
    assert pinned is not None
    assert tuple(map(int, pinned.groups())) >= tuple(map(int, floor.groups()))
