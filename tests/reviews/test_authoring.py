"""The author's lifecycle: write, edit inside the window, and the daily ceiling.

The world is arranged through the table-owner session; every call under test
runs through the restricted application role, with the lens resolved by the
real dependency against the real clock.
"""

from __future__ import annotations

import datetime as dt
import threading
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import reviewer_lens
from app.auth.ceilings import HUB_REVIEW_ACCOUNT_DAILY, CeilingBreach
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.hub.public.invalidation import owner_paths
from app.hub.public.settings import HUB_REVIEWS_ENV
from app.local_time import bangladesh_today
from app.reviews import authoring
from app.reviews.lens import ReviewerLens
from tests.reviews.support import (
    PublicBatch,
    account,
    add_review,
    attend,
    guardian_seat,
    hold_classes,
    public_batch,
)

pytestmark = pytest.mark.usefixtures("reviews_on")


def _today() -> dt.date:
    """Give Bangladesh's date by the real clock.

    :return: Today in Bangladesh
    """
    return bangladesh_today()


def _member(
    session: Session,
    batch_id: uuid.UUID,
    guardian: uuid.UUID,
    *,
    joined_days_ago: int = 100,
    attended: int = 4,
    inactive_days_ago: int | None = None,
) -> uuid.UUID:
    """Seat a guardian's child and record attended classes.

    :param session: An arranging session
    :param batch_id: The batch
    :param guardian: The guardian
    :param joined_days_ago: How long ago the child joined
    :param attended: Classes attended
    :param inactive_days_ago: How long ago the seat stopped, if it did
    :return: The enrollment id
    """
    seat = guardian_seat(
        session,
        batch_id,
        guardian,
        joined_on=_today() - dt.timedelta(days=joined_days_ago),
        inactive_from=(
            None
            if inactive_days_ago is None
            else _today() - dt.timedelta(days=inactive_days_ago)
        ),
    )
    attend(session, hold_classes(session, batch_id, attended), seat)
    return seat


def _lens(session: Session, batch_id: uuid.UUID, guardian: uuid.UUID) -> ReviewerLens:
    """Resolve the lens as the route would.

    :param session: The restricted session
    :param batch_id: The batch
    :param guardian: The caller
    :return: The lens
    """
    lens = reviewer_lens(batch_id, session, guardian)
    session.rollback()
    return lens


def _review(session: Session, batch_id: uuid.UUID, author: uuid.UUID) -> Any:
    """Read the stored review, every column.

    :param session: An arranging session
    :param batch_id: The batch
    :param author: The author
    :return: The row, or None
    """
    session.rollback()
    return session.execute(
        sa.text("SELECT * FROM review WHERE batch_id = :b AND author_account_id = :a"),
        {"b": batch_id, "a": author},
    ).one_or_none()


def _consumed(session: Session, author: uuid.UUID) -> int:
    """Count today's review writes against an account.

    :param session: An arranging session
    :param author: The account
    :return: The counter's value, 0 when no row exists
    """
    session.rollback()
    value = session.execute(
        sa.text(
            "SELECT coalesce(sum(count), 0) FROM rate_limit_counter "
            "WHERE scope_kind = 'hub_review_day' AND scope_value = :a"
        ),
        {"a": str(author)},
    ).scalar_one()
    return int(value)


def _invalidated(session: Session) -> set[str]:
    """List the paths in the invalidation outbox.

    :param session: An arranging session
    :return: The paths
    """
    session.rollback()
    return set(session.scalars(sa.text("SELECT path FROM cdn_invalidation")))


def _owner_slug(session: Session, batch: PublicBatch) -> str:
    """Read the owner listing's slug.

    :param session: An arranging session
    :param batch: The batch
    :return: The slug
    """
    return str(
        session.execute(
            sa.text("SELECT slug FROM owner_listing WHERE owner_id = :o"),
            {"o": batch.owner_id},
        ).scalar_one()
    )


def _now() -> dt.datetime:
    """Give the present.

    :return: Now, in UTC
    """
    return dt.datetime.now(tz=dt.UTC)


def test_first_write_creates_a_pending_review(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian)
    now = _now()

    state = authoring.write(
        restricted_session,
        _lens(restricted_session, batch.batch_id, guardian),
        rating=5,
        body="  Clear teaching.  ",
        now=now,
    )

    stored = _review(owner_session, batch.batch_id, guardian)
    assert stored.status == "pending"
    assert stored.rating == 5
    assert stored.body == "Clear teaching."
    assert stored.author_role == "guardian"
    assert stored.submitted_at == now
    assert stored.edited_at is None
    assert state.review is not None
    assert state.review.status == "pending"
    assert state.review.body == "Clear teaching."
    assert state.can_write is True
    assert state.edit_until == bangladesh_today(now) + dt.timedelta(days=30)
    assert _consumed(owner_session, guardian) == 1


