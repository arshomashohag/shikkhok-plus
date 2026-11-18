"""``S3MediaStore`` against botocore's Stubber: hosts, refreshes, copies, deletes.

No request leaves the process: presigning is local, and every S3 call is
answered by a :class:`~botocore.stub.Stubber` that also asserts its
parameters. The credentials come only from a file written here, as the
container's come only from the host-refreshed mount.
"""

from __future__ import annotations

import io
import logging
import os
import pathlib
import time
import urllib.parse
import uuid
from typing import Final

import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from app.errors import TransientError
from app.hub.media.storage import (
    S3MediaStore,
    SanitiseResult,
    SourceChanged,
    parse_result,
)

BUCKET: Final[str] = "shikkhokplus-staging-media-123456789012"
HOST: Final[str] = f"https://{BUCKET}.s3.ap-south-1.amazonaws.com/"


def _creds(path: pathlib.Path, key: str) -> None:
    """Write a credentials file the way the host job does: a new file, renamed.

    :param path: Where the container reads it
    :param key: The access key id it carries
    :return: None
    """
    staging = path.with_name(".credentials.tmp")
    staging.write_text(
        "[default]\n"
        f"aws_access_key_id = {key}\n"
        "aws_secret_access_key = c2VjcmV0\n"
        f"aws_session_token = token-for-{key}\n"
    )
    os.replace(staging, path)


@pytest.fixture
def creds(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    for name in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-config"))
    path = tmp_path / "credentials"
    _creds(path, "ASIAFIRSTKEY00000000")
    return path


@pytest.fixture
def store(creds: pathlib.Path) -> S3MediaStore:
    return S3MediaStore(bucket=BUCKET, region="ap-south-1", credentials_file=str(creds))


def _body(data: bytes) -> StreamingBody:
    return StreamingBody(io.BytesIO(data), len(data))


def test_a_rewritten_credentials_file_is_used_by_the_next_operation(
    store: S3MediaStore, creds: pathlib.Path
) -> None:
    # botocore's own provider reads the file once and never again, while
    # the host rewrites it every 15 minutes and each copy lasts one hour.
    first = store.presign_upload(uuid.uuid4(), "image/jpeg")
    _creds(creds, "ASIASECONDKEY0000000")
    second = store.presign_upload(uuid.uuid4(), "image/jpeg")

    assert first.fields["x-amz-credential"].startswith("ASIAFIRSTKEY00000000/")
    assert second.fields["x-amz-credential"].startswith("ASIASECONDKEY0000000/")
    assert second.fields["x-amz-security-token"] == "token-for-ASIASECONDKEY0000000"

    # A rewrite in place, same inode, is picked up too.
    creds.write_text(creds.read_text().replace("SECONDKEY0", "THIRDKEY00"))
    third = store.presign_get(f"staged/{uuid.uuid4()}/320.webp")
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(third).query)
    assert query["X-Amz-Credential"][0].startswith("ASIATHIRDKEY00000000/")


def test_an_unchanged_file_reuses_the_client(store: S3MediaStore) -> None:
    assert store._client() is store._client()


def test_a_missing_credentials_file_fails_fast(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The container has no IMDS fallback: before the host job's first run
    # the upload answers a transient error at once rather than hanging.
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    store = S3MediaStore(
        bucket=BUCKET,
        region="ap-south-1",
        credentials_file=str(tmp_path / "not-yet-written"),
    )

    started = time.monotonic()
    with pytest.raises(TransientError) as refused:
        store.presign_upload(uuid.uuid4(), "image/jpeg")
    assert time.monotonic() - started < 1.0
    assert refused.value.code == "SERVICE_UNAVAILABLE"

    # An empty file -- a half-written mount -- is the same refusal.
    (tmp_path / "not-yet-written").write_text("")
    with pytest.raises(TransientError):
        store.presign_upload(uuid.uuid4(), "image/jpeg")


def test_unset_bucket_refuses_uploads_and_deletes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # R9: a delete with nowhere to go is a failure, never a silent success,
    # so the outbox keeps the row and the drain's heartbeat goes stale.
    store = S3MediaStore(bucket="", region="ap-south-1", credentials_file="")
    with pytest.raises(TransientError):
        store.presign_upload(uuid.uuid4(), "image/jpeg")

    with (
        caplog.at_level(logging.WARNING, logger="app.hub.media.storage"),
        pytest.raises(TransientError),
    ):
        store.delete_prefix(f"staged/{uuid.uuid4()}/")
    assert "no media bucket" in caplog.text


def test_presign_get_is_regional_and_lasts_five_minutes(store: S3MediaStore) -> None:
    media_id = uuid.uuid4()
    for key in (f"staged/{media_id}/320.webp", f"archive/{media_id}/1600.webp"):
        url = store.presign_get(key)
        parts = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parts.query)
        assert f"{parts.scheme}://{parts.netloc}/" == HOST
        assert parts.path == f"/{key}"
        assert query["X-Amz-Expires"] == ["300"]

    for key in (
        f"quarantine/{media_id}",
        f"public/{uuid.uuid4().hex}/320.webp",
        f"staged/{media_id}/result.json",
        f"staged/{media_id}/../{uuid.uuid4()}/320.webp",
    ):
        with pytest.raises(ValueError, match="preview"):
            store.presign_get(key)


