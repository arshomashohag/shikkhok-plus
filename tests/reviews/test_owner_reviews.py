"""The teacher's side: published reviews of their own batches, and replies.

Written before :mod:`app.reviews.owner` existed: owner scoping is an
authorization predicate [team: Testing Posture]. A teacher reads review
content only through ``hub_public_review`` and ``hub_public_rating``, so
the threshold that guards the public guards the teacher too (Review
Focus 2): below three published reviews a batch shows no count, no average,
no distribution and no review [T2-a]. Another owner's review and an id
that was never minted are refused with the same bytes.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from app.auth.ceilings import HUB_LISTING_OWNER_DAILY, CeilingChecker
from app.authz.lenses import TeacherLens
from app.errors import (
    AuthorizationError,
    ConflictError,
    ValidationError,
    to_response,
)
from app.hub.public.invalidation import owner_paths
from app.hub.public.settings import HUB_REVIEWS_ENV
from app.local_time import bangladesh_today
from app.reviews import owner
from tests.reviews.support import (
    PublicBatch,
    account,
    add_review,
    public_batch,
    public_centre_batch,
    second_batch,
)

pytestmark = pytest.mark.usefixtures("reviews_on")


def _now() -> dt.datetime:
    """Give the present.

    :return: Now, in UTC
    """
    return dt.datetime.now(tz=dt.UTC)


def _month(months_ago: int = 0) -> dt.date:
    """Give the first of a month in Bangladesh, some months back.

    :param months_ago: How many months before this one
    :return: The date
    """
    first = bangladesh_today().replace(day=1)
    for _ in range(months_ago):
        first = (first - dt.timedelta(days=1)).replace(day=1)
    return first


def _lens(batch: PublicBatch) -> TeacherLens:
    """Give the batch owner's teacher lens.

    :param batch: The batch
    :return: The lens
    """
    return TeacherLens(account_id=batch.teacher_account_id, owner_id=batch.owner_id)


def _set_status(session: Session, review_id: uuid.UUID, status: str) -> None:
    """Move a stored review to a status, with the columns that status needs.

    :param session: An arranging session
    :param review_id: The review
    :param status: Any review status
    :return: None
    """
    shown = status in ("published", "held")
    session.execute(
        sa.text(
            "UPDATE review SET status = CAST(:s AS hub_review_status), "
            "published_month = :m, approved_at = :a, rejection_code = :c "
            "WHERE id = :r"
        ),
        {
            "s": status,
            "m": _month() if shown else None,
            "a": _now() if status == "approved" else None,
            "c": "off_topic" if status in ("rejected", "removed") else None,
            "r": review_id,
        },
    )
    session.commit()


def _reviewed(
    session: Session, batch_id: uuid.UUID, status: str, *, rating: int = 4
) -> uuid.UUID:
    """Add another guardian's review of a batch, in a status.

    :param session: An arranging session
    :param batch_id: The batch
    :param status: The review's status
    :param rating: 1 to 5
    :return: The review id
    """
    review_id = add_review(session, batch_id, account(session), rating=rating)
    _set_status(session, review_id, status)
    return review_id


def _published(
    session: Session, batch_id: uuid.UUID, ratings: tuple[int, ...] = (5, 4, 4)
) -> list[uuid.UUID]:
    """Publish one review per rating.

    :param session: An arranging session
    :param batch_id: The batch
    :param ratings: The ratings
    :return: The review ids
    """
    return [_reviewed(session, batch_id, "published", rating=r) for r in ratings]


def _reply(
    session: Session,
    review_id: uuid.UUID,
    *,
    status: str = "published",
    body: str = "Thank you for writing.",
    writer: uuid.UUID | None = None,
) -> None:
    """Store a reply directly.

    :param session: An arranging session
    :param review_id: The review
    :param status: ``pending`` or ``published``
    :param body: The text
    :param writer: The writing account
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO review_reply (review_id, body, status, published_month, "
            "written_by_account_id) VALUES (:r, :b, CAST(:s AS hub_reply_status), "
            ":m, :w)"
        ),
        {
            "r": review_id,
            "b": body,
            "s": status,
            "m": _month() if status == "published" else None,
            "w": writer,
        },
    )
    session.commit()