@pytest.mark.parametrize(
    ("seat", "message_key", "dated"),
    [
        ({"joined_days_ago": 10}, "hub.review.not_yet_eligible", True),
        ({"attended": 3}, "hub.review.needs_attendance", False),
        ({"joined_days_ago": 10, "attended": 3}, "hub.review.needs_attendance", True),
        ({"inactive_days_ago": 181}, "hub.review.window_closed", False),
    ],
    ids=["tenure", "attendance", "tenure-and-attendance", "closed"],
)
def test_create_requires_eligible(
    owner_session: Session,
    restricted_session: Session,
    seat: dict[str, int],
    message_key: str,
    dated: bool,
) -> None:
    """T3-e: the lens admits not_yet and closed members; a first write does not."""
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian, **seat)
    lens = _lens(restricted_session, batch.batch_id, guardian)
    assert lens.assessment.standing != "eligible"

    with pytest.raises(ConflictError) as refused:
        authoring.write(restricted_session, lens, rating=4, body=None, now=_now())

    assert refused.value.code == "REVIEW_NOT_YET_ELIGIBLE"
    assert refused.value.status == 409
    assert refused.value.message_key == message_key
    if not dated:
        assert refused.value.details is None
    else:
        joined = _today() - dt.timedelta(days=seat.get("joined_days_ago", 100))
        assert refused.value.details == {
            "eligible_from": (joined + dt.timedelta(days=30)).isoformat()
        }
    assert _review(owner_session, batch.batch_id, guardian) is None
    assert _consumed(owner_session, guardian) == 0


def test_create_freezes_tenure_and_evidence_enrollment(
    owner_session: Session, restricted_session: Session
) -> None:
    """Review Focus 1: siblings write one review, evidenced by the eligible seat."""
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian, joined_days_ago=10)
    eligible = _member(owner_session, batch.batch_id, guardian, joined_days_ago=200)

    authoring.write(
        restricted_session,
        _lens(restricted_session, batch.batch_id, guardian),
        rating=4,
        body=None,
        now=_now(),
    )
    created = _review(owner_session, batch.batch_id, guardian)
    assert created.enrollment_id == eligible
    assert created.tenure_bucket == "6_12m"

    # Two years on the evidencing seat would be ``gt_1y`` at a first submit.
    owner_session.execute(
        sa.text("UPDATE enrollment SET joined_on = :j WHERE id = :e"),
        {"j": _today() - dt.timedelta(days=800), "e": eligible},
    )
    owner_session.commit()
    authoring.write(
        restricted_session,
        _lens(restricted_session, batch.batch_id, guardian),
        rating=2,
        body=None,
        now=_now(),
    )

    edited = _review(owner_session, batch.batch_id, guardian)
    assert edited.id == created.id
    assert edited.rating == 2
    assert edited.tenure_bucket == "6_12m"
    assert edited.enrollment_id == eligible


def _published_trio(owner_session: Session, batch: PublicBatch) -> None:
    """Publish three other guardians' reviews, so the batch meets the threshold.

    :param owner_session: An arranging session
    :param batch: The batch
    :return: None
    """
    for _ in range(3):
        review = add_review(owner_session, batch.batch_id, account(owner_session))
        _set_status(owner_session, review, "published")


def _set_status(session: Session, review_id: uuid.UUID, status: str) -> None:
    """Move a stored review to a status, with the columns that status needs.

    :param session: An arranging session
    :param review_id: The review
    :param status: ``pending``, ``approved``, ``published``, ``held``,
        ``rejected`` or ``removed``
    :return: None
    """
    shown = status in ("published", "held")
    session.execute(
        sa.text(
            "UPDATE review SET status = CAST(:s AS hub_review_status), "
            "published_month = :m, approved_at = :a, rejection_code = :c, "
            "decided_at = :d WHERE id = :r"
        ),
        {
            "s": status,
            "m": _today().replace(day=1) if shown else None,
            "a": _now() if status == "approved" else None,
            "c": "off_topic" if status in ("rejected", "removed") else None,
            "d": None if status == "pending" else _now(),
            "r": review_id,
        },
    )
    session.commit()


