"""The teacher's side of reviews: read their batches' reviews, reply to one.

**Review content is read only through the public views** [T2-b]. A
teacher sees exactly what the public sees of their own batches:
``hub_public_review`` and ``hub_public_rating``, under the same threshold.
Below three published reviews a batch shows no review, and no count either
[T2-a] -- a count of 1 or 2 is what lets a teacher who knows which family
just became eligible guess who wrote. This module never names the ``review``
base table for content; ``tests/gates/test_teacher_reviews_read_views.py``
enforces it, allowlisting one ownership check that reads a review's id and
batch only (see the delete below).
Its own reads of ``batch_listing`` (which batches are the owner's) and
``review_reply`` (the owner's own replies) carry nothing a guardian wrote.

**Order says nothing about who wrote first** [T2-c]: every read of the
review view orders by ``published_month DESC, id``, and ids are random.

**A review the teacher cannot reach is not found by a reply.** Another
owner's review, a review of a batch below the threshold, a review deleted
while the reply was being written, and an id that was never minted all
answer ``REVIEW_NOT_FOUND`` with the same bytes, so the refusal is not an
existence oracle.

**A reply is pre-moderated.** Writing or replacing one puts it back to
``pending`` with the last decision cleared; replacing a published reply
takes it off the owner's pages, which are evicted in the same transaction.
The reply is the owner's, so it spends the owner's daily listing allowance
[F5], and only when it changes something: an identical body spends
nothing. A suspended listing may not reply [F6]; that refusal comes first,
because a suspended owner's batches have left the views and the review
would otherwise be "not found".

**A delete is total and never refused for a switch, a suspension or the
review's visibility** [F8, T5-a]: the reply and every report filed against
it go together, and a delete that finds nothing of the owner's to delete
answers the same quiet success.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final, cast

import sqlalchemy as sa
from sqlalchemy.engine import Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.ceilings import CeilingChecker
from app.authz.lenses import TeacherLens
from app.db.models import OwnerListing
from app.errors import AuthorizationError, ValidationError
from app.hub.listings.shared import refuse_suspended
from app.hub.public import invalidation
from app.reviews.content import refuse_contact
from app.reviews.eligibility import Tenure
from app.reviews.switch import require_reviews_on

__all__ = [
    "MAX_REPLY",
    "OwnerBatchRating",
    "OwnerReview",
    "delete_reply",
    "owner_reviews",
    "put_reply",
]

#: The longest reply, counted after surrounding whitespace is stripped.
MAX_REPLY: Final = 1000

#: The reply's foreign key to its review: violated when the review is
#: deleted while a first reply to it is being written.
_REPLY_REVIEW_FK: Final = "fk_review_reply_review_id"

#: Every batch listing of the owner; the published ones are reported on.
_LISTINGS: Final = sa.text(
    """
    SELECT batch_id, public_title, status
    FROM batch_listing
    WHERE owner_id = :owner_id
    ORDER BY public_title, batch_id
    """
)

#: The rating of batches over the threshold; a batch below it has no row.
_RATINGS: Final = sa.text(
    """
    SELECT batch_id, review_count, average_tenths, distribution
    FROM hub_public_rating
    WHERE batch_id = ANY(:batch_ids)
    """
)

#: The owner's published reviews over the threshold, with the owner's own
#: reply in whatever status it is.
_REVIEWS: Final = sa.text(
    """
    SELECT v.id, v.batch_id, v.rating, v.body, v.tenure_bucket,
           v.published_month, v.reply_body, v.reply_month,
           p.status AS my_reply_status, p.body AS my_reply_body,
           p.rejection_code AS my_reply_rejection_code
    FROM hub_public_review v
    LEFT JOIN review_reply p ON p.review_id = v.id
    WHERE v.batch_id = ANY(:owned)
    ORDER BY v.published_month DESC, v.id
    """
)

#: One review of the owner's, if the teacher can reach it.
_ONE: Final = sa.text(
    """
    SELECT v.id, v.batch_id, v.rating, v.body, v.tenure_bucket,
           v.published_month, v.reply_body, v.reply_month,
           p.status AS my_reply_status, p.body AS my_reply_body,
           p.rejection_code AS my_reply_rejection_code
    FROM hub_public_review v
    LEFT JOIN review_reply p ON p.review_id = v.id
    WHERE v.id = :review_id
      AND v.batch_id IN (
          SELECT batch_id FROM batch_listing WHERE owner_id = :owner_id
      )
    ORDER BY v.published_month DESC, v.id
    """
)

#: The reply to a review, locked for the rest of the write or delete.
_LOCK_REPLY: Final = sa.text(
    "SELECT body, status FROM review_reply WHERE review_id = :review_id FOR UPDATE"
)

#: A first reply; nothing when another call's insert won the race.
_CREATE: Final = sa.text(
    """
    INSERT INTO review_reply (review_id, body, status, written_by_account_id,
                              created_at)
    VALUES (:review_id, :body, 'pending', :account_id, :now)
    ON CONFLICT (review_id) DO NOTHING
    RETURNING review_id
    """
)

#: A replacement: new words, back to moderation, the last decision forgotten.
_REPLACE: Final = sa.text(
    """
    UPDATE review_reply
    SET body = :body, status = 'pending', written_by_account_id = :account_id,
        edited_at = :now, published_month = NULL, decided_at = NULL,
        decided_by_account_id = NULL, rejection_code = NULL
    WHERE review_id = :review_id
    """
)

#: Every report filed against the reply; a reply's id is its review's.
_DELETE_REPORTS: Final = sa.text(
    "DELETE FROM hub_report WHERE target_kind = 'reply' AND target_id = :review_id"
)

#: The reply itself.
_DELETE_REPLY: Final = sa.text("DELETE FROM review_reply WHERE review_id = :review_id")


@dataclass(frozen=True, slots=True)
class OwnerBatchRating:
    """One published batch of the owner's, with its rating if it has one.

    Below the threshold every figure is None, the count included [T2-a]:
    such a batch is indistinguishable from one nobody has reviewed.

    :ivar batch_id: The batch
    :ivar batch_title: Its public title
    :ivar review_count: Published reviews, or None below the threshold
    :ivar average_tenths: The average in tenths (43 is 4.3), or None
    :ivar distribution: Reviews per star from one to five, or None
    """

    batch_id: uuid.UUID
    batch_title: str | None
    review_count: int | None
    average_tenths: int | None
    distribution: list[int] | None


@dataclass(frozen=True, slots=True)
class OwnerReview:
    """One published review of the owner's batch, as the teacher sees it.

    :ivar id: The review
    :ivar batch_id: The batch
    :ivar rating: 1 to 5
    :ivar body: The text, or None
    :ivar tenure: The author's tenure bucket
    :ivar published_month: The first of the month it was published in
    :ivar reply_body: The reply's text while it is published
    :ivar reply_month: The first of the month the reply was published in
    :ivar my_reply_status: The owner's reply's status, or None without one
    :ivar my_reply_body: The owner's reply's text in any status
    :ivar my_reply_rejection_code: Why the reply was rejected or removed
    """

    id: uuid.UUID
    batch_id: uuid.UUID
    rating: int
    body: str | None
    tenure: Tenure
    published_month: dt.date
    reply_body: str | None
    reply_month: dt.date | None
    my_reply_status: str | None
    my_reply_body: str | None
    my_reply_rejection_code: str | None


def _owner_review(row: Row[tuple[object, ...]]) -> OwnerReview:
    """Map a row of :data:`_REVIEWS` or :data:`_ONE`.

    :param row: The row
    :return: The review
    """
    return OwnerReview(
        id=cast("uuid.UUID", row.id),
        batch_id=cast("uuid.UUID", row.batch_id),
        rating=cast("int", row.rating),
        body=cast("str | None", row.body),
        tenure=cast("Tenure", row.tenure_bucket),
        published_month=cast("dt.date", row.published_month),
        reply_body=cast("str | None", row.reply_body),
        reply_month=cast("dt.date | None", row.reply_month),
        my_reply_status=cast("str | None", row.my_reply_status),
        my_reply_body=cast("str | None", row.my_reply_body),
        my_reply_rejection_code=cast("str | None", row.my_reply_rejection_code),
    )


def owner_reviews(
    session: Session, lens: TeacherLens
) -> tuple[list[OwnerBatchRating], list[OwnerReview]]:
    """Read the owner's published batches' ratings and their reviews.

    :param session: The session to read through
    :param lens: The teacher's lens
    :return: One rating per published batch listing, including those with no
        reviews, and the reviews, newest month first
    """
    listings = session.execute(_LISTINGS, {"owner_id": lens.owner_id}).all()
    published = [row for row in listings if row.status == "published"]
    ratings = {
        row.batch_id: row
        for row in session.execute(
            _RATINGS, {"batch_ids": [row.batch_id for row in published]}
        )
    }
    batches = []
    for listing in published:
        rating = ratings.get(listing.batch_id)
        batches.append(
            OwnerBatchRating(
                batch_id=listing.batch_id,
                batch_title=listing.public_title,
                review_count=None if rating is None else rating.review_count,
                average_tenths=None if rating is None else rating.average_tenths,
                distribution=None if rating is None else list(rating.distribution),
            )
        )
    reviews = session.execute(
        _REVIEWS, {"owned": [row.batch_id for row in listings]}
    ).all()
    return batches, [_owner_review(row) for row in reviews]


def _not_found() -> AuthorizationError:
    """Build the refusal for a review the teacher cannot reach.

    One value for another owner's review, a review below the threshold and
    an id never minted, so the answer is not an existence oracle.

    :return: A 404 authorization error
    """
    return AuthorizationError(
        code="REVIEW_NOT_FOUND", message_key="hub.review.not_found", status=404
    )


def _reachable(
    session: Session, lens: TeacherLens, review_id: uuid.UUID
) -> OwnerReview:
    """Read one review the teacher can reach, or refuse.

    :param session: The session
    :param lens: The teacher's lens
    :param review_id: The review
    :return: The review
    :raises AuthorizationError: ``REVIEW_NOT_FOUND``
    """
    row = session.execute(
        _ONE, {"review_id": review_id, "owner_id": lens.owner_id}
    ).one_or_none()
    if row is None:
        raise _not_found()
    return _owner_review(row)


def _normalised_reply(body: str) -> str:
    """Strip a reply, refusing an empty or overlong one.

    :param body: The reply as sent
    :return: The stripped reply
    :raises ValidationError: ``REQUEST_INVALID`` when it is blank or longer
        than :data:`MAX_REPLY` stripped
    """
    text = body.strip()
    if not 1 <= len(text) <= MAX_REPLY:
        raise ValidationError(
            code="REQUEST_INVALID",
            message_key="error.unexpected",
            details={"fields": "body"},
        )
    return text


def _refuse_suspended_owner(session: Session, lens: TeacherLens) -> None:
    """Refuse a reply from an owner whose listing is suspended [F6].

    :param session: The session
    :param lens: The teacher's lens
    :raises ConflictError: ``HUB_LISTING_SUSPENDED``
    """
    listing = session.get(OwnerListing, lens.owner_id)
    if listing is not None:
        refuse_suspended(listing)


def _evict_owner(session: Session, lens: TeacherLens, now: dt.datetime) -> None:
    """Enqueue the owner's pages for eviction, in the caller's transaction.

    :param session: The session
    :param lens: The teacher's lens
    :param now: The moment of the change
    :return: None
    """
    slug = session.execute(
        sa.select(OwnerListing.slug).where(OwnerListing.owner_id == lens.owner_id)
    ).scalar_one_or_none()
    if slug is not None:
        invalidation.enqueue(session, invalidation.owner_paths(slug), now)


def _create_reply(
    session: Session,
    lens: TeacherLens,
    review_id: uuid.UUID,
    text: str,
    now: dt.datetime,
) -> uuid.UUID | None:
    """Insert a first reply, if no other call's insert won the race.

    The review was read through the view, but its author may delete it
    before the insert's key check: that is the review going, not a fault,
    and it answers as any other unreachable review does [T5-b].

    :param session: The write's session
    :param lens: The teacher's lens; its account is recorded as the writer
    :param review_id: The review
    :param text: The normalised reply
    :param now: The moment of the write
    :return: The review id when this call inserted the reply, else None
    :raises AuthorizationError: ``REVIEW_NOT_FOUND`` when the review was
        deleted first; the session is rolled back
    """
    try:
        return session.execute(
            _CREATE,
            {
                "review_id": review_id,
                "body": text,
                "account_id": lens.account_id,
                "now": now,
            },
        ).scalar_one_or_none()
    except IntegrityError as error:
        diag = getattr(error.orig, "diag", None)
        if getattr(diag, "constraint_name", None) != _REPLY_REVIEW_FK:
            raise
        session.rollback()
        raise _not_found() from error


def put_reply(
    session: Session,
    lens: TeacherLens,
    review_id: uuid.UUID,
    body: str,
    now: dt.datetime,
) -> OwnerReview:
    """Write or replace the owner's reply to a review.

    Commits on success and rolls back on any failure.

    :param session: The session to write through
    :param lens: The teacher's lens; its account is recorded as the writer
    :param review_id: The review
    :param body: The reply; stripped, 1 to 1000 characters
    :param now: The moment of the write
    :return: The review with the reply as it now stands
    :raises AuthorizationError: ``HUB_REVIEWS_OFF`` while reviews are off,
        ``REVIEW_NOT_FOUND`` for a review the teacher cannot reach
    :raises ConflictError: ``HUB_LISTING_SUSPENDED``
    :raises ValidationError: ``REVIEW_CONTAINS_CONTACT``, or
        ``REQUEST_INVALID`` for a blank or overlong reply
    :raises CeilingBreach: ``HUB_WRITE_CEILING``, the owner's allowance
    """
    require_reviews_on()
    try:
        _refuse_suspended_owner(session, lens)
        _reachable(session, lens, review_id)
        text = _normalised_reply(body)
        refuse_contact("body", text)
        keys = {"review_id": review_id}
        current = session.execute(_LOCK_REPLY, keys).one_or_none()
        if current is None:
            created = _create_reply(session, lens, review_id, text, now)
            if created is None:
                # Another call's first reply won the race: this call
                # replaces it, and spends only if it changes it.
                current = session.execute(_LOCK_REPLY, keys).one_or_none()
                if current is None:
                    # The winner was deleted in between: the delete stands.
                    session.rollback()
                    return _reachable(session, lens, review_id)
        if current is not None:
            if current.body == text:
                session.rollback()
                return _reachable(session, lens, review_id)
            session.execute(
                _REPLACE,
                {**keys, "body": text, "account_id": lens.account_id, "now": now},
            )
            if current.status == "published":
                _evict_owner(session, lens, now)
        # Counted only now that the reply changes; a breach rolls the
        # write back with the count.
        CeilingChecker(session).consume_hub_listing_in_transaction(lens.owner_id, now)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return _reachable(session, lens, review_id)


def _reply_target_batch_owned(
    session: Session, lens: TeacherLens, review_id: uuid.UUID
) -> bool:
    """Say whether a review is in one of the owner's batches, whatever its state.

    **The one read of the** ``review`` **base table in this module**
    [T5-a]. Removing one's own words is never gated by publication, so a
    reply must be deletable while its review is held, below the threshold
    or on a hidden or suspended listing -- states in which the review has
    left the views. The statement reads only the review's ``id`` and
    ``batch_id``, never what anyone wrote, its status or its author; the
    source gate allowlists exactly this function and checks that.

    The review row is share-locked, so a concurrent author delete, which
    locks the review before its reports and its reply, is ordered before or
    after this one rather than deadlocking with it.

    :param session: The write's session
    :param lens: The teacher's lens
    :param review_id: The review
    :return: True when the review exists in a batch the owner lists
    """
    found = session.execute(
        sa.text(
            """
            SELECT r.id
            FROM review r
            JOIN batch_listing bl ON bl.batch_id = r.batch_id
            WHERE r.id = :review_id AND bl.owner_id = :owner_id
            FOR SHARE OF r
            """
        ),
        {"review_id": review_id, "owner_id": lens.owner_id},
    ).scalar_one_or_none()
    return found is not None


def delete_reply(
    session: Session, lens: TeacherLens, review_id: uuid.UUID, now: dt.datetime
) -> None:
    """Delete the owner's reply to a review, and every report on it.

    Works whatever the review's visibility [T5-a]: held, below the
    threshold, or on a hidden or suspended listing. Never switch-gated.
    Refuses nothing: a reply that is absent, already deleted, or on a
    review that is not the owner's is a quiet success that changes nothing,
    so the answer says nothing about another owner's review.

    :param session: The session to write through
    :param lens: The teacher's lens
    :param review_id: The review
    :param now: The moment of the delete
    :return: None
    """
    try:
        if not _reply_target_batch_owned(session, lens, review_id):
            session.rollback()
            return
        keys = {"review_id": review_id}
        # The review (above), then the reply, then its reports: the order
        # every report decision takes. The author's delete takes the review,
        # then the reports, then the reply by cascade; both hold the review
        # lock first, so they serialize there and cannot deadlock.
        current = session.execute(_LOCK_REPLY, keys).one_or_none()
        if current is not None:
            session.execute(_DELETE_REPORTS, keys)
            session.execute(_DELETE_REPLY, keys)
            if current.status == "published":
                _evict_owner(session, lens, now)
        session.commit()
    except Exception:
        session.rollback()
        raise
