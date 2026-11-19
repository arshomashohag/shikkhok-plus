"""The weekly publication of approved reviews, and the review notifications.

Written before :mod:`app.reviews.publication` existed. A moderator's
approval queues a review; the job makes it public on the next run after the
Friday-midnight Dhaka boundary that follows the approval, so a family
watching the page cannot match an approval to the day it appeared.

Who is told what is part of the contract: the author always learns the
outcome (``published``, ``rejected`` or ``removed``, never the moderator's
code), and the people who run the batch are told only once the batch is at
or above the public threshold, because a count of one or two published
reviews is exactly what the threshold hides.

Arranged through the table-owner session, exercised through the restricted
one.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
import uuid
from typing import Final

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine, Row
from sqlalchemy.orm import Session, sessionmaker

from app.authz.lenses import PlatformAdminLens
from app.hub.public.settings import HUB_REVIEWS_ENV
from app.local_time import DHAKA
from app.moderation import reports, reviews
from app.reviews import commands, publication
from tests.reviews.support import (
    PublicBatch,
    account,
    add_review,
    public_batch,
    public_centre_batch,
)

#: 03:10 in Dhaka on Friday 2026-11-20, when the cron entry fires.
RUN: Final = dt.datetime(2026, 11, 19, 21, 10, tzinfo=dt.UTC)

#: The boundary ``RUN`` publishes up to: Friday 2026-11-20 00:00 Dhaka.
BOUNDARY: Final = dt.datetime(2026, 11, 19, 18, 0, tzinfo=dt.UTC)

#: Long enough before any boundary a test uses.
LONG_AGO: Final = dt.datetime(2026, 10, 1, 9, 0, tzinfo=dt.UTC)


def _approved(
    session: Session,
    batch_id: uuid.UUID,
    approved_at: dt.datetime = LONG_AGO,
    *,
    author: uuid.UUID | None = None,
) -> uuid.UUID:
    """Store an approved review, waiting for the publication.

    :param session: An arranging session
    :param batch_id: The batch
    :param approved_at: When a moderator approved it
    :param author: The author; a fresh account by default
    :return: The review id
    """
    review_id = add_review(session, batch_id, author or account(session))
    session.execute(
        sa.text(
            "UPDATE review SET status = 'approved', approved_at = :a WHERE id = :r"
        ),
        {"a": approved_at, "r": review_id},
    )
    session.commit()
    return review_id


def _published(session: Session, batch_id: uuid.UUID, n: int) -> list[uuid.UUID]:
    """Store ``n`` reviews already published in an earlier month.

    :param session: An arranging session
    :param batch_id: The batch
    :param n: How many
    :return: The review ids
    """
    ids = []
    for _ in range(n):
        review_id = add_review(session, batch_id, account(session))
        session.execute(
            sa.text(
                "UPDATE review SET status = 'published', "
                "published_month = DATE '2026-10-01' WHERE id = :r"
            ),
            {"r": review_id},
        )
        ids.append(review_id)
    session.commit()
    return ids


def _review(session: Session, review_id: uuid.UUID) -> Row[tuple[object, ...]]:
    """Read a stored review fresh.

    :param session: An arranging session
    :param review_id: The review
    :return: The row
    """
    session.rollback()
    return session.execute(
        sa.text(
            "SELECT status::text AS status, published_month, approved_at "
            "FROM review WHERE id = :r"
        ),
        {"r": review_id},
    ).one()


def _author(session: Session, review_id: uuid.UUID) -> uuid.UUID:
    """Read a review's author.

    :param session: An arranging session
    :param review_id: The review
    :return: The author's account
    """
    return session.execute(
        sa.text("SELECT author_account_id FROM review WHERE id = :r"),
        {"r": review_id},
    ).scalar_one()


def _notes(
    session: Session, kind: str | None = None
) -> list[tuple[uuid.UUID, str, str | None, uuid.UUID | None, str]]:
    """Read the inbox rows, optionally of one kind.

    :param session: An arranging session
    :param kind: The kind to read, or None for every kind
    :return: ``(account, kind, preview, source_id, batch_name)``, sorted
    """
    session.rollback()
    rows = session.execute(
        sa.text(
            "SELECT account_id, kind, preview, source_id, batch_name "
            "FROM notification WHERE CAST(:k AS text) IS NULL OR kind = :k"
        ),
        {"k": kind},
    ).all()
    return sorted(((r[0], r[1], r[2], r[3], r[4]) for r in rows), key=lambda r: str(r))


def _published_events(session: Session) -> list[tuple[uuid.UUID, bool]]:
    """Read the ``review_published`` events.

    :param session: An arranging session
    :return: ``(target, has an actor)`` per event, sorted
    """
    session.rollback()
    rows = session.execute(
        sa.text(
            "SELECT target_id, actor_admin_account_id IS NOT NULL "
            "FROM hub_moderation_event WHERE event = 'review_published' "
            "AND target_kind = 'review'"
        )
    ).all()
    return sorted(((r[0], r[1]) for r in rows), key=lambda r: str(r))


def _a_lock_waiter(session: Session) -> bool:
    """Wait up to ten seconds for some backend to wait on a lock.

    ``pg_locks`` rather than ``pg_stat_activity``: every role may read the
    former, while the latter hides other roles' wait events.

    :param session: An arranging session
    :return: True once a lock waiter is seen; False on timeout
    """
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        session.rollback()
        waiting = session.execute(
            sa.text("SELECT count(*) FROM pg_locks WHERE NOT granted")
        ).scalar_one()
        if waiting:
            return True
        time.sleep(0.05)
    return False


def _heartbeat(session: Session) -> dt.datetime | None:
    """Read this job's heartbeat.

    :param session: An arranging session
    :return: Its last success, or None
    """
    session.rollback()
    return session.execute(
        sa.text(
            "SELECT last_success_at FROM job_heartbeat "
            "WHERE job_name = 'hub_review_publication'"
        )
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# The boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # Thursday 23:59 Dhaka: still last week, back to the previous Friday.
        (
            dt.datetime(2026, 11, 19, 23, 59, tzinfo=DHAKA),
            dt.datetime(2026, 11, 12, 18, 0, tzinfo=dt.UTC),
        ),
        # Friday 00:00 Dhaka is its own boundary.
        (
            dt.datetime(2026, 11, 20, 0, 0, tzinfo=DHAKA),
            BOUNDARY,
        ),
        # 18:00 UTC on Thursday is that same Friday midnight in Dhaka.
        (
            dt.datetime(2026, 11, 19, 18, 0, tzinfo=dt.UTC),
            BOUNDARY,
        ),
        # The cron run itself, three hours into the Dhaka Friday.
        (RUN, BOUNDARY),
        # One second before the boundary, in UTC.
        (
            dt.datetime(2026, 11, 19, 17, 59, 59, tzinfo=dt.UTC),
            dt.datetime(2026, 11, 12, 18, 0, tzinfo=dt.UTC),
        ),
    ],
)
def test_week_start_is_friday_midnight_dhaka(
    now: dt.datetime, expected: dt.datetime
) -> None:
    start = publication.week_start(now)

    assert start == expected
    assert start.utcoffset() == dt.timedelta(0)


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("reviews_on")
def test_approved_before_boundary_published_after_not(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session, title="HSC Physics")
    due = _approved(owner_session, batch.batch_id, BOUNDARY - dt.timedelta(minutes=1))
    on_boundary = _approved(owner_session, batch.batch_id, BOUNDARY)
    after = _approved(owner_session, batch.batch_id, BOUNDARY + dt.timedelta(hours=1))
    waiting = add_review(owner_session, batch.batch_id, account(owner_session))

    assert publication.publish_due(restricted_session, RUN) == 1
    restricted_session.commit()

    assert tuple(_review(owner_session, due)) == (
        "published",
        dt.date(2026, 11, 1),
        None,
    )
    for kept in (on_boundary, after):
        assert _review(owner_session, kept).status == "approved"
        assert _review(owner_session, kept).approved_at is not None
    assert _review(owner_session, waiting).status == "pending"
    assert _published_events(owner_session) == [(due, False)]
    # The author learns it is up, keyed by the batch; one published review
    # is below the threshold, so nobody who runs the batch is told.
    assert _notes(owner_session) == [
        (
            _author(owner_session, due),
            "hub_review_outcome",
            "published",
            batch.batch_id,
            "HSC Physics",
        )
    ]


@pytest.mark.usefixtures("reviews_on")
def test_published_month_is_dhaka_month(
    owner_session: Session, restricted_session: Session
) -> None:
    # 18:30 UTC on New Year's Eve is 00:30 on 1 January 2027 in Dhaka, a
    # Friday: the boundary is half an hour back and the month is January.
    now = dt.datetime(2026, 12, 31, 18, 30, tzinfo=dt.UTC)
    batch = public_batch(owner_session)
    review_id = _approved(
        owner_session, batch.batch_id, dt.datetime(2026, 12, 31, 10, tzinfo=dt.UTC)
    )

    assert publication.publish_due(restricted_session, now) == 1
    restricted_session.commit()

    assert _review(owner_session, review_id).published_month == dt.date(2027, 1, 1)


@pytest.mark.usefixtures("reviews_on")
def test_overlapping_runs_publish_and_notify_once(
    owner_session: Session, restricted_engine: Engine
) -> None:
    batch = public_batch(owner_session, title="SSC Maths")
    due = [_approved(owner_session, batch.batch_id) for _ in range(3)]
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    # The first run has updated and holds its row locks when the second
    # starts; it commits only once the second is seen waiting on them, so
    # the two runs genuinely overlap rather than merely running close.
    barrier = threading.Barrier(2)
    release = threading.Event()
    outcomes: dict[str, object] = {}

    def run(name: str) -> None:
        with factory() as session:
            try:
                if name == "first":
                    outcomes[name] = publication.publish_due(session, RUN)
                    barrier.wait(timeout=10)
                    release.wait(timeout=10)
                else:
                    barrier.wait(timeout=10)
                    outcomes[name] = publication.publish_due(session, RUN)
                session.commit()
            except Exception as error:  # noqa: BLE001 -- reported below
                session.rollback()
                outcomes[name] = error

    threads = [threading.Thread(target=run, args=(n,)) for n in ("first", "second")]
    for thread in threads:
        thread.start()
    waited = _a_lock_waiter(owner_session)
    release.set()
    for thread in threads:
        thread.join(timeout=30)

    assert waited, "the second run never waited on the first run's row locks"
    assert outcomes == {"first": 3, "second": 0}
    assert sorted(_published_events(owner_session)) == sorted((r, False) for r in due)
    outcomes_sent = _notes(owner_session, "hub_review_outcome")
    assert sorted(n[0] for n in outcomes_sent) == sorted(
        _author(owner_session, r) for r in due
    )
    assert _notes(owner_session, "hub_reviews_published") == [
        (
            batch.teacher_account_id,
            "hub_reviews_published",
            "3",
            batch.owner_id,
            "SSC Maths",
        )
    ]


@pytest.mark.usefixtures("reviews_on")
def test_owner_notified_only_at_or_above_threshold(
    owner_session: Session, restricted_session: Session
) -> None:
    # Two published plus one due: three after the run, so the owner is told
    # how many THIS run added, not the total.
    reaching = public_batch(owner_session, title="Reaching")
    _published(owner_session, reaching.batch_id, 2)
    _approved(owner_session, reaching.batch_id)
    # One published plus one due: two after the run, still hidden.
    short = public_batch(owner_session, title="Short")
    _published(owner_session, short.batch_id, 1)
    _approved(owner_session, short.batch_id)
    # A centre: every accepted manager is told, under the owner's id.
    centre: PublicBatch = public_centre_batch(owner_session, title="Centre batch")
    _published(owner_session, centre.batch_id, 1)
    _approved(owner_session, centre.batch_id)
    _approved(owner_session, centre.batch_id)

    assert publication.publish_due(restricted_session, RUN) == 4
    restricted_session.commit()

    assert _notes(owner_session, "hub_reviews_published") == sorted(
        [
            (
                reaching.teacher_account_id,
                "hub_reviews_published",
                "1",
                reaching.owner_id,
                "Reaching",
            ),
            (
                centre.teacher_account_id,
                "hub_reviews_published",
                "2",
                centre.owner_id,
                "Centre batch",
            ),
        ],
        key=lambda r: str(r),
    )
    assert len(_notes(owner_session, "hub_review_outcome")) == 4


@pytest.mark.usefixtures("reviews_on")
def test_a_second_run_finds_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    for _ in range(3):
        _approved(owner_session, batch.batch_id)

    assert publication.publish_due(restricted_session, RUN) == 3
    restricted_session.commit()
    assert publication.publish_due(restricted_session, RUN + dt.timedelta(days=1)) == 0
    restricted_session.commit()

    assert len(_notes(owner_session, "hub_reviews_published")) == 1
    assert len(_notes(owner_session, "hub_review_outcome")) == 3


# ---------------------------------------------------------------------------
# Moderation outcomes reach the author
# ---------------------------------------------------------------------------


def _admin(session: Session) -> PlatformAdminLens:
    """Give an administrator's lens over a fresh account.

    :param session: An arranging session
    :return: The lens
    """
    return PlatformAdminLens(account_id=account(session))


def _set(session: Session, review_id: uuid.UUID, status: str) -> None:
    """Move a stored review to ``pending``, ``published`` or ``held``.

    :param session: An arranging session
    :param review_id: The review
    :param status: The status
    :return: None
    """
    session.execute(
        sa.text(
            "UPDATE review SET status = CAST(:s AS hub_review_status), "
            "published_month = :m, approved_at = NULL WHERE id = :r"
        ),
        {
            "s": status,
            "m": dt.date(2026, 10, 1) if status in ("published", "held") else None,
            "r": review_id,
        },
    )
    session.commit()


@pytest.mark.usefixtures("reviews_on")
def test_rejection_and_removal_notify_author_without_code(
    owner_session: Session, restricted_session: Session
) -> None:
    now = dt.datetime.now(tz=dt.UTC)
    batch = public_batch(owner_session, title="HSC Chemistry")
    rejected = add_review(owner_session, batch.batch_id, account(owner_session))
    held = add_review(owner_session, batch.batch_id, account(owner_session))
    _set(owner_session, held, "held")
    approved = add_review(owner_session, batch.batch_id, account(owner_session))
    shown = _published(owner_session, batch.batch_id, 3)

    reviews.decide(
        restricted_session,
        _admin(owner_session),
        "review",
        rejected,
        approve=False,
        code="identifiable_child",
        now=now,
    )
    reviews.decide(
        restricted_session,
        _admin(owner_session),
        "review",
        held,
        approve=False,
        code="personal_info",
        now=now,
    )
    # An approval only queues the review: the publication tells the author.
    reviews.decide(
        restricted_session,
        _admin(owner_session),
        "review",
        approved,
        approve=True,
        code=None,
        now=now,
    )
    # An upheld report removes a published review, and [F9] one edited back
    # to pending after it was reported. Both are filed while the batch is
    # public; the third published review keeps no report.
    reported = [shown[0], shown[2]]
    for target in reported:
        reports.file(
            restricted_session,
            account(owner_session),
            "review",
            target,
            "abusive",
            None,
            now,
        )
    _set(owner_session, shown[2], "pending")
    for target in reported:
        report_id = owner_session.execute(
            sa.text("SELECT id FROM hub_report WHERE target_id = :t"), {"t": target}
        ).scalar_one()
        reports.decide(
            restricted_session, _admin(owner_session), report_id, "upheld", now
        )

    expected = [
        (_author(owner_session, rejected), "rejected"),
        (_author(owner_session, held), "removed"),
        (_author(owner_session, shown[0]), "removed"),
        (_author(owner_session, shown[2]), "removed"),
    ]
    notes = _notes(owner_session)
    assert sorted((n[0], n[2]) for n in notes) == sorted(expected)
    assert {(n[1], n[3], n[4]) for n in notes} == {
        ("hub_review_outcome", batch.batch_id, "HSC Chemistry")
    }
    # The code reaches the author's own my-review, never the inbox.
    codes = {"identifiable_child", "personal_info", "abusive", "other"}
    assert not any(code in str(n) for n in notes for code in codes)


@pytest.mark.usefixtures("reviews_on")
def test_a_rejection_that_rolls_back_sends_nothing(
    owner_session: Session,
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The message is in the decision's transaction, so it goes with it."""
    batch = public_batch(owner_session)
    review_id = add_review(owner_session, batch.batch_id, account(owner_session))

    def fail() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(restricted_session, "commit", fail)
    with pytest.raises(RuntimeError, match="commit failed"):
        reviews.decide(
            restricted_session,
            _admin(owner_session),
            "review",
            review_id,
            approve=False,
            code="off_topic",
            now=dt.datetime.now(tz=dt.UTC),
        )

    assert _review(owner_session, review_id).status == "pending"
    assert _notes(owner_session) == []


