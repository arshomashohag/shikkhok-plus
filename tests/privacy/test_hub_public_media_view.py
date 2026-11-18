"""``hub_public_media``: approved photos under a visible owner and batch only.

A photo is public when it is ``approved``, its owner listing is published,
and -- for a batch photo -- its batch appears in ``hub_public_batch`` (batch
listing published, batch active, owner listing published). The view reads
the two existing views rather than restating their rules, so the photo
rule cannot drift from the page rule; every case is still probed here, as
the hub reader, against rows arranged as the table owner.
"""

from __future__ import annotations

import re
import uuid
from typing import Final

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.hub.public.db import as_hub_reader
from tests.batches.conftest import make_teacher
from tests.privacy.test_hub_public_views import (
    PRIVATE_TABLES,
    _batch_listing,
    _owner_listing,
)

#: What the view shows, and nothing else of ``listing_media``.
COLUMNS: Final[tuple[str, ...]] = (
    "owner_slug",
    "batch_slug",
    "media_id",
    "public_key",
    "width",
    "height",
    "widths",
    "alt_en",
    "alt_bn",
    "position",
)

#: Every status but ``approved``.
NOT_APPROVED: Final[tuple[str, ...]] = (
    "awaiting_upload",
    "processing",
    "pending_review",
    "rejected",
    "withdrawn",
    "held",
)


def _media(
    session: Session,
    owner_id: uuid.UUID,
    *,
    batch_id: uuid.UUID | None = None,
    status: str = "approved",
    position: int = 0,
) -> uuid.UUID:
    """Insert one photo with every field the view shows.

    :param session: An arranging session
    :param owner_id: The owner
    :param batch_id: Its batch, or None for an owner-level photo
    :param status: Its status; approved photos get a public key
    :param position: Its place in the gallery
    :return: The media id
    """
    media_id = uuid.uuid4()
    session.execute(
        sa.text(
            "INSERT INTO listing_media (id, owner_id, batch_id, status, "
            "content_type, byte_size, public_key, width, height, widths, "
            "alt_en, alt_bn, position, rejection_code) VALUES "
            "(:id, :o, :b, CAST(:st AS media_status), 'image/jpeg', 2048, "
            ":key, 1200, 800, '{320,960}', 'A classroom', 'একটি শ্রেণিকক্ষ', "
            ":pos, NULL)"
        ),
        {
            "id": media_id,
            "o": owner_id,
            "b": batch_id,
            "st": status,
            "key": uuid.uuid4().hex if status == "approved" else None,
            "pos": position,
        },
    )
    session.commit()
    return media_id


def _seen(session: Session) -> set[uuid.UUID]:
    """Read the media ids the view shows, as the hub reader.

    :param session: The application role's session; left as the reader
    :return: The visible media ids
    """
    as_hub_reader(session)
    return set(
        session.execute(sa.text("SELECT media_id FROM hub_public_media")).scalars()
    )