def _reply_row(
    session: Session, review_id: uuid.UUID
) -> Row[tuple[object, ...]] | None:
    """Read a stored reply.

    :param session: An arranging session
    :param review_id: The review
    :return: The row, or None
    """
    session.rollback()
    return session.execute(
        sa.text("SELECT * FROM review_reply WHERE review_id = :r"), {"r": review_id}
    ).one_or_none()


def _report(
    session: Session, kind: str, target: uuid.UUID, reporter: uuid.UUID
) -> None:
    """File an open report.

    :param session: An arranging session
    :param kind: ``review`` or ``reply``
    :param target: The target id
    :param reporter: The reporting account
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO hub_report (id, target_kind, target_id, "
            "reporter_account_id, reason) VALUES (gen_random_uuid(), "
            "CAST(:k AS hub_report_target), :t, :a, 'other')"
        ),
        {"k": kind, "t": target, "a": reporter},
    )
    session.commit()


def _reports(session: Session, kind: str, target: uuid.UUID) -> int:
    """Count reports on a target.

    :param session: An arranging session
    :param kind: ``review`` or ``reply``
    :param target: The target id
    :return: The count
    """
    session.rollback()
    return int(
        session.execute(
            sa.text(
                "SELECT count(*) FROM hub_report WHERE target_id = :t "
                "AND target_kind = CAST(:k AS hub_report_target)"
            ),
            {"t": target, "k": kind},
        ).scalar_one()
    )


def _spent(session: Session, owner_id: uuid.UUID) -> int:
    """Count today's listing writes against an owner.

    :param session: An arranging session
    :param owner_id: The owner
    :return: The counter's value, 0 when no row exists
    """
    session.rollback()
    value = session.execute(
        sa.text(
            "SELECT coalesce(sum(count), 0) FROM rate_limit_counter "
            "WHERE scope_kind = 'hub_owner_day' AND scope_value = :o"
        ),
        {"o": str(owner_id)},
    ).scalar_one()
    return int(value)


def _invalidated(session: Session) -> set[str]:
    """List the paths in the invalidation outbox.

    :param session: An arranging session
    :return: The paths
    """
    session.rollback()
    return set(session.scalars(sa.text("SELECT path FROM cdn_invalidation")))


def _clear_outbox(session: Session) -> None:
    """Empty the invalidation outbox.

    :param session: An arranging session
    :return: None
    """
    session.execute(sa.text("DELETE FROM cdn_invalidation"))
    session.commit()


def _owner_slug(session: Session, owner_id: uuid.UUID) -> str:
    """Read an owner listing's slug.

    :param session: An arranging session
    :param owner_id: The owner
    :return: The slug
    """
    return str(
        session.execute(
            sa.text("SELECT slug FROM owner_listing WHERE owner_id = :o"),
            {"o": owner_id},
        ).scalar_one()
    )


def test_teacher_sees_only_published_above_threshold(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    shown = _published(owner_session, batch.batch_id, (5, 4, 4))
    for status in ("pending", "approved", "held", "rejected", "removed"):
        _reviewed(owner_session, batch.batch_id, status, rating=1)

    ratings, reviews = owner.owner_reviews(restricted_session, _lens(batch))

    assert {r.id for r in reviews} == set(shown)
    assert {r.batch_id for r in reviews} == {batch.batch_id}
    assert [
        (r.batch_id, r.batch_title, r.review_count, r.average_tenths, r.distribution)
        for r in ratings
    ] == [(batch.batch_id, "HSC Physics", 3, 43, [0, 0, 0, 2, 1])]


def test_teacher_sees_nothing_below_threshold(
    owner_session: Session, restricted_session: Session
) -> None:
    """Review Focus 2: dropping from 3 to 2 hides everything, the count too."""
    batch = public_batch(owner_session)
    shown = _published(owner_session, batch.batch_id)
    empty = second_batch(owner_session, batch.owner_id, title="SSC Chemistry")
    _published(owner_session, empty, (5, 5))
    _set_status(owner_session, shown[0], "held")

    ratings, reviews = owner.owner_reviews(restricted_session, _lens(batch))

    assert reviews == []
    assert sorted(
        (r.batch_title, r.review_count, r.average_tenths, r.distribution)
        for r in ratings
    ) == [("HSC Physics", None, None, None), ("SSC Chemistry", None, None, None)]


def test_every_published_batch_is_listed_and_unpublished_ones_are_not(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    second_batch(owner_session, batch.owner_id, title="Never reviewed")
    second_batch(owner_session, batch.owner_id, title="A draft", status="draft")

    ratings, _ = owner.owner_reviews(restricted_session, _lens(batch))

    assert sorted(r.batch_title or "" for r in ratings) == [
        "HSC Physics",
        "Never reviewed",
    ]


def test_reviews_are_ordered_by_month_then_id_never_by_submission(
    owner_session: Session, restricted_session: Session
) -> None:
    """T2-c: the order says nothing about who wrote first."""
    batch = public_batch(owner_session)
    ids = _published(owner_session, batch.batch_id, (5, 4, 3, 2))
    fixed = [uuid.UUID(int=n) for n in (2, 0, 3, 1)]
    months = [_month(), _month(1), _month(1), _month()]
    submitted = _now() - dt.timedelta(days=10)
    for position, (review_id, new_id, month) in enumerate(
        zip(ids, fixed, months, strict=True)
    ):
        owner_session.execute(
            sa.text(
                "UPDATE review SET id = :n, published_month = :m, "
                "submitted_at = :s WHERE id = :r"
            ),
            {
                "n": new_id,
                "m": month,
                "s": submitted + dt.timedelta(hours=position),
                "r": review_id,
            },
        )
    owner_session.commit()

    _, reviews = owner.owner_reviews(restricted_session, _lens(batch))

    assert [r.id.int for r in reviews] == [1, 2, 0, 3]
    assert [r.published_month for r in reviews] == [
        _month(),
        _month(),
        _month(1),
        _month(1),
    ]


def test_owner_review_carries_the_public_reply_and_my_reply(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    published, pending, rejected = _published(owner_session, batch.batch_id)
    _reply(owner_session, published, body="Shown")
    _reply(owner_session, pending, status="pending", body="Waiting")
    owner_session.execute(
        sa.text(
            "INSERT INTO review_reply (review_id, body, status, rejection_code) "
            "VALUES (:r, 'Too much', 'rejected', 'off_topic')"
        ),
        {"r": rejected},
    )
    owner_session.commit()

    _, reviews = owner.owner_reviews(restricted_session, _lens(batch))

    by_id = {r.id: r for r in reviews}
    assert (
        by_id[published].reply_body,
        by_id[published].reply_month,
        by_id[published].my_reply_status,
        by_id[published].my_reply_body,
    ) == ("Shown", _month(), "published", "Shown")
    assert (
        by_id[pending].reply_body,
        by_id[pending].reply_month,
        by_id[pending].my_reply_status,
        by_id[pending].my_reply_body,
    ) == (None, None, "pending", "Waiting")
    assert (
        by_id[rejected].reply_body,
        by_id[rejected].my_reply_status,
        by_id[rejected].my_reply_rejection_code,
    ) == (None, "rejected", "off_topic")
    assert by_id[published].tenure == "lt_6m"
    assert by_id[published].rating == 5


def test_other_owner_cannot_list_or_reply(
    owner_session: Session, restricted_session: Session
) -> None:
    mine = public_batch(owner_session)
    target = _published(owner_session, mine.batch_id)[0]
    _reply(owner_session, target, body="Ours")
    theirs = public_batch(owner_session, title="Other teacher's batch")
    intruder = _lens(theirs)

    ratings, reviews = owner.owner_reviews(restricted_session, intruder)
    assert reviews == []
    assert [r.batch_id for r in ratings] == [theirs.batch_id]

    with pytest.raises(AuthorizationError) as foreign:
        owner.put_reply(restricted_session, intruder, target, "Mine now", _now())
    with pytest.raises(AuthorizationError) as invented:
        owner.put_reply(restricted_session, intruder, uuid.uuid4(), "Mine now", _now())
    owner.delete_reply(restricted_session, intruder, target, _now())
    owner.delete_reply(restricted_session, intruder, uuid.uuid4(), _now())

    responses = [to_response(e.value) for e in (foreign, invented)]
    assert {r.status_code for r in responses} == {404}
    assert len({r.body for r in responses}) == 1
    assert foreign.value.code == "REVIEW_NOT_FOUND"
    assert foreign.value.message_key == "hub.review.not_found"
    reply = _reply_row(owner_session, target)
    assert reply is not None
    assert (reply.body, reply.status) == ("Ours", "published")
    assert _spent(owner_session, theirs.owner_id) == 0


def test_a_review_below_threshold_cannot_be_replied_to(
    owner_session: Session, restricted_session: Session
) -> None:
    """Not in the view means not found, even for the batch's own owner."""
    batch = public_batch(owner_session)
    first, second = _published(owner_session, batch.batch_id, (4, 5))
    held = _reviewed(owner_session, batch.batch_id, "held")

    for review_id in (first, held):
        with pytest.raises(AuthorizationError) as refused:
            owner.put_reply(restricted_session, _lens(batch), review_id, "Hi", _now())
        assert refused.value.code == "REVIEW_NOT_FOUND"
    assert _reply_row(owner_session, second) is None


