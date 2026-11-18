"""``0045`` adds reviews: ``review``, ``review_reply`` and their two views.

The views themselves -- the threshold, visibility and what they never read
-- are probed as the hub reader in
``tests/privacy/test_hub_public_review_view.py``. Here: the four enums, the
two tables' constraints and cascades, the governance entries, and that the
downgrade restores ``0044``'s shape -- and refuses while a review exists.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from typing import Final

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    HUB_REPLY_STATUS_VALUES,
    HUB_REVIEW_AUTHOR_ROLE_VALUES,
    HUB_REVIEW_STATUS_VALUES,
    HUB_REVIEW_TENURE_VALUES,
)
from app.governance.deletion import HARD_DELETE_SCOPES, Scope
from app.governance.dispositions import DISPOSITIONS, Disposition, RetentionClass
from tests.batches.conftest import _account, enroll, make_teacher
from tests.db.migration_support import _alembic_config, insert_account, stage_at

#: Each enum ``0045`` creates and its labels, in declaration order.
ENUMS: Final[dict[str, tuple[str, ...]]] = {
    "hub_review_status": (
        "pending",
        "approved",
        "published",
        "rejected",
        "removed",
        "held",
    ),
    "hub_reply_status": ("pending", "published", "rejected", "removed", "held"),
    "hub_review_author_role": ("guardian", "student"),
    "hub_review_tenure": ("lt_6m", "6_12m", "gt_1y"),
}

#: The relations ``0045`` creates, and their kinds.
RELATIONS: Final[dict[str, str]] = {
    "review": "r",
    "review_reply": "r",
    "hub_public_rating": "v",
    "hub_public_review": "v",
}

#: The first of this month: the only shape ``published_month`` takes.
MONTH: Final[dt.date] = dt.date(2026, 11, 1)


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0044``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0044") as engine:
        yield engine


def _listed_batch(session: Session) -> tuple[uuid.UUID, uuid.UUID]:
    """Arrange a batch with a published listing, which reviews hang off.

    :param session: An arranging session
    :return: ``(owner_id, batch_id)``
    """
    teacher = make_teacher(session)
    session.execute(
        sa.text(
            "INSERT INTO batch_listing (batch_id, owner_id, slug, status, "
            "public_title, description_en, class_levels, subject_tags, "
            "show_fee, show_schedule, published_at) VALUES "
            "(:b, :o, 'class-9-maths', 'published', 'Class 9 maths', "
            "'Weekly maths', '{class_9}', '{maths}', true, true, now())"
        ),
        {"b": teacher.batch_id, "o": teacher.owner_id},
    )
    session.commit()
    return teacher.owner_id, teacher.batch_id


def _review(
    session: Session,
    batch_id: uuid.UUID,
    *,
    author: uuid.UUID | None = None,
    status: str = "pending",
    published_month: dt.date | None = None,
    approved_at: dt.datetime | None = None,
    rejection_code: str | None = None,
    author_role: str = "guardian",
    rating: int = 4,
    body: str | None = "Clear and patient.",
    enrollment_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert one review by raw SQL, letting the server mint its id.

    :param session: An arranging session
    :param batch_id: The reviewed batch
    :param author: The author's account; a fresh one by default
    :param status: Its status
    :param published_month: Its publication month
    :param approved_at: When a moderator approved it
    :param rejection_code: Why it was rejected or removed
    :param author_role: ``guardian`` or ``student``
    :param rating: 1 to 5
    :param body: Its text
    :param enrollment_id: The seat that evidenced eligibility
    :return: The new review's id
    """
    review_id: uuid.UUID = session.execute(
        sa.text(
            "INSERT INTO review (batch_id, author_account_id, enrollment_id, "
            "author_role, rating, body, status, tenure_bucket, published_month, "
            "approved_at, rejection_code) VALUES (:b, :a, :e, "
            "CAST(:role AS hub_review_author_role), :rating, :body, "
            "CAST(:st AS hub_review_status), 'lt_6m', :pm, :aa, :rc) "
            "RETURNING id"
        ),
        {
            "b": batch_id,
            "a": author if author is not None else _account(session),
            "e": enrollment_id,
            "role": author_role,
            "rating": rating,
            "body": body,
            "st": status,
            "pm": published_month,
            "aa": approved_at,
            "rc": rejection_code,
        },
    ).scalar_one()
    return review_id


