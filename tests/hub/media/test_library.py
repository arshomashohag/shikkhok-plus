"""The owner's photo library: list, edit alt text, reorder, withdraw.

An approved photo is public at ``/m/{key}/{w}.webp`` and on its page. So an
alt-text edit that sends it back to review, and a withdrawal, both take it
down in their own transaction: the ``public/{key}/`` objects are enqueued for
deletion, and the ``/m/`` path and the page it sits on for invalidation.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.batches.service import BatchNotFound
from app.errors import AuthorizationError, ValidationError
from app.hub.media import library
from app.hub.public import commands
from tests.hub.media.support import (
    NOW,
    Owner,
    arrange,
    batch_listing,
    invalidations,
    media_row,
    owner_listing,
    tasks,
)


@pytest.fixture
def tutor(owner_session: Session) -> Owner:
    return arrange(owner_session)


def _row(session: Session, media_id: uuid.UUID) -> sa.Row[tuple[object, ...]]:
    session.rollback()
    return session.execute(
        sa.text(
            "SELECT status, public_key, alt_en, alt_bn, position "
            "FROM listing_media WHERE id = :m"
        ),
        {"m": media_id},
    ).one()


def _approved(
    session: Session, tutor: Owner, *, batch: bool = False
) -> tuple[uuid.UUID, str]:
    media_id = media_row(
        session,
        tutor.lens.owner_id,
        status="approved",
        batch_id=tutor.batch_id if batch else None,
    )
    key = _row(session, media_id).public_key
    assert isinstance(key, str)
    return media_id, key


def test_list_media_shows_one_gallery_without_withdrawn(
    restricted_session: Session, owner_session: Session, tutor: Owner
) -> None:
    owner_id = tutor.lens.owner_id
    second = media_row(owner_session, owner_id, status="rejected", position=1)
    first = media_row(owner_session, owner_id, status="awaiting_upload", position=0)
    media_row(owner_session, owner_id, status="withdrawn", position=2)
    in_batch = media_row(owner_session, owner_id, batch_id=tutor.batch_id)
    stranger = arrange(owner_session)
    media_row(owner_session, stranger.lens.owner_id)

    owner_gallery = library.list_media(restricted_session, tutor.lens, None)
    batch_gallery = library.list_media(restricted_session, tutor.lens, tutor.batch_id)

    assert [m.id for m in owner_gallery] == [first, second]
    assert [m.id for m in batch_gallery] == [in_batch]
    with pytest.raises(BatchNotFound):
        library.list_media(restricted_session, tutor.lens, stranger.batch_id)


def test_alt_edit_on_approved_returns_to_review_and_unpublishes(
    restricted_session: Session, owner_session: Session, tutor: Owner
) -> None:
    owner_listing(owner_session, tutor.lens.owner_id, "rahim-sir")
    media_id, key = _approved(owner_session, tutor)

    # The same text is no change: the photo stays public.
    library.update_alt(
        restricted_session,
        tutor.lens,
        media_id,
        alt_en="A classroom",
        alt_bn=None,
        now=NOW,
    )
    assert _row(owner_session, media_id).status == "approved"
    assert tasks(owner_session) == []
    assert invalidations(owner_session) == set()

    edited = library.update_alt(
        restricted_session,
        tutor.lens,
        media_id,
        alt_en="Our new classroom",
        alt_bn=None,
        now=NOW,
    )

    assert edited.status == "pending_review"
    row = _row(owner_session, media_id)
    assert (row.status, row.public_key, row.alt_en, row.alt_bn) == (
        "pending_review",
        None,
        "Our new classroom",
        "একটি শ্রেণিকক্ষ",
    )
    assert tasks(owner_session) == [f"public/{key}/"]
    assert invalidations(owner_session) == {
        f"/m/{key}/*",
        "/hub/bn/t/rahim-sir*",
        "/hub/en/t/rahim-sir*",
        "/hub/sitemap.xml",
    }


def test_alt_edit_off_the_page_enqueues_nothing(
    restricted_session: Session, owner_session: Session, tutor: Owner
) -> None:
    media_id = media_row(owner_session, tutor.lens.owner_id, status="pending_review")

    library.update_alt(
        restricted_session,
        tutor.lens,
        media_id,
        alt_en=None,
        alt_bn="নতুন বিবরণ",
        now=NOW,
    )

    row = _row(owner_session, media_id)
    assert (row.status, row.alt_en, row.alt_bn) == (
        "pending_review",
        "A classroom",
        "নতুন বিবরণ",
    )
    assert tasks(owner_session) == []
    assert invalidations(owner_session) == set()

    for alt_en, alt_bn, code in (
        ("", None, "MEDIA_ALT_INVALID"),
        (None, "ক" * 201, "MEDIA_ALT_INVALID"),
        ("Phone 01711000000", None, "HUB_TEXT_CONTAINS_CONTACT"),
    ):
        with pytest.raises(ValidationError) as refused:
            library.update_alt(
                restricted_session,
                tutor.lens,
                media_id,
                alt_en=alt_en,
                alt_bn=alt_bn,
                now=NOW,
            )
        assert refused.value.code == code
    assert _row(owner_session, media_id).alt_bn == "নতুন বিবরণ"


def test_withdraw_enqueues_all_prefixes_and_invalidation(
    restricted_session: Session, owner_session: Session, tutor: Owner
) -> None:
    owner_listing(owner_session, tutor.lens.owner_id, "rahim-sir")
    batch_listing(owner_session, tutor.lens.owner_id, tutor.batch_id, "class-nine")
    media_id, key = _approved(owner_session, tutor, batch=True)

    library.withdraw(restricted_session, tutor.lens, media_id, now=NOW)

    row = _row(owner_session, media_id)
    assert (row.status, row.public_key) == ("withdrawn", None)
    assert tasks(owner_session) == [
        f"public/{key}/",
        f"quarantine/{media_id}",
        f"staged/{media_id}/",
        f"archive/{media_id}/",
    ]
    assert invalidations(owner_session) == {
        f"/m/{key}/*",
        "/hub/bn/t/rahim-sir/class-nine",
        "/hub/en/t/rahim-sir/class-nine",
        "/hub/sitemap.xml",
    }

    # A second withdrawal is a no-op, so a retried DELETE enqueues nothing.
    library.withdraw(restricted_session, tutor.lens, media_id, now=NOW)
    assert len(tasks(owner_session)) == 4

    # The /m/ path is a wildcard: it counts toward the claim's cap.
    claimed = commands.claim(restricted_session, now=NOW)
    assert f"/m/{key}/*" in claimed.paths


def test_withdraw_unapproved_deletes_objects_without_invalidating(
    restricted_session: Session, owner_session: Session, tutor: Owner
) -> None:
    media_id = media_row(owner_session, tutor.lens.owner_id, status="pending_review")

    library.withdraw(restricted_session, tutor.lens, media_id, now=NOW)

    assert _row(owner_session, media_id).status == "withdrawn"
    assert tasks(owner_session) == [
        f"quarantine/{media_id}",
        f"staged/{media_id}/",
        f"archive/{media_id}/",
    ]
    assert invalidations(owner_session) == set()


def test_library_refuses_another_owners_photo(
    restricted_session: Session, owner_session: Session, tutor: Owner
) -> None:
    media_id = media_row(owner_session, tutor.lens.owner_id)
    stranger = arrange(owner_session)

    for call in (
        lambda: library.withdraw(restricted_session, stranger.lens, media_id, now=NOW),
        lambda: library.update_alt(
            restricted_session,
            stranger.lens,
            media_id,
            alt_en="Mine now",
            alt_bn=None,
            now=NOW,
        ),
        lambda: library.reorder(restricted_session, stranger.lens, None, [media_id]),
    ):
        with pytest.raises(AuthorizationError) as refused:
            call()
        assert refused.value.code == "MEDIA_NOT_FOUND"
    assert _row(owner_session, media_id).status == "pending_review"


def test_reorder_swaps_approved_slots(
    restricted_session: Session, owner_session: Session, tutor: Owner
) -> None:
    owner_id = tutor.lens.owner_id
    a = media_row(owner_session, owner_id, status="approved", position=0)
    b = media_row(owner_session, owner_id, status="approved", position=1)
    c = media_row(owner_session, owner_id, status="pending_review", position=2)
    in_batch = media_row(owner_session, owner_id, batch_id=tutor.batch_id)

    # Swapping two approved slots must not trip the unique slot index
    # halfway through; ids left out keep their order after the named ones.
    ordered = library.reorder(restricted_session, tutor.lens, None, [b, a])

    assert [m.id for m in ordered] == [b, a, c]
    assert [_row(owner_session, m).position for m in (b, a, c)] == [0, 1, 2]

    # A photo from another gallery is not in this one.
    with pytest.raises(AuthorizationError, match="MEDIA_NOT_FOUND"):
        library.reorder(restricted_session, tutor.lens, None, [in_batch, a])
    assert _row(owner_session, a).position == 1