def test_first_reply_is_pending_and_spends_one(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    _clear_outbox(owner_session)
    now = _now()

    result = owner.put_reply(
        restricted_session, _lens(batch), target, "  Thank you.  ", now
    )

    assert (result.id, result.my_reply_status, result.my_reply_body) == (
        target,
        "pending",
        "Thank you.",
    )
    assert (result.reply_body, result.reply_month) == (None, None)
    reply = _reply_row(owner_session, target)
    assert reply is not None
    assert (reply.body, reply.status, reply.written_by_account_id) == (
        "Thank you.",
        "pending",
        batch.teacher_account_id,
    )
    assert _spent(owner_session, batch.owner_id) == 1
    assert _invalidated(owner_session) == set()


def test_centre_manager_reply_records_writer(
    owner_session: Session, restricted_session: Session
) -> None:
    centre = public_centre_batch(owner_session)
    target = _published(owner_session, centre.batch_id)[1]

    owner.put_reply(
        restricted_session, _lens(centre), target, "From the centre", _now()
    )

    reply = _reply_row(owner_session, target)
    assert reply is not None
    assert reply.written_by_account_id == centre.teacher_account_id
    assert _spent(owner_session, centre.owner_id) == 1


@pytest.mark.parametrize(
    "body",
    ["Call 017 1234 5678", "Call ০১৭১২৩৪৫৬৭৮", "See www.example.com", "fb.com/page"],
)
def test_reply_contact_refused(
    owner_session: Session, restricted_session: Session, body: str
) -> None:
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]

    with pytest.raises(ValidationError) as refused:
        owner.put_reply(restricted_session, _lens(batch), target, body, _now())

    assert refused.value.code == "REVIEW_CONTAINS_CONTACT"
    assert refused.value.message_key == "hub.review.contains_contact"
    assert refused.value.details == {"field": "body"}
    assert _reply_row(owner_session, target) is None
    assert _spent(owner_session, batch.owner_id) == 0