def _valid(status: str) -> dict[str, object]:
    """Build the status-bound columns a review in one status must carry.

    :param status: A review status
    :return: Keyword arguments for :func:`_review`
    """
    return {
        "status": status,
        "published_month": MONTH if status in ("published", "held") else None,
        "approved_at": dt.datetime.now(tz=dt.UTC) if status == "approved" else None,
        "rejection_code": (
            "personal_info" if status in ("rejected", "removed") else None
        ),
    }


def test_0045_creates_tables_enums_and_views(staged: Engine) -> None:
    """Upgrade creates the four enums, both tables and both views; downgrade drops all.

    :param staged: The engine staged at ``0044``
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    command.upgrade(_alembic_config(url), "0045")

    with staged.connect() as connection:
        labels = {
            name: tuple(
                connection.execute(
                    sa.text(
                        "SELECT e.enumlabel FROM pg_enum e "
                        "JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = :n ORDER BY e.enumsortorder"
                    ),
                    {"n": name},
                ).scalars()
            )
            for name in ENUMS
        }
        kinds = dict(
            connection.execute(
                sa.text(
                    "SELECT relname, relkind::text FROM pg_class "
                    "WHERE relname = ANY(:r)"
                ),
                {"r": sorted(RELATIONS)},
            ).all()
        )
    assert labels == ENUMS
    assert (
        HUB_REVIEW_STATUS_VALUES,
        HUB_REPLY_STATUS_VALUES,
        HUB_REVIEW_AUTHOR_ROLE_VALUES,
        HUB_REVIEW_TENURE_VALUES,
    ) == tuple(ENUMS.values())
    assert kinds == RELATIONS

    command.downgrade(_alembic_config(url), "0044")

    with staged.connect() as connection:
        left = connection.execute(
            sa.text("SELECT count(*) FROM pg_class WHERE relname = ANY(:r)"),
            {"r": sorted(RELATIONS)},
        ).scalar_one()
        enums_left = connection.execute(
            sa.text("SELECT count(*) FROM pg_type WHERE typname = ANY(:n)"),
            {"n": sorted(ENUMS)},
        ).scalar_one()
    assert (left, enums_left) == (0, 0)


def test_0045_downgrade_refuses_while_a_review_exists(staged: Engine) -> None:
    """A review is what a guardian wrote and cannot be rebuilt.

    :param staged: The engine staged at ``0044``
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    command.upgrade(_alembic_config(url), "0045")
    owner_id, batch_id = uuid.uuid4(), uuid.uuid4()
    with staged.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO owner (id, account_id, created_at) VALUES (:o, :a, now())"
            ),
            {"o": owner_id, "a": insert_account(connection, "+8801711000045")},
        )
        connection.execute(
            sa.text(
                "INSERT INTO batch (id, owner_id, name, marksheet_visible, active, "
                "created_at) VALUES (:b, :o, 'B', true, true, now())"
            ),
            {"b": batch_id, "o": owner_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO batch_listing (batch_id, owner_id, slug, public_title, "
                "class_levels, subject_tags, show_fee, show_schedule) VALUES "
                "(:b, :o, 'class-9', 'Class 9', '{class_9}', '{maths}', true, true)"
            ),
            {"b": batch_id, "o": owner_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO review (batch_id, author_account_id, author_role, "
                "rating, tenure_bucket) VALUES (:b, :a, 'guardian', 5, 'lt_6m')"
            ),
            {"b": batch_id, "a": insert_account(connection, "+8801711000046")},
        )

    with pytest.raises(Exception, match="Cannot downgrade 0045"):
        command.downgrade(_alembic_config(url), "0044")


def test_review_id_is_a_random_uuid_minted_by_the_server(
    owner_session: Session,
) -> None:
    """A raw-SQL insert gets a version-4 id: order within a month says nothing.

    Call 10 orders a page by ``published_month DESC, id``, which hides the
    submission order only while the id is random. A raw ``INSERT`` bypasses
    the ORM default, so the column's own default must be random too [F22].

    :param owner_session: An arranging session
    :return: None
    """
    _, batch_id = _listed_batch(owner_session)
    ids = [_review(owner_session, batch_id) for _ in range(3)]
    owner_session.commit()

    assert {review_id.version for review_id in ids} == {4}
    assert len(set(ids)) == 3


@pytest.mark.parametrize("status", ENUMS["hub_review_status"])
def test_published_month_iff_published_or_held(
    owner_session: Session, status: str
) -> None:
    """Only a published or held review has a month, and both must.

    :param owner_session: An arranging session
    :param status: The status to try both ways
    :return: None
    """
    _, batch_id = _listed_batch(owner_session)
    wrong = {**_valid(status)}
    wrong["published_month"] = None if wrong["published_month"] else MONTH

    with pytest.raises(IntegrityError, match="ck_review_published_month_iff_shown"):
        _review(owner_session, batch_id, **wrong)  # type: ignore[arg-type]
    owner_session.rollback()

    _review(owner_session, batch_id, **_valid(status))  # type: ignore[arg-type]
    owner_session.commit()


@pytest.mark.parametrize("table", ["review", "review_reply"])
def test_published_month_is_the_first_of_a_month(
    owner_session: Session, table: str
) -> None:
    """A month is stored as its first day; any other day would be a date.

    :param owner_session: An arranging session
    :param table: Which table's month to try
    :return: None
    """
    _, batch_id = _listed_batch(owner_session)
    if table == "review":
        with pytest.raises(IntegrityError, match="ck_review_published_month_first"):
            _review(
                owner_session,
                batch_id,
                status="published",
                published_month=dt.date(2026, 11, 14),
            )
        return
    review_id = _review(owner_session, batch_id, **_valid("published"))  # type: ignore[arg-type]
    owner_session.commit()
    with pytest.raises(IntegrityError, match="ck_review_reply_published_month_first"):
        _reply(
            owner_session,
            review_id,
            status="published",
            published_month=dt.date(2026, 11, 2),
        )


@pytest.mark.parametrize("status", ["rejected", "removed"])
def test_rejection_needs_code(owner_session: Session, status: str) -> None:
    """A rejected or removed review, or reply, says why in a closed code.

    :param owner_session: An arranging session
    :param status: ``rejected`` or ``removed``
    :return: None
    """
    _, batch_id = _listed_batch(owner_session)
    with pytest.raises(IntegrityError, match="ck_review_rejection_code"):
        _review(owner_session, batch_id, status=status)
    owner_session.rollback()

    review_id = _review(owner_session, batch_id, **_valid("published"))  # type: ignore[arg-type]
    owner_session.commit()
    with pytest.raises(IntegrityError, match="ck_review_reply_rejection_code"):
        _reply(owner_session, review_id, status=status)
    owner_session.rollback()

    _reply(owner_session, review_id, status=status, rejection_code="abusive")
    owner_session.commit()


@pytest.mark.parametrize("status", ENUMS["hub_review_status"])
def test_approved_iff_approved_at(owner_session: Session, status: str) -> None:
    """``approved_at`` is the weekly job's queue: set exactly while approved.

    :param owner_session: An arranging session
    :param status: The status to try both ways
    :return: None
    """
    _, batch_id = _listed_batch(owner_session)
    wrong = {**_valid(status)}
    wrong["approved_at"] = None if wrong["approved_at"] else dt.datetime.now(tz=dt.UTC)

    with pytest.raises(IntegrityError, match="ck_review_approved_at_iff_approved"):
        _review(owner_session, batch_id, **wrong)  # type: ignore[arg-type]
    owner_session.rollback()

    _review(owner_session, batch_id, **_valid(status))  # type: ignore[arg-type]
    owner_session.commit()


def test_one_review_per_author_per_batch(owner_session: Session) -> None:
    """A guardian with two children in one batch writes one review.

    The same guardian may review another batch, and another guardian this one.

    :param owner_session: An arranging session
    :return: None
    """
    _, batch_id = _listed_batch(owner_session)
    _, other_batch = _listed_batch(owner_session)
    author = _account(owner_session)
    _review(owner_session, batch_id, author=author)
    _review(owner_session, other_batch, author=author)
    _review(owner_session, batch_id)
    owner_session.commit()

    with pytest.raises(IntegrityError, match="uq_review_batch_author"):
        _review(owner_session, batch_id, author=author, rating=1)


def test_v1_reviews_are_guardians_only(owner_session: Session) -> None:
    """``student`` is a label the enum holds for later and a CHECK refuses now.

    :param owner_session: An arranging session
    :return: None
    """
    _, batch_id = _listed_batch(owner_session)
    with pytest.raises(IntegrityError, match="ck_review_author_role_v1"):
        _review(owner_session, batch_id, author_role="student")


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("rating", 0, "ck_review_rating"),
        ("rating", 6, "ck_review_rating"),
        ("body", "x" * 1001, "ck_review_body"),
    ],
)
def test_review_content_bounds(
    owner_session: Session, column: str, value: object, constraint: str
) -> None:
    """A rating is 1 to 5 and a body at most 1000 characters.

    :param owner_session: An arranging session
    :param column: The column given a value outside its bounds
    :param value: That value
    :param constraint: The CHECK that refuses it
    :return: None
    """
    _, batch_id = _listed_batch(owner_session)
    _review(owner_session, batch_id, rating=1, body="x" * 1000)
    _review(owner_session, batch_id, rating=5, body=None)
    owner_session.commit()

    with pytest.raises(IntegrityError, match=constraint):
        _review(owner_session, batch_id, **{column: value})  # type: ignore[arg-type]


