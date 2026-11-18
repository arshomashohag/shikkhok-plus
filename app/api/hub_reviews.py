"""Guardian reviews: the reviewer's routes and the teacher's [H4].

**Who reaches what.** The three ``/v1/hub/batches/{batch_id}/my-review``
routes resolve a :class:`~app.reviews.lens.ReviewerLens` for the batch in
the path; the three ``/v1/hub/reviews`` routes resolve the owner's
:class:`~app.authz.lenses.TeacherLens`. The reviewable list is the one
lens-exempt route: it reports which reviewer lenses exist, from the
authenticated account alone, on ``/v1/invitations``'s reasoning.

**The switch runs first** (global constraints, the off table). Each gated
route lists :func:`~app.reviews.switch.require_reviews_on` in its
decorator, which FastAPI resolves before any parameter dependency, so an
off switch answers ``HUB_REVIEWS_OFF`` to a member and a stranger alike and
never ``NOT_AVAILABLE``. The switch gates no deletion, and not the author's
own read: with reviews off, the read says nothing can be written and the
list keeps only what the caller already reviewed.

**Nothing joinable leaves here** [T3-e, T4-b]. The lens's seat, its
assessment and the review's submit time stay on the server; months go out
as ``YYYY-MM`` and the edit window as its last day. The average goes out
rendered [F13].

**Transactions.** Each write service commits on success and rolls back on
any exception, taxonomy or not, and the request scope rolls back every 4xx
and 5xx besides; ``test_write_routes_roll_back_on_an_unexpected_error``
holds both write routes to it.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Final, cast

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import authenticated_account, get_session, reviewer_lens, teacher_lens
from app.authz.lenses import TeacherLens
from app.hub.public.settings import reviews_enabled
from app.local_time import bangladesh_today
from app.reviews import authoring, eligibility, owner
from app.reviews.authoring import MyReview, MyReviewState
from app.reviews.eligibility import Assessment
from app.reviews.lens import ReviewerLens
from app.reviews.owner import OwnerBatchRating, OwnerReview
from app.reviews.switch import require_reviews_on
from app.schemas.errors import ErrorEnvelope
from app.schemas.reviews import (
    MyReviewBody,
    MyReviewResponse,
    OwnerBatchRatingWire,
    OwnerReviewsResponse,
    OwnerReviewWire,
    ReplyStatus,
    ReplyWrite,
    ReviewableBatch,
    ReviewableState,
    ReviewWrite,
)

__all__ = ["router"]

router = APIRouter(prefix="/v1/hub", tags=["hub"])

#: The path of one batch's review by the caller.
_MY_REVIEW: Final = "/batches/{batch_id}/my-review"

#: The path of the owner's reply to one review.
_REPLY: Final = "/reviews/{review_id}/reply"

_Responses = dict[int | str, dict[str, object]]


def _envelope(description: str) -> dict[str, object]:
    """Document one error status as the error envelope.

    :param description: What the status means here, naming its codes
    :return: The OpenAPI response entry
    """
    return {"model": ErrorEnvelope, "description": description}


_UNAUTHENTICATED: Final = _envelope("No credential, or an expired one.")

_NOT_A_MEMBER: Final = _envelope(
    "NOT_AVAILABLE: not a member of this batch nor the author of a review "
    "of it; a batch that does not exist answers the same."
)

_NO_TEACHER: Final = _envelope(
    "NO_TEACHER_LENS: the caller runs no workspace, or not the one named."
)

_OFF: Final = "HUB_REVIEWS_OFF: reviews are switched off."

#: The reviewable list: authentication only.
_LIST_ERRORS: Final[_Responses] = {401: _UNAUTHENTICATED}

#: The author's read and delete: the lens alone.
_MINE_ERRORS: Final[_Responses] = {401: _UNAUTHENTICATED, 403: _NOT_A_MEMBER}

#: The author's write.
_WRITE_ERRORS: Final[_Responses] = {
    400: _envelope(
        "REVIEW_CONTAINS_CONTACT: the words carry a phone number or a web "
        "address; details name the field."
    ),
    401: _UNAUTHENTICATED,
    403: _NOT_A_MEMBER,
    404: _envelope(_OFF),
    409: _envelope(
        "REVIEW_NOT_YET_ELIGIBLE: a first review by a member not yet, or no "
        "longer, eligible (hub.review.not_yet_eligible with eligible_from, "
        "hub.review.needs_attendance, hub.review.window_closed). "
        "REVIEW_EDIT_CLOSED: the edit window has passed. "
        "HUB_REVIEW_CEILING: today's changing writes are spent."
    ),
}

#: The teacher's read.
_OWNER_READ_ERRORS: Final[_Responses] = {
    401: _UNAUTHENTICATED,
    403: _NO_TEACHER,
    404: _envelope(_OFF),
}

#: The teacher's reply.
_REPLY_ERRORS: Final[_Responses] = {
    400: _envelope(
        "REVIEW_CONTAINS_CONTACT: the reply carries a phone number or a web "
        "address; details name the field."
    ),
    401: _UNAUTHENTICATED,
    403: _NO_TEACHER,
    404: _envelope(
        f"{_OFF} REVIEW_NOT_FOUND: no published review of yours by that id; "
        "another owner's review answers the same."
    ),
    409: _envelope(
        "HUB_LISTING_SUSPENDED: your listing is suspended. "
        "HUB_WRITE_CEILING: today's listing edits are spent."
    ),
}

#: The teacher's reply delete: the lens alone.
_REPLY_DELETE_ERRORS: Final[_Responses] = {401: _UNAUTHENTICATED, 403: _NO_TEACHER}


def _month(month: dt.date | None) -> str | None:
    """Render a stored month as ``YYYY-MM``.

    :param month: The first of a month, or None
    :return: The month, or None
    """
    return None if month is None else f"{month:%Y-%m}"


def _label(tenths: int | None) -> str | None:
    """Render an average in tenths with one decimal place [F13].

    :param tenths: The average times ten (43 is 4.3), or None
    :return: ``"4.3"``, or None
    """
    return None if tenths is None else f"{tenths // 10}.{tenths % 10}"


def _reviewable(assessment: Assessment) -> ReviewableBatch:
    """Render one row of the reviewable list.

    :param assessment: The caller's standing with the batch
    :return: The row; ``reviewed`` once the caller wrote a review
    """
    state: ReviewableState
    if assessment.review_id is not None:
        state = "reviewed"
    elif assessment.standing == "eligible":
        state = "eligible"
    else:
        state = "not_yet"
    return ReviewableBatch(
        batch_id=assessment.batch_id,
        batch_title=assessment.batch_title,
        owner_public_name=assessment.owner_public_name,
        state=state,
        eligible_from=assessment.eligible_from if state == "not_yet" else None,
    )


def _my_review(review: MyReview) -> MyReviewBody:
    """Render the author's review, leaving its submit time behind [T4-b].

    :param review: The review
    :return: The wire body
    """
    return MyReviewBody(
        rating=review.rating,
        body=review.body,
        status=review.status,
        rejection_code=review.rejection_code,
        tenure=review.tenure,
        published_month=_month(review.published_month),
        reply_body=review.reply_body,
    )


def _state(state: MyReviewState) -> MyReviewResponse:
    """Render the author's state, leaving the seat and assessment behind.

    The waiting reason and the day are sent for a ``not_yet`` standing
    only: a closed window has no day to come [T3-b].

    :param state: The state
    :return: The wire response
    """
    assessment = state.assessment
    waiting = assessment.standing == "not_yet"
    return MyReviewResponse(
        standing=assessment.standing,
        waiting_on=assessment.waiting_on if waiting else None,
        eligible_from=assessment.eligible_from if waiting else None,
        can_write=state.can_write,
        edit_until=state.edit_until,
        review=None if state.review is None else _my_review(state.review),
    )


def _rating(rating: OwnerBatchRating) -> OwnerBatchRatingWire:
    """Render one batch's rating, every figure None below the threshold.

    :param rating: The rating
    :return: The wire row
    """
    return OwnerBatchRatingWire(
        batch_id=rating.batch_id,
        batch_title=rating.batch_title,
        review_count=rating.review_count,
        average_tenths=rating.average_tenths,
        average_label=_label(rating.average_tenths),
        distribution=rating.distribution,
    )


def _owner_review(review: OwnerReview) -> OwnerReviewWire:
    """Render one review for its batch's owner.

    :param review: The review
    :return: The wire row
    """
    return OwnerReviewWire(
        id=review.id,
        batch_id=review.batch_id,
        rating=review.rating,
        body=review.body,
        tenure=review.tenure,
        published_month=f"{review.published_month:%Y-%m}",
        reply_body=review.reply_body,
        reply_month=_month(review.reply_month),
        # The column is the reply-status enum; the service types it loosely.
        my_reply_status=cast("ReplyStatus | None", review.my_reply_status),
        my_reply_body=review.my_reply_body,
        my_reply_rejection_code=review.my_reply_rejection_code,
    )


def _now() -> dt.datetime:
    """Give the present.

    :return: Now, in UTC
    """
    return dt.datetime.now(tz=dt.UTC)


@router.get("/reviewable", response_model=list[ReviewableBatch], responses=_LIST_ERRORS)
def list_reviewable(
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> list[ReviewableBatch]:
    """List the batches the caller may review, is waiting to, or reviewed.

    Not switch-gated: while reviews are off it lists only the batches the
    caller already reviewed, so a review can still be found and deleted.

    :param session: The request-scoped session
    :param account_id: The authenticated account
    :return: The rows, by batch title
    """
    rows = eligibility.reviewable(
        session, account_id, bangladesh_today(), include_open=reviews_enabled()
    )
    return [_reviewable(row) for row in rows]


@router.get(_MY_REVIEW, response_model=MyReviewResponse, responses=_MINE_ERRORS)
def get_my_review(
    lens: Annotated[ReviewerLens, Depends(reviewer_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> MyReviewResponse:
    """Read where the caller stands with this batch's review.

    Not switch-gated: while reviews are off ``can_write`` is false.

    :param lens: The caller's reviewer lens for the batch
    :param session: The request-scoped session
    :return: The state
    """
    return _state(authoring.state(session, lens, bangladesh_today()))


@router.put(
    _MY_REVIEW,
    response_model=MyReviewResponse,
    responses=_WRITE_ERRORS,
    dependencies=[Depends(require_reviews_on)],
)
def put_my_review(
    body: ReviewWrite,
    lens: Annotated[ReviewerLens, Depends(reviewer_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> MyReviewResponse:
    """Write the caller's review of this batch, or edit it.

    A first review needs an eligible standing; an edit needs the window
    open. An edit goes back to moderation.

    :param body: The rating and the optional words
    :param lens: The caller's reviewer lens for the batch
    :param session: The request-scoped session
    :return: The state after the write
    """
    state = authoring.write(
        session, lens, rating=body.rating, body=body.body, now=_now()
    )
    return _state(state)


@router.delete(
    _MY_REVIEW,
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=_MINE_ERRORS,
)
def delete_my_review(
    lens: Annotated[ReviewerLens, Depends(reviewer_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Delete the caller's review of this batch, with its reply and reports.

    Never switch-gated, and quiet when there is nothing to delete.

    :param lens: The caller's reviewer lens for the batch
    :param session: The request-scoped session
    :return: An empty 204
    """
    authoring.delete(session, lens, _now())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/reviews",
    response_model=OwnerReviewsResponse,
    responses=_OWNER_READ_ERRORS,
    dependencies=[Depends(require_reviews_on)],
)
def get_owner_reviews(
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> OwnerReviewsResponse:
    """Read the owner's batches' ratings and their published reviews.

    Exactly what the public sees of them: below three published reviews a
    batch shows no review and no figure [T2-a].

    :param lens: The owner's lens
    :param session: The request-scoped session
    :return: Every published batch's rating, and the reviews
    """
    batches, reviews = owner.owner_reviews(session, lens)
    return OwnerReviewsResponse(
        batches=[_rating(row) for row in batches],
        reviews=[_owner_review(row) for row in reviews],
    )


@router.put(
    _REPLY,
    response_model=OwnerReviewWire,
    responses=_REPLY_ERRORS,
    dependencies=[Depends(require_reviews_on)],
)
def put_reply(
    review_id: uuid.UUID,
    body: ReplyWrite,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> OwnerReviewWire:
    """Write or replace the owner's reply to a review; it is pre-moderated.

    :param review_id: The review
    :param body: The reply
    :param lens: The owner's lens
    :param session: The request-scoped session
    :return: The review with the reply as it now stands
    """
    review = owner.put_reply(session, lens, review_id, body.body, _now())
    return _owner_review(review)


@router.delete(
    _REPLY,
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=_REPLY_DELETE_ERRORS,
)
def delete_reply(
    review_id: uuid.UUID,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Delete the owner's reply to a review, and every report on it.

    Never switch-gated, never refused for a suspension or the review's
    visibility, and quiet when there is nothing of the owner's to delete.

    :param review_id: The review
    :param lens: The owner's lens
    :param session: The request-scoped session
    :return: An empty 204
    """
    owner.delete_reply(session, lens, review_id, _now())
    return Response(status_code=status.HTTP_204_NO_CONTENT)
