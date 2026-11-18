"""``hub_public_review`` and ``hub_public_rating``: the k-threshold, in SQL.

**These views are the authorization boundary for reviews**, so these tests
were written before the migration (Review Focus 2). A batch shows review
text, an average, a distribution -- or even a count -- only once it holds
:data:`THRESHOLD` published reviews [F18]: below that, a count of one or two
helps a teacher who knows which family just became eligible work out who
wrote it. No caller, the teacher API included, reads anything below the
threshold, because no row exists for it to read.

Every case reads the views as the hub reader, against rows arranged as the
table owner. A review is visible exactly where its batch is: in
``hub_public_batch`` (listing published, batch active, owner listing
published).
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Final

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.roles import APP_ROLE, HUB_READER_ROLE
from app.hub.public.db import as_hub_reader
from tests.batches.conftest import _account, make_teacher
from tests.privacy.test_hub_public_views import (
    PRIVATE_TABLES,
    _batch_listing,
    _owner_listing,
)

#: Published reviews a batch needs before anything about them is public.
THRESHOLD: Final[int] = 3

#: The month a published review carries in these tests.
MONTH: Final[dt.date] = dt.date(2026, 10, 1)

#: Exactly what ``hub_public_review`` shows, in order.
REVIEW_COLUMNS: Final[tuple[str, ...]] = (
    "id",
    "batch_id",
    "rating",
    "body",
    "tenure_bucket",
    "author_role",
    "published_month",
    "reply_body",
    "reply_month",
)

#: Exactly what ``hub_public_rating`` shows, in order.
RATING_COLUMNS: Final[tuple[str, ...]] = (
    "batch_id",
    "review_count",
    "average_tenths",
    "rating_sum",
    "distribution",
)

#: Columns that would join a review to a person, a seat or a moment
#: finer than a month. No view may depend on any of them.
IDENTITY_COLUMNS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("review", "author_account_id"),
        ("review", "enrollment_id"),
        ("review", "submitted_at"),
        ("review", "edited_at"),
        ("review", "approved_at"),
        ("review", "decided_at"),
        ("review", "decided_by_account_id"),
        ("review", "rejection_code"),
        ("review_reply", "written_by_account_id"),
        ("review_reply", "created_at"),
        ("review_reply", "edited_at"),
        ("review_reply", "decided_at"),
        ("review_reply", "decided_by_account_id"),
        ("review_reply", "rejection_code"),
    }
)

#: Every review status that is not ``published``.
NOT_PUBLISHED: Final[tuple[str, ...]] = (
    "pending",
    "approved",
    "held",
    "rejected",
    "removed",
)

#: Both views and every view they read, followed through ``pg_depend``.
_DEPENDS: Final[str] = (
    "WITH RECURSIVE reads(view_oid) AS ("
    "  SELECT oid FROM pg_class WHERE relname = ANY(:roots)"
    "  UNION"
    "  SELECT d.refobjid FROM reads"
    "  JOIN pg_rewrite r ON r.ev_class = reads.view_oid"
    "  JOIN pg_depend d ON d.classid = 'pg_rewrite'::regclass"
    "   AND d.objid = r.oid AND d.refclassid = 'pg_class'::regclass"
    "  JOIN pg_class t ON t.oid = d.refobjid"
    "  WHERE t.relkind = 'v' AND t.oid <> reads.view_oid"
    ") "
    "SELECT DISTINCT v.relname AS view, t.relname AS tbl, "
    "t.relkind::text AS kind, a.attname AS col FROM reads "
    "JOIN pg_class v ON v.oid = reads.view_oid "
    "JOIN pg_rewrite r ON r.ev_class = v.oid "
    "JOIN pg_depend d ON d.classid = 'pg_rewrite'::regclass "
    "AND d.objid = r.oid AND d.refclassid = 'pg_class'::regclass "
    "JOIN pg_class t ON t.oid = d.refobjid "
    "LEFT JOIN pg_attribute a ON a.attrelid = t.oid "
    "AND a.attnum = d.refobjsubid "
    "WHERE t.oid <> v.oid"
)


def _live_batch(session: Session, slug: str = "live-tutor") -> uuid.UUID:
    """Arrange a tutor whose listing and batch listing are both published.

    :param session: An arranging session
    :param slug: The owner's slug
    :return: The batch id
    """
    teacher = make_teacher(session)
    _owner_listing(session, teacher.owner_id, slug=slug)
    _batch_listing(session, teacher.batch_id, teacher.owner_id)
    return teacher.batch_id


def _review(
    session: Session,
    batch_id: uuid.UUID,
    rating: int,
    *,
    status: str = "published",
    body: str | None = "Clear and patient.",
) -> uuid.UUID:
    """Insert one review by a fresh guardian, carrying what its status needs.

    :param session: An arranging session
    :param batch_id: The reviewed batch
    :param rating: 1 to 5
    :param status: Its status
    :param body: Its text
    :return: The review id
    """
    review_id: uuid.UUID = session.execute(
        sa.text(
            "INSERT INTO review (batch_id, author_account_id, author_role, "
            "rating, body, status, tenure_bucket, published_month, approved_at, "
            "rejection_code) VALUES (:b, :a, 'guardian', :rating, :body, "
            "CAST(:st AS hub_review_status), '6_12m', :pm, :aa, :rc) RETURNING id"
        ),
        {
            "b": batch_id,
            "a": _account(session),
            "rating": rating,
            "body": body,
            "st": status,
            "pm": MONTH if status in ("published", "held") else None,
            "aa": dt.datetime.now(tz=dt.UTC) if status == "approved" else None,
            "rc": "abusive" if status in ("rejected", "removed") else None,
        },
    ).scalar_one()
    session.commit()
    return review_id


def _reply(session: Session, review_id: uuid.UUID, status: str) -> None:
    """Insert the reply to one review.

    :param session: An arranging session
    :param review_id: The review answered
    :param status: The reply's status
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO review_reply (review_id, body, status, published_month, "
            "rejection_code) VALUES (:r, 'Thank you for writing.', "
            "CAST(:st AS hub_reply_status), :pm, :rc)"
        ),
        {
            "r": review_id,
            "st": status,
            "pm": dt.date(2026, 11, 1) if status in ("published", "held") else None,
            "rc": "abusive" if status in ("rejected", "removed") else None,
        },
    )
    session.commit()


