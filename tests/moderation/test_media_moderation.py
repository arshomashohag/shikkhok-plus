"""Photo moderation: an administrator's decision, and the report-driven hold.

**Approval publishes and archives.** The variants are copied to
``public/{key}/`` under a fresh 128-bit key and to ``archive/{id}/``, the
copy that outlives ``staged/``'s thirty days; any later approval -- after an
alt-text edit or a hold -- copies from the archive, never from ``staged/``.

**A child-safety or personal-information report hides the photo at once**,
in the report's own transaction [Review Focus 3]: rolling the report back
leaves the photo approved; committing it leaves the photo ``held``, its
public objects enqueued for deletion and its paths for invalidation.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from typing import Final

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.hub_media import media_store
from app.authz.admin import PLATFORM_ADMIN_PHONES_ENV
from app.authz.lenses import PlatformAdminLens
from app.errors import (
    AuthorizationError,
    ConflictError,
    TransientError,
    ValidationError,
)
from app.hub.media import library
from app.hub.media.objects import UPLOAD_WINDOW
from app.hub.public import invalidation
from app.hub.public.db import as_hub_reader
from app.moderation import media, reports
from tests.batches.conftest import make_teacher
from tests.help.conftest import People, phone_of
from tests.hub.media.fakes import FakeMediaStore
from tests.hub.media.support import (
    NOW,
    Owner,
    arrange,
    invalidations,
    media_row,
    tasks,
)
from tests.moderation.conftest import admin_headers
from tests.moderation.support import publish_batch, publish_owner

#: Every variant width the sanitiser writes.
WIDTHS: Final[list[int]] = [320, 960, 1600]

#: What the sanitiser wrote for a readable upload.
OK: Final[dict[str, object]] = {
    "ok": True,
    "width": 1600,
    "height": 1200,
    "widths": WIDTHS,
}

LATER: Final[dt.datetime] = NOW + dt.timedelta(hours=2)

#: When an arranged upload was signed: its upload window long closed by NOW.
SIGNED: Final[dt.datetime] = NOW - dt.timedelta(hours=1)


@pytest.fixture
def tutor(owner_session: Session) -> Owner:
    return arrange(owner_session)


@pytest.fixture
def admin(owner_session: Session) -> PlatformAdminLens:
    return PlatformAdminLens(account_id=make_teacher(owner_session).account_id)


@pytest.fixture
def store() -> FakeMediaStore:
    return FakeMediaStore()


def _pending(
    session: Session,
    store: FakeMediaStore,
    owner_id: uuid.UUID,
    *,
    batch_id: uuid.UUID | None = None,
    created_at: dt.datetime = SIGNED,
) -> uuid.UUID:
    """Arrange a photo the sanitiser read, waiting for review.

    :param session: The arranging session
    :param store: The fake bucket, given its staged variants
    :param owner_id: The owner
    :param batch_id: The batch, or None for the owner's gallery
    :param created_at: When its upload was signed; by default an hour
        before NOW, so its upload window has closed
    :return: The media id
    """
    media_id = media_row(session, owner_id, batch_id=batch_id, created_at=created_at)
    session.execute(
        sa.text(
            "UPDATE listing_media SET width = 1600, height = 1200, widths = :ws "
            "WHERE id = :m"
        ),
        {"ws": WIDTHS, "m": media_id},
    )
    session.commit()
    store.put_result(media_id, OK)
    return media_id


def _row(session: Session, media_id: uuid.UUID) -> sa.Row[tuple[object, ...]]:
    session.rollback()
    return session.execute(
        sa.text(
            "SELECT status::text AS status, public_key, archived_at, decided_at, "
            "position, rejection_code FROM listing_media WHERE id = :m"
        ),
        {"m": media_id},
    ).one()


def _events(session: Session) -> list[tuple[str, str, str | None, uuid.UUID | None]]:
    session.rollback()
    return [
        (r.event, r.target_kind, r.decision_code, r.actor_admin_account_id)
        for r in session.execute(
            sa.text(
                "SELECT event::text AS event, target_kind::text AS target_kind, "
                "decision_code, actor_admin_account_id FROM hub_moderation_event "
                "ORDER BY at, event"
            )
        )
    ]


def _approve(
    session: Session,
    store: FakeMediaStore,
    admin: PlatformAdminLens,
    media_id: uuid.UUID,
    now: dt.datetime = NOW,
) -> str:
    """Approve a photo and return its public key.

    :param session: The application role's session
    :param store: The fake bucket
    :param admin: The administrator
    :param media_id: The photo
    :param now: The moment of approval
    :return: The key
    """
    decided = media.decide(
        session, store, admin, media_id, approve=True, code=None, now=now
    )
    assert decided.public_key is not None
    return decided.public_key


def _drop_staged(store: FakeMediaStore, media_id: uuid.UUID) -> None:
    """Expire ``staged/{id}/`` as the bucket's 30-day lifecycle would.

    :param store: The fake bucket
    :param media_id: The photo
    :return: None
    """
    for key in [k for k in store.objects if k.startswith(f"staged/{media_id}/")]:
        del store.objects[key]


def test_approve_copies_to_public_and_archive_and_sets_key(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
) -> None:
    """Both copies, a 32-hex key, the next free slot and the event."""
    taken = media_row(owner_session, tutor.lens.owner_id, status="approved")
    media_id = _pending(owner_session, store, tutor.lens.owner_id)

    key = _approve(restricted_session, store, admin, media_id)

    row = _row(owner_session, media_id)
    assert row.status == "approved"
    assert row.public_key == key
    assert len(key) == 32
    assert int(key, 16) >= 0
    assert row.archived_at == NOW
    assert row.decided_at == NOW
    # Slot 0 holds an approved photo already; the newcomer takes slot 1.
    assert _row(owner_session, taken).position == 0
    assert row.position == 1
    for width in WIDTHS:
        public = store.objects[f"public/{key}/{width}.webp"]
        archived = store.objects[f"archive/{media_id}/{width}.webp"]
        assert public.content_type == archived.content_type == "image/webp"
    assert _events(owner_session) == [
        ("media_approved", "media", None, admin.account_id)
    ]


def test_approval_keeps_a_free_position(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
) -> None:
    """A slot the owner chose and no approved photo holds is kept."""
    media_row(owner_session, tutor.lens.owner_id, status="approved", position=0)
    media_id = _pending(owner_session, store, tutor.lens.owner_id)
    owner_session.execute(
        sa.text("UPDATE listing_media SET position = 4 WHERE id = :m"),
        {"m": media_id},
    )
    owner_session.commit()

    _approve(restricted_session, store, admin, media_id)

    assert _row(owner_session, media_id).position == 4


def test_reapproval_after_alt_edit_copies_from_archive(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
) -> None:
    """``staged/`` has expired; the archive copy is what gets published."""
    media_id = _pending(owner_session, store, tutor.lens.owner_id)
    first = _approve(restricted_session, store, admin, media_id)
    library.update_alt(
        restricted_session,
        tutor.lens,
        media_id,
        alt_en="A bright classroom",
        alt_bn=None,
        now=NOW,
    )
    assert _row(owner_session, media_id).status == "pending_review"
    _drop_staged(store, media_id)

    second = _approve(restricted_session, store, admin, media_id, LATER)

    row = _row(owner_session, media_id)
    assert (row.status, row.public_key) == ("approved", second)
    assert second != first
    # The archive is written once, at the first approval.
    assert row.archived_at == NOW
    assert all(f"public/{second}/{w}.webp" in store.objects for w in WIDTHS)


def test_first_approval_without_staged_variants_changes_nothing(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
) -> None:
    """A copy that fails leaves the photo waiting and its key unrecorded."""
    media_id = _pending(owner_session, store, tutor.lens.owner_id)
    _drop_staged(store, media_id)

    with pytest.raises(TransientError):
        media.decide(
            restricted_session, store, admin, media_id, approve=True, code=None, now=NOW
        )

    row = _row(owner_session, media_id)
    assert (row.status, row.public_key, row.archived_at) == (
        "pending_review",
        None,
        None,
    )
    assert _events(owner_session) == []
    # The key that never reached the row is enqueued for deletion, so a
    # partial copy under it cannot stay in the bucket.
    left = tasks(owner_session)
    assert len(left) == 1
    assert left[0].startswith("public/")


def test_reject_enqueues_all_deletes(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
) -> None:
    """Every prefix the photo could hold goes, with the closed code."""
    media_id = _pending(owner_session, store, tutor.lens.owner_id)

    decided = media.decide(
        restricted_session,
        store,
        admin,
        media_id,
        approve=False,
        code="identifiable_child",
        now=NOW,
    )

    assert decided.status == "rejected"
    row = _row(owner_session, media_id)
    assert (row.status, row.rejection_code, row.public_key, row.decided_at) == (
        "rejected",
        "identifiable_child",
        None,
        NOW,
    )
    assert set(tasks(owner_session)) == {
        f"quarantine/{media_id}",
        f"staged/{media_id}/",
        f"archive/{media_id}/",
    }
    assert _events(owner_session) == [
        ("media_rejected", "media", "identifiable_child", admin.account_id)
    ]


def test_rejecting_a_held_photo_leaves_nothing_public(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
) -> None:
    """The hold took the public copy down; the rejection takes the rest."""
    publish_owner(owner_session, tutor.lens.owner_id)
    media_id = _pending(owner_session, store, tutor.lens.owner_id)
    key = _approve(restricted_session, store, admin, media_id)
    reports.file(
        restricted_session,
        make_teacher(owner_session).account_id,
        "media",
        media_id,
        "child_safety",
        None,
        NOW,
    )

    media.decide(
        restricted_session,
        store,
        admin,
        media_id,
        approve=False,
        code="personal_info",
        now=LATER,
    )

    assert set(tasks(owner_session)) == {
        f"public/{key}/",
        f"quarantine/{media_id}",
        f"staged/{media_id}/",
        f"archive/{media_id}/",
    }
    assert set(invalidation.media_paths(key)) <= invalidations(owner_session)
    assert _row(owner_session, media_id).status == "rejected"


@pytest.mark.parametrize("reason", ["child_safety", "personal_info"])
@pytest.mark.parametrize("batch", [False, True])
def test_child_safety_report_holds_photo_in_same_transaction(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
    batch: bool,
) -> None:
    """Rolled back: still approved, nothing enqueued. Committed: held."""
    publish_owner(owner_session, tutor.lens.owner_id)
    publish_batch(owner_session, tutor.lens.owner_id, tutor.batch_id)
    media_id = _pending(
        owner_session,
        store,
        tutor.lens.owner_id,
        batch_id=tutor.batch_id if batch else None,
    )
    key = _approve(restricted_session, store, admin, media_id)
    reporter = make_teacher(owner_session).account_id
    owner_slug, batch_slug = owner_session.execute(
        sa.text(
            "SELECT o.slug, b.slug FROM owner_listing o JOIN batch_listing b "
            "ON b.owner_id = o.owner_id WHERE o.owner_id = :o"
        ),
        {"o": tutor.lens.owner_id},
    ).one()

    # ``reports.file`` commits once before the hold -- the daily ceiling's
    # counter -- so only the commit AFTER the hold is made to fail: the
    # wrapper runs the real hold, then arms the failure.
    real_hold = media.hold
    held_in_rolled_back_leg: list[uuid.UUID] = []

    def failing_commit() -> None:
        raise RuntimeError("the report's commit failed")

    with monkeypatch.context() as patch:

        def hold_then_fail_commit(
            session: Session, target: uuid.UUID, **kwargs: object
        ) -> None:
            real_hold(session, target, **kwargs)  # type: ignore[arg-type]
            held_in_rolled_back_leg.append(target)
            patch.setattr(session, "commit", failing_commit)

        patch.setattr(media, "hold", hold_then_fail_commit)
        with pytest.raises(RuntimeError, match="the report's commit failed"):
            reports.file(
                restricted_session, reporter, "media", media_id, reason, None, NOW
            )
    restricted_session.rollback()
    assert held_in_rolled_back_leg == [media_id]

    row = _row(owner_session, media_id)
    assert (row.status, row.public_key) == ("approved", key)
    assert tasks(owner_session) == []
    assert invalidations(owner_session) == set()
    assert (
        owner_session.execute(sa.text("SELECT count(*) FROM hub_report")).scalar_one()
        == 0
    )

    reports.file(restricted_session, reporter, "media", media_id, reason, None, NOW)

    row = _row(owner_session, media_id)
    assert (row.status, row.public_key) == ("held", None)
    assert tasks(owner_session) == [f"public/{key}/"]
    page = (
        {f"/hub/{lc}/t/{owner_slug}/{batch_slug}" for lc in ("en", "bn")}
        if batch
        else {f"/hub/{lc}/t/{owner_slug}*" for lc in ("en", "bn")}
    )
    assert invalidations(owner_session) == {
        *invalidation.media_paths(key),
        "/hub/sitemap.xml",
        *page,
    }
    assert _events(owner_session)[-2:] == [
        ("media_held", "media", reason, None),
        ("report_filed", "media", reason, None),
    ]


@pytest.mark.parametrize("reason", ["abusive", "fake", "misleading", "other"])
def test_other_report_reasons_do_not_hold(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
    reason: str,
) -> None:
    """The report is filed; the photo stays public until an admin acts."""
    publish_owner(owner_session, tutor.lens.owner_id)
    media_id = _pending(owner_session, store, tutor.lens.owner_id)
    key = _approve(restricted_session, store, admin, media_id)

    reports.file(
        restricted_session,
        make_teacher(owner_session).account_id,
        "media",
        media_id,
        reason,
        None,
        NOW,
    )

    row = _row(owner_session, media_id)
    assert (row.status, row.public_key) == ("approved", key)
    assert tasks(owner_session) == []
    assert (
        owner_session.execute(sa.text("SELECT count(*) FROM hub_report")).scalar_one()
        == 1
    )


def test_restore_from_hold_uses_fresh_key(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
) -> None:
    """Cleared after a hold: a new key, copied from the archive."""
    publish_owner(owner_session, tutor.lens.owner_id)
    media_id = _pending(owner_session, store, tutor.lens.owner_id)
    old = _approve(restricted_session, store, admin, media_id)
    reports.file(
        restricted_session,
        make_teacher(owner_session).account_id,
        "media",
        media_id,
        "personal_info",
        None,
        NOW,
    )
    _drop_staged(store, media_id)
    # The drain deletes the old public copy, as it would in production.
    for key in [k for k in store.objects if k.startswith(f"public/{old}/")]:
        del store.objects[key]
    # A direct approval of a held photo needs no open holding report: here
    # the reporter deleted their account, and the report went with it.
    owner_session.execute(
        sa.text("DELETE FROM hub_report WHERE target_id = :m"), {"m": media_id}
    )
    owner_session.commit()

    new = _approve(restricted_session, store, admin, media_id, LATER)

    assert new != old
    row = _row(owner_session, media_id)
    assert (row.status, row.public_key) == ("approved", new)
    assert all(f"public/{new}/{w}.webp" in store.objects for w in WIDTHS)
    assert not any(k.startswith(f"public/{old}/") for k in store.objects)
    assert _events(owner_session)[-1] == (
        "media_restored",
        "media",
        None,
        admin.account_id,
    )


@pytest.mark.parametrize(
    ("status", "decisions"),
    [
        ("approved", ((True, None),)),
        ("rejected", ((True, None), (False, "other"))),
    ],
)
def test_decision_on_approved_or_rejected_is_conflict(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
    status: str,
    decisions: tuple[tuple[bool, str | None], ...],
) -> None:
    """Deciding twice is a conflict that changes nothing.

    Rejecting an approved photo is not deciding twice: it is a takedown
    [I2], tested below.
    """
    media_id = media_row(owner_session, tutor.lens.owner_id, status=status)
    before = _row(owner_session, media_id)

    for approve, code in decisions:
        with pytest.raises(ConflictError) as caught:
            media.decide(
                restricted_session,
                store,
                admin,
                media_id,
                approve=approve,
                code=code,
                now=NOW,
            )
        assert caught.value.code == "MEDIA_ALREADY_DECIDED"
        assert caught.value.message_key == "hub.media.already_decided"

    assert _row(owner_session, media_id) == before
    assert tasks(owner_session) == []
    assert _events(owner_session) == []


@pytest.mark.parametrize("status", ["awaiting_upload", "processing", "withdrawn"])
def test_decision_on_nothing_to_review_is_admin_not_found(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
    status: str,
) -> None:
    """An upload in flight, a withdrawn photo and a missing id read alike."""
    media_id = media_row(owner_session, tutor.lens.owner_id, status=status)
    for target in (media_id, uuid.uuid4()):
        with pytest.raises(AuthorizationError) as caught:
            media.decide(
                restricted_session,
                store,
                admin,
                target,
                approve=True,
                code=None,
                now=NOW,
            )
        assert caught.value.code == "HUB_ADMIN_TARGET_NOT_FOUND"


@pytest.mark.parametrize(
    ("approve", "code"),
    [(True, "other"), (False, None), (False, "blurry"), (False, "child_safety")],
)
def test_a_code_goes_with_a_rejection_only(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
    approve: bool,
    code: str | None,
) -> None:
    """Approve carries no code; reject carries one of the five."""
    media_id = _pending(owner_session, store, tutor.lens.owner_id)
    with pytest.raises(ValidationError) as caught:
        media.decide(
            restricted_session,
            store,
            admin,
            media_id,
            approve=approve,
            code=code,
            now=NOW,
        )
    assert caught.value.code == "MEDIA_REJECTION_CODE_INVALID"
    assert _row(owner_session, media_id).status == "pending_review"


def _in_public_view(session: Session, media_id: uuid.UUID) -> bool:
    """Ask the public view, as the hub reader, whether a photo is shown.

    :param session: The application role's session
    :param media_id: The photo
    :return: Whether ``hub_public_media`` has it
    """
    session.rollback()
    as_hub_reader(session)
    found = session.execute(
        sa.text("SELECT count(*) FROM hub_public_media WHERE media_id = :m"),
        {"m": media_id},
    ).scalar_one()
    session.rollback()
    return bool(found)


@pytest.mark.parametrize(
    ("owner_status", "batch_status", "batch_active", "on_batch", "status", "shown"),
    [
        ("published", None, True, False, "approved", True),
        ("hidden", None, True, False, "approved", False),
        ("suspended", None, True, False, "approved", False),
        ("published", "published", True, True, "approved", True),
        ("published", "hidden", True, True, "approved", False),
        ("published", "published", False, True, "approved", False),
        ("hidden", "published", True, True, "approved", False),
        ("published", None, True, False, "pending_review", False),
        ("published", None, True, False, "held", False),
        ("published", None, True, False, "rejected", False),
    ],
)
def test_a_photo_is_reportable_exactly_where_the_public_view_shows_it(
    owner_session: Session,
    restricted_session: Session,
    tutor: Owner,
    owner_status: str,
    batch_status: str | None,
    batch_active: bool,
    on_batch: bool,
    status: str,
    shown: bool,
) -> None:
    """``_reportable`` and ``hub_public_media`` agree on every state."""
    publish_owner(owner_session, tutor.lens.owner_id, status=owner_status)
    if batch_status is not None:
        publish_batch(
            owner_session, tutor.lens.owner_id, tutor.batch_id, status=batch_status
        )
    if not batch_active:
        owner_session.execute(
            sa.text("UPDATE batch SET active = false WHERE id = :b"),
            {"b": tutor.batch_id},
        )
        owner_session.commit()
    media_id = media_row(
        owner_session,
        tutor.lens.owner_id,
        status=status,
        batch_id=tutor.batch_id if on_batch else None,
    )

    assert _in_public_view(restricted_session, media_id) is shown
    assert reports._reportable(restricted_session, "media", media_id) is shown


def test_report_on_a_photo_not_shown_answers_the_shared_refusal(
    owner_session: Session,
    restricted_session: Session,
    tutor: Owner,
) -> None:
    """A held or pending photo reads exactly like a missing one."""
    publish_owner(owner_session, tutor.lens.owner_id)
    reporter = make_teacher(owner_session).account_id
    refusals = set()
    for target in (
        media_row(owner_session, tutor.lens.owner_id, status="held"),
        media_row(owner_session, tutor.lens.owner_id, status="pending_review"),
        uuid.uuid4(),
    ):
        with pytest.raises(AuthorizationError) as caught:
            reports.file(
                restricted_session, reporter, "media", target, "child_safety", None, NOW
            )
        restricted_session.rollback()
        refusals.add((caught.value.code, caught.value.status))
    assert refusals == {("REPORT_TARGET_NOT_FOUND", 404)}


def test_media_queue_lists_waiting_and_held_photos(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
) -> None:
    """Pending and held photos, titled by the page they are for."""
    publish_owner(owner_session, tutor.lens.owner_id, name="Rahim Sir")
    publish_batch(owner_session, tutor.lens.owner_id, tutor.batch_id)
    waiting = _pending(
        owner_session, store, tutor.lens.owner_id, batch_id=tutor.batch_id
    )
    held = _pending(owner_session, store, tutor.lens.owner_id)
    _approve(restricted_session, store, admin, held)
    reports.file(
        restricted_session,
        make_teacher(owner_session).account_id,
        "media",
        held,
        "child_safety",
        None,
        NOW,
    )
    media_row(owner_session, tutor.lens.owner_id, status="approved", position=3)
    media_row(owner_session, tutor.lens.owner_id, status="rejected")

    items = reports.queue(restricted_session, "media", NOW + dt.timedelta(hours=5))

    by_id = {i.target_id: i for i in items}
    assert set(by_id) == {waiting, held}
    assert all(i.kind == "media" and i.target_kind == "media" for i in items)
    assert by_id[waiting].title == "HSC Physics"
    assert by_id[waiting].reason is None
    assert dict(by_id[waiting].fields) == {
        "alt_en": "A classroom",
        "alt_bn": "একটি শ্রেণিকক্ষ",
    }
    assert by_id[held].title == "Rahim Sir"
    assert by_id[held].reason == "child_safety"
    assert by_id[held].waited_hours == 5
    assert by_id[held].owner_id == tutor.lens.owner_id


def test_a_photo_report_row_names_the_page(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
) -> None:
    """A report on a photo shows its page's public name and its alt text."""
    publish_owner(owner_session, tutor.lens.owner_id, name="Rahim Sir")
    media_id = _pending(owner_session, store, tutor.lens.owner_id)
    _approve(restricted_session, store, admin, media_id)
    reports.file(
        restricted_session,
        make_teacher(owner_session).account_id,
        "media",
        media_id,
        "misleading",
        None,
        NOW,
    )

    (item,) = reports.queue(restricted_session, "report", NOW)

    assert (item.target_kind, item.target_id) == ("media", media_id)
    assert (item.owner_id, item.title) == (tutor.lens.owner_id, "Rahim Sir")
    assert dict(item.fields)["alt_en"] == "A classroom"