def test_read_result_parses_and_distinguishes_absent(store: S3MediaStore) -> None:
    media_id = uuid.uuid4()
    key = f"staged/{media_id}/result.json"
    client = store._client()
    with Stubber(client) as stub:
        stub.add_response(
            "get_object",
            {
                "Body": _body(
                    b'{"ok": true, "width": 900, "height": 600, "widths": [320]}'
                )
            },
            {"Bucket": BUCKET, "Key": key},
        )
        stub.add_client_error(
            "get_object", service_error_code="NoSuchKey", http_status_code=404
        )
        # Without ListBucket on the key S3 answers 403 for a missing key;
        # an exact-prefix listing tells absence from a refusal.
        stub.add_client_error(
            "get_object", service_error_code="AccessDenied", http_status_code=403
        )
        stub.add_response(
            "list_objects_v2",
            {"KeyCount": 0},
            {"Bucket": BUCKET, "Prefix": key, "MaxKeys": 1},
        )
        stub.add_client_error(
            "get_object", service_error_code="AccessDenied", http_status_code=403
        )
        stub.add_response(
            "list_objects_v2",
            {"KeyCount": 1, "Contents": [{"Key": key}]},
            {"Bucket": BUCKET, "Prefix": key, "MaxKeys": 1},
        )
        stub.add_client_error(
            "get_object", service_error_code="InvalidRequest", http_status_code=400
        )

        assert store.read_result(media_id) == SanitiseResult(
            ok=True, width=900, height=600, widths=(320,), reason=None
        )
        assert store.read_result(media_id) is None
        assert store.read_result(media_id) is None
        with pytest.raises(TransientError):
            store.read_result(media_id)
        with pytest.raises(TransientError):
            store.read_result(media_id)
        stub.assert_no_pending_responses()


def test_copy_variants_keeps_the_objects_content_type(store: S3MediaStore) -> None:
    # The /m/* behaviour sets no Content-Type of its own [Task 2 ruling]:
    # the copy must carry the source's image/webp, which only COPY does.
    media_id = uuid.uuid4()
    key = uuid.uuid4().hex
    with Stubber(store._client()) as stub:
        for width in (320, 960):
            stub.add_response(
                "copy_object",
                {"CopyObjectResult": {}},
                {
                    "Bucket": BUCKET,
                    "Key": f"public/{key}/{width}.webp",
                    "CopySource": {
                        "Bucket": BUCKET,
                        "Key": f"staged/{media_id}/{width}.webp",
                    },
                    "MetadataDirective": "COPY",
                },
            )
        store.copy_variants(f"staged/{media_id}/", f"public/{key}/", [320, 960])
        stub.assert_no_pending_responses()

    for src, dst, widths in (
        ("staged/", f"public/{key}/", [320]),
        (f"staged/{media_id}/", f"quarantine/{media_id}", [320]),
        (f"staged/{media_id}/", f"public/{key}/", [640]),
    ):
        with pytest.raises(ValueError):
            store.copy_variants(src, dst, widths)


def test_a_pinned_copy_names_the_etag_and_refuses_a_changed_source(
    store: S3MediaStore,
) -> None:
    """[I1] ``CopySourceIfMatch`` per variant; a 412 is :class:`SourceChanged`.

    Anything else S3 says is still a transient error.
    """
    media_id = uuid.uuid4()
    pins = {320: '"etag-320"', 960: '"etag-960"'}
    copy = {
        "Bucket": BUCKET,
        "Key": f"archive/{media_id}/320.webp",
        "CopySource": {"Bucket": BUCKET, "Key": f"staged/{media_id}/320.webp"},
        "MetadataDirective": "COPY",
        "CopySourceIfMatch": '"etag-320"',
    }
    with Stubber(store._client()) as stub:
        for width in (320, 960):
            stub.add_response(
                "copy_object",
                {"CopyObjectResult": {}},
                {
                    **copy,
                    "Key": f"archive/{media_id}/{width}.webp",
                    "CopySource": {
                        "Bucket": BUCKET,
                        "Key": f"staged/{media_id}/{width}.webp",
                    },
                    "CopySourceIfMatch": pins[width],
                },
            )
        store.copy_variants(
            f"staged/{media_id}/", f"archive/{media_id}/", [320, 960], if_match=pins
        )
        stub.add_client_error(
            "copy_object",
            service_error_code="PreconditionFailed",
            http_status_code=412,
            expected_params=copy,
        )
        with pytest.raises(SourceChanged):
            store.copy_variants(
                f"staged/{media_id}/", f"archive/{media_id}/", [320], if_match=pins
            )
        stub.add_client_error(
            "copy_object", service_error_code="SlowDown", expected_params=copy
        )
        with pytest.raises(TransientError):
            store.copy_variants(
                f"staged/{media_id}/", f"archive/{media_id}/", [320], if_match=pins
            )
        stub.assert_no_pending_responses()

    # A pin that does not name every width copied is a caller's bug.
    with pytest.raises(ValueError, match="pin"):
        store.copy_variants(
            f"staged/{media_id}/", f"archive/{media_id}/", [1600], if_match=pins
        )