@pytest.mark.parametrize(
    ("status", "invalidates"),
    [
        ("published", True),
        ("approved", False),
        ("held", False),
        ("rejected", False),
        ("pending", False),
    ],
)
def test_edit_returns_published_review_to_pending_and_invalidates(
    owner_session: Session,
    restricted_session: Session,
    status: str,
    invalidates: bool,
) -> None:
    batch = public_batch(owner_session)
    _published_trio(owner_session, batch)
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian)
    authoring.write(
        restricted_session,
        _lens(restricted_session, batch.batch_id, guardian),
        rating=5,
        body="Good",
        now=_now(),
    )
    review_id = _review(owner_session, batch.batch_id, guardian).id
    _set_status(owner_session, review_id, status)
    owner_session.execute(sa.text("DELETE FROM cdn_invalidation"))
    owner_session.commit()
    edited_at = _now()

    state = authoring.write(
        restricted_session,
        _lens(restricted_session, batch.batch_id, guardian),
        rating=3,
        body="Good, but slow",
        now=edited_at,
    )

    edited = _review(owner_session, batch.batch_id, guardian)
    assert edited.status == "pending"
    assert edited.rating == 3
    assert edited.body == "Good, but slow"
    assert edited.edited_at == edited_at
    assert edited.approved_at is None
    assert edited.published_month is None
    assert edited.rejection_code is None
    assert edited.decided_at is None
    assert edited.decided_by_account_id is None
    assert state.review is not None
    assert state.review.status == "pending"
    paths = _invalidated(owner_session)
    if invalidates:
        assert set(owner_paths(_owner_slug(owner_session, batch))) <= paths
    else:
        assert paths == set()


@pytest.mark.parametrize(("age", "allowed"), [(30, True), (31, False)])
def test_edit_after_30_days_closed(
    owner_session: Session, restricted_session: Session, age: int, allowed: bool
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian)
    now = _now()
    authoring.write(
        restricted_session,
        _lens(restricted_session, batch.batch_id, guardian),
        rating=5,
        body=None,
        now=now - dt.timedelta(days=age),
    )
    lens = _lens(restricted_session, batch.batch_id, guardian)

    before = authoring.state(restricted_session, lens, bangladesh_today(now))
    assert before.edit_until == bangladesh_today(now) + dt.timedelta(days=30 - age)
    assert before.can_write is allowed

    if allowed:
        authoring.write(restricted_session, lens, rating=1, body=None, now=now)
        assert _review(owner_session, batch.batch_id, guardian).rating == 1
    else:
        with pytest.raises(ConflictError) as refused:
            authoring.write(restricted_session, lens, rating=1, body=None, now=now)
        assert refused.value.code == "REVIEW_EDIT_CLOSED"
        assert refused.value.message_key == "hub.review.edit_closed"
        assert _review(owner_session, batch.batch_id, guardian).rating == 5


def test_a_member_no_longer_eligible_may_still_edit_inside_the_window(
    owner_session: Session, restricted_session: Session
) -> None:
    """Call 7: an edit needs membership plus the window, not full eligibility."""
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    seat = _member(owner_session, batch.batch_id, guardian)
    authoring.write(
        restricted_session,
        _lens(restricted_session, batch.batch_id, guardian),
        rating=5,
        body=None,
        now=_now(),
    )
    owner_session.execute(
        sa.text("UPDATE enrollment SET inactive_from = :i WHERE id = :e"),
        {"i": _today() - dt.timedelta(days=200), "e": seat},
    )
    owner_session.commit()
    lens = _lens(restricted_session, batch.batch_id, guardian)
    assert lens.assessment.standing == "closed"

    state = authoring.write(restricted_session, lens, rating=2, body=None, now=_now())

    assert state.can_write is True
    assert _review(owner_session, batch.batch_id, guardian).rating == 2


