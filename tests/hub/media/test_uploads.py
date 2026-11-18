"""Upload sessions: the quota, the daily ceiling, and completing an upload.

``init_upload`` validates, locks the owner, checks the 12 / 8 quotas,
consumes the daily ceiling and signs a POST; ``complete`` reads the
sanitiser's ``result.json`` and moves the photo to review, or rejects it as
unreadable. Every test runs the services as the application role against
:class:`~tests.hub.media.fakes.FakeMediaStore`; the presigned POST policy
itself is pinned against the real :class:`~app.hub.media.storage.S3MediaStore`
in :func:`test_presign_policy_exact`.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import pathlib
import threading
import uuid
from typing import Final

import pytest
import sqlalchemy as sa
from botocore.stub import Stubber
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.ceilings import HUB_MEDIA_OWNER_DAILY
from app.batches.service import BatchNotFound
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.hub.media import quota, uploads
from app.hub.media.objects import UPLOAD_WINDOW
from app.hub.media.storage import S3MediaStore, UploadTicket
from tests.hub.media.fakes import FakeMediaStore
from tests.hub.media.support import NOW, Owner, arrange, media_row, tasks

#: An ok result, as the sanitiser writes it.
OK: Final[dict[str, object]] = {
    "ok": True,
    "width": 1600,
    "height": 1200,
    "widths": [320, 960, 1600],
}

#: Statuses that count against the quota: every one but the two terminal.
COUNTED: Final[tuple[str, ...]] = (
    "awaiting_upload",
    "processing",
    "pending_review",
    "approved",
    "held",
)


@pytest.fixture
def store() -> FakeMediaStore:
    return FakeMediaStore()


@pytest.fixture
def tutor(owner_session: Session) -> Owner:
    return arrange(owner_session)


def _init(
    session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    *,
    batch: bool = False,
    content_type: str = "image/jpeg",
    byte_size: int = 2048,
    now: dt.datetime = NOW,
) -> UploadTicket:
    return uploads.init_upload(
        session,
        store,
        tutor.lens,
        batch_id=tutor.batch_id if batch else None,
        content_type=content_type,
        byte_size=byte_size,
        now=now,
    )


def _status(session: Session, media_id: uuid.UUID) -> sa.Row[tuple[object, ...]]:
    session.rollback()
    return session.execute(
        sa.text(
            "SELECT status, rejection_code, width, height, widths, alt_en, alt_bn "
            "FROM listing_media WHERE id = :m"
        ),
        {"m": media_id},
    ).one()


def _rows(session: Session) -> int:
    session.rollback()
    return int(
        session.execute(sa.text("SELECT count(*) FROM listing_media")).scalar_one()
    )


def _daily_count(session: Session) -> int:
    session.rollback()
    return int(
        session.execute(
            sa.text(
                "SELECT coalesce(sum(count), 0) FROM rate_limit_counter "
                "WHERE scope_kind = 'hub_media_day'"
            )
        ).scalar_one()
    )


def test_init_inserts_awaiting_upload_and_signs(
    restricted_session: Session,
    owner_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
) -> None:
    ticket = _init(
        restricted_session, store, tutor, batch=True, content_type="image/png"
    )

    owner_session.rollback()
    row = owner_session.execute(
        sa.text(
            "SELECT owner_id, batch_id, status, content_type, byte_size, created_at "
            "FROM listing_media WHERE id = :m"
        ),
        {"m": ticket.media_id},
    ).one()
    assert tuple(row) == (
        tutor.lens.owner_id,
        tutor.batch_id,
        "awaiting_upload",
        "image/png",
        2048,
        NOW,
    )
    assert store.presigned == [(ticket.media_id, "image/png")]
    assert ticket.fields["key"] == f"quarantine/{ticket.media_id}"
    assert _daily_count(owner_session) == 1


def test_init_refuses_type_size_and_foreign_batch(
    restricted_session: Session,
    owner_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
) -> None:
    for content_type in ("image/gif", "image/svg+xml", "text/html", "IMAGE/JPEG"):
        with pytest.raises(ValidationError) as refused:
            _init(restricted_session, store, tutor, content_type=content_type)
        assert refused.value.code == "MEDIA_TYPE_NOT_ALLOWED"
        assert refused.value.message_key == "hub.media.type_not_allowed"

    for size in (8_388_609, 0, -1):
        with pytest.raises(ValidationError) as refused:
            _init(restricted_session, store, tutor, byte_size=size)
        assert refused.value.code == "MEDIA_TOO_LARGE"
        assert refused.value.message_key == "hub.media.too_large"

    other = arrange(owner_session)
    with pytest.raises(BatchNotFound) as refused:
        uploads.init_upload(
            restricted_session,
            store,
            tutor.lens,
            batch_id=other.batch_id,
            content_type="image/jpeg",
            byte_size=2048,
            now=NOW,
        )
    assert refused.value.status == 404

    # The largest allowed upload is accepted; none of the refusals left a
    # row, a signature or a spent daily allowance behind.
    _init(restricted_session, store, tutor, byte_size=8_388_608)
    assert _rows(owner_session) == 1
    assert len(store.presigned) == 1
    assert _daily_count(owner_session) == 1


@pytest.mark.parametrize("batch", [False, True], ids=["owner", "batch"])
def test_init_counts_every_nonterminal_status_against_quota(
    restricted_session: Session,
    owner_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    batch: bool,
) -> None:
    limit = quota.BATCH_LIMIT if batch else quota.OWNER_LIMIT
    batch_id = tutor.batch_id if batch else None
    ids = [
        media_row(
            owner_session,
            tutor.lens.owner_id,
            status=COUNTED[i % len(COUNTED)],
            batch_id=batch_id,
            position=i,
        )
        for i in range(limit)
    ]
    # Photos in the other gallery never count against this one.
    other_batch = None if batch else tutor.batch_id
    for i in range(3):
        media_row(owner_session, tutor.lens.owner_id, batch_id=other_batch, position=i)

    with pytest.raises(ConflictError) as refused:
        _init(restricted_session, store, tutor, batch=batch)
    assert refused.value.code == "MEDIA_LIMIT_REACHED"
    assert refused.value.message_key == "hub.media.limit_reached"
    assert _daily_count(owner_session) == 0

    # A rejected or withdrawn photo frees its slot.
    for status, media_id in zip(("rejected", "withdrawn"), ids[-2:], strict=True):
        owner_session.execute(
            sa.text(
                "UPDATE listing_media SET status = CAST(:s AS media_status), "
                "public_key = NULL WHERE id = :m"
            ),
            {"s": status, "m": media_id},
        )
        owner_session.commit()
        _init(restricted_session, store, tutor, batch=batch)

    with pytest.raises(ConflictError):
        _init(restricted_session, store, tutor, batch=batch)
    assert (quota.OWNER_LIMIT, quota.BATCH_LIMIT) == (12, 8)


@pytest.mark.parametrize("batch", [False, True], ids=["owner", "batch"])
def test_concurrent_inits_never_exceed_quota(
    restricted_engine: Engine,
    owner_session: Session,
    tutor: Owner,
    batch: bool,
) -> None:
    # Review Focus 4. One slot is left; two sessions race for it. The
    # presign sleeps inside the transaction, so without the owner-row lock
    # both would count the same eleven (or seven) rows and both insert.
    limit = quota.BATCH_LIMIT if batch else quota.OWNER_LIMIT
    batch_id = tutor.batch_id if batch else None
    for i in range(limit - 1):
        media_row(owner_session, tutor.lens.owner_id, batch_id=batch_id, position=i)

    slow = FakeMediaStore(delay=0.5)
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    barrier = threading.Barrier(2)
    won: list[uuid.UUID] = []
    refused: list[str] = []
    other: list[BaseException] = []
    lock = threading.Lock()

    def attempt() -> None:
        session = factory()
        try:
            barrier.wait(timeout=30)
            ticket = _init(session, slow, tutor, batch=batch)
            with lock:
                won.append(ticket.media_id)
        except ConflictError as error:
            with lock:
                refused.append(error.code)
        except BaseException as error:  # noqa: BLE001  recorded, then asserted
            with lock:
                other.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert other == []
    assert len(won) == 1
    assert refused == ["MEDIA_LIMIT_REACHED"]
    owner_session.rollback()
    counted = owner_session.execute(
        sa.text(
            "SELECT count(*) FROM listing_media WHERE owner_id = :o "
            "AND batch_id IS NOT DISTINCT FROM :b"
        ),
        {"o": tutor.lens.owner_id, "b": batch_id},
    ).scalar_one()
    assert counted == limit


def test_daily_ceiling_30(
    restricted_session: Session,
    owner_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
) -> None:
    for _ in range(30):
        ticket = _init(restricted_session, store, tutor)
        # Withdrawn at once, so the 12-photo quota never binds first.
        owner_session.execute(
            sa.text("UPDATE listing_media SET status = 'withdrawn' WHERE id = :m"),
            {"m": ticket.media_id},
        )
        owner_session.commit()

    with pytest.raises(ConflictError) as refused:
        _init(restricted_session, store, tutor, now=NOW + dt.timedelta(hours=14))
    assert refused.value.code == "MEDIA_LIMIT_REACHED"
    assert refused.value.message_key == "hub.media.limit_reached"
    # The refusal inserted nothing and spent nothing.
    assert _rows(owner_session) == 30
    assert _daily_count(owner_session) == 30
    assert len(store.presigned) == 30

    # Another owner has their own allowance; tomorrow this one does too.
    _init(restricted_session, store, arrange(owner_session))
    _init(restricted_session, store, tutor, now=NOW + dt.timedelta(days=1))
    assert HUB_MEDIA_OWNER_DAILY == 30


def _creds(path: pathlib.Path, key: str) -> None:
    path.write_text(
        "[default]\n"
        f"aws_access_key_id = {key}\n"
        "aws_secret_access_key = c2VjcmV0\n"
        f"aws_session_token = token-for-{key}\n"
    )


@pytest.fixture
def s3_store(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[S3MediaStore, pathlib.Path]:
    # Only the mounted file may supply credentials, as in the container.
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
    store = S3MediaStore(
        bucket="shikkhokplus-staging-media-123456789012",
        region="ap-south-1",
        credentials_file=str(path),
    )
    return store, path


def test_presign_policy_exact(s3_store: tuple[S3MediaStore, pathlib.Path]) -> None:
    store, _ = s3_store
    media_id = uuid.uuid4()
    bucket = "shikkhokplus-staging-media-123456789012"

    with Stubber(store._client()) as stub:
        before = dt.datetime.now(tz=dt.UTC).replace(microsecond=0)
        ticket = store.presign_upload(media_id, "image/webp")
        # Signing is local: not one request reached S3.
        stub.assert_no_pending_responses()

    policy = json.loads(base64.b64decode(ticket.fields["policy"]))
    conditions = policy["conditions"]
    assert ["content-length-range", 1, 8388608] in conditions
    assert {"Content-Type": "image/webp"} in conditions
    assert {"x-amz-meta-declared-type": "image/webp"} in conditions
    assert {"key": f"quarantine/{media_id}"} in conditions
    assert {"bucket": bucket} in conditions
    # No condition is a prefix match: each field is pinned exactly.
    assert not [c for c in conditions if isinstance(c, list) and c[0] == "starts-with"]

    assert ticket.fields["key"] == f"quarantine/{media_id}"
    assert ticket.fields["Content-Type"] == "image/webp"
    assert ticket.fields["x-amz-meta-declared-type"] == "image/webp"
    assert ticket.fields["x-amz-security-token"] == "token-for-ASIAFIRSTKEY00000000"
    # The regional, virtual-hosted endpoint the web CSPs admit, and nothing
    # the browser would have to preflight.
    assert ticket.url == f"https://{bucket}.s3.ap-south-1.amazonaws.com/"

    expiration = dt.datetime.fromisoformat(policy["expiration"].replace("Z", "+00:00"))
    signed = dt.datetime.strptime(
        ticket.fields["x-amz-date"], "%Y%m%dT%H%M%SZ"
    ).replace(tzinfo=dt.UTC)
    assert abs((expiration - signed) - dt.timedelta(seconds=600)) <= dt.timedelta(
        seconds=1
    )
    assert before + dt.timedelta(seconds=599) <= ticket.expires_at
    assert ticket.expires_at <= expiration + dt.timedelta(seconds=1)
    assert ticket.media_id == media_id


def test_complete_before_result_is_not_uploaded_then_succeeds(
    restricted_session: Session,
    owner_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
) -> None:
    # Review Focus 2: a double tap, or a slow Lambda.
    media_id = _init(restricted_session, store, tutor).media_id

    with pytest.raises(ConflictError) as early:
        uploads.complete(
            restricted_session,
            store,
            tutor.lens,
            media_id,
            alt_en="Our classroom",
            alt_bn="আমাদের শ্রেণিকক্ষ",
            now=NOW + dt.timedelta(minutes=1),
        )
    assert early.value.code == "MEDIA_NOT_UPLOADED"
    assert early.value.message_key == "hub.media.not_uploaded"
    assert tuple(_status(owner_session, media_id)) == (
        "awaiting_upload",
        None,
        None,
        None,
        None,
        None,
        None,
    )

    store.put_result(media_id, OK)
    done = uploads.complete(
        restricted_session,
        store,
        tutor.lens,
        media_id,
        alt_en="  Our classroom ",
        alt_bn="আমাদের শ্রেণিকক্ষ",
        now=NOW + dt.timedelta(minutes=2),
    )
    assert done.id == media_id
    assert tuple(_status(owner_session, media_id)) == (
        "pending_review",
        None,
        1600,
        1200,
        [320, 960, 1600],
        "Our classroom",
        "আমাদের শ্রেণিকক্ষ",
    )

    # Idempotent: a second call changes nothing and raises nothing.
    again = uploads.complete(
        restricted_session,
        store,
        tutor.lens,
        media_id,
        alt_en="Something else",
        alt_bn="অন্য কিছু",
        now=NOW + dt.timedelta(minutes=3),
    )
    assert again.status == "pending_review"
    assert _status(owner_session, media_id).alt_en == "Our classroom"
    assert tasks(owner_session) == []

    # It carries what approval needs, so the approved-dimensions CHECK holds.
    owner_session.execute(
        sa.text(
            "UPDATE listing_media SET status = 'approved', public_key = :k "
            "WHERE id = :m"
        ),
        {"k": uuid.uuid4().hex, "m": media_id},
    )
    owner_session.commit()


def test_complete_unreadable_marks_rejected(
    restricted_session: Session,
    owner_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
) -> None:
    media_id = _init(restricted_session, store, tutor).media_id
    store.put_result(media_id, {"ok": False, "reason": "unreadable"})

    for _ in range(2):
        with pytest.raises(ValidationError) as refused:
            uploads.complete(
                restricted_session,
                store,
                tutor.lens,
                media_id,
                alt_en="Our classroom",
                alt_bn="আমাদের শ্রেণিকক্ষ",
                now=NOW,
            )
        assert refused.value.code == "MEDIA_UNREADABLE"
        assert refused.value.message_key == "hub.media.unreadable"

    row = _status(owner_session, media_id)
    assert (row.status, row.rejection_code, row.width) == (
        "rejected",
        "unreadable",
        None,
    )
    # The second call changed nothing and enqueued nothing more.
    assert tasks(owner_session) == [f"quarantine/{media_id}", f"staged/{media_id}/"]
    # A rejected photo frees its quota slot.
    assert quota.counted(restricted_session, tutor.lens.owner_id, None) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"ok": True, "width": 10, "height": 10, "widths": []},
        {"ok": True, "width": 10, "height": 10, "widths": [640]},
        {"ok": True, "width": 0, "height": 10, "widths": [320]},
        {"ok": True, "width": True, "height": 10, "widths": [320]},
        {"ok": "yes"},
    ],
)
def test_malformed_result_is_unreadable(
    restricted_session: Session,
    owner_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    payload: dict[str, object],
) -> None:
    media_id = _init(restricted_session, store, tutor).media_id
    store.put_result(media_id, payload)

    with pytest.raises(ValidationError, match="MEDIA_UNREADABLE"):
        uploads.complete(
            restricted_session,
            store,
            tutor.lens,
            media_id,
            alt_en="A",
            alt_bn="ক",
            now=NOW,
        )
    assert _status(owner_session, media_id).status == "rejected"


def test_complete_with_no_result_after_twenty_minutes_is_unreadable(
    restricted_session: Session,
    owner_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
) -> None:
    # R7c: the Lambda never retries, so a timeout or OOM writes no result,
    # and the API is the only party that can give the photo an end.
    media_id = _init(restricted_session, store, tutor).media_id

    def complete(at: dt.timedelta) -> None:
        uploads.complete(
            restricted_session,
            store,
            tutor.lens,
            media_id,
            alt_en="Our classroom",
            alt_bn="আমাদের শ্রেণিকক্ষ",
            now=NOW + at,
        )

    with pytest.raises(ConflictError, match="MEDIA_NOT_UPLOADED"):
        complete(dt.timedelta(minutes=20))
    assert _status(owner_session, media_id).status == "awaiting_upload"
    assert tasks(owner_session) == []

    with pytest.raises(ValidationError, match="MEDIA_UNREADABLE"):
        complete(dt.timedelta(minutes=20, seconds=1))
    row = _status(owner_session, media_id)
    assert (row.status, row.rejection_code) == ("rejected", "unreadable")
    assert tasks(owner_session) == [f"quarantine/{media_id}", f"staged/{media_id}/"]
    assert uploads.RESULT_DEADLINE == dt.timedelta(minutes=20)


def test_alt_text_phone_scanned_and_required(
    restricted_session: Session,
    owner_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
) -> None:
    media_id = _init(restricted_session, store, tutor).media_id
    store.put_result(media_id, OK)

    def complete(alt_en: str, alt_bn: str) -> None:
        uploads.complete(
            restricted_session,
            store,
            tutor.lens,
            media_id,
            alt_en=alt_en,
            alt_bn=alt_bn,
            now=NOW,
        )

    for alt_en, alt_bn, field in (
        ("", "আমাদের শ্রেণিকক্ষ", "alt_en"),
        ("Our classroom", "   ", "alt_bn"),
        ("x" * 201, "আমাদের শ্রেণিকক্ষ", "alt_en"),
        ("Our classroom", "ক" * 201, "alt_bn"),
    ):
        with pytest.raises(ValidationError) as refused:
            complete(alt_en, alt_bn)
        assert refused.value.code == "MEDIA_ALT_INVALID"
        assert refused.value.message_key == "hub.media.alt_invalid"
        assert refused.value.details == {"field": field}

    for alt_en, alt_bn, field in (
        ("Call 01711-000000", "আমাদের শ্রেণিকক্ষ", "alt_en"),
        ("Our classroom", "ফোন ০১৭১১০০০০০০", "alt_bn"),
    ):
        with pytest.raises(ValidationError) as refused:
            complete(alt_en, alt_bn)
        assert refused.value.code == "HUB_TEXT_CONTAINS_CONTACT"
        assert refused.value.details == {"field": field}

    assert _status(owner_session, media_id).status == "awaiting_upload"
    complete("x" * 200, "ক" * 200)
    assert _status(owner_session, media_id).status == "pending_review"


def test_complete_refuses_another_owners_photo(
    restricted_session: Session,
    owner_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
) -> None:
    media_id = _init(restricted_session, store, tutor).media_id
    store.put_result(media_id, OK)
    stranger = arrange(owner_session)

    for target in (media_id, uuid.uuid4()):
        with pytest.raises(AuthorizationError) as refused:
            uploads.complete(
                restricted_session,
                store,
                stranger.lens,
                target,
                alt_en="A",
                alt_bn="ক",
                now=NOW,
            )
        assert refused.value.code == "MEDIA_NOT_FOUND"
        assert refused.value.status == 404
    assert _status(owner_session, media_id).status == "awaiting_upload"


# ---------------------------------------------------------------------------
# [I3] An abandoned upload gives its slot back once its window has closed.
# ---------------------------------------------------------------------------

#: An upload signed so long ago that nothing can still land for it.
ABANDONED: Final[dt.datetime] = NOW - UPLOAD_WINDOW

#: An upload signed a second too recently for that.
FRESH: Final[dt.datetime] = ABANDONED + dt.timedelta(seconds=1)


@pytest.mark.parametrize("batch", [False, True], ids=["owner", "batch"])
def test_init_withdraws_abandoned_uploads_and_takes_their_slot(
    restricted_session: Session,
    owner_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    batch: bool,
) -> None:
    """A full gallery of abandoned uploads accepts one more; they are withdrawn.

    Every in-flight row of the owner's past the window goes, in either
    gallery, with its quarantine and staged objects enqueued; another
    owner's abandoned upload is not this owner's to withdraw.
    """
    limit = quota.BATCH_LIMIT if batch else quota.OWNER_LIMIT
    batch_id = tutor.batch_id if batch else None
    abandoned = [
        media_row(
            owner_session,
            tutor.lens.owner_id,
            status=("awaiting_upload", "processing")[i % 2],
            batch_id=batch_id,
            created_at=ABANDONED,
            position=i,
        )
        for i in range(limit)
    ]
    elsewhere = media_row(
        owner_session,
        tutor.lens.owner_id,
        status="awaiting_upload",
        batch_id=tutor.batch_id if not batch else None,
        created_at=ABANDONED,
    )
    stranger = arrange(owner_session)
    theirs = media_row(
        owner_session,
        stranger.lens.owner_id,
        status="awaiting_upload",
        created_at=ABANDONED,
    )

    ticket = _init(restricted_session, store, tutor, batch=batch)

    for media_id in [*abandoned, elsewhere]:
        assert _status(owner_session, media_id).status == "withdrawn"
    assert _status(owner_session, theirs).status == "awaiting_upload"
    assert _status(owner_session, ticket.media_id).status == "awaiting_upload"
    assert sorted(tasks(owner_session)) == sorted(
        prefix
        for media_id in [*abandoned, elsewhere]
        for prefix in (f"quarantine/{media_id}", f"staged/{media_id}/")
    )
    # A completion for a withdrawn upload finds nothing.
    store.put_result(abandoned[0], OK)
    with pytest.raises(AuthorizationError) as refused:
        uploads.complete(
            restricted_session,
            store,
            tutor.lens,
            abandoned[0],
            alt_en="A classroom",
            alt_bn="একটি শ্রেণিকক্ষ",
            now=NOW,
        )
    assert refused.value.code == "MEDIA_NOT_FOUND"


def test_a_fresh_upload_still_holds_its_slot(
    restricted_session: Session,
    owner_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
) -> None:
    """Inside its window an upload may still land, so it counts and stays."""
    fresh = media_row(
        owner_session,
        tutor.lens.owner_id,
        status="awaiting_upload",
        created_at=FRESH,
    )
    for i in range(1, quota.OWNER_LIMIT):
        media_row(owner_session, tutor.lens.owner_id, position=i)

    with pytest.raises(ConflictError) as refused:
        _init(restricted_session, store, tutor)

    assert refused.value.code == "MEDIA_LIMIT_REACHED"
    assert _status(owner_session, fresh).status == "awaiting_upload"
    assert tasks(owner_session) == []


def test_concurrent_inits_withdraw_an_abandoned_upload_once(
    restricted_engine: Engine,
    owner_session: Session,
    tutor: Owner,
) -> None:
    """Two inits race for the one slot an abandoned upload frees.

    The sweep runs under the owner lock, so the second init sees the first's
    withdrawal and its new row: exactly one wins, and the abandoned upload is
    withdrawn and enqueued exactly once.
    """
    stale = media_row(
        owner_session,
        tutor.lens.owner_id,
        status="awaiting_upload",
        created_at=ABANDONED,
    )
    for i in range(1, quota.OWNER_LIMIT):
        media_row(owner_session, tutor.lens.owner_id, position=i)

    slow = FakeMediaStore(delay=0.5)
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    barrier = threading.Barrier(2)
    won: list[uuid.UUID] = []
    refused: list[str] = []
    other: list[BaseException] = []
    lock = threading.Lock()

    def attempt() -> None:
        session = factory()
        try:
            barrier.wait(timeout=30)
            ticket = _init(session, slow, tutor)
            with lock:
                won.append(ticket.media_id)
        except ConflictError as error:
            with lock:
                refused.append(error.code)
        except BaseException as error:  # noqa: BLE001  recorded, then asserted
            with lock:
                other.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert other == []
    assert len(won) == 1
    assert refused == ["MEDIA_LIMIT_REACHED"]
    assert _status(owner_session, stale).status == "withdrawn"
    assert sorted(tasks(owner_session)) == [f"quarantine/{stale}", f"staged/{stale}/"]
    assert quota.counted(owner_session, tutor.lens.owner_id, None) == quota.OWNER_LIMIT
