"""The ReviewerLens: granted to a member or an author, refused identically.

Written before the dependency existed [spec §6]. The refusal must not tell a
caller whether a batch exists: a non-member of a real batch and a caller
naming a batch that was never created get the same status and the same
bytes.
"""

from __future__ import annotations

import datetime as dt
import typing
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.api.deps import reviewer_lens
from app.authz.lenses import Lens
from app.errors import AuthorizationError, to_response
from app.local_time import bangladesh_today
from app.reviews.lens import ReviewerLens
from tests.reviews.support import (
    account,
    add_review,
    attend,
    guardian_seat,
    hold_classes,
    public_batch,
)


def _member(session: Session, batch_id: uuid.UUID, guardian: uuid.UUID) -> uuid.UUID:
    """Seat an eligible child for a guardian, against the real clock.

    :param session: An arranging session
    :param batch_id: The batch
    :param guardian: The guardian
    :return: The enrollment id
    """
    seat = guardian_seat(
        session,
        batch_id,
        guardian,
        joined_on=bangladesh_today() - dt.timedelta(days=100),
    )
    attend(session, hold_classes(session, batch_id, 4), seat)
    return seat


def test_reviewer_lens_refusal_is_identical_for_nonmember_and_missing_batch(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    _member(owner_session, batch.batch_id, account(owner_session))
    stranger = account(owner_session)

    with pytest.raises(AuthorizationError) as nonmember:
        reviewer_lens(batch.batch_id, restricted_session, stranger)
    with pytest.raises(AuthorizationError) as missing:
        reviewer_lens(uuid.uuid4(), restricted_session, stranger)

    first, second = to_response(nonmember.value), to_response(missing.value)
    assert first.status_code == second.status_code == 403
    assert first.body == second.body
    assert nonmember.value.code == "NOT_AVAILABLE"
    assert nonmember.value.message_key == "authz.lens.not_available"


def test_reviewer_lens_carries_the_assessment_for_a_member(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    seat = _member(owner_session, batch.batch_id, guardian)

    lens = reviewer_lens(batch.batch_id, restricted_session, guardian)

    assert isinstance(lens, ReviewerLens)
    assert lens.account_id == guardian
    assert lens.batch_id == batch.batch_id
    assert lens.assessment.standing == "eligible"
    assert lens.assessment.enrollment_id == seat


def test_reviewer_lens_grants_an_author_who_lost_membership(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    seat = _member(owner_session, batch.batch_id, guardian)
    review = add_review(owner_session, batch.batch_id, guardian, enrollment_id=seat)
    owner_session.execute(
        sa.text("UPDATE enrollment SET guardian_decision = 'declined' WHERE id = :e"),
        {"e": seat},
    )
    owner_session.commit()

    lens = reviewer_lens(batch.batch_id, restricted_session, guardian)

    assert lens.assessment.standing == "author_only"
    assert lens.assessment.review_id == review


def test_reviewer_lens_is_not_memoised(
    owner_session: Session, restricted_session: Session
) -> None:
    """A seat declined between two requests withdraws the lens at once."""
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    seat = _member(owner_session, batch.batch_id, guardian)
    reviewer_lens(batch.batch_id, restricted_session, guardian)
    restricted_session.rollback()

    owner_session.execute(
        sa.text("UPDATE enrollment SET guardian_decision = 'declined' WHERE id = :e"),
        {"e": seat},
    )
    owner_session.commit()

    with pytest.raises(AuthorizationError):
        reviewer_lens(batch.batch_id, restricted_session, guardian)


def test_reviewer_lens_is_discoverable_by_the_route_gate() -> None:
    """The gate matches a dependency's return annotation on ``Lens``."""
    returned = typing.get_type_hints(reviewer_lens)["return"]

    assert returned is ReviewerLens
    assert issubclass(ReviewerLens, Lens)


def test_reviewer_lens_refuses_the_batch_owner_as_a_stranger(
    owner_session: Session, restricted_session: Session
) -> None:
    """T3-c: an owner seating their own child learns nothing from the refusal."""
    batch = public_batch(owner_session)
    _member(owner_session, batch.batch_id, batch.teacher_account_id)
    stranger = account(owner_session)

    with pytest.raises(AuthorizationError) as owner:
        reviewer_lens(batch.batch_id, restricted_session, batch.teacher_account_id)
    with pytest.raises(AuthorizationError) as other:
        reviewer_lens(batch.batch_id, restricted_session, stranger)

    assert to_response(owner.value).status_code == 403
    assert to_response(owner.value).body == to_response(other.value).body
