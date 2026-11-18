"""The author's side of a review: read it, write it, edit it, delete it.

**Who may write** [spec §6, Call 7, T3-e]. A *first* review needs the lens
standing ``eligible``. The lens also admits members who are ``not_yet`` or
``closed`` and authors who are no longer members (``author_only``); those
may read and delete a review they wrote, and a member may edit theirs inside
the edit window, but none of them may create one.

**The edit window** runs :data:`EDIT_WINDOW` from the first submit, in
Bangladesh's calendar, and an edit does not extend it (Call 8). An edit
sends the review back to moderation: ``pending``, with every trace of the
last decision cleared, so an edited review is never shown on the strength of
an approval of different words. Editing a ``held`` review moves it to
``pending`` too; it does not escape the report that held it, because an
upheld report removes its target whatever the target's status [F9].

**Only a write that changes something is counted** (Call 9). An identical
rating and body is a no-op that returns the state and spends nothing. The
daily allowance is consumed by the non-committing consume, after the no-op
check and inside the write's own transaction [F5], so a refused or failed
write counts nothing.

**Two devices writing a first review at once make one review** (Review
Focus 1). The insert is ``ON CONFLICT DO NOTHING`` on the one-review-per-
author constraint; the call that loses the race continues as an edit of the
winner's row, and both succeed. The loser spends its allowance only if
it changes the winner's words: a double submit of the same review counts
once.

**Delete is total and never switch-gated**: :func:`delete` hands the review
to :func:`app.reviews.forget.forget`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final, Literal, cast

import sqlalchemy as sa
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from app.auth.ceilings import CeilingChecker
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.errors.codes import NOT_AVAILABLE
from app.hub.public import invalidation
from app.hub.public.settings import reviews_enabled
from app.local_time import bangladesh_today
from app.reviews import forget
from app.reviews.content import refuse_contact
from app.reviews.eligibility import Assessment, Tenure
from app.reviews.lens import ReviewerLens
from app.reviews.switch import require_reviews_on

__all__ = [
    "EDIT_WINDOW",
    "MAX_BODY",
    "MyReview",
    "MyReviewState",
    "ReviewStatus",
    "delete",
    "state",
    "write",
]

#: How long after the first submit an author may still edit.
EDIT_WINDOW: Final = dt.timedelta(days=30)

#: The longest body, counted after surrounding whitespace is stripped.
MAX_BODY: Final = 1000

#: Where a review is in moderation (Call 2).
ReviewStatus = Literal[
    "pending", "approved", "published", "rejected", "removed", "held"
]

#: The caller's review of the batch, with its reply's text only while the
#: reply is published.
_MINE: Final = sa.text(
    """
    SELECT r.rating, r.body, r.status, r.rejection_code, r.tenure_bucket,
           r.published_month, r.submitted_at,
           CASE WHEN p.status = 'published' THEN p.body END AS reply_body
    FROM review r
    LEFT JOIN review_reply p ON p.review_id = r.id
    WHERE r.batch_id = :batch_id AND r.author_account_id = :account_id
    """
)

#: The caller's review, locked for the rest of the write or delete.
_LOCK_MINE: Final = sa.text(
    """
    SELECT id, rating, body, status, submitted_at
    FROM review
    WHERE batch_id = :batch_id AND author_account_id = :account_id
    FOR UPDATE
    """
)

#: A first review; nothing when another call's insert won the race.
_CREATE: Final = sa.text(
    """
    INSERT INTO review (batch_id, author_account_id, enrollment_id,
                        author_role, rating, body, tenure_bucket, submitted_at)
    VALUES (:batch_id, :account_id, :enrollment_id, 'guardian', :rating,
            :body, CAST(:tenure AS hub_review_tenure), :now)
    ON CONFLICT (batch_id, author_account_id) DO NOTHING
    RETURNING id
    """
)

#: An edit: new words, back to moderation, the last decision forgotten.
_EDIT: Final = sa.text(
    """
    UPDATE review
    SET rating = :rating, body = :body, status = 'pending', edited_at = :now,
        approved_at = NULL, published_month = NULL, rejection_code = NULL,
        decided_at = NULL, decided_by_account_id = NULL
    WHERE id = :review_id
    """
)

#: The slug of the owner whose page shows the batch.
_OWNER_SLUG: Final = sa.text(
    """
    SELECT ol.slug
    FROM batch_listing bl
    JOIN owner_listing ol ON ol.owner_id = bl.owner_id
    WHERE bl.batch_id = :batch_id
    """
)


@dataclass(frozen=True, slots=True)
class MyReview:
    """The caller's own review, as its author may see it.

    :ivar rating: 1 to 5
    :ivar body: The text, or None when none was written
    :ivar status: Where it is in moderation
    :ivar rejection_code: Why it was rejected or removed
    :ivar tenure: The tenure bucket frozen at the first submit
    :ivar published_month: The first of the month it was published in
    :ivar reply_body: The owner's reply, only while the reply is published
    :ivar submitted_at: The first submit; the edit window runs from it.
        Never sent to a client: the wire carries ``edit_until`` instead
    """

    rating: int
    body: str | None
    status: ReviewStatus
    rejection_code: str | None
    tenure: Tenure
    published_month: dt.date | None
    reply_body: str | None
    submitted_at: dt.datetime


@dataclass(frozen=True, slots=True)
class MyReviewState:
    """Where the caller stands with one batch's review.

    :ivar assessment: The lens's assessment of the caller
    :ivar can_write: Whether a write now would be accepted on standing and
        window: the switch is on, and either there is no review and the
        standing is ``eligible``, or there is one, the standing is not
        ``author_only`` and today is on or before ``edit_until``
    :ivar edit_until: The last day an edit is accepted, or None without a
        review
    :ivar review: The caller's review, or None
    """

    assessment: Assessment
    can_write: bool
    edit_until: dt.date | None
    review: MyReview | None


def _edit_until(submitted_at: dt.datetime) -> dt.date:
    """Give the last day an edit is accepted.

    :param submitted_at: The first submit
    :return: The submit's date in Bangladesh plus the edit window
    """
    return bangladesh_today(submitted_at) + EDIT_WINDOW


def _can_write(
    assessment: Assessment, submitted_at: dt.datetime | None, today: dt.date
) -> bool:
    """Decide whether a write now would be accepted.

    :param assessment: The caller's standing
    :param submitted_at: The review's first submit, or None without one
    :param today: Bangladesh's date
    :return: True when :func:`write` would not refuse on standing or window
    """
    if not reviews_enabled():
        return False
    if submitted_at is None:
        return assessment.standing == "eligible"
    return assessment.standing != "author_only" and today <= _edit_until(submitted_at)


def _my_review(row: Row[tuple[object, ...]]) -> MyReview:
    """Map a row of :data:`_MINE`.

    :param row: The row
    :return: The review
    """
    return MyReview(
        rating=cast("int", row.rating),
        body=cast("str | None", row.body),
        status=cast("ReviewStatus", row.status),
        rejection_code=cast("str | None", row.rejection_code),
        tenure=cast("Tenure", row.tenure_bucket),
        published_month=cast("dt.date | None", row.published_month),
        reply_body=cast("str | None", row.reply_body),
        submitted_at=cast("dt.datetime", row.submitted_at),
    )


def state(session: Session, lens: ReviewerLens, today: dt.date) -> MyReviewState:
    """Read where the caller stands with the lens's batch.

    :param session: The session to read through
    :param lens: The caller's reviewer lens
    :param today: Bangladesh's date
    :return: The state
    """
    row = session.execute(
        _MINE, {"batch_id": lens.batch_id, "account_id": lens.account_id}
    ).one_or_none()
    review = None if row is None else _my_review(row)
    submitted_at = None if review is None else review.submitted_at
    return MyReviewState(
        assessment=lens.assessment,
        can_write=_can_write(lens.assessment, submitted_at, today),
        edit_until=None if submitted_at is None else _edit_until(submitted_at),
        review=review,
    )


def _normalised_body(body: str | None) -> str | None:
    """Strip a body, storing a blank one as none.

    :param body: The body as sent
    :return: The stripped body, or None when it is absent or blank
    :raises ValidationError: It is longer than :data:`MAX_BODY` stripped
    """
    if body is None:
        return None
    text = body.strip()
    if len(text) > MAX_BODY:
        raise ValidationError(
            code="REQUEST_INVALID",
            message_key="error.unexpected",
            details={"fields": "body"},
        )
    return text or None


def _require_rating(rating: int) -> None:
    """Refuse a rating outside one to five.

    :param rating: The rating as sent
    :raises ValidationError: It is not 1 to 5
    """
    if not 1 <= rating <= 5:
        raise ValidationError(
            code="REQUEST_INVALID",
            message_key="error.unexpected",
            details={"fields": "rating"},
        )


def _dated(assessment: Assessment) -> dict[str, str] | None:
    """Give a refusal's ``eligible_from`` detail, when tenure is unmet [F20].

    :param assessment: The caller's standing
    :return: The detail, or None when no date is known
    """
    if assessment.eligible_from is None:
        return None
    return {"eligible_from": assessment.eligible_from.isoformat()}


def _refuse_create(assessment: Assessment) -> None:
    """Refuse a first review unless the caller is eligible [T3-e].

    :param assessment: The caller's standing
    :raises ConflictError: ``REVIEW_NOT_YET_ELIGIBLE`` for a member who is
        not yet, or no longer, eligible
    :raises AuthorizationError: ``NOT_AVAILABLE`` for an author whose review
        was deleted after the lens was resolved
    """
    if assessment.standing == "eligible":
        return
    if assessment.standing == "closed":
        raise ConflictError(
            code="REVIEW_NOT_YET_ELIGIBLE", message_key="hub.review.window_closed"
        )
    if assessment.standing == "author_only":
        raise AuthorizationError(
            code=NOT_AVAILABLE, message_key="authz.lens.not_available"
        )
    if assessment.waiting_on == "attendance":
        raise ConflictError(
            code="REVIEW_NOT_YET_ELIGIBLE",
            message_key="hub.review.needs_attendance",
            details=_dated(assessment),
        )
    raise ConflictError(
        code="REVIEW_NOT_YET_ELIGIBLE",
        message_key="hub.review.not_yet_eligible",
        details=_dated(assessment),
    )


def _refuse_edit(
    assessment: Assessment, submitted_at: dt.datetime, today: dt.date
) -> None:
    """Refuse an edit by a former member or after the window.

    :param assessment: The caller's standing
    :param submitted_at: The review's first submit
    :param today: Bangladesh's date
    :raises ConflictError: ``REVIEW_EDIT_CLOSED``
    """
    if assessment.standing == "author_only" or today > _edit_until(submitted_at):
        raise ConflictError(
            code="REVIEW_EDIT_CLOSED", message_key="hub.review.edit_closed"
        )


def _edit(
    session: Session,
    current: Row[tuple[object, ...]],
    batch_id: uuid.UUID,
    *,
    rating: int,
    body: str | None,
    now: dt.datetime,
) -> None:
    """Replace a review's words and send it back to moderation.

    A review that was published leaves its page, so the owner's pages are
    enqueued for eviction in this transaction.

    :param session: The write's session
    :param current: The locked row of :data:`_LOCK_MINE`
    :param batch_id: The reviewed batch
    :param rating: The new rating
    :param body: The new, normalised body
    :param now: The moment of the edit
    :return: None
    """
    session.execute(
        _EDIT,
        {"rating": rating, "body": body, "now": now, "review_id": current.id},
    )
    if current.status != "published":
        return
    slug = session.execute(_OWNER_SLUG, {"batch_id": batch_id}).scalar_one_or_none()
    if slug is not None:
        invalidation.enqueue(session, invalidation.owner_paths(slug), now)


def _unchanged(current: Row[tuple[object, ...]], rating: int, body: str | None) -> bool:
    """Say whether a write would leave a review as it is.

    :param current: The locked row of :data:`_LOCK_MINE`
    :param rating: The rating sent
    :param body: The normalised body sent
    :return: True when both are what is stored
    """
    return bool(current.rating == rating and current.body == body)


def _spend(session: Session, lens: ReviewerLens, now: dt.datetime) -> None:
    """Count one changing write against the author, without committing [F5].

    Called only once a create or an edit is certain, so an identical
    resubmit -- a retry, or a double submit that lost the insert race --
    spends nothing.

    :param session: The write's session
    :param lens: The caller's reviewer lens
    :param now: The moment of the write
    :return: None
    :raises CeilingBreach: ``HUB_REVIEW_CEILING``
    """
    CeilingChecker(session).consume_hub_review_in_transaction(lens.account_id, now)


def write(
    session: Session,
    lens: ReviewerLens,
    *,
    rating: int,
    body: str | None,
    now: dt.datetime,
) -> MyReviewState:
    """Write the caller's review of the lens's batch, or edit it.

    Commits on success and rolls back on any failure.

    :param session: The session to write through
    :param lens: The caller's reviewer lens
    :param rating: 1 to 5
    :param body: The text, or None; stripped, and stored as None when blank
    :param now: The moment of the write
    :return: The state after the write
    :raises AuthorizationError: ``HUB_REVIEWS_OFF`` while reviews are off
    :raises ValidationError: ``REVIEW_CONTAINS_CONTACT``, or
        ``REQUEST_INVALID`` for a rating or body out of range
    :raises ConflictError: ``REVIEW_NOT_YET_ELIGIBLE`` for a first review
        by a member who is not eligible, ``REVIEW_EDIT_CLOSED`` for an edit
        by a former member or after the window
    :raises CeilingBreach: ``HUB_REVIEW_CEILING``, the sixth changing write
        today
    """
    require_reviews_on()
    _require_rating(rating)
    text = _normalised_body(body)
    refuse_contact("body", text)
    today = bangladesh_today(now)
    keys = {"batch_id": lens.batch_id, "account_id": lens.account_id}
    try:
        current = session.execute(_LOCK_MINE, keys).one_or_none()
        if current is None:
            _refuse_create(lens.assessment)
            created = session.execute(
                _CREATE,
                {
                    **keys,
                    "enrollment_id": lens.assessment.enrollment_id,
                    "rating": rating,
                    "body": text,
                    "tenure": lens.assessment.tenure,
                    "now": now,
                },
            ).scalar_one_or_none()
            if created is not None:
                # Counted only now that a review was written; a breach
                # rolls the insert back with the count.
                _spend(session, lens, now)
                session.commit()
                return state(session, lens, today)
            # Another call's first review won the race: this call is an
            # edit of that one, and spends only if it changes it.
            current = session.execute(_LOCK_MINE, keys).one_or_none()
            if current is None:
                # The winner was deleted in between: the delete stands.
                session.rollback()
                return state(session, lens, today)
        _refuse_edit(lens.assessment, current.submitted_at, today)
        if _unchanged(current, rating, text):
            session.rollback()
            return state(session, lens, today)
        _spend(session, lens, now)
        _edit(session, current, lens.batch_id, rating=rating, body=text, now=now)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return state(session, lens, today)


def delete(session: Session, lens: ReviewerLens, now: dt.datetime) -> None:
    """Delete the caller's review of the lens's batch, totally.

    Refuses nothing when there is no review: deleting is idempotent. Never
    switch-gated.

    :param session: The session to write through
    :param lens: The caller's reviewer lens
    :param now: The moment of the delete
    :return: None
    """
    try:
        found = session.execute(
            _LOCK_MINE, {"batch_id": lens.batch_id, "account_id": lens.account_id}
        ).one_or_none()
        forget.forget(session, [] if found is None else [found.id], now)
        session.commit()
    except Exception:
        session.rollback()
        raise