def _ratings(session: Session) -> dict[uuid.UUID, tuple[object, ...]]:
    """Read ``hub_public_rating`` as the hub reader.

    :param session: The application role's session; left as the reader
    :return: Batch id to ``(count, average, sum, distribution)``
    """
    as_hub_reader(session)
    return {
        row.batch_id: (
            row.review_count,
            row.average_tenths,
            row.rating_sum,
            row.distribution,
        )
        for row in session.execute(sa.text("SELECT * FROM hub_public_rating"))
    }


def _reviews(session: Session) -> set[uuid.UUID]:
    """Read the review ids ``hub_public_review`` shows, as the hub reader.

    :param session: The application role's session; left as the reader
    :return: The visible review ids
    """
    as_hub_reader(session)
    return set(session.execute(sa.text("SELECT id FROM hub_public_review")).scalars())


def test_threshold_is_enforced_by_the_views(
    owner_session: Session, restricted_session: Session
) -> None:
    """Two published reviews show nothing at all; the third shows all three.

    Review Focus 2. Below the threshold neither view has a row for the
    batch: no text, no average, no distribution and, under F18, no count.
    Reviews in every other status count toward nothing, so a batch with
    two published and one of each other status is still below it.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    batch_id = _live_batch(owner_session)
    first = _review(owner_session, batch_id, 5)
    second = _review(owner_session, batch_id, 4)
    for status in NOT_PUBLISHED:
        _review(owner_session, batch_id, 1, status=status)

    assert _reviews(restricted_session) == set()
    restricted_session.rollback()
    assert _ratings(restricted_session) == {}
    restricted_session.rollback()

    third = _review(owner_session, batch_id, 4)

    assert _reviews(restricted_session) == {first, second, third}
    restricted_session.rollback()
    assert _ratings(restricted_session) == {batch_id: (3, 43, 13, [0, 0, 0, 2, 1])}
    restricted_session.rollback()

    # Dropping back to two -- removed, held, or deleted -- hides it all.
    owner_session.execute(
        sa.text(
            "UPDATE review SET status = 'held' WHERE id = :r",
        ),
        {"r": third},
    )
    owner_session.commit()
    assert _reviews(restricted_session) == set()
    restricted_session.rollback()
    assert _ratings(restricted_session) == {}


def test_threshold_is_counted_per_batch(
    owner_session: Session, restricted_session: Session
) -> None:
    """Three reviews spread over two batches of one owner put neither over.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    teacher = make_teacher(owner_session)
    _owner_listing(owner_session, teacher.owner_id, slug="two-batches")
    _batch_listing(owner_session, teacher.batch_id, teacher.owner_id)
    other = make_teacher(owner_session)
    _owner_listing(owner_session, other.owner_id, slug="other-tutor")
    _batch_listing(owner_session, other.batch_id, other.owner_id)
    for rating in (5, 4):
        _review(owner_session, teacher.batch_id, rating)
    _review(owner_session, other.batch_id, 3)

    assert _reviews(restricted_session) == set()
    restricted_session.rollback()
    assert _ratings(restricted_session) == {}