def test_author_only_cannot_edit_but_can_read_and_delete(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    seat = _member(owner_session, batch.batch_id, guardian)
    authoring.write(
        restricted_session,
        _lens(restricted_session, batch.batch_id, guardian),
        rating=5,
        body="Kind",
        now=_now(),
    )
    owner_session.execute(
        sa.text("UPDATE enrollment SET guardian_decision = 'declined' WHERE id = :e"),
        {"e": seat},
    )
    owner_session.commit()
    lens = _lens(restricted_session, batch.batch_id, guardian)
    assert lens.assessment.standing == "author_only"

    state = authoring.state(restricted_session, lens, _today())
    assert state.can_write is False
    assert state.review is not None
    assert state.review.body == "Kind"
    with pytest.raises(ConflictError) as refused:
        authoring.write(restricted_session, lens, rating=1, body=None, now=_now())
    assert refused.value.code == "REVIEW_EDIT_CLOSED"
    assert refused.value.message_key == "hub.review.edit_closed"

    authoring.delete(restricted_session, lens, _now())

    assert _review(owner_session, batch.batch_id, guardian) is None


def test_identical_put_is_a_noop_and_consumes_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    _published_trio(owner_session, batch)
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian)
    authoring.write(
        restricted_session,
        _lens(restricted_session, batch.batch_id, guardian),
        rating=4,
        body="Patient teacher",
        now=_now(),
    )
    review_id = _review(owner_session, batch.batch_id, guardian).id
    _set_status(owner_session, review_id, "published")
    owner_session.execute(sa.text("DELETE FROM cdn_invalidation"))
    owner_session.commit()

    state = authoring.write(
        restricted_session,
        _lens(restricted_session, batch.batch_id, guardian),
        rating=4,
        body="  Patient teacher ",
        now=_now(),
    )

    stored = _review(owner_session, batch.batch_id, guardian)
    assert stored.status == "published"
    assert stored.edited_at is None
    assert stored.published_month is not None
    assert state.review is not None
    assert state.review.status == "published"
    assert _consumed(owner_session, guardian) == 1
    assert _invalidated(owner_session) == set()


def test_sixth_write_in_a_day_hits_ceiling(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian)
    for rating in range(1, HUB_REVIEW_ACCOUNT_DAILY + 1):
        authoring.write(
            restricted_session,
            _lens(restricted_session, batch.batch_id, guardian),
            rating=rating,
            body=None,
            now=_now(),
        )

    with pytest.raises(CeilingBreach) as refused:
        authoring.write(
            restricted_session,
            _lens(restricted_session, batch.batch_id, guardian),
            rating=1,
            body=None,
            now=_now(),
        )

    assert HUB_REVIEW_ACCOUNT_DAILY == 5
    assert refused.value.code == "HUB_REVIEW_CEILING"
    assert refused.value.message_key == "hub.review.ceiling"
    assert refused.value.status == 409
    assert _review(owner_session, batch.batch_id, guardian).rating == 5
    assert _consumed(owner_session, guardian) == HUB_REVIEW_ACCOUNT_DAILY