@pytest.mark.parametrize("body", ["", "x" * 1001])
def test_reply_body_bounds(owner_session: Session, body: str) -> None:
    """A reply has 1 to 1000 characters.

    :param owner_session: An arranging session
    :param body: A body outside the bounds
    :return: None
    """
    _, batch_id = _listed_batch(owner_session)
    review_id = _review(owner_session, batch_id)
    owner_session.commit()

    with pytest.raises(IntegrityError, match="ck_review_reply_body"):
        _reply(owner_session, review_id, body=body)
    owner_session.rollback()

    _reply(owner_session, review_id, body="x" * 1000)
    owner_session.commit()


def _reply(
    session: Session,
    review_id: uuid.UUID,
    *,
    body: str = "Thank you.",
    status: str = "pending",
    published_month: dt.date | None = None,
    rejection_code: str | None = None,
    written_by: uuid.UUID | None = None,
) -> None:
    """Insert the reply to one review.

    :param session: An arranging session
    :param review_id: The review answered
    :param body: Its text
    :param status: Its status
    :param published_month: Its publication month
    :param rejection_code: Why it was rejected or removed
    :param written_by: The account that wrote it
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO review_reply (review_id, body, status, published_month, "
            "rejection_code, written_by_account_id) VALUES (:r, :body, "
            "CAST(:st AS hub_reply_status), :pm, :rc, :w)"
        ),
        {
            "r": review_id,
            "body": body,
            "st": status,
            "pm": published_month,
            "rc": rejection_code,
            "w": written_by,
        },
    )


def test_reply_published_month_iff_published_or_held(owner_session: Session) -> None:
    """A reply carries the review's month rule: shown or held, and only then.

    :param owner_session: An arranging session
    :return: None
    """
    _, batch_id = _listed_batch(owner_session)
    for status in ENUMS["hub_reply_status"]:
        review_id = _review(owner_session, batch_id)
        owner_session.commit()
        shown = status in ("published", "held")
        code = "abusive" if status in ("rejected", "removed") else None
        with pytest.raises(
            IntegrityError, match="ck_review_reply_published_month_iff_shown"
        ):
            _reply(
                owner_session,
                review_id,
                status=status,
                published_month=None if shown else MONTH,
                rejection_code=code,
            )
        owner_session.rollback()
        _reply(
            owner_session,
            review_id,
            status=status,
            published_month=MONTH if shown else None,
            rejection_code=code,
        )
        owner_session.commit()


def test_cascades_follow_the_owner_of_each_row(owner_session: Session) -> None:
    """Author and listing take the review; the seat and writer are only cleared.

    * deleting the author's account deletes the review and its reply;
    * deleting the batch listing deletes the reviews of that batch;
    * deleting the evidencing seat leaves the review, unlinked;
    * deleting the reply's writer leaves a centre's reply, unattributed.

    :param owner_session: An arranging session
    :return: None
    """
    _, batch_id = _listed_batch(owner_session)
    author = _account(owner_session)
    writer = _account(owner_session)
    seat = enroll(
        owner_session,
        batch_id=batch_id,
        display_name="Rahim",
        guardian_account_id=author,
        guardian_decision="accepted",
    )
    by_author = _review(owner_session, batch_id, author=author, enrollment_id=seat)
    kept = _review(owner_session, batch_id)
    _reply(owner_session, by_author, written_by=writer)
    _reply(owner_session, kept, written_by=writer)
    owner_session.commit()

    def count(sql: str) -> int:
        return int(owner_session.execute(sa.text(sql)).scalar_one())

    owner_session.execute(sa.text("DELETE FROM enrollment WHERE id = :e"), {"e": seat})
    owner_session.commit()
    assert count("SELECT count(*) FROM review WHERE enrollment_id IS NOT NULL") == 0
    assert count("SELECT count(*) FROM review") == 2

    owner_session.execute(sa.text("DELETE FROM account WHERE id = :a"), {"a": writer})
    owner_session.commit()
    assert count("SELECT count(*) FROM review_reply") == 2
    assert (
        count("SELECT count(*) FROM review_reply WHERE written_by_account_id IS NULL")
        == 2
    )

    owner_session.execute(sa.text("DELETE FROM account WHERE id = :a"), {"a": author})
    owner_session.commit()
    assert count("SELECT count(*) FROM review") == 1
    assert count("SELECT count(*) FROM review_reply") == 1

    owner_session.execute(
        sa.text("DELETE FROM batch_listing WHERE batch_id = :b"), {"b": batch_id}
    )
    owner_session.commit()
    assert count("SELECT count(*) FROM review") == 0
    assert count("SELECT count(*) FROM review_reply") == 0


def test_review_dispositions() -> None:
    """A review goes with its author; its reply goes with the review.

    ``review`` is reached by its author column, and also falls with a solo
    owner's batch listing through ``ON DELETE CASCADE``. ``review_reply`` is
    reached only through ``review``: a centre's reply survives a manager's
    deletion, with its writer cleared.

    :return: None
    """
    review = DISPOSITIONS["review"]
    reply = DISPOSITIONS["review_reply"]

    assert (review.disposition, review.retention) == (
        Disposition.HARD_DELETE,
        RetentionClass.LIFE_OF_ACCOUNT,
    )
    assert (reply.disposition, reply.retention) == (
        Disposition.HARD_DELETE,
        RetentionClass.LIFE_OF_ACCOUNT,
    )
    assert "listing" in review.basis
    assert HARD_DELETE_SCOPES["review"].scope is Scope.ACCOUNT_COLUMN
    assert HARD_DELETE_SCOPES["review"].column == "author_account_id"
    assert HARD_DELETE_SCOPES["review_reply"].scope is Scope.VIA_CASCADE
    assert HARD_DELETE_SCOPES["review_reply"].column is None