def _hide(session: Session, case: str, batch_id: uuid.UUID) -> None:
    """Make a reviewed batch invisible in one of the ways a page disappears.

    :param session: An arranging session
    :param case: Which way
    :param batch_id: The batch
    :return: None
    """
    statements = {
        "owner_draft": "UPDATE owner_listing SET status = 'draft' "
        "WHERE owner_id = (SELECT owner_id FROM batch WHERE id = :b)",
        "owner_suspended": "UPDATE owner_listing SET status = 'suspended' "
        "WHERE owner_id = (SELECT owner_id FROM batch WHERE id = :b)",
        "batch_draft": "UPDATE batch_listing SET status = 'draft' WHERE batch_id = :b",
        "batch_hidden": "UPDATE batch_listing SET status = 'hidden' "
        "WHERE batch_id = :b",
        "batch_inactive": "UPDATE batch SET active = false WHERE id = :b",
    }
    session.execute(sa.text(statements[case]), {"b": batch_id})
    session.commit()


@pytest.mark.parametrize(
    "case",
    ["owner_draft", "owner_suspended", "batch_draft", "batch_hidden", "batch_inactive"],
)
def test_views_hide_reviews_of_invisible_batches(
    owner_session: Session, restricted_session: Session, case: str
) -> None:
    """A batch over the threshold shows nothing once its page is not public.

    A second, untouched batch keeps showing, so the test is not vacuous.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :param case: How the page stops being public
    :return: None
    """
    hidden = _live_batch(owner_session, "hidden-tutor")
    shown = _live_batch(owner_session, "shown-tutor")
    for batch_id in (hidden, shown):
        for rating in (5, 5, 4):
            _review(owner_session, batch_id, rating)
    _hide(owner_session, case, hidden)

    as_hub_reader(restricted_session)
    batches = set(
        restricted_session.execute(
            sa.text("SELECT batch_id FROM hub_public_review")
        ).scalars()
    )
    assert batches == {shown}
    restricted_session.rollback()
    assert set(_ratings(restricted_session)) == {shown}


@pytest.mark.parametrize("status", ["pending", "rejected", "removed", "held"])
def test_unpublished_reply_is_not_exposed(
    owner_session: Session, restricted_session: Session, status: str
) -> None:
    """Only a published reply's text and month reach the view.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :param status: A reply status that is not public
    :return: None
    """
    batch_id = _live_batch(owner_session)
    answered = _review(owner_session, batch_id, 5)
    unanswered = _review(owner_session, batch_id, 4)
    published = _review(owner_session, batch_id, 3)
    _reply(owner_session, answered, status)
    _reply(owner_session, published, "published")

    as_hub_reader(restricted_session)
    replies = {
        row.id: (row.reply_body, row.reply_month)
        for row in restricted_session.execute(
            sa.text("SELECT id, reply_body, reply_month FROM hub_public_review")
        )
    }

    assert replies == {
        answered: (None, None),
        unanswered: (None, None),
        published: ("Thank you for writing.", dt.date(2026, 11, 1)),
    }


@pytest.mark.parametrize(
    ("ratings", "tenths"),
    [
        ([5, 4, 4], 43),
        ([5, 4, 4, 4], 43),
        ([1, 2, 2], 17),
        ([5, 5, 5], 50),
        ([1, 1, 1], 10),
        ([4, 4, 5, 5], 45),
    ],
)
def test_average_tenths_cases(
    owner_session: Session,
    restricted_session: Session,
    ratings: list[int],
    tenths: int,
) -> None:
    """The average is integer tenths, rounded half up, in SQL.

    ``[5, 4, 4, 4]`` is 4.25, which rounds up to 43; ``[4, 4, 5, 5]`` is
    exactly 4.5.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :param ratings: The published ratings
    :param tenths: The expected average, in tenths
    :return: None
    """
    batch_id = _live_batch(owner_session)
    for rating in ratings:
        _review(owner_session, batch_id, rating)

    count, average, total, distribution = _ratings(restricted_session)[batch_id]

    assert (count, average, total) == (len(ratings), tenths, sum(ratings))
    assert distribution == [ratings.count(star) for star in range(1, 6)]