def test_staged_etags_reads_each_variant_or_reports_one_missing(
    store: S3MediaStore,
) -> None:
    media_id = uuid.uuid4()
    with Stubber(store._client()) as stub:
        for width in (320, 960):
            stub.add_response(
                "head_object",
                {"ETag": f'"etag-{width}"'},
                {"Bucket": BUCKET, "Key": f"staged/{media_id}/{width}.webp"},
            )
        assert store.staged_etags(media_id, [320, 960]) == {
            320: '"etag-320"',
            960: '"etag-960"',
        }
        stub.add_response(
            "head_object",
            {"ETag": '"etag-320"'},
            {"Bucket": BUCKET, "Key": f"staged/{media_id}/320.webp"},
        )
        stub.add_client_error(
            "head_object",
            service_error_code="404",
            http_status_code=404,
            expected_params={
                "Bucket": BUCKET,
                "Key": f"staged/{media_id}/960.webp",
            },
        )
        assert store.staged_etags(media_id, [320, 960]) is None
        stub.add_client_error(
            "head_object",
            service_error_code="500",
            http_status_code=500,
            expected_params={
                "Bucket": BUCKET,
                "Key": f"staged/{media_id}/320.webp",
            },
        )
        with pytest.raises(TransientError):
            store.staged_etags(media_id, [320])
        stub.assert_no_pending_responses()


def test_delete_prefix_lists_then_deletes(store: S3MediaStore) -> None:
    media_id = uuid.uuid4()
    prefix = f"staged/{media_id}/"
    keys = [f"{prefix}{w}.webp" for w in (320, 960)] + [f"{prefix}result.json"]
    with Stubber(store._client()) as stub:
        stub.add_response(
            "list_objects_v2",
            {"KeyCount": 3, "Contents": [{"Key": k} for k in keys]},
            {"Bucket": BUCKET, "Prefix": prefix},
        )
        stub.add_response(
            "delete_objects",
            {"Deleted": [{"Key": k} for k in keys]},
            {
                "Bucket": BUCKET,
                "Delete": {"Objects": [{"Key": k} for k in keys], "Quiet": True},
            },
        )
        # An empty prefix lists nothing and deletes nothing.
        stub.add_response(
            "list_objects_v2",
            {"KeyCount": 0},
            {"Bucket": BUCKET, "Prefix": f"quarantine/{media_id}"},
        )
        # A partial failure is a failure: the task is retried.
        stub.add_response(
            "list_objects_v2",
            {"KeyCount": 1, "Contents": [{"Key": keys[0]}]},
            {"Bucket": BUCKET, "Prefix": prefix},
        )
        stub.add_response(
            "delete_objects",
            {"Errors": [{"Key": keys[0], "Code": "AccessDenied"}]},
            {
                "Bucket": BUCKET,
                "Delete": {"Objects": [{"Key": keys[0]}], "Quiet": True},
            },
        )

        store.delete_prefix(prefix)
        store.delete_prefix(f"quarantine/{media_id}")
        with pytest.raises(TransientError):
            store.delete_prefix(prefix)
        stub.assert_no_pending_responses()

    for wide in ("staged/", "", "public/", f"staged/{media_id}", "../etc/"):
        with pytest.raises(ValueError):
            store.delete_prefix(wide)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            b'{"ok": true, "width": 40000, "height": 1000, "widths": [320, 960, 1600]}',
            SanitiseResult(
                ok=True, width=40000, height=1000, widths=(320, 960, 1600), reason=None
            ),
        ),
        (
            b'{"ok": false, "reason": "unreadable"}',
            SanitiseResult(
                ok=False, width=None, height=None, widths=(), reason="unreadable"
            ),
        ),
        (
            b"not json",
            SanitiseResult(
                ok=False, width=None, height=None, widths=(), reason="malformed"
            ),
        ),
        (
            b"[1, 2]",
            SanitiseResult(
                ok=False, width=None, height=None, widths=(), reason="malformed"
            ),
        ),
    ],
)
def test_parse_result(raw: bytes, expected: SanitiseResult) -> None:
    assert parse_result(raw) == expected