def _live_tutor(session: Session, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Arrange a tutor whose listing and batch listing are both published.

    :param session: An arranging session
    :param slug: The owner's slug
    :return: ``(owner_id, batch_id)``
    """
    teacher = make_teacher(session)
    _owner_listing(session, teacher.owner_id, slug=slug)
    _batch_listing(session, teacher.batch_id, teacher.owner_id)
    return teacher.owner_id, teacher.batch_id


def test_approved_media_under_visible_owner_and_batch_is_shown(
    owner_session: Session, restricted_session: Session
) -> None:
    """Both galleries show, with exactly the public columns.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    owner_id, batch_id = _live_tutor(owner_session, "live-tutor")
    owner_level = _media(owner_session, owner_id, position=2)
    batch_level = _media(owner_session, owner_id, batch_id=batch_id)
    key = owner_session.execute(
        sa.text("SELECT public_key FROM listing_media WHERE id = :m"),
        {"m": owner_level},
    ).scalar_one()

    as_hub_reader(restricted_session)
    result = restricted_session.execute(
        sa.text("SELECT * FROM hub_public_media ORDER BY batch_slug NULLS FIRST")
    )
    rows = result.mappings().all()

    assert tuple(result.keys()) == COLUMNS
    assert [dict(r) for r in rows] == [
        {
            "owner_slug": "live-tutor",
            "batch_slug": None,
            "media_id": owner_level,
            "public_key": key,
            "width": 1200,
            "height": 800,
            "widths": [320, 960],
            "alt_en": "A classroom",
            "alt_bn": "একটি শ্রেণিকক্ষ",
            "position": 2,
        },
        {
            "owner_slug": "live-tutor",
            "batch_slug": "class-9-maths",
            "media_id": batch_level,
            "public_key": rows[1]["public_key"],
            "width": 1200,
            "height": 800,
            "widths": [320, 960],
            "alt_en": "A classroom",
            "alt_bn": "একটি শ্রেণিকক্ষ",
            "position": 0,
        },
    ]
    assert rows[1]["public_key"] is not None


@pytest.mark.parametrize("status", NOT_APPROVED)
def test_media_view_hides_unapproved_and_unpublished(
    owner_session: Session, restricted_session: Session, status: str
) -> None:
    """A photo in any status but ``approved`` is in neither gallery.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :param status: A status that is not public
    :return: None
    """
    owner_id, batch_id = _live_tutor(owner_session, "live-tutor")
    shown = _media(owner_session, owner_id, position=9)
    _media(owner_session, owner_id, status=status)
    _media(owner_session, owner_id, batch_id=batch_id, status=status)

    assert _seen(restricted_session) == {shown}


@pytest.mark.parametrize("status", ["draft", "hidden", "suspended"])
def test_media_hidden_under_unpublished_owner(
    owner_session: Session, restricted_session: Session, status: str
) -> None:
    """An owner not published shows no photo, its batch's included.

    The batch listing stays ``published``: unpublishing an owner does not
    touch it, so the owner's own status must hide the batch photos too.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :param status: An owner listing status that is not public
    :return: None
    """
    teacher = make_teacher(owner_session)
    _owner_listing(owner_session, teacher.owner_id, slug="not-live", status=status)
    _batch_listing(owner_session, teacher.batch_id, teacher.owner_id)
    _media(owner_session, teacher.owner_id)
    _media(owner_session, teacher.owner_id, batch_id=teacher.batch_id)

    assert _seen(restricted_session) == set()


def test_media_hidden_without_owner_listing(
    owner_session: Session, restricted_session: Session
) -> None:
    """An owner who never made a listing shows no photo.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    teacher = make_teacher(owner_session)
    _media(owner_session, teacher.owner_id)

    assert _seen(restricted_session) == set()


@pytest.mark.parametrize("status", ["draft", "hidden", "suspended"])
def test_batch_media_hidden_under_unpublished_batch(
    owner_session: Session, restricted_session: Session, status: str
) -> None:
    """A batch listing not published hides its photos, not the owner's.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :param status: A batch listing status that is not public
    :return: None
    """
    teacher = make_teacher(owner_session)
    _owner_listing(owner_session, teacher.owner_id, slug="live-tutor")
    _batch_listing(owner_session, teacher.batch_id, teacher.owner_id, status=status)
    owner_level = _media(owner_session, teacher.owner_id)
    _media(owner_session, teacher.owner_id, batch_id=teacher.batch_id)

    assert _seen(restricted_session) == {owner_level}


def test_batch_media_hidden_without_batch_listing(
    owner_session: Session, restricted_session: Session
) -> None:
    """A batch never listed shows no photo, though its owner is live.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    teacher = make_teacher(owner_session)
    _owner_listing(owner_session, teacher.owner_id, slug="live-tutor")
    owner_level = _media(owner_session, teacher.owner_id)
    _media(owner_session, teacher.owner_id, batch_id=teacher.batch_id)

    assert _seen(restricted_session) == {owner_level}


def test_batch_media_hidden_for_inactive_batch(
    owner_session: Session, restricted_session: Session
) -> None:
    """A retired batch's photos leave with its page.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    owner_id, batch_id = _live_tutor(owner_session, "live-tutor")
    owner_level = _media(owner_session, owner_id)
    _media(owner_session, owner_id, batch_id=batch_id)
    owner_session.execute(
        sa.text("UPDATE batch SET active = false WHERE id = :b"), {"b": batch_id}
    )
    owner_session.commit()

    assert _seen(restricted_session) == {owner_level}


def test_batch_media_hidden_when_batch_belongs_to_another_owner(
    owner_session: Session, restricted_session: Session
) -> None:
    """A photo whose batch is someone else's is never shown on either page.

    Nothing in the table ties ``batch_id`` to ``owner_id``; the upload
    service checks it. Should a row ever disagree, the view shows it under
    neither owner rather than putting one owner's photo on another's page.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    mine, _ = _live_tutor(owner_session, "mine")
    _, theirs = _live_tutor(owner_session, "theirs")
    _media(owner_session, mine, batch_id=theirs)

    assert _seen(restricted_session) == set()


def test_media_view_references_no_private_table(restricted_session: Session) -> None:
    """The view, and every view it reads, names no private table.

    The text is what a reviewer reads; ``pg_depend``, followed through the
    views ``hub_public_media`` reads, is what PostgreSQL resolved. Of
    ``listing_media`` itself, only the public columns and the ones the
    filter needs are read: never ``rejection_code``, the declared upload
    type and size, or the timestamps.

    :param restricted_session: A session as the application role
    :return: None
    """
    text = restricted_session.execute(
        sa.text("SELECT definition FROM pg_views WHERE viewname = 'hub_public_media'")
    ).scalar_one()
    for table in PRIVATE_TABLES:
        assert not re.search(rf"\b{table}\b", text), table
    assert not re.search(r"\b(batch|b)\.name\b", text)

    depends = restricted_session.execute(
        sa.text(
            "WITH RECURSIVE reads(view_oid) AS ("
            "  SELECT 'hub_public_media'::regclass::oid"
            "  UNION"
            "  SELECT d.refobjid FROM reads"
            "  JOIN pg_rewrite r ON r.ev_class = reads.view_oid"
            "  JOIN pg_depend d ON d.classid = 'pg_rewrite'::regclass"
            "   AND d.objid = r.oid AND d.refclassid = 'pg_class'::regclass"
            "  JOIN pg_class t ON t.oid = d.refobjid"
            "  WHERE t.relkind = 'v' AND t.oid <> reads.view_oid"
            ") "
            "SELECT DISTINCT v.relname AS view, t.relname AS tbl, "
            "t.relkind::text AS kind, a.attname AS col FROM reads "
            "JOIN pg_class v ON v.oid = reads.view_oid "
            "JOIN pg_rewrite r ON r.ev_class = v.oid "
            "JOIN pg_depend d ON d.classid = 'pg_rewrite'::regclass "
            "AND d.objid = r.oid AND d.refclassid = 'pg_class'::regclass "
            "JOIN pg_class t ON t.oid = d.refobjid "
            "LEFT JOIN pg_attribute a ON a.attrelid = t.oid "
            "AND a.attnum = d.refobjsubid "
            "WHERE t.oid <> v.oid"
        )
    ).all()

    views = {row.view for row in depends}
    tables = {row.tbl for row in depends if row.kind == "r"}
    media_columns = {row.col for row in depends if row.tbl == "listing_media"}
    assert views == {"hub_public_media", "hub_public_owner", "hub_public_batch"}
    assert tables == {
        "listing_media",
        "owner_listing",
        "owner",
        "batch_listing",
        "batch",
        "schedule_slot",
    }
    assert tables.isdisjoint(PRIVATE_TABLES), tables
    assert ("batch", "name") not in {(row.tbl, row.col) for row in depends}
    assert media_columns == {
        "id",
        "owner_id",
        "batch_id",
        "status",
        "public_key",
        "width",
        "height",
        "widths",
        "alt_en",
        "alt_bn",
        "position",
    }