def test_distribution_runs_from_one_star_to_five(
    owner_session: Session, restricted_session: Session
) -> None:
    """``[5, 4, 4]`` is ``[0, 0, 0, 2, 1]``: one star first.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    batch_id = _live_batch(owner_session)
    for rating in (5, 4, 4):
        _review(owner_session, batch_id, rating)

    assert _ratings(restricted_session)[batch_id][3] == [0, 0, 0, 2, 1]


def test_review_view_shows_exactly_the_public_columns(
    owner_session: Session, restricted_session: Session
) -> None:
    """No name, no phone, no seat, no author and no time finer than a month.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    batch_id = _live_batch(owner_session)
    ids = [_review(owner_session, batch_id, r) for r in (5, 4, 3)]

    as_hub_reader(restricted_session)
    result = restricted_session.execute(
        sa.text("SELECT * FROM hub_public_review ORDER BY rating DESC")
    )
    rows = [dict(row) for row in result.mappings()]
    assert tuple(result.keys()) == REVIEW_COLUMNS
    assert rows[0] == {
        "id": ids[0],
        "batch_id": batch_id,
        "rating": 5,
        "body": "Clear and patient.",
        "tenure_bucket": "6_12m",
        "author_role": "guardian",
        "published_month": MONTH,
        "reply_body": None,
        "reply_month": None,
    }
    restricted_session.rollback()

    as_hub_reader(restricted_session)
    rating = restricted_session.execute(sa.text("SELECT * FROM hub_public_rating"))
    assert tuple(rating.keys()) == RATING_COLUMNS


def test_review_views_never_depend_on_identity_columns(
    restricted_session: Session,
) -> None:
    """What PostgreSQL resolved, not what the text says.

    Followed through every view the two read. Of the two tables, only the
    public columns and the ones the filter needs are read; no private
    table is reached at all.

    :param restricted_session: A session as the application role
    :return: None
    """
    roots = ["hub_public_review", "hub_public_rating"]
    for view in roots:
        text = restricted_session.execute(
            sa.text("SELECT definition FROM pg_views WHERE viewname = :v"),
            {"v": view},
        ).scalar_one()
        for table in PRIVATE_TABLES:
            assert not re.search(rf"\b{table}\b", text), (view, table)

    depends = restricted_session.execute(sa.text(_DEPENDS), {"roots": roots}).all()
    read = {(row.tbl, row.col) for row in depends if row.kind == "r"}
    tables = {table for table, _ in read}

    assert {"review", "review_reply", "batch_listing"} <= tables  # not vacuous
    assert tables.isdisjoint(PRIVATE_TABLES), tables
    assert read.isdisjoint(IDENTITY_COLUMNS), sorted(read & IDENTITY_COLUMNS)
    assert {col for table, col in read if table == "review"} == {
        "id",
        "batch_id",
        "rating",
        "body",
        "status",
        "tenure_bucket",
        "author_role",
        "published_month",
    }
    assert {col for table, col in read if table == "review_reply"} == {
        "review_id",
        "body",
        "status",
        "published_month",
    }


@pytest.mark.parametrize("view", ["hub_public_review", "hub_public_rating"])
@pytest.mark.parametrize("role", [HUB_READER_ROLE, APP_ROLE])
def test_review_views_are_read_only_to_reader_and_app(
    restricted_session: Session, view: str, role: str
) -> None:
    """Both may SELECT each view (Call 6); neither may write it.

    :param restricted_session: A session as the application role
    :param view: The view
    :param role: The grantee
    :return: None
    """
    privileges = restricted_session.execute(
        sa.text(
            "SELECT has_table_privilege(:r, :v, 'SELECT'), "
            "has_table_privilege(:r, :v, 'INSERT') "
            "OR has_table_privilege(:r, :v, 'UPDATE') "
            "OR has_table_privilege(:r, :v, 'DELETE')"
        ),
        {"r": role, "v": view},
    ).one()

    assert tuple(privileges) == (True, False)


def test_review_views_are_security_barrier(restricted_session: Session) -> None:
    """A caller's predicate cannot run beneath either view's filter.

    :param restricted_session: A session as the application role
    :return: None
    """
    options = dict(
        restricted_session.execute(
            sa.text(
                "SELECT relname, reloptions FROM pg_class "
                "WHERE relkind = 'v' AND relname = ANY(:v)"
            ),
            {"v": ["hub_public_review", "hub_public_rating"]},
        ).all()
    )

    assert {v: "security_barrier=true" in (o or []) for v, o in options.items()} == {
        "hub_public_review": True,
        "hub_public_rating": True,
    }
