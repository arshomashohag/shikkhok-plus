"""Arrangement helpers for the media service tests.

Rows are written through the table-owner session; each service under test
is handed the application role's session, so the role's grants on
``listing_media``, ``media_object_task``, ``cdn_invalidation`` and
``rate_limit_counter`` are what the tests exercise.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from tests.batches.conftest import make_teacher

__all__ = [
    "NOW",
    "Owner",
    "arrange",
    "batch_listing",
    "invalidations",
    "media_row",
    "owner_listing",
    "tasks",
]

#: A fixed moment for every test that does not need the real clock.
NOW: Final[dt.datetime] = dt.datetime(2026, 11, 18, 9, 0, tzinfo=dt.UTC)


@dataclass(frozen=True, slots=True)
class Owner:
    """A solo tutor with one batch.

    :ivar lens: Their teacher lens
    :ivar batch_id: Their batch
    """

    lens: TeacherLens
    batch_id: uuid.UUID


def arrange(session: Session) -> Owner:
    """Arrange a solo tutor with one batch.

    :param session: The arranging session
    :return: The tutor
    """
    teacher = make_teacher(session)
    return Owner(
        lens=TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id),
        batch_id=teacher.batch_id,
    )


def media_row(
    session: Session,
    owner_id: uuid.UUID,
    *,
    status: str = "pending_review",
    batch_id: uuid.UUID | None = None,
    created_at: dt.datetime = NOW,
    position: int = 0,
) -> uuid.UUID:
    """Insert one photo row directly; approved rows get a key and a size.

    :param session: The arranging session
    :param owner_id: The owner
    :param status: Its status
    :param batch_id: Its batch, or None for the owner's gallery
    :param created_at: When its upload started
    :param position: Its gallery position
    :return: The media id
    """
    media_id = uuid.uuid4()
    approved = status == "approved"
    session.execute(
        sa.text(
            "INSERT INTO listing_media (id, owner_id, batch_id, status, "
            "content_type, byte_size, public_key, width, height, widths, alt_en, "
            "alt_bn, position, created_at) VALUES (:id, :o, :b, "
            "CAST(:st AS media_status), 'image/jpeg', 2048, :key, :w, :h, :ws, "
            "'A classroom', 'একটি শ্রেণিকক্ষ', :pos, :at)"
        ),
        {
            "id": media_id,
            "o": owner_id,
            "b": batch_id,
            "st": status,
            "key": uuid.uuid4().hex if approved else None,
            "w": 1200 if approved else None,
            "h": 800 if approved else None,
            "ws": [320, 960] if approved else None,
            "pos": position,
            "at": created_at,
        },
    )
    session.commit()
    return media_id


def owner_listing(session: Session, owner_id: uuid.UUID, slug: str) -> None:
    """Publish the owner's listing under a slug.

    :param session: The arranging session
    :param owner_id: The owner
    :param slug: The public slug
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, slug, status, public_name, "
            "published_at) VALUES (:o, :s, 'published', 'Tutor', now())"
        ),
        {"o": owner_id, "s": slug},
    )
    session.commit()


def batch_listing(
    session: Session, owner_id: uuid.UUID, batch_id: uuid.UUID, slug: str
) -> None:
    """Give a batch a listing slug.

    :param session: The arranging session
    :param owner_id: The batch's owner
    :param batch_id: The batch
    :param slug: The batch's public slug
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO batch_listing (batch_id, owner_id, slug, show_fee, "
            "show_schedule) VALUES (:b, :o, :s, false, false)"
        ),
        {"b": batch_id, "o": owner_id, "s": slug},
    )
    session.commit()


def tasks(session: Session) -> list[str]:
    """Read every object-outbox prefix, oldest first.

    :param session: The arranging session
    :return: The prefixes
    """
    session.rollback()
    return list(
        session.execute(
            sa.text("SELECT prefix FROM media_object_task ORDER BY id")
        ).scalars()
    )


def invalidations(session: Session) -> set[str]:
    """Read every CDN outbox path.

    :param session: The arranging session
    :return: The paths
    """
    session.rollback()
    return set(session.execute(sa.text("SELECT path FROM cdn_invalidation")).scalars())