def test_reply_on_suspended_listing_refused(
    owner_session: Session, restricted_session: Session
) -> None:
    """F6: the suspension answers first, before the review is looked up."""
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    owner_session.execute(
        sa.text("UPDATE owner_listing SET status = 'suspended' WHERE owner_id = :o"),
        {"o": batch.owner_id},
    )
    owner_session.commit()

    with pytest.raises(ConflictError) as refused:
        owner.put_reply(restricted_session, _lens(batch), target, "Hello", _now())

    assert refused.value.code == "HUB_LISTING_SUSPENDED"
    assert _reply_row(owner_session, target) is None
    assert _spent(owner_session, batch.owner_id) == 0


@pytest.mark.parametrize("body", ["", "   \n\t", "x" * 1001])
def test_reply_body_out_of_range_refused(
    owner_session: Session, restricted_session: Session, body: str
) -> None:
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]

    with pytest.raises(ValidationError) as refused:
        owner.put_reply(restricted_session, _lens(batch), target, body, _now())

    assert refused.value.code == "REQUEST_INVALID"
    assert _reply_row(owner_session, target) is None


def test_reply_of_1000_after_strip_is_accepted(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]

    owner.put_reply(
        restricted_session, _lens(batch), target, f"  {'x' * 1000}  ", _now()
    )

    reply = _reply_row(owner_session, target)
    assert reply is not None
    assert reply.body == "x" * 1000