# ---------------------------------------------------------------------------
# The two admin routes, through the real app and the restricted role.
# ---------------------------------------------------------------------------


@pytest.fixture
def served(api_client: TestClient, store: FakeMediaStore) -> Iterator[FakeMediaStore]:
    api_client.app.dependency_overrides[media_store] = lambda: store  # type: ignore[attr-defined]
    yield store
    api_client.app.dependency_overrides.pop(media_store, None)  # type: ignore[attr-defined]


def _admin(
    session: Session, people: People, monkeypatch: pytest.MonkeyPatch
) -> dict[str, str]:
    monkeypatch.setenv(PLATFORM_ADMIN_PHONES_ENV, phone_of(session, people.stranger))
    return admin_headers(session, people.stranger)


def test_admin_preview_carries_no_account_fields(
    api_client: TestClient,
    owner_session: Session,
    served: FakeMediaStore,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Five-minute previews of each variant, public names, and no account."""
    teacher = people.teacher
    publish_owner(owner_session, teacher.owner_id, name="Rahim Sir")
    publish_batch(owner_session, teacher.owner_id, teacher.batch_id)
    media_id = _pending(
        owner_session, served, teacher.owner_id, batch_id=teacher.batch_id
    )
    owner_session.execute(
        sa.text("UPDATE listing_media SET widths = :ws WHERE id = :m"),
        {"ws": [320, 960], "m": media_id},
    )
    # The teacher's private label, which nothing administrative may read.
    owner_session.execute(
        sa.text("UPDATE batch SET name = 'Karim family home batch' WHERE id = :b"),
        {"b": teacher.batch_id},
    )
    owner_session.commit()
    headers = _admin(owner_session, people, monkeypatch)

    response = api_client.get(f"/v1/admin/hub/media/{media_id}", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["media_id"] == str(media_id)
    assert body["status"] == "pending_review"
    assert [p["width"] for p in body["previews"]] == [320, 960]
    for preview in body["previews"]:
        assert preview["url"].endswith(
            f"staged/{media_id}/{preview['width']}.webp?X-Amz-Expires=300"
        )
    assert (body["alt_en"], body["alt_bn"]) == ("A classroom", "একটি শ্রেণিকক্ষ")
    assert (body["public_name"], body["public_title"]) == ("Rahim Sir", "HSC Physics")
    assert body["report_count"] == 0
    batch_name = owner_session.execute(
        sa.text("SELECT name FROM batch WHERE id = :b"), {"b": teacher.batch_id}
    ).scalar_one()
    raw = response.text
    assert batch_name not in raw
    assert phone_of(owner_session, teacher.account_id) not in raw
    assert str(teacher.account_id) not in raw
    assert str(teacher.owner_id) not in raw
    assert set(body) == {
        "media_id",
        "status",
        "width",
        "height",
        "previews",
        "alt_en",
        "alt_bn",
        "public_name",
        "public_title",
        "report_count",
    }


def test_admin_preview_of_a_held_photo_reads_the_archive(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    served: FakeMediaStore,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Once archived, previews come from ``archive/``; reports are counted."""
    teacher = people.teacher
    publish_owner(owner_session, teacher.owner_id)
    media_id = _pending(owner_session, served, teacher.owner_id)
    admin = PlatformAdminLens(account_id=make_teacher(owner_session).account_id)
    _approve(restricted_session, served, admin, media_id)
    reports.file(
        restricted_session,
        make_teacher(owner_session).account_id,
        "media",
        media_id,
        "child_safety",
        None,
        NOW,
    )
    headers = _admin(owner_session, people, monkeypatch)

    body = api_client.get(f"/v1/admin/hub/media/{media_id}", headers=headers).json()

    assert body["status"] == "held"
    assert body["report_count"] == 1
    assert body["public_title"] is None
    assert all(f"archive/{media_id}/" in p["url"] for p in body["previews"])


def test_admin_decision_route_approves_and_refuses_bad_codes(
    api_client: TestClient,
    owner_session: Session,
    served: FakeMediaStore,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approve answers the new status; a reject needs one of the codes."""
    first = _pending(owner_session, served, people.teacher.owner_id)
    second = _pending(owner_session, served, people.teacher.owner_id)
    headers = _admin(owner_session, people, monkeypatch)

    approved = api_client.post(
        f"/v1/admin/hub/media/{first}/decision",
        json={"decision": "approve"},
        headers=headers,
    )
    bad = api_client.post(
        f"/v1/admin/hub/media/{second}/decision",
        json={"decision": "reject", "code": "child_safety"},
        headers=headers,
    )
    missing = api_client.post(
        f"/v1/admin/hub/media/{second}/decision",
        json={"decision": "reject"},
        headers=headers,
    )
    rejected = api_client.post(
        f"/v1/admin/hub/media/{second}/decision",
        json={"decision": "reject", "code": "low_quality"},
        headers=headers,
    )
    again = api_client.post(
        f"/v1/admin/hub/media/{second}/decision",
        json={"decision": "approve"},
        headers=headers,
    )
    queue = api_client.get("/v1/admin/hub/queue?kind=media", headers=headers)

    assert approved.status_code == 200, approved.text
    assert approved.json() == {"media_id": str(first), "status": "approved"}
    assert bad.status_code in (400, 422)
    assert missing.status_code in (400, 422)
    assert rejected.json() == {"media_id": str(second), "status": "rejected"}
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "MEDIA_ALREADY_DECIDED"
    assert queue.status_code == 200, queue.text
    assert queue.json() == {"kind": "media", "items": []}


def test_admin_media_routes_refuse_a_non_admin(
    api_client: TestClient,
    owner_session: Session,
    served: FakeMediaStore,
    people: People,
) -> None:
    """An ordinary account's token reaches neither route."""
    from tests.conftest import bearer

    media_id = _pending(owner_session, served, people.teacher.owner_id)
    headers = bearer(owner_session, people.teacher.account_id)

    read = api_client.get(f"/v1/admin/hub/media/{media_id}", headers=headers)
    write = api_client.post(
        f"/v1/admin/hub/media/{media_id}/decision",
        json={"decision": "approve"},
        headers=headers,
    )

    assert read.status_code in (401, 403, 404)
    assert write.status_code in (401, 403, 404)
    assert _row(owner_session, media_id).status == "pending_review"


def test_rejection_codes_are_one_vocabulary() -> None:
    """The service's tuple and the wire's ``Literal`` are the same five codes."""
    from typing import get_args

    from app.moderation.vocab import MEDIA_REJECTION_CODES, MediaRejectionCode

    assert get_args(MediaRejectionCode) == MEDIA_REJECTION_CODES
    assert MEDIA_REJECTION_CODES == (
        "identifiable_child",
        "personal_info",
        "not_relevant",
        "low_quality",
        "other",
    )


# ---------------------------------------------------------------------------
# R11: an administrator's decision on a photo report carries to the photo.
# ---------------------------------------------------------------------------


def _report_on(
    owner_session: Session,
    restricted_session: Session,
    media_id: uuid.UUID,
    reason: str,
) -> uuid.UUID:
    """File a report on a photo and return the report's id.

    :param owner_session: The arranging session
    :param restricted_session: The application role's session
    :param media_id: The photo
    :param reason: The report reason
    :return: The report id
    """
    reports.file(
        restricted_session,
        make_teacher(owner_session).account_id,
        "media",
        media_id,
        reason,
        None,
        NOW,
    )
    owner_session.rollback()
    return owner_session.execute(
        sa.text(
            "SELECT id FROM hub_report WHERE target_id = :m AND reason = "
            "CAST(:r AS hub_report_reason)"
        ),
        {"m": media_id, "r": reason},
    ).scalar_one()


def _published(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
) -> tuple[uuid.UUID, str]:
    publish_owner(owner_session, tutor.lens.owner_id)
    media_id = _pending(owner_session, store, tutor.lens.owner_id)
    return media_id, _approve(restricted_session, store, admin, media_id)


@pytest.mark.parametrize(
    ("reason", "code"), [("abusive", "other"), ("misleading", "other")]
)
def test_upholding_a_report_on_an_approved_photo_removes_it(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
    reason: str,
    code: str,
) -> None:
    """Rejected with the mapped code; every prefix and path enqueued."""
    media_id, key = _published(owner_session, restricted_session, store, tutor, admin)
    report_id = _report_on(owner_session, restricted_session, media_id, reason)

    reports.decide(restricted_session, admin, report_id, "upheld", LATER, store=store)

    row = _row(owner_session, media_id)
    assert (row.status, row.public_key, row.rejection_code, row.decided_at) == (
        "rejected",
        None,
        code,
        LATER,
    )
    assert set(tasks(owner_session)) == {
        f"public/{key}/",
        f"quarantine/{media_id}",
        f"staged/{media_id}/",
        f"archive/{media_id}/",
    }
    assert set(invalidation.media_paths(key)) <= invalidations(owner_session)
    assert ("media_rejected", "media", code, admin.account_id) in _events(owner_session)


@pytest.mark.parametrize(
    ("reason", "code"),
    [("child_safety", "identifiable_child"), ("personal_info", "personal_info")],
)
def test_upholding_a_report_on_a_held_photo_removes_it(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
    reason: str,
    code: str,
) -> None:
    """The hold took the public copy down; upholding deletes the rest."""
    media_id, key = _published(owner_session, restricted_session, store, tutor, admin)
    report_id = _report_on(owner_session, restricted_session, media_id, reason)
    assert _row(owner_session, media_id).status == "held"

    reports.decide(restricted_session, admin, report_id, "upheld", LATER, store=store)

    row = _row(owner_session, media_id)
    assert (row.status, row.rejection_code) == ("rejected", code)
    assert set(tasks(owner_session)) == {
        f"public/{key}/",
        f"quarantine/{media_id}",
        f"staged/{media_id}/",
        f"archive/{media_id}/",
    }


def test_dismissing_the_report_that_held_a_photo_restores_it(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
) -> None:
    """Back up from the archive under a fresh key, recorded as a restore."""
    media_id, old = _published(owner_session, restricted_session, store, tutor, admin)
    report_id = _report_on(owner_session, restricted_session, media_id, "child_safety")
    _drop_staged(store, media_id)

    reports.decide(
        restricted_session, admin, report_id, "dismissed", LATER, store=store
    )

    row = _row(owner_session, media_id)
    assert row.status == "approved"
    assert row.public_key not in (None, old)
    assert all(f"public/{row.public_key}/{w}.webp" in store.objects for w in WIDTHS)
    events = _events(owner_session)
    assert ("media_restored", "media", None, admin.account_id) in events
    assert ("report_dismissed", "media", "child_safety", admin.account_id) in events


def test_dismissing_one_report_keeps_a_hold_another_still_stands_on(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
) -> None:
    """An earlier non-holding report is dismissed; the child-safety one remains."""
    media_id, _ = _published(owner_session, restricted_session, store, tutor, admin)
    abusive = _report_on(owner_session, restricted_session, media_id, "abusive")
    _report_on(owner_session, restricted_session, media_id, "child_safety")

    reports.decide(restricted_session, admin, abusive, "dismissed", LATER, store=store)

    assert _row(owner_session, media_id).status == "held"


def test_dismissing_a_report_on_an_approved_photo_changes_nothing(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
) -> None:
    """A dismissal leaves a photo that was never held exactly as it was."""
    media_id, key = _published(owner_session, restricted_session, store, tutor, admin)
    report_id = _report_on(owner_session, restricted_session, media_id, "fake")

    reports.decide(
        restricted_session, admin, report_id, "dismissed", LATER, store=store
    )

    assert (
        _row(owner_session, media_id).status,
        _row(owner_session, media_id).public_key,
    ) == (
        "approved",
        key,
    )
    assert tasks(owner_session) == []


def test_an_upheld_report_that_rolls_back_leaves_nothing(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The removal stands or falls with the decision's own commit."""
    media_id, key = _published(owner_session, restricted_session, store, tutor, admin)
    report_id = _report_on(owner_session, restricted_session, media_id, "abusive")
    events_before = _events(owner_session)

    # As for the hold: fail only the commit after the photo was settled,
    # and prove the settlement ran in this leg.
    real_settle = media.settle_report
    settled_in_rolled_back_leg: list[uuid.UUID] = []

    def failing_commit() -> None:
        raise RuntimeError("the decision's commit failed")

    with monkeypatch.context() as patch:

        def settle_then_fail_commit(
            session: Session, *args: object, **kwargs: object
        ) -> None:
            real_settle(session, *args, **kwargs)  # type: ignore[arg-type]
            settled_in_rolled_back_leg.append(media_id)
            patch.setattr(session, "commit", failing_commit)

        patch.setattr(media, "settle_report", settle_then_fail_commit)
        with pytest.raises(RuntimeError, match="the decision's commit failed"):
            reports.decide(
                restricted_session, admin, report_id, "upheld", LATER, store=store
            )
    restricted_session.rollback()
    assert settled_in_rolled_back_leg == [media_id]

    row = _row(owner_session, media_id)
    assert (row.status, row.public_key) == ("approved", key)
    assert tasks(owner_session) == []
    assert invalidations(owner_session) == set()
    assert _events(owner_session) == events_before
    assert (
        owner_session.execute(
            sa.text("SELECT status::text FROM hub_report WHERE id = :r"),
            {"r": report_id},
        ).scalar_one()
        == "open"
    )


def test_the_report_decision_route_removes_an_upheld_photo(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    served: FakeMediaStore,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Through the admin route: uphold removes; the store reaches the service."""
    teacher = people.teacher
    publish_owner(owner_session, teacher.owner_id)
    held = _pending(owner_session, served, teacher.owner_id)
    admin = PlatformAdminLens(account_id=make_teacher(owner_session).account_id)
    _approve(restricted_session, served, admin, held)
    report_id = _report_on(owner_session, restricted_session, held, "child_safety")
    headers = _admin(owner_session, people, monkeypatch)

    dismissed = api_client.post(
        f"/v1/admin/hub/reports/{report_id}/decision",
        json={"decision": "dismissed"},
        headers=headers,
    )

    assert dismissed.status_code == 200, dismissed.text
    assert _row(owner_session, held).status == "approved"


# ---------------------------------------------------------------------------
# [I1] Nothing is approved while its upload can still change.
# ---------------------------------------------------------------------------


def _due(session: Session) -> set[tuple[str, dt.datetime]]:
    """Read every object-outbox row with the moment it falls due.

    :param session: The arranging session
    :return: ``{(prefix, requested_at)}``
    """
    session.rollback()
    return {
        (r.prefix, r.requested_at)
        for r in session.execute(
            sa.text("SELECT prefix, requested_at FROM media_object_task")
        )
    }


def test_approval_waits_until_the_upload_window_closes(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
) -> None:
    """Not queued and not approvable until ``created_at + UPLOAD_WINDOW``.

    The presigned POST can be posted to again until it expires, and the
    sanitiser re-stages whatever lands, so before the window closes the
    variants an administrator previewed need not be the ones an approval
    would copy.
    """
    media_id = _pending(owner_session, store, tutor.lens.owner_id, created_at=NOW)
    inside = NOW + UPLOAD_WINDOW - dt.timedelta(seconds=1)

    assert reports.queue(restricted_session, "media", inside) == []
    with pytest.raises(ConflictError) as caught:
        media.decide(
            restricted_session,
            store,
            admin,
            media_id,
            approve=True,
            code=None,
            now=inside,
        )
    assert caught.value.code == "MEDIA_UPLOAD_WINDOW_OPEN"
    assert caught.value.message_key == "hub.media.not_uploaded"
    row = _row(owner_session, media_id)
    assert (row.status, row.public_key, row.archived_at) == (
        "pending_review",
        None,
        None,
    )
    assert not any(k.startswith(("public/", "archive/")) for k in store.objects)
    assert tasks(owner_session) == []
    assert _events(owner_session) == []

    closed = NOW + UPLOAD_WINDOW
    (item,) = reports.queue(restricted_session, "media", closed)
    assert item.target_id == media_id
    key = _approve(restricted_session, store, admin, media_id, closed)
    assert _row(owner_session, media_id).public_key == key


def test_the_admin_route_refuses_an_approval_inside_the_window(
    api_client: TestClient,
    owner_session: Session,
    served: FakeMediaStore,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Through the route, on the real clock: 409, and the queue omits it."""
    media_id = _pending(
        owner_session,
        served,
        people.teacher.owner_id,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    headers = _admin(owner_session, people, monkeypatch)

    refused = api_client.post(
        f"/v1/admin/hub/media/{media_id}/decision",
        json={"decision": "approve"},
        headers=headers,
    )
    queue = api_client.get("/v1/admin/hub/queue?kind=media", headers=headers)

    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "MEDIA_UPLOAD_WINDOW_OPEN"
    assert queue.json() == {"kind": "media", "items": []}
    assert _row(owner_session, media_id).status == "pending_review"


def test_a_rejection_inside_the_window_deletes_what_lands_later(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
) -> None:
    """Removal is never refused; a file posted after it is deleted too."""
    media_id = _pending(owner_session, store, tutor.lens.owner_id, created_at=NOW)
    at = NOW + dt.timedelta(minutes=5)

    media.decide(
        restricted_session,
        store,
        admin,
        media_id,
        approve=False,
        code="other",
        now=at,
    )

    assert _row(owner_session, media_id).status == "rejected"
    closes = NOW + UPLOAD_WINDOW
    assert _due(owner_session) == {
        (f"quarantine/{media_id}", at),
        (f"staged/{media_id}/", at),
        (f"archive/{media_id}/", at),
        (f"quarantine/{media_id}", closes),
        (f"staged/{media_id}/", closes),
    }


# ---------------------------------------------------------------------------
# [I2] An approved photo can always be taken down by an administrator.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("listing", ["suspended", "hidden", "published"])
def test_rejecting_an_approved_photo_takes_it_down_wherever_it_is(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
    listing: str,
) -> None:
    """Off any page or on one: unpublished, every prefix, its ``/m/`` paths.

    Suspension and unpublishing leave an approved photo's URL live, and a
    photo on no page cannot be reported, so the administrator's rejection
    is the one takedown that reaches it.
    """
    publish_owner(owner_session, tutor.lens.owner_id, status=listing)
    media_id = _pending(owner_session, store, tutor.lens.owner_id)
    key = _approve(restricted_session, store, admin, media_id)
    assert media.is_public(restricted_session, media_id) is (listing == "published")

    decided = media.decide(
        restricted_session,
        store,
        admin,
        media_id,
        approve=False,
        code="identifiable_child",
        now=LATER,
    )

    assert decided.status == "rejected"
    row = _row(owner_session, media_id)
    assert (row.status, row.public_key, row.rejection_code, row.decided_at) == (
        "rejected",
        None,
        "identifiable_child",
        LATER,
    )
    assert set(tasks(owner_session)) == {
        f"public/{key}/",
        f"quarantine/{media_id}",
        f"staged/{media_id}/",
        f"archive/{media_id}/",
    }
    assert set(invalidation.media_paths(key)) <= invalidations(owner_session)
    assert (
        "media_rejected",
        "media",
        "identifiable_child",
        admin.account_id,
    ) in _events(owner_session)


def test_the_admin_route_rejects_an_approved_photo(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    served: FakeMediaStore,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Through the route: an approved photo's detail is readable and rejectable."""
    teacher = people.teacher
    media_id = _pending(owner_session, served, teacher.owner_id)
    admin = PlatformAdminLens(account_id=make_teacher(owner_session).account_id)
    key = _approve(restricted_session, served, admin, media_id)
    headers = _admin(owner_session, people, monkeypatch)

    detail = api_client.get(f"/v1/admin/hub/media/{media_id}", headers=headers)
    rejected = api_client.post(
        f"/v1/admin/hub/media/{media_id}/decision",
        json={"decision": "reject", "code": "other"},
        headers=headers,
    )

    assert detail.json()["status"] == "approved"
    assert rejected.status_code == 200, rejected.text
    assert rejected.json() == {"media_id": str(media_id), "status": "rejected"}
    assert f"public/{key}/" in tasks(owner_session)


# ---------------------------------------------------------------------------
# A held photo is approved only once no report holds it.
# ---------------------------------------------------------------------------


def test_approving_a_held_photo_waits_for_its_open_holding_report(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
) -> None:
    """The direct approval checks what dismissing the report checks.

    While a child-safety or personal-information report on the photo is
    open, an approval would put back what the report took down without
    anyone deciding the report; it is refused, and nothing changes. Once
    the report is decided the photo is decided the usual way.
    """
    media_id, old = _published(owner_session, restricted_session, store, tutor, admin)
    report_id = _report_on(owner_session, restricted_session, media_id, "child_safety")
    before = _row(owner_session, media_id)
    tasks_before = tasks(owner_session)

    with pytest.raises(ConflictError) as caught:
        media.decide(
            restricted_session,
            store,
            admin,
            media_id,
            approve=True,
            code=None,
            now=LATER,
        )

    assert caught.value.code == "MEDIA_REPORT_OPEN"
    assert caught.value.message_key == "hub.media.report_open"
    assert _row(owner_session, media_id) == before
    assert tasks(owner_session) == tasks_before
    assert ("media_restored", "media", None, admin.account_id) not in _events(
        owner_session
    )

    # Once the report is decided, the approval goes ahead. (A rejection
    # never waits: test_rejecting_a_held_photo_leaves_nothing_public.)
    owner_session.execute(
        sa.text("UPDATE hub_report SET status = 'dismissed' WHERE id = :r"),
        {"r": report_id},
    )
    owner_session.commit()
    key = _approve(restricted_session, store, admin, media_id, LATER)
    assert key != old


# ---------------------------------------------------------------------------
# A copy that outlives a failed commit is deleted, not orphaned.
# ---------------------------------------------------------------------------


def _fail_next_commit_after(
    patch: pytest.MonkeyPatch, session: Session, target: object, name: str
) -> list[str]:
    """Make the first commit after ``target.name`` runs fail, as a lost link would.

    :param patch: The monkeypatch context
    :param session: The session whose commit fails
    :param target: The module holding the function
    :param name: The function after which the commit fails
    :return: A list that records the function's runs
    """
    real = getattr(target, name)
    real_commit = session.commit
    ran: list[str] = []

    def flaky_commit() -> None:
        patch.setattr(session, "commit", real_commit)
        raise sa.exc.OperationalError("COMMIT", {}, Exception("connection lost"))

    def wrapped(*args: object, **kwargs: object) -> object:
        result = real(*args, **kwargs)
        ran.append(name)
        patch.setattr(session, "commit", flaky_commit)
        return result

    patch.setattr(target, name, wrapped)
    return ran


def _public_keys(store: FakeMediaStore) -> set[str]:
    return {k.split("/")[1] for k in store.objects if k.startswith("public/")}


def test_an_approval_whose_commit_fails_deletes_its_public_copy(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The copy succeeded, the commit did not: its key is enqueued for deletion.

    The key is recorded nowhere else, so without this no withdrawal or
    account deletion would ever reach ``public/{key}/``.
    """
    media_id = _pending(owner_session, store, tutor.lens.owner_id)

    with monkeypatch.context() as patch:
        ran = _fail_next_commit_after(patch, restricted_session, media, "_publish")
        with pytest.raises(sa.exc.OperationalError):
            media.decide(
                restricted_session,
                store,
                admin,
                media_id,
                approve=True,
                code=None,
                now=NOW,
            )

    assert ran == ["_publish"]
    (copied,) = _public_keys(store)
    row = _row(owner_session, media_id)
    assert (row.status, row.public_key) == ("pending_review", None)
    assert f"public/{copied}/" in tasks(owner_session)
    assert _events(owner_session) == []


def test_a_restore_whose_commit_fails_deletes_its_public_copy(
    owner_session: Session,
    restricted_session: Session,
    store: FakeMediaStore,
    tutor: Owner,
    admin: PlatformAdminLens,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dismissing a holding report restores under a fresh key; same rule."""
    media_id, old = _published(owner_session, restricted_session, store, tutor, admin)
    report_id = _report_on(owner_session, restricted_session, media_id, "child_safety")

    with monkeypatch.context() as patch:
        ran = _fail_next_commit_after(patch, restricted_session, media, "_publish")
        with pytest.raises(sa.exc.OperationalError):
            reports.decide(
                restricted_session, admin, report_id, "dismissed", LATER, store=store
            )

    assert ran == ["_publish"]
    (fresh,) = _public_keys(store) - {old}
    assert _row(owner_session, media_id).status == "held"
    assert f"public/{fresh}/" in tasks(owner_session)
    assert (
        owner_session.execute(
            sa.text("SELECT status::text FROM hub_report WHERE id = :r"),
            {"r": report_id},
        ).scalar_one()
        == "open"
    )
