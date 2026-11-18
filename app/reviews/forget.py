"""Forget reviews totally: the review, its reply and every report on either.

**Deletion is total** (Call 15; project.md). An author may delete their
review at any time, and nothing about it may outlive the delete: not the
text, not the owner's reply to it, and not the reports other readers filed
against either, which quote neither but name its id and would otherwise
keep a pointer to something that no longer exists. ``hub_moderation_event``
rows stay: they are bare ids and closed codes, kept twelve months, and
describe what moderation did rather than what anyone wrote.

**A visible review's page is evicted.** A review shown on a batch page is
cached at the edge; deleting it, or dropping the batch below the threshold
by deleting it, changes that page. Visibility is read from
``hub_public_review`` **before** the delete, so the threshold is the view's
and never restated here.

:func:`forget` commits nothing: the author's delete (Task 4) and account
deletion (Task 10) call it inside their own transaction.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.hub.public import invalidation

__all__ = ["forget"]

#: The owner slugs of the given reviews that the public can see now.
_VISIBLE_OWNER_SLUGS: Final = sa.text(
    """
    SELECT DISTINCT ol.slug
    FROM hub_public_review v
    JOIN batch_listing bl ON bl.batch_id = v.batch_id
    JOIN owner_listing ol ON ol.owner_id = bl.owner_id
    WHERE v.id = ANY(:ids) AND ol.slug IS NOT NULL
    ORDER BY ol.slug
    """
)

#: Every report on the reviews or on their replies; a reply's id is its
#: review's.
_DELETE_REPORTS: Final = sa.text(
    "DELETE FROM hub_report "
    "WHERE target_kind IN ('review', 'reply') AND target_id = ANY(:ids)"
)

#: The reviews; each reply goes with its review by ``ON DELETE CASCADE``.
_DELETE_REVIEWS: Final = sa.text("DELETE FROM review WHERE id = ANY(:ids)")


def forget(session: Session, review_ids: Sequence[uuid.UUID], now: dt.datetime) -> None:
    """Delete reviews, their replies and every report on either.

    :param session: The caller's session, inside its transaction
    :param review_ids: The reviews; ids that do not exist are ignored
    :param now: The moment of the delete, for the invalidation rows
    :return: None
    """
    ids = list(review_ids)
    if not ids:
        return
    slugs = list(session.scalars(_VISIBLE_OWNER_SLUGS, {"ids": ids}))
    session.execute(_DELETE_REPORTS, {"ids": ids})
    session.execute(_DELETE_REVIEWS, {"ids": ids})
    if slugs:
        invalidation.enqueue(
            session,
            [path for slug in slugs for path in invalidation.owner_paths(slug)],
            now,
        )
