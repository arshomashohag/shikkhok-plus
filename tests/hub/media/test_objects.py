"""The bucket's deletion outbox, ``media_object_task``, and its drain.

A takedown enqueues the prefixes in its own transaction; the drain deletes
them from the bucket every two minutes, marks each done, and counts a failed
attempt on the rest. Its heartbeat moves only on progress [R8a]: a drain with
nothing to do, or one that finished at least one deletion.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db.models import HUB_MEDIA_OBJECT_JOB
from app.hub.media import commands, objects
from app.hub.media.storage import S3MediaStore
from tests.hub.media.fakes import FakeMediaStore, Stored
from tests.hub.media.support import NOW


def _tasks(session: Session) -> list[tuple[str, dt.datetime | None, int]]:
    session.rollback()
    return [
        (r.prefix, r.done_at, r.attempts)
        for r in session.execute(
            sa.text(
                "SELECT prefix, done_at, attempts FROM media_object_task ORDER BY id"
            )
        )
    ]


def _heartbeat(session: Session) -> dt.datetime | None:
    session.rollback()
    return session.execute(
        sa.text("SELECT last_success_at FROM job_heartbeat WHERE job_name = :j"),
        {"j": HUB_MEDIA_OBJECT_JOB},
    ).scalar_one_or_none()


def test_enqueue_commits_nothing_and_refuses_wide_prefixes(
    restricted_session: Session, owner_session: Session
) -> None:
    media_id = uuid.uuid4()
    objects.enqueue(
        restricted_session,
        [f"staged/{media_id}/", f"staged/{media_id}/", f"quarantine/{media_id}"],
        NOW,
    )
    # The caller's transaction decides: rolled back, nothing is left.
    restricted_session.rollback()
    assert _tasks(owner_session) == []

    for wide in (
        "staged/",
        "",
        "public/",
        f"staged/{media_id}",
        f"quarantine/{media_id}/",
        f"public/{uuid.uuid4().hex.upper()}/",
        f"other/{media_id}/",
        f"staged/{media_id}/../",
    ):
        with pytest.raises(ValueError, match="prefix"):
            objects.enqueue(restricted_session, [wide], NOW)


def test_drain_marks_done_and_retries_failures(
    restricted_session: Session,
    owner_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    first, second = uuid.uuid4(), uuid.uuid4()
    key = uuid.uuid4().hex
    prefixes = [f"staged/{first}/", f"public/{key}/", f"quarantine/{second}"]
    objects.enqueue(restricted_session, prefixes, NOW)
    restricted_session.commit()

    store = FakeMediaStore()
    store.objects[f"staged/{first}/320.webp"] = Stored(b"x", "image/webp")
    store.objects[f"staged/{second}/320.webp"] = Stored(b"y", "image/webp")
    store.failing.add(f"public/{key}/")

    later = NOW + dt.timedelta(minutes=2)
    with caplog.at_level(logging.WARNING, logger="app.hub.media.commands"):
        done = commands.drain(restricted_session, store, later)

    assert done == 2
    assert _tasks(owner_session) == [
        (f"staged/{first}/", later, 0),
        (f"public/{key}/", None, 1),
        (f"quarantine/{second}", later, 0),
    ]
    assert list(store.objects) == [f"staged/{second}/320.webp"]
    assert "media object delete failed" in caplog.text
    # Partial progress is progress.
    assert _heartbeat(owner_session) == later

    store.failing.clear()
    again = NOW + dt.timedelta(minutes=4)
    assert commands.drain(restricted_session, store, again) == 1
    assert _tasks(owner_session)[1] == (f"public/{key}/", again, 1)
    assert store.deleted == [
        f"staged/{first}/",
        f"quarantine/{second}",
        f"public/{key}/",
    ]


def test_drain_heartbeat_only_on_progress(
    restricted_session: Session, owner_session: Session
) -> None:
    # Nothing waiting: the drain is healthy and says so.
    assert commands.drain(restricted_session, FakeMediaStore(), NOW) == 0
    assert _heartbeat(owner_session) == NOW

    # Every deletion failing is not progress: the heartbeat stays where it
    # was, so a drain that cannot reach the bucket goes stale and alerts.
    prefix = f"staged/{uuid.uuid4()}/"
    objects.enqueue(restricted_session, [prefix], NOW)
    restricted_session.commit()
    store = FakeMediaStore(failing={prefix})
    later = NOW + dt.timedelta(minutes=10)
    assert commands.drain(restricted_session, store, later) == 0
    assert _heartbeat(owner_session) == NOW
    assert _tasks(owner_session) == [(prefix, None, 1)]


def test_drain_takes_fresh_rows_before_failing_ones(
    restricted_session: Session, owner_session: Session
) -> None:
    # A prefix that always fails must not starve the rows behind it.
    stuck = f"staged/{uuid.uuid4()}/"
    fresh = f"staged/{uuid.uuid4()}/"
    objects.enqueue(restricted_session, [stuck], NOW)
    restricted_session.commit()
    store = FakeMediaStore(failing={stuck})
    commands.drain(restricted_session, store, NOW, limit=1)
    objects.enqueue(restricted_session, [fresh], NOW)
    restricted_session.commit()

    assert commands.drain(restricted_session, store, NOW, limit=1) == 1
    assert store.deleted == [fresh]


def test_drain_command(
    restricted_engine: Engine,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prefix = f"archive/{uuid.uuid4()}/"
    with Session(restricted_engine) as session:
        # The command runs on the real clock, so the row is due by it.
        objects.enqueue(session, [prefix], dt.datetime.now(tz=dt.UTC))
        session.commit()
    store = FakeMediaStore()
    monkeypatch.setattr(commands, "build_engine", lambda: restricted_engine)
    monkeypatch.setattr(commands, "S3MediaStore", lambda: store)

    assert commands.main(["drain", "--limit", "5"]) == 0

    assert store.deleted == [prefix]
    assert _tasks(owner_session)[0][1] is not None
    assert _heartbeat(owner_session) is not None
    with pytest.raises(SystemExit):
        commands.main(["drain", "--limit", "0"])


def test_drain_without_a_bucket_keeps_rows_and_skips_heartbeat(
    restricted_session: Session, owner_session: Session
) -> None:
    # R9: no bucket configured is a failed delete. The row stays pending
    # with an attempt counted, and a run where every row failed is not
    # progress, so the heartbeat is not stamped and the check alerts.
    prefix = f"public/{uuid.uuid4().hex}/"
    objects.enqueue(restricted_session, [prefix], NOW)
    restricted_session.commit()
    store = S3MediaStore(bucket="", region="ap-south-1", credentials_file="")

    assert commands.drain(restricted_session, store, NOW) == 0

    assert _tasks(owner_session) == [(prefix, None, 1)]
    assert _heartbeat(owner_session) is None


def test_deferred_rows_wait_for_the_upload_window(
    restricted_session: Session, owner_session: Session
) -> None:
    # An upload signed at NOW may still land, and be sanitised, until the
    # 20-minute deadline; deletes enqueued for that moment wait for it.
    media_id = uuid.uuid4()
    objects.enqueue_upload_window(
        restricted_session, media_id, NOW, NOW + dt.timedelta(minutes=1)
    )
    restricted_session.commit()
    due = NOW + objects.UPLOAD_WINDOW
    store = FakeMediaStore()

    # Nothing is due yet: an empty drain, and a healthy one.
    assert commands.drain(restricted_session, store, due - dt.timedelta(seconds=1)) == 0
    assert store.deleted == []
    assert _heartbeat(owner_session) == due - dt.timedelta(seconds=1)

    assert commands.drain(restricted_session, store, due) == 2
    assert store.deleted == [f"quarantine/{media_id}", f"staged/{media_id}/"]

    # The late-upload backstop catches a post that lands later still.
    backstop = NOW + objects.LATE_UPLOAD_BACKSTOP
    assert commands.drain(restricted_session, store, backstop) == 2
    assert store.deleted[2:] == [f"quarantine/{media_id}", f"staged/{media_id}/"]

    # Past both, there is nothing to defer.
    objects.enqueue_upload_window(restricted_session, uuid.uuid4(), NOW, backstop)
    restricted_session.commit()
    assert len(_tasks(owner_session)) == 4
    assert objects.UPLOAD_WINDOW == dt.timedelta(minutes=20)
    assert objects.LATE_UPLOAD_BACKSTOP == dt.timedelta(days=1)