def test_replacing_published_reply_returns_it_to_pending_and_invalidates(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    _reply(owner_session, target, body="Old words")
    owner_session.execute(
        sa.text(
            "UPDATE review_reply SET decided_at = now(), "
            "decided_by_account_id = :a WHERE review_id = :r"
        ),
        {"a": account(owner_session), "r": target},
    )
    owner_session.commit()
    _clear_outbox(owner_session)
    now = _now()

    result = owner.put_reply(restricted_session, _lens(batch), target, "New words", now)

    reply = _reply_row(owner_session, target)
    assert reply is not None
    assert (
        reply.body,
        reply.status,
        reply.published_month,
        reply.decided_at,
        reply.decided_by_account_id,
        reply.rejection_code,
        reply.edited_at,
        reply.written_by_account_id,
    ) == ("New words", "pending", None, None, None, None, now, batch.teacher_account_id)
    assert (result.reply_body, result.my_reply_status) == (None, "pending")
    assert set(owner_paths(_owner_slug(owner_session, batch.owner_id))) <= (
        _invalidated(owner_session)
    )
    assert _spent(owner_session, batch.owner_id) == 1


def test_replacing_pending_reply_invalidates_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    _reply(owner_session, target, status="pending", body="Draft")
    _clear_outbox(owner_session)

    owner.put_reply(restricted_session, _lens(batch), target, "Second draft", _now())

    reply = _reply_row(owner_session, target)
    assert reply is not None
    assert (reply.body, reply.status) == ("Second draft", "pending")
    assert _invalidated(owner_session) == set()


def test_identical_reply_is_a_noop_and_spends_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    """An identical body changes nothing, so it spends nothing [F5]."""
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    _reply(owner_session, target, body="Same words")
    _clear_outbox(owner_session)

    result = owner.put_reply(
        restricted_session, _lens(batch), target, " Same words \n", _now()
    )

    reply = _reply_row(owner_session, target)
    assert reply is not None
    assert (reply.status, reply.edited_at) == ("published", None)
    assert (result.reply_body, result.my_reply_status) == ("Same words", "published")
    assert _spent(owner_session, batch.owner_id) == 0
    assert _invalidated(owner_session) == set()


def _wait_for_a_lock_waiter(session: Session) -> None:
    """Block until some backend waits on a lock, or give up and roll back.

    :param session: The session holding the lock the write must wait on
    :return: None
    :raises AssertionError: Nobody waited within ten seconds
    """
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        waiting = session.execute(
            sa.text("SELECT count(*) FROM pg_locks WHERE NOT granted")
        ).scalar_one()
        if waiting:
            return
        time.sleep(0.05)
    session.rollback()
    raise AssertionError("the reply never waited on the other's insert")


@pytest.mark.parametrize(
    ("body", "spent", "edited"),
    [("Same words", 0, False), ("Other words", 1, True)],
    ids=["identical", "different"],
)
def test_a_first_reply_losing_the_insert_race_spends_only_on_a_change(
    owner_session: Session,
    restricted_session: Session,
    body: str,
    spent: int,
    edited: bool,
) -> None:
    """Two managers reply at once: one reply, counted only if it changed.

    The other manager's first reply is inserted and held uncommitted, so
    this reply finds none, blocks on the key, and loses the insert once the
    other commits; it then continues as a replacement of the winner.
    """
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    lens = _lens(batch)
    owner_session.execute(
        sa.text(
            "INSERT INTO review_reply (review_id, body, status) "
            "VALUES (:r, 'Same words', 'pending')"
        ),
        {"r": target},
    )
    outcome: list[object] = []

    def submit() -> None:
        try:
            outcome.append(
                owner.put_reply(restricted_session, lens, target, body, _now())
            )
        except Exception as error:  # noqa: BLE001 -- reported below
            outcome.append(error)

    thread = threading.Thread(target=submit)
    thread.start()
    _wait_for_a_lock_waiter(owner_session)
    owner_session.commit()
    thread.join(timeout=30)

    assert len(outcome) == 1
    assert isinstance(outcome[0], owner.OwnerReview), outcome
    reply = _reply_row(owner_session, target)
    assert reply is not None
    assert reply.body == body
    assert (reply.edited_at is not None) is edited
    assert _spent(owner_session, batch.owner_id) == spent


def test_reply_beyond_the_owner_allowance_is_refused_and_rolled_back(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    lens = _lens(batch)
    now = _now()
    checker = CeilingChecker(owner_session)
    for _ in range(HUB_LISTING_OWNER_DAILY):
        checker.consume_hub_listing_in_transaction(batch.owner_id, now)
    owner_session.commit()

    with pytest.raises(ConflictError) as refused:
        owner.put_reply(restricted_session, lens, target, "One too many", now)

    assert refused.value.code == "HUB_WRITE_CEILING"
    assert _reply_row(owner_session, target) is None
    assert _spent(owner_session, batch.owner_id) == HUB_LISTING_OWNER_DAILY


def test_delete_reply_idempotent(
    owner_session: Session, restricted_session: Session
) -> None:
    """F8: deletion is total; a second delete is a quiet success."""
    batch = public_batch(owner_session)
    target, other = _published(owner_session, batch.batch_id)[:2]
    _reply(owner_session, target)
    _reply(owner_session, other)
    reporter = account(owner_session)
    _report(owner_session, "reply", target, reporter)
    _report(owner_session, "review", target, reporter)
    _report(owner_session, "reply", other, reporter)
    _clear_outbox(owner_session)

    owner.delete_reply(restricted_session, _lens(batch), target, _now())

    assert _reply_row(owner_session, target) is None
    assert _reports(owner_session, "reply", target) == 0
    assert _reports(owner_session, "review", target) == 1
    assert _reports(owner_session, "reply", other) == 1
    assert _reply_row(owner_session, other) is not None
    assert set(owner_paths(_owner_slug(owner_session, batch.owner_id))) <= (
        _invalidated(owner_session)
    )

    _clear_outbox(owner_session)
    owner.delete_reply(restricted_session, _lens(batch), target, _now())

    assert _invalidated(owner_session) == set()
    assert _spent(owner_session, batch.owner_id) == 0


def test_teacher_deletes_their_reply_on_a_held_review(
    owner_session: Session, restricted_session: Session
) -> None:
    """T5-a: removing one's own words is never gated by publication."""
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id, (5, 4, 4, 3))[0]
    _reply(owner_session, target)
    _report(owner_session, "reply", target, account(owner_session))
    _set_status(owner_session, target, "held")

    owner.delete_reply(restricted_session, _lens(batch), target, _now())

    assert _reply_row(owner_session, target) is None
    assert _reports(owner_session, "reply", target) == 0


def test_teacher_deletes_their_reply_below_threshold(
    owner_session: Session, restricted_session: Session
) -> None:
    """Below the threshold the owner still deletes their reply, and only it.

    Another owner's delete of the same reply is a quiet no-op that leaves
    it in place; the owner's own delete removes it and leaves the reply to
    their other review standing.
    """
    batch = public_batch(owner_session)
    target, other = _published(owner_session, batch.batch_id, (5, 4))
    _reply(owner_session, target, status="pending")
    _reply(owner_session, other, status="pending")
    stranger = public_batch(owner_session, title="Someone else's batch")

    owner.delete_reply(restricted_session, _lens(stranger), target, _now())

    assert _reply_row(owner_session, target) is not None

    owner.delete_reply(restricted_session, _lens(batch), target, _now())

    assert _reply_row(owner_session, target) is None
    assert _reply_row(owner_session, other) is not None
    assert owner.owner_reviews(restricted_session, _lens(batch))[1] == []


def test_teacher_deletes_their_reply_on_a_suspended_listing(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    _reply(owner_session, target)
    owner_session.execute(
        sa.text("UPDATE owner_listing SET status = 'suspended' WHERE owner_id = :o"),
        {"o": batch.owner_id},
    )
    owner_session.commit()

    owner.delete_reply(restricted_session, _lens(batch), target, _now())

    assert _reply_row(owner_session, target) is None


def test_another_owners_delete_leaves_a_hidden_reply_and_answers_quietly(
    owner_session: Session, restricted_session: Session
) -> None:
    """T5-a: a foreign delete is the same quiet success and deletes nothing."""
    mine = public_batch(owner_session)
    target = _published(owner_session, mine.batch_id, (5, 4))[0]
    _reply(owner_session, target, status="pending", body="Ours")
    reporter = account(owner_session)
    _report(owner_session, "reply", target, reporter)
    theirs = public_batch(owner_session, title="Other teacher's batch")
    _clear_outbox(owner_session)

    result = owner.delete_reply(restricted_session, _lens(theirs), target, _now())

    assert result is None
    reply = _reply_row(owner_session, target)
    assert reply is not None
    assert reply.body == "Ours"
    assert _reports(owner_session, "reply", target) == 1
    assert _invalidated(owner_session) == set()


def test_a_first_reply_losing_to_a_review_delete_is_not_found(
    owner_session: Session, restricted_session: Session
) -> None:
    """T5-b: the review is deleted under the reply; not found, not a 500.

    The author's delete is held uncommitted, so the reply reads the review
    through the view, finds no reply, and its insert's key check waits on the
    deleted row; once the delete commits, the key check fails.
    """
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    lens = _lens(batch)
    owner_session.execute(sa.text("DELETE FROM review WHERE id = :r"), {"r": target})
    outcome: list[object] = []

    def submit() -> None:
        try:
            outcome.append(
                owner.put_reply(restricted_session, lens, target, "Thanks", _now())
            )
        except Exception as error:  # noqa: BLE001 -- asserted below
            outcome.append(error)

    thread = threading.Thread(target=submit)
    thread.start()
    _wait_for_a_lock_waiter(owner_session)
    owner_session.commit()
    thread.join(timeout=30)

    assert len(outcome) == 1
    refused = outcome[0]
    assert isinstance(refused, AuthorizationError), outcome
    assert (refused.code, refused.message_key, refused.status) == (
        "REVIEW_NOT_FOUND",
        "hub.review.not_found",
        404,
    )
    assert _reply_row(owner_session, target) is None
    assert _spent(owner_session, batch.owner_id) == 0


def test_deleting_a_pending_reply_invalidates_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    _reply(owner_session, target, status="pending")
    _clear_outbox(owner_session)

    owner.delete_reply(restricted_session, _lens(batch), target, _now())

    assert _reply_row(owner_session, target) is None
    assert _invalidated(owner_session) == set()


def test_delete_reply_works_with_the_switch_off(
    owner_session: Session,
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The switch never gates a deletion."""
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    _reply(owner_session, target, status="pending")
    monkeypatch.delenv(HUB_REVIEWS_ENV, raising=False)

    owner.delete_reply(restricted_session, _lens(batch), target, _now())

    assert _reply_row(owner_session, target) is None


def test_put_reply_refused_while_reviews_are_off(
    owner_session: Session,
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    monkeypatch.delenv(HUB_REVIEWS_ENV, raising=False)

    with pytest.raises(AuthorizationError) as refused:
        owner.put_reply(restricted_session, _lens(batch), target, "Hello", _now())

    assert refused.value.code == "HUB_REVIEWS_OFF"
    assert _reply_row(owner_session, target) is None
