"""No photo write survives its owner's account deletion [R13].

Account deletion keeps a solo teacher's ``owner`` row and clears its
``account_id``; the teacher's photos are deleted and their objects queued
(Task 8). A photo write that was already past its lens check -- an upload
init, a completion, an approval, a report's dismiss-restore -- can be
waiting on the owner row lock while the deletion commits. Each re-checks,
under that lock, that a solo owner still has its account, and refuses while
writing nothing. A centre's owner row has no account by design and is
unaffected.

The races are run with real overlapping sessions: the deletion is held at
its commit, holding the owner lock, until the competing write is seen
waiting in ``pg_locks``; or the approval is held inside its copy, holding
the owner lock, until the deletion is seen waiting.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
import uuid
from collections.abc import Callable
from typing import Final

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.authz.lenses import PlatformAdminLens, TeacherLens
from app.errors import AuthorizationError
from app.governance.deletion import delete_account
from app.hub.media import uploads
from app.hub.public import invalidation
from app.moderation import media, reports
from tests.batches.conftest import make_teacher
from tests.hub.media.fakes import FakeMediaStore
from tests.hub.media.support import NOW, arrange, media_row, owner_listing, tasks
from tests.hub.support import centre_with_manager

#: The variant widths the arranged photos carry.
WIDTHS: Final[list[int]] = [320, 960, 1600]

#: An ok sanitiser result.
OK: Final[dict[str, object]] = {
    "ok": True,
    "width": 1600,
    "height": 1200,
    "widths": WIDTHS,
}

#: How long a race waits for the other side before failing the test.
PATIENCE: Final[float] = 20.0


def _phone(session: Session, account_id: uuid.UUID) -> str:
    """Read an account's number.

    :param session: A session
    :param account_id: The account
    :return: Its phone number
    """
    session.rollback()
    return str(
        session.execute(
            sa.text("SELECT phone FROM account WHERE id = :a"), {"a": account_id}
        ).scalar_one()
    )


def _wait_for_a_waiter(engine: Engine) -> None:
    """Block until some backend is waiting on a row lock.

    :param engine: An engine able to read ``pg_locks``
    :return: None
    :raises AssertionError: Nobody waited within :data:`PATIENCE`
    """
    deadline = time.monotonic() + PATIENCE
    while time.monotonic() < deadline:
        with engine.connect() as connection:
            waiting = connection.execute(
                sa.text("SELECT count(*) FROM pg_locks WHERE NOT granted")
            ).scalar_one()
        if waiting:
            return
        time.sleep(0.05)
    raise AssertionError("nobody waited on the lock")


def _in_thread(work: Callable[[], object]) -> tuple[threading.Thread, list[object]]:
    """Run work on a thread, recording its result or its exception.

    :param work: The work
    :return: The started thread and the one-item outcome list it fills
    """
    outcome: list[object] = []

    def run() -> None:
        try:
            outcome.append(work())
        except BaseException as error:  # noqa: BLE001  recorded, then asserted
            outcome.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    return thread, outcome


def _held_deletion(
    factory: sessionmaker[Session], owner_engine: Engine, phone: str
) -> tuple[threading.Thread, list[object], threading.Event]:
    """Start an account deletion that pauses at its commit, locks held.

    It signals ``ready`` at the commit and commits only once another backend
    is waiting on a lock.

    :param factory: Application-role sessions
    :param owner_engine: An engine able to read ``pg_locks``
    :param phone: The number whose account is deleted
    :return: The thread, its outcome and the ``ready`` event
    """
    ready = threading.Event()
    session = factory()
    commit = session.commit

    def held_commit() -> None:
        ready.set()
        _wait_for_a_waiter(owner_engine)
        commit()

    session.commit = held_commit  # type: ignore[method-assign]

    def work() -> object:
        try:
            return delete_account(session, phone)
        finally:
            session.close()

    thread, outcome = _in_thread(work)
    return thread, outcome, ready


def _media_rows(session: Session, owner_id: uuid.UUID) -> int:
    """Count an owner's photo rows.

    :param session: The arranging session
    :param owner_id: The owner
    :return: The count
    """
    session.rollback()
    return int(
        session.execute(
            sa.text("SELECT count(*) FROM listing_media WHERE owner_id = :o"),
            {"o": owner_id},
        ).scalar_one()
    )


def _pending(
    session: Session, store: FakeMediaStore, owner_id: uuid.UUID, **row: object
) -> uuid.UUID:
    """Arrange a photo the sanitiser read, waiting for review.

    :param session: The arranging session
    :param store: The fake bucket, given its staged variants
    :param owner_id: The owner
    :param row: Passed to :func:`media_row`; ``created_at`` defaults to an
        hour before NOW, so the upload window has closed and it can be
        approved [I1]
    :return: The media id
    """
    row.setdefault("created_at", NOW - dt.timedelta(hours=1))
    media_id = media_row(session, owner_id, **row)  # type: ignore[arg-type]
    session.execute(
        sa.text(
            "UPDATE listing_media SET width = 1600, height = 1200, widths = :ws "
            "WHERE id = :m"
        ),
        {"ws": WIDTHS, "m": media_id},
    )
    session.commit()
    store.put_result(media_id, OK)
    # What `complete` records: each staged variant's ETag [I1].
    pins = store.staged_etags(media_id, WIDTHS)
    assert pins is not None
    session.execute(
        sa.text("UPDATE listing_media SET variant_etags = :e WHERE id = :m"),
        {"e": [pins[w] for w in WIDTHS], "m": media_id},
    )
    session.commit()
    return media_id


def _depart(session: Session, owner_id: uuid.UUID) -> None:
    """Leave a solo owner as an account deletion leaves it: no account.

    :param session: The arranging session
    :param owner_id: The owner
    :return: None
    """
    session.execute(
        sa.text("UPDATE owner SET account_id = NULL WHERE id = :o"), {"o": owner_id}
    )
    session.commit()


@pytest.fixture
def admin(owner_session: Session) -> PlatformAdminLens:
    return PlatformAdminLens(account_id=make_teacher(owner_session).account_id)


def test_upload_init_racing_account_deletion_refuses(
    restricted_engine: Engine, owner_engine: Engine, owner_session: Session
) -> None:
    """The init waits on the owner lock, the deletion commits, the init refuses.

    No photo row and no object task for the owner exist afterwards, and no
    upload was signed.

    :param restricted_engine: The application role's engine
    :param owner_engine: The table owner's engine
    :param owner_session: An arranging session
    :return: None
    """
    tutor = arrange(owner_session)
    store = FakeMediaStore()
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    deleting, deleted, ready = _held_deletion(
        factory, owner_engine, _phone(owner_session, tutor.lens.account_id)
    )
    assert ready.wait(PATIENCE)

    def init() -> object:
        session = factory()
        try:
            return uploads.init_upload(
                session,
                store,
                tutor.lens,
                batch_id=None,
                content_type="image/jpeg",
                byte_size=2048,
                now=dt.datetime.now(tz=dt.UTC),
            )
        finally:
            session.close()

    initing, inited = _in_thread(init)
    deleting.join(PATIENCE * 2)
    initing.join(PATIENCE * 2)

    assert not isinstance(deleted[0], BaseException), deleted
    assert isinstance(inited[0], AuthorizationError), inited
    assert inited[0].code == "NO_TEACHER_LENS"
    assert _media_rows(owner_session, tutor.lens.owner_id) == 0
    assert tasks(owner_session) == []
    assert store.presigned == []


def test_approval_waiting_on_a_deletion_refuses(
    restricted_engine: Engine,
    owner_engine: Engine,
    owner_session: Session,
    admin: PlatformAdminLens,
) -> None:
    """The approval waits on the owner lock the deletion holds, then refuses.

    Nothing is copied to ``public/``, and the deletion's queued prefixes cover
    the photo.

    :param restricted_engine: The application role's engine
    :param owner_engine: The table owner's engine
    :param owner_session: An arranging session
    :param admin: The administrator
    :return: None
    """
    tutor = arrange(owner_session)
    store = FakeMediaStore()
    media_id = _pending(owner_session, store, tutor.lens.owner_id)
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    deleting, deleted, ready = _held_deletion(
        factory, owner_engine, _phone(owner_session, tutor.lens.account_id)
    )
    assert ready.wait(PATIENCE)

    def approve() -> object:
        session = factory()
        try:
            return media.decide(
                session, store, admin, media_id, approve=True, code=None, now=NOW
            )
        finally:
            session.close()

    approving, approved = _in_thread(approve)
    deleting.join(PATIENCE * 2)
    approving.join(PATIENCE * 2)

    assert not isinstance(deleted[0], BaseException), deleted
    assert isinstance(approved[0], AuthorizationError), approved
    assert approved[0].code == "HUB_ADMIN_TARGET_NOT_FOUND"
    assert not any(key.startswith("public/") for key in store.objects)
    assert _media_rows(owner_session, tutor.lens.owner_id) == 0
    assert {
        f"quarantine/{media_id}",
        f"staged/{media_id}/",
        f"archive/{media_id}/",
    } <= set(tasks(owner_session))


def test_deletion_waiting_on_an_approval_queues_its_public_copy(
    restricted_engine: Engine,
    owner_engine: Engine,
    owner_session: Session,
    admin: PlatformAdminLens,
) -> None:
    """The other order: the approval holds the lock and commits first.

    The deletion then reads the approved photo, so ``public/{key}/`` and
    its ``/m/{key}/{w}.webp`` paths are queued with everything else.

    :param restricted_engine: The application role's engine
    :param owner_engine: The table owner's engine
    :param owner_session: An arranging session
    :param admin: The administrator
    :return: None
    """
    tutor = arrange(owner_session)
    store = FakeMediaStore()
    media_id = _pending(owner_session, store, tutor.lens.owner_id)
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    copying = threading.Event()
    copy = store.copy_variants

    def held_copy(source: str, target: str, widths: object, **pin: object) -> None:
        copying.set()
        _wait_for_a_waiter(owner_engine)
        copy(source, target, widths, **pin)  # type: ignore[arg-type]

    store.copy_variants = held_copy  # type: ignore[method-assign]

    def approve() -> object:
        session = factory()
        try:
            return media.decide(
                session, store, admin, media_id, approve=True, code=None, now=NOW
            ).public_key
        finally:
            session.close()

    approving, approved = _in_thread(approve)
    assert copying.wait(PATIENCE)
    phone = _phone(owner_session, tutor.lens.account_id)

    def delete() -> object:
        session = factory()
        try:
            return delete_account(session, phone)
        finally:
            session.close()

    deleting, deleted = _in_thread(delete)
    approving.join(PATIENCE * 2)
    deleting.join(PATIENCE * 2)

    assert not isinstance(deleted[0], BaseException), deleted
    key = approved[0]
    assert isinstance(key, str), approved
    assert _media_rows(owner_session, tutor.lens.owner_id) == 0
    assert {
        f"public/{key}/",
        f"quarantine/{media_id}",
        f"staged/{media_id}/",
        f"archive/{media_id}/",
    } <= set(tasks(owner_session))
    owner_session.rollback()
    paths = set(
        owner_session.execute(sa.text("SELECT path FROM cdn_invalidation")).scalars()
    )
    assert set(invalidation.media_paths(key)) <= paths


def test_writes_for_a_departed_solo_owner_refuse(
    owner_session: Session, restricted_session: Session, admin: PlatformAdminLens
) -> None:
    """Under the lock, a solo owner with no account gets nothing written.

    A stale lens's init and completion, an administrator's approval and a
    report's dismiss-restore each find the owner departed and leave the photo
    and both outboxes exactly as they were. A rejection, which only deletes,
    still goes ahead.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :param admin: The administrator
    :return: None
    """
    tutor = arrange(owner_session)
    owner_listing(owner_session, tutor.lens.owner_id, "rahim-sir")
    store = FakeMediaStore()
    uploading = media_row(
        owner_session, tutor.lens.owner_id, status="awaiting_upload", position=1
    )
    store.put_result(uploading, OK)
    waiting = _pending(owner_session, store, tutor.lens.owner_id, position=2)
    held = _pending(owner_session, store, tutor.lens.owner_id, position=3)
    key = media.decide(
        restricted_session, store, admin, held, approve=True, code=None, now=NOW
    ).public_key
    reports.file(
        restricted_session,
        make_teacher(owner_session).account_id,
        "media",
        held,
        "personal_info",
        None,
        NOW,
    )
    owner_session.rollback()
    report_id = owner_session.execute(
        sa.text("SELECT id FROM hub_report WHERE target_id = :m"), {"m": held}
    ).scalar_one()
    before_tasks = tasks(owner_session)
    _depart(owner_session, tutor.lens.owner_id)
    objects_before = dict(store.objects)

    with pytest.raises(AuthorizationError) as refused:
        uploads.init_upload(
            restricted_session,
            store,
            tutor.lens,
            batch_id=None,
            content_type="image/jpeg",
            byte_size=2048,
            now=NOW,
        )
    assert refused.value.code == "NO_TEACHER_LENS"

    with pytest.raises(AuthorizationError) as refused:
        uploads.complete(
            restricted_session,
            store,
            tutor.lens,
            uploading,
            alt_en="A classroom",
            alt_bn="একটি শ্রেণিকক্ষ",
            now=NOW,
        )
    assert refused.value.code == "MEDIA_NOT_FOUND"

    with pytest.raises(AuthorizationError) as refused:
        media.decide(
            restricted_session, store, admin, waiting, approve=True, code=None, now=NOW
        )
    assert refused.value.code == "HUB_ADMIN_TARGET_NOT_FOUND"

    reports.decide(
        restricted_session,
        admin,
        report_id,
        "dismissed",
        NOW + dt.timedelta(hours=1),
        store=store,
    )

    owner_session.rollback()
    statuses = dict(
        owner_session.execute(
            sa.text("SELECT id, status::text FROM listing_media WHERE owner_id = :o"),
            {"o": tutor.lens.owner_id},
        ).all()
    )
    assert statuses == {
        uploading: "awaiting_upload",
        waiting: "pending_review",
        held: "held",
    }
    report_status = owner_session.execute(
        sa.text("SELECT status::text FROM hub_report WHERE id = :r"), {"r": report_id}
    ).scalar_one()
    assert report_status == "dismissed"
    assert tasks(owner_session) == before_tasks
    assert store.objects == objects_before
    assert store.presigned == []
    assert key is not None

    # A rejection only deletes, so it still goes ahead for a departed owner.
    rejected = media.decide(
        restricted_session,
        store,
        admin,
        waiting,
        approve=False,
        code="other",
        now=NOW,
    )
    assert rejected.status == "rejected"
    assert {
        f"quarantine/{waiting}",
        f"staged/{waiting}/",
        f"archive/{waiting}/",
    } <= set(tasks(owner_session))


def test_a_centre_upload_still_works(
    owner_session: Session, restricted_session: Session
) -> None:
    """A centre's owner row has no account by design, and uploads still work.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    centre = centre_with_manager(owner_session)
    lens = TeacherLens(account_id=centre.manager_account_id, owner_id=centre.owner_id)
    store = FakeMediaStore()

    ticket = uploads.init_upload(
        restricted_session,
        store,
        lens,
        batch_id=centre.batch_id,
        content_type="image/png",
        byte_size=2048,
        now=NOW,
    )

    assert store.presigned == [(ticket.media_id, "image/png")]
    assert _media_rows(owner_session, centre.owner_id) == 1
