"""Deletion is total: a review goes with its reply and every report on either.

Review Focus 4. After an author's delete, nothing in the schema refers to the
review's id except ``hub_moderation_event``, whose rows are bare ids and
closed codes kept for twelve months. The check walks every uuid column of
every table rather than a list of the tables we thought of, so a table a
later migration adds is covered without anyone remembering it.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.api.deps import reviewer_lens
from app.hub.public.invalidation import owner_paths
from app.hub.public.settings import HUB_REVIEWS_ENV
from app.local_time import bangladesh_today
from app.reviews import authoring, forget
from tests.reviews.support import (
    PublicBatch,
    account,
    add_review,
    attend,
    guardian_seat,
    hold_classes,
    public_batch,
)


def _now() -> dt.datetime:
    """Give the present.

    :return: Now, in UTC
    """
    return dt.datetime.now(tz=dt.UTC)


def _month() -> dt.date:
    """Give the first of this month in Bangladesh.

    :return: The date
    """
    return bangladesh_today().replace(day=1)


def _member(session: Session, batch_id: uuid.UUID, guardian: uuid.UUID) -> uuid.UUID:
    """Seat an eligible child for a guardian.

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


def _show(session: Session, review_id: uuid.UUID, status: str) -> None:
    """Move a review to ``published`` or ``held``.

    :param session: An arranging session
    :param review_id: The review
    :param status: ``published`` or ``held``
    :return: None
    """
    session.execute(
        sa.text(
            "UPDATE review SET status = CAST(:s AS hub_review_status), "
            "published_month = :m WHERE id = :r"
        ),
        {"s": status, "m": _month(), "r": review_id},
    )
    session.commit()


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


def _references(session: Session, value: uuid.UUID) -> dict[str, int]:
    """Count, per table and uuid column, the rows holding a value.

    :param session: An arranging session
    :param value: The id to look for
    :return: ``{"table.column": count}`` for every nonzero count
    """
    session.rollback()
    columns = session.execute(
        sa.text(
            "SELECT c.table_name, c.column_name FROM information_schema.columns c "
            "JOIN information_schema.tables t ON t.table_name = c.table_name "
            "AND t.table_schema = c.table_schema "
            "WHERE c.table_schema = 'public' AND c.data_type = 'uuid' "
            "AND t.table_type = 'BASE TABLE'"
        )
    ).all()
    found: dict[str, int] = {}
    for table, column in columns:
        count = session.execute(
            sa.text(f'SELECT count(*) FROM "{table}" WHERE "{column}" = :v'),  # noqa: S608
            {"v": value},
        ).scalar_one()
        if count:
            found[f"{table}.{column}"] = count
    return found


def _arrange(
    owner_session: Session, status: str
) -> tuple[PublicBatch, uuid.UUID, uuid.UUID]:
    """Arrange a reviewed, replied-to, doubly reported review.

    Three other published reviews put the batch over the threshold, so a
    ``published`` review under test is visible on the public page.

    :param owner_session: An arranging session
    :param status: The review's status
    :return: The batch, the author and the review id
    """
    batch = public_batch(owner_session)
    for _ in range(3):
        _show(
            owner_session,
            add_review(owner_session, batch.batch_id, account(owner_session)),
            "published",
        )
    guardian = account(owner_session)
    seat = _member(owner_session, batch.batch_id, guardian)
    review_id = add_review(owner_session, batch.batch_id, guardian, enrollment_id=seat)
    if status != "pending":
        _show(owner_session, review_id, status)
    owner_session.execute(
        sa.text(
            "INSERT INTO review_reply (review_id, body, status, published_month, "
            "written_by_account_id) VALUES (:r, 'Thank you', 'published', :m, :w)"
        ),
        {"r": review_id, "m": _month(), "w": batch.teacher_account_id},
    )
    owner_session.execute(
        sa.text(
            "INSERT INTO hub_moderation_event (id, event, target_kind, target_id, "
            "correlation_id) VALUES (gen_random_uuid(), 'report_filed', "
            "'review', :r, 'c-1')"
        ),
        {"r": review_id},
    )
    owner_session.commit()
    for _ in range(2):
        reporter = account(owner_session)
        _report(owner_session, "review", review_id, reporter)
        _report(owner_session, "reply", review_id, reporter)
    owner_session.execute(sa.text("DELETE FROM cdn_invalidation"))
    owner_session.commit()
    return batch, guardian, review_id


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


@pytest.mark.usefixtures("reviews_on")
@pytest.mark.parametrize(
    ("status", "visible"),
    [("held", False), ("pending", False), ("published", True)],
)
def test_delete_is_total(
    owner_session: Session,
    restricted_session: Session,
    status: str,
    visible: bool,
) -> None:
    batch, guardian, review_id = _arrange(owner_session, status)
    assert set(_references(owner_session, review_id)) == {
        "review.id",
        "review_reply.review_id",
        "hub_report.target_id",
        "hub_moderation_event.target_id",
    }
    lens = reviewer_lens(batch.batch_id, restricted_session, guardian)

    authoring.delete(restricted_session, lens, _now())

    assert _references(owner_session, review_id) == {
        "hub_moderation_event.target_id": 1
    }
    paths = set(owner_session.scalars(sa.text("SELECT path FROM cdn_invalidation")))
    if visible:
        assert set(owner_paths(_owner_slug(owner_session, batch))) <= paths
    else:
        assert paths == set()
    others = owner_session.execute(sa.text("SELECT count(*) FROM review")).scalar()
    assert others == 3


def test_delete_works_with_switch_off(
    owner_session: Session,
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The switch never gates a deletion."""
    monkeypatch.delenv(HUB_REVIEWS_ENV, raising=False)
    batch, guardian, review_id = _arrange(owner_session, "published")
    lens = reviewer_lens(batch.batch_id, restricted_session, guardian)

    authoring.delete(restricted_session, lens, _now())

    assert _references(owner_session, review_id) == {
        "hub_moderation_event.target_id": 1
    }


def test_delete_without_a_review_is_a_quiet_success(
    owner_session: Session, restricted_session: Session
) -> None:
    """An idempotent DELETE: the second call, like the first, answers nothing."""
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian)
    lens = reviewer_lens(batch.batch_id, restricted_session, guardian)

    authoring.delete(restricted_session, lens, _now())

    owner_session.rollback()
    assert owner_session.execute(sa.text("SELECT count(*) FROM review")).scalar() == 0
    paths = owner_session.execute(sa.text("SELECT count(*) FROM cdn_invalidation"))
    assert paths.scalar() == 0


def test_forget_commits_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    """Tasks 4 and 10 call it inside their own transaction."""
    _, _, review_id = _arrange(owner_session, "published")

    forget.forget(restricted_session, [review_id], _now())
    restricted_session.rollback()

    assert "review.id" in _references(owner_session, review_id)
    assert (
        owner_session.execute(sa.text("SELECT count(*) FROM cdn_invalidation")).scalar()
        == 0
    )


def test_forget_of_nothing_does_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    forget.forget(restricted_session, [], _now())

    assert (
        restricted_session.execute(
            sa.text("SELECT count(*) FROM cdn_invalidation")
        ).scalar()
        == 0
    )
