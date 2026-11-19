"""The weekly publication of approved reviews, and what it tells people.

**A moderator's approval queues a review; this makes it public** [hub spec
D7, Call 2]. :func:`publish_due` publishes every review approved before the
most recent Friday 00:00 in Dhaka (:func:`week_start`), so a review appears
in a weekly batch and a family watching the page cannot match it to the day
it was approved. The cron entry runs daily at 03:10 Dhaka; every run after
the first in a week finds nothing new, and a missed run publishes on the
next one.

**One statement decides what is published**: an ``UPDATE ... RETURNING``
over ``status = 'approved'``. Under READ COMMITTED a second, overlapping run
waits on the first run's row locks, re-checks the condition once they are
released, and finds those rows ``published`` -- so it returns, records and
notifies nothing for them. No advisory lock or "already ran" flag is needed.

**Notifications land in the same transaction as the change they describe**
(:func:`~app.notifications.inbox.deliver` never commits), so a run or a
decision that rolls back sends nothing:

* the author is told the outcome, :data:`HUB_REVIEW_OUTCOME`, by
  :func:`tell_author` -- ``published`` here, ``rejected`` or ``removed`` from
  moderation, and never the moderator's code, which only the author's own
  ``my-review`` shows;
* the people who run the batch are told, :data:`HUB_REVIEWS_PUBLISHED`,
  only when the batch is in ``hub_public_rating`` after the run -- that view
  holds no row below the public threshold, so a batch whose reviews are
  still hidden tells its owner nothing either.

**Nothing is invalidated**: a publication only adds to a page, and additions
ride the edge cache's ten-minute TTL (the H3 ruling). Removals evict, in
:mod:`app.moderation.reviews`.

**Switched off, the job publishes nothing and sends nothing**; its command
still stamps the heartbeat, so an off switch is not a stale job.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import Counter
from typing import Final, Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import BatchListing, HubModerationEvent, Owner
from app.hub.listings.shared import managing_accounts
from app.hub.public.settings import reviews_enabled
from app.local_time import DHAKA, bangladesh_now
from app.notifications.inbox import (
    HUB_REVIEW_OUTCOME,
    HUB_REVIEWS_PUBLISHED,
    deliver,
)

__all__ = [
    "PUBLISH_WEEKDAY",
    "Outcome",
    "publish_due",
    "tell_author",
    "week_start",
]

#: What an author is told about their review.
Outcome = Literal["published", "rejected", "removed"]

#: Friday, in :meth:`datetime.date.weekday` numbering.
PUBLISH_WEEKDAY: Final[int] = 4

#: The correlation id the job's moderation events carry; no request caused
#: them.
_CORRELATION: Final[str] = "hub_review_publication"

#: Publish every review approved before the boundary, in one statement.
#: ``published_month`` is the Dhaka month of the run, computed in SQL.
_PUBLISH: Final = sa.text(
    """
    UPDATE review
    SET status = 'published',
        published_month = date_trunc(
            'month', CAST(:now AS timestamptz) AT TIME ZONE 'Asia/Dhaka'
        )::date,
        approved_at = NULL
    WHERE status = 'approved' AND approved_at < :week_start
    RETURNING id, batch_id, author_account_id
    """
)

#: The batches, among some, the public can now see a rating for. The view
#: holds no row below the threshold, so presence is the threshold test.
_SHOWN: Final = sa.text(
    "SELECT batch_id FROM hub_public_rating WHERE batch_id = ANY(CAST(:ids AS uuid[]))"
)


def week_start(now: dt.datetime) -> dt.datetime:
    """Find the most recent Friday 00:00 in Dhaka at or before a moment.

    :param now: An aware moment
    :return: That Friday midnight, as an aware UTC datetime
    """
    local = bangladesh_now(now)
    back = (local.weekday() - PUBLISH_WEEKDAY) % 7
    friday = local.date() - dt.timedelta(days=back)
    return dt.datetime.combine(friday, dt.time(0), tzinfo=DHAKA).astimezone(dt.UTC)


def tell_author(
    session: Session,
    *,
    author_account_id: uuid.UUID,
    batch_id: uuid.UUID,
    outcome: Outcome,
    now: dt.datetime,
) -> None:
    """Tell a review's author what became of it, in the caller's transaction.

    Keyed by the batch and named by its public title, which is all the
    author needs to find their review again. Commits nothing.

    :param session: The caller's session
    :param author_account_id: The review's author
    :param batch_id: The reviewed batch
    :param outcome: ``published``, ``rejected`` or ``removed``
    :param now: When it happened
    :return: None
    """
    title = session.scalar(
        sa.select(BatchListing.public_title).where(BatchListing.batch_id == batch_id)
    )
    deliver(
        session,
        account_ids=[author_account_id],
        kind=HUB_REVIEW_OUTCOME,
        batch_name=title or "",
        now=now,
        source_id=batch_id,
        preview=outcome,
    )


def _tell_owners(
    session: Session, published: Counter[uuid.UUID], now: dt.datetime
) -> None:
    """Tell who runs each batch now shown with a rating how many were added.

    :param session: The run's session
    :param published: Reviews this run published, per batch
    :param now: When the run happened
    :return: None
    """
    shown = set(session.scalars(_SHOWN, {"ids": [str(b) for b in published]}).all())
    for batch_id in sorted(shown, key=str):
        listing = session.scalars(
            sa.select(BatchListing).where(BatchListing.batch_id == batch_id)
        ).one()
        owner = session.get(Owner, listing.owner_id)
        if owner is None:  # pragma: no cover - the listing's owner FK
            continue
        deliver(
            session,
            account_ids=managing_accounts(session, owner),
            kind=HUB_REVIEWS_PUBLISHED,
            batch_name=listing.public_title or "",
            now=now,
            source_id=owner.id,
            preview=str(published[batch_id]),
        )


def publish_due(session: Session, now: dt.datetime) -> int:
    """Publish every review approved before this week's boundary.

    Adds to the caller's transaction and commits nothing.

    :param session: The run's session
    :param now: The moment of the run
    :return: How many reviews this run published; 0 while switched off
    """
    if not reviews_enabled():
        return 0
    rows = session.execute(_PUBLISH, {"now": now, "week_start": week_start(now)}).all()
    published: Counter[uuid.UUID] = Counter()
    for review_id, batch_id, author in rows:
        published[batch_id] += 1
        session.add(
            HubModerationEvent(
                event="review_published",
                target_kind="review",
                target_id=review_id,
                actor_admin_account_id=None,
                decision_code=None,
                correlation_id=_CORRELATION,
                at=now,
            )
        )
        tell_author(
            session,
            author_account_id=author,
            batch_id=batch_id,
            outcome="published",
            now=now,
        )
    if published:
        _tell_owners(session, published, now)
    return len(rows)