@pytest.mark.usefixtures("reviews_on")
def test_reply_rejection_tells_nobody(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    review_id = _published(owner_session, batch.batch_id, 1)[0]
    owner_session.execute(
        sa.text(
            "INSERT INTO review_reply (review_id, body, status) "
            "VALUES (:r, 'Thanks', 'pending')"
        ),
        {"r": review_id},
    )
    owner_session.commit()

    reviews.decide(
        restricted_session,
        _admin(owner_session),
        "reply",
        review_id,
        approve=False,
        code="off_topic",
        now=dt.datetime.now(tz=dt.UTC),
    )

    assert _notes(owner_session) == []


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def test_off_publishes_nothing_but_stamps_heartbeat(
    owner_session: Session,
    restricted_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review Focus 5: the job is gated, its heartbeat is not."""
    monkeypatch.delenv(HUB_REVIEWS_ENV, raising=False)
    batch = public_batch(owner_session)
    due = [_approved(owner_session, batch.batch_id) for _ in range(3)]
    monkeypatch.setattr(commands, "build_engine", lambda: restricted_engine)

    assert commands.main(["publish"]) == 0

    assert {_review(owner_session, r).status for r in due} == {"approved"}
    assert _notes(owner_session) == []
    assert _published_events(owner_session) == []
    assert _heartbeat(owner_session) is not None


@pytest.mark.usefixtures("reviews_on")
def test_command_publishes_commits_and_stamps(
    owner_session: Session,
    restricted_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = public_batch(owner_session)
    due = _approved(owner_session, batch.batch_id)
    monkeypatch.setattr(commands, "build_engine", lambda: restricted_engine)

    assert commands.main(["publish"]) == 0

    assert _review(owner_session, due).status == "published"
    assert len(_notes(owner_session, "hub_review_outcome")) == 1
    assert _heartbeat(owner_session) is not None
    with pytest.raises(SystemExit):
        commands.main(["nonsense"])