def test_concurrent_first_writes_make_one_review(
    owner_session: Session, restricted_engine: Engine
) -> None:
    """Review Focus 1: two devices submit a first review at once."""
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian)
    _member(owner_session, batch.batch_id, guardian)
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def submit(rating: int) -> None:
        with factory() as session:
            lens = _lens(session, batch.batch_id, guardian)
            barrier.wait(timeout=10)
            try:
                outcomes.append(
                    authoring.write(session, lens, rating=rating, body=None, now=_now())
                )
            except Exception as error:  # noqa: BLE001 -- reported below
                outcomes.append(error)

    threads = [threading.Thread(target=submit, args=(n,)) for n in (3, 4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(outcomes) == 2
    assert all(isinstance(o, authoring.MyReviewState) for o in outcomes), outcomes
    owner_session.rollback()
    count = owner_session.execute(
        sa.text("SELECT count(*) FROM review WHERE author_account_id = :a"),
        {"a": guardian},
    ).scalar_one()
    assert count == 1


def test_body_over_1000_after_strip_refused(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian)
    lens = _lens(restricted_session, batch.batch_id, guardian)

    with pytest.raises(ValidationError) as refused:
        authoring.write(restricted_session, lens, rating=4, body="a" * 1001, now=_now())
    assert refused.value.details == {"fields": "body"}
    assert _review(owner_session, batch.batch_id, guardian) is None
    assert _consumed(owner_session, guardian) == 0

    authoring.write(
        restricted_session, lens, rating=4, body=f"  {'a' * 1000}\n", now=_now()
    )
    assert _review(owner_session, batch.batch_id, guardian).body == "a" * 1000


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_blank_body_stored_as_null(
    owner_session: Session, restricted_session: Session, blank: str
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian)

    state = authoring.write(
        restricted_session,
        _lens(restricted_session, batch.batch_id, guardian),
        rating=4,
        body=blank,
        now=_now(),
    )

    assert _review(owner_session, batch.batch_id, guardian).body is None
    assert state.review is not None
    assert state.review.body is None


def test_contact_in_body_is_refused_before_anything_is_written(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian)

    with pytest.raises(ValidationError) as refused:
        authoring.write(
            restricted_session,
            _lens(restricted_session, batch.batch_id, guardian),
            rating=4,
            body="Call 017 1234 5678",
            now=_now(),
        )

    assert refused.value.code == "REVIEW_CONTAINS_CONTACT"
    assert _review(owner_session, batch.batch_id, guardian) is None
    assert _consumed(owner_session, guardian) == 0


def test_state_carries_only_a_published_reply(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    seat = _member(owner_session, batch.batch_id, guardian)
    review_id = add_review(owner_session, batch.batch_id, guardian, enrollment_id=seat)
    owner_session.execute(
        sa.text(
            "INSERT INTO review_reply (review_id, body, status) "
            "VALUES (:r, 'Thank you', 'pending')"
        ),
        {"r": review_id},
    )
    owner_session.commit()
    lens = _lens(restricted_session, batch.batch_id, guardian)

    pending = authoring.state(restricted_session, lens, _today())
    owner_session.execute(
        sa.text(
            "UPDATE review_reply SET status = 'published', published_month = :m "
            "WHERE review_id = :r"
        ),
        {"m": _today().replace(day=1), "r": review_id},
    )
    owner_session.commit()
    published = authoring.state(restricted_session, lens, _today())

    assert pending.review is not None
    assert pending.review.reply_body is None
    assert published.review is not None
    assert published.review.reply_body == "Thank you"


def test_state_without_a_review(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    eligible, waiting = account(owner_session), account(owner_session)
    _member(owner_session, batch.batch_id, eligible)
    _member(owner_session, batch.batch_id, waiting, joined_days_ago=5)

    can = authoring.state(
        restricted_session,
        _lens(restricted_session, batch.batch_id, eligible),
        _today(),
    )
    cannot = authoring.state(
        restricted_session, _lens(restricted_session, batch.batch_id, waiting), _today()
    )

    assert (can.can_write, can.review, can.edit_until) == (True, None, None)
    assert (cannot.can_write, cannot.review) == (False, None)


def test_switch_off_refuses_a_write_and_no_state_can_write(
    owner_session: Session,
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian)
    authoring.write(
        restricted_session,
        _lens(restricted_session, batch.batch_id, guardian),
        rating=5,
        body=None,
        now=_now(),
    )
    monkeypatch.delenv(HUB_REVIEWS_ENV)
    lens = _lens(restricted_session, batch.batch_id, guardian)

    state = authoring.state(restricted_session, lens, _today())
    assert state.can_write is False
    assert state.review is not None
    with pytest.raises(AuthorizationError) as refused:
        authoring.write(restricted_session, lens, rating=1, body=None, now=_now())
    assert refused.value.code == "HUB_REVIEWS_OFF"
    assert _review(owner_session, batch.batch_id, guardian).rating == 5


@pytest.mark.parametrize("rating", [0, 6, -1])
def test_rating_outside_one_to_five_refused(
    owner_session: Session, restricted_session: Session, rating: int
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian)

    with pytest.raises(ValidationError) as refused:
        authoring.write(
            restricted_session,
            _lens(restricted_session, batch.batch_id, guardian),
            rating=rating,
            body=None,
            now=_now(),
        )

    assert refused.value.details == {"fields": "rating"}
    assert _review(owner_session, batch.batch_id, guardian) is None


def test_author_whose_review_went_cannot_write_a_new_one(
    owner_session: Session, restricted_session: Session
) -> None:
    """An ``author_only`` lens outliving its review grants no first write."""
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    seat = _member(owner_session, batch.batch_id, guardian)
    review_id = add_review(owner_session, batch.batch_id, guardian, enrollment_id=seat)
    owner_session.execute(
        sa.text("UPDATE enrollment SET guardian_decision = 'declined' WHERE id = :e"),
        {"e": seat},
    )
    owner_session.commit()
    lens = _lens(restricted_session, batch.batch_id, guardian)
    owner_session.execute(sa.text("DELETE FROM review WHERE id = :r"), {"r": review_id})
    owner_session.commit()

    with pytest.raises(AuthorizationError) as refused:
        authoring.write(restricted_session, lens, rating=4, body=None, now=_now())

    assert refused.value.code == "NOT_AVAILABLE"
    assert _review(owner_session, batch.batch_id, guardian) is None
    assert _consumed(owner_session, guardian) == 0
