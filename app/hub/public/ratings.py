"""Ratings and reviews as the public pages show them [H4].

**Read only from ``hub_public_rating`` and ``hub_public_review``, and only
while reviews are switched on.** Every reader here returns nothing while
:func:`~app.hub.public.settings.reviews_enabled` is false, so an off switch
reaches no review view at all. The views apply the threshold [Task 2]: a
batch with fewer than three published reviews has no rating row and no
review rows, so nothing here can show text, an average, a distribution --
or a count -- below it [F18, T2-a]. A missing rating row therefore reads as
``below_threshold``, identically for 0, 1 or 2 reviews.

**Owner ratings cover qualifying batches only** (Call 12): they aggregate
rating rows, and only a batch at the threshold has one, so a small batch's
ratings never leak through its owner's average.

**All arithmetic is in SQL or integer operations.** The average arrives as
integer tenths and :func:`tenths_label` renders it with ``//`` and ``%``;
no float and no Python ``decimal`` is involved [spec 6].

The caller chooses the role: the public pages call these as the hub reader,
the owner's preview as the application role, which the views are also
granted to (Call 6).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.hub.public.messages import Locale, t
from app.hub.public.settings import reviews_enabled
from app.hub.public.views import HubReply, HubReview, RatingSummary

__all__ = [
    "BELOW_THRESHOLD",
    "MAX_REVIEWS",
    "SCORE_MILLI",
    "batch_ratings",
    "batch_reviews",
    "month_label",
    "owner_rating_of_batches",
    "owner_ratings",
    "tenths_label",
]

#: The most reviews a batch page shows; the newest, by month (Call 10).
MAX_REVIEWS: Final[int] = 50

#: What every batch under the threshold says: the same, whatever its count.
BELOW_THRESHOLD: Final[RatingSummary] = RatingSummary(state="below_threshold")

#: An owner's Bayesian score in thousandths, for ``sort=rating``: prior 3.5,
#: weight 5, over the owner's qualifying batches only (Call 11). A scalar
#: subquery over the outer ``hub_public_owner o``; with no qualifying batch
#: the aggregates are empty and it is exactly 17500 / 5 = 3500.
SCORE_MILLI: Final[str] = """(
    SELECT round(
        (17500 + 1000 * coalesce(sum(g.rating_sum), 0))::numeric
        / (5 + coalesce(sum(g.review_count), 0))
    )::int
    FROM hub_public_rating g
    JOIN hub_public_batch b ON b.batch_id = g.batch_id
    WHERE b.owner_slug = o.slug
)"""

#: Batches' ratings; a batch below the threshold has no row.
_BATCH_RATINGS: Final = sa.text(
    "SELECT batch_id, review_count, average_tenths, distribution "
    "FROM hub_public_rating WHERE batch_id = ANY(:ids)"
)

#: Owners' ratings over their qualifying batches, by public slug.
_OWNER_RATINGS: Final = sa.text(
    """
    SELECT b.owner_slug,
           sum(g.review_count)::int AS review_count,
           round(10 * sum(g.rating_sum)::numeric / sum(g.review_count))::int
               AS average_tenths
    FROM hub_public_rating g
    JOIN hub_public_batch b ON b.batch_id = g.batch_id
    WHERE b.owner_slug = ANY(:slugs)
    GROUP BY b.owner_slug
    """
)

#: One owner's rating over some of its batches, for the owner's preview;
#: no row when none of them qualifies.
_BATCHES_AGGREGATE: Final = sa.text(
    """
    SELECT sum(g.review_count)::int AS review_count,
           round(10 * sum(g.rating_sum)::numeric / sum(g.review_count))::int
               AS average_tenths
    FROM hub_public_rating g
    WHERE g.batch_id = ANY(:ids)
    HAVING count(*) > 0
    """
)

#: A batch's newest published reviews. Ordered by month, then by the random
#: id, so the order says nothing about who wrote first [T2-c].
_REVIEWS: Final = sa.text(
    """
    SELECT id, rating, body, tenure_bucket::text AS tenure_bucket,
           published_month, reply_body, reply_month
    FROM hub_public_review
    WHERE batch_id = :batch
    ORDER BY published_month DESC, id
    LIMIT :limit
    """
)


def tenths_label(tenths: int) -> str:
    """Render an average in tenths as it reads, by integer operations.

    :param tenths: The average in tenths, 10 to 50
    :return: ``"4.3"`` for 43
    """
    return f"{tenths // 10}.{tenths % 10}"


def month_label(month: dt.date, locale: Locale) -> str:
    """Name a month and its year, never a day.

    :param month: Any day of the month; only its month and year are read
    :param locale: The page's locale
    :return: ``Nov 2026`` or ``নভেম্বর 2026``, the year in Latin digits
    """
    return f"{t(f'month_{month.month}', locale)} {month.year}"


def _shown(row: Any, *, distribution: bool) -> RatingSummary:
    """Build a shown rating from a rating row.

    :param row: A row with ``review_count`` and ``average_tenths``, and
        ``distribution`` when asked for
    :param distribution: Whether the row carries a distribution
    :return: The summary
    """
    return RatingSummary(
        state="shown",
        count=row.review_count,
        average_tenths=row.average_tenths,
        average_label=tenths_label(row.average_tenths),
        distribution=list(row.distribution) if distribution else None,
    )


def batch_ratings(
    session: Session, batch_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, RatingSummary]:
    """Rate some batches, ``below_threshold`` for those without a row.

    :param session: A session reading as a role the views are granted to
    :param batch_ids: The batches
    :return: Each batch's rating; empty while reviews are off
    """
    if not reviews_enabled() or not batch_ids:
        return {}
    rows = {
        row.batch_id: row
        for row in session.execute(_BATCH_RATINGS, {"ids": list(batch_ids)})
    }
    return {
        batch_id: BELOW_THRESHOLD
        if batch_id not in rows
        else _shown(rows[batch_id], distribution=True)
        for batch_id in batch_ids
    }


def owner_ratings(
    session: Session, owner_slugs: Sequence[str]
) -> dict[str, RatingSummary]:
    """Rate published owners over their qualifying batches.

    :param session: A session reading as a role the views are granted to
    :param owner_slugs: The owners' public slugs
    :return: Each owner with a qualifying batch; an owner without one is
        absent, and the result is empty while reviews are off
    """
    if not reviews_enabled() or not owner_slugs:
        return {}
    return {
        row.owner_slug: _shown(row, distribution=False)
        for row in session.execute(_OWNER_RATINGS, {"slugs": list(owner_slugs)})
    }


def owner_rating_of_batches(
    session: Session, batch_ids: Sequence[uuid.UUID]
) -> RatingSummary | None:
    """Rate one owner over those of its batches that qualify.

    For the owner's preview, whose owner listing may have no public slug.

    :param session: A session reading as a role the views are granted to
    :param batch_ids: The owner's batches
    :return: The rating, or None when none qualifies or reviews are off
    """
    if not reviews_enabled() or not batch_ids:
        return None
    row = session.execute(_BATCHES_AGGREGATE, {"ids": list(batch_ids)}).one_or_none()
    return None if row is None else _shown(row, distribution=False)


def batch_reviews(
    session: Session, batch_id: uuid.UUID, locale: Locale
) -> list[HubReview]:
    """Read a batch's newest published reviews at the threshold.

    :param session: A session reading as a role the views are granted to
    :param batch_id: The batch
    :param locale: The page's locale
    :return: At most :data:`MAX_REVIEWS`, newest month first then by id;
        empty below the threshold and while reviews are off
    """
    if not reviews_enabled():
        return []
    rows = session.execute(_REVIEWS, {"batch": batch_id, "limit": MAX_REVIEWS})
    return [
        HubReview(
            review_id=row.id,
            rating=row.rating,
            body=row.body,
            author_label=t(f"review_by_{row.tenure_bucket}", locale),
            month_label=month_label(row.published_month, locale),
            reply=None
            if row.reply_body is None
            else HubReply(
                body=row.reply_body, month_label=month_label(row.reply_month, locale)
            ),
        )
        for row in rows
    ]
