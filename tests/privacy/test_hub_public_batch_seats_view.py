"""``hub_public_batch_seats``: a public batch's seats, only where shown.

A batch's seat counts are two numbers its owner typed, never counted from
enrollments [0048]. The view has a row for a batch exactly while that
batch is in ``hub_public_batch`` -- published, active, under a published
owner -- AND its owner chose ``show_seats``. It publishes the day the
counts last changed, never the time.

Every case reads the view as the hub reader, against rows arranged as the
table owner.
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
from tests.batches.conftest import make_teacher
from tests.privacy.test_hub_public_views import (
    PRIVATE_TABLES,
    _batch_listing,
    _owner_listing,
)

VIEW: Final[str] = "hub_public_batch_seats"

#: Exactly what the view shows, in order.
COLUMNS: Final[tuple[str, ...]] = (
    "batch_id",
    "seat_capacity",
    "seats_free",
    "seats_updated_on",
)

#: Every column the view itself depends on, by ``(relation, column)``.
#: Which batches are public is ``hub_public_batch``'s business, probed in
#: ``test_hub_public_views.py``.
DIRECT_READS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("hub_public_batch", "batch_id"),
        ("batch_listing", "batch_id"),
        ("batch_listing", "show_seats"),
        ("batch_listing", "seat_capacity"),
        ("batch_listing", "seats_free"),
        ("batch_listing", "seats_updated_at"),
    }
)

#: 23:30 UTC on 27 Nov is 05:30 on 28 Nov in Dhaka.
LATE_EVENING_UTC: Final[dt.datetime] = dt.datetime(2026, 11, 27, 23, 30, tzinfo=dt.UTC)


def _batch(
    session: Session,
    slug: str,
    *,
    owner_status: str = "published",
    batch_status: str = "published",
    show: bool = True,
) -> uuid.UUID:
    """Arrange a solo tutor's batch whose owner typed 18 seats, 4 free.

    :param session: An arranging session
    :param slug: The owner's slug
    :param owner_status: The owner listing's status
    :param batch_status: The batch listing's status
    :param show: Whether the owner chose to show the seats
    :return: The batch id
    """
    teacher = make_teacher(session)
    _owner_listing(session, teacher.owner_id, slug=slug, status=owner_status)
    _batch_listing(session, teacher.batch_id, teacher.owner_id, status=batch_status)
    session.execute(
        sa.text(
            "UPDATE batch_listing SET show_seats = :show, seat_capacity = 18, "
            "seats_free = 4, seats_updated_at = :at WHERE batch_id = :b"
        ),
        {"show": show, "at": LATE_EVENING_UTC, "b": teacher.batch_id},
    )
    session.commit()
    return teacher.batch_id


def _seats(session: Session) -> dict[uuid.UUID, tuple[object, ...]]:
    """Read the view as the hub reader.

    :param session: The application role's session; left as the reader
    :return: Each row's values after the batch id, by batch id
    """
    as_hub_reader(session)
    rows = session.execute(
        sa.text(
            "SELECT batch_id, seat_capacity, seats_free, seats_updated_on "
            "FROM hub_public_batch_seats"
        )
    ).all()
    return {row[0]: tuple(row[1:]) for row in rows}


def test_seats_of_a_public_batch_are_shown_with_the_dhaka_day(
    owner_session: Session, restricted_session: Session
) -> None:
    """Both counts, and the day they changed in Bangladesh, not in UTC.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    batch_id = _batch(owner_session, "seated-tutor")

    assert _seats(restricted_session)[batch_id] == (18, 4, dt.date(2026, 11, 28))


@pytest.mark.parametrize(
    ("owner_status", "batch_status", "show"),
    [
        ("published", "published", False),
        ("published", "draft", True),
        ("published", "hidden", True),
        ("published", "suspended", True),
        ("draft", "published", True),
        ("hidden", "published", True),
        ("suspended", "published", True),
    ],
    ids=[
        "not-chosen",
        "draft-batch",
        "hidden-batch",
        "suspended-batch",
        "draft-owner",
        "hidden-owner",
        "suspended-owner",
    ],
)
def test_seats_not_chosen_or_not_public_are_absent(
    owner_session: Session,
    restricted_session: Session,
    owner_status: str,
    batch_status: str,
    show: bool,
) -> None:
    """No row for seats the owner did not choose to show, or a batch not public.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :param owner_status: The owner listing's status
    :param batch_status: The batch listing's status
    :param show: Whether the owner chose to show the seats
    :return: None
    """
    visible = _batch(owner_session, "visible-tutor")
    hidden = _batch(
        owner_session,
        "other-tutor",
        owner_status=owner_status,
        batch_status=batch_status,
        show=show,
    )

    rows = _seats(restricted_session)
    assert visible in rows  # not vacuous
    assert hidden not in rows


def test_an_inactive_batch_shows_no_seats(
    owner_session: Session, restricted_session: Session
) -> None:
    """Retiring the batch takes its seats off the page with it.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    batch_id = _batch(owner_session, "retired-tutor")
    owner_session.execute(
        sa.text("UPDATE batch SET active = false WHERE id = :b"), {"b": batch_id}
    )
    owner_session.commit()

    assert batch_id not in _seats(restricted_session)


def test_seats_view_shows_exactly_its_columns(
    owner_session: Session, restricted_session: Session
) -> None:
    """The batch id, the two counts and a day, and nothing else.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    _batch(owner_session, "column-tutor")
    as_hub_reader(restricted_session)
    result = restricted_session.execute(
        sa.text(f"SELECT * FROM {VIEW}")  # noqa: S608 -- module constant
    )

    assert tuple(result.keys()) == COLUMNS


def test_seats_view_never_depends_on_private_columns(
    restricted_session: Session,
) -> None:
    """What PostgreSQL resolved, not what the text says.

    :param restricted_session: A session as the application role
    :return: None
    """
    text = restricted_session.execute(
        sa.text("SELECT definition FROM pg_views WHERE viewname = :v"), {"v": VIEW}
    ).scalar_one()
    for table in PRIVATE_TABLES:
        assert not re.search(rf"\b{table}\b", text), table

    depends = restricted_session.execute(
        sa.text(
            "SELECT DISTINCT t.relname AS rel, a.attname AS col "
            "FROM pg_rewrite r "
            "JOIN pg_class v ON v.oid = r.ev_class "
            "JOIN pg_depend d ON d.classid = 'pg_rewrite'::regclass "
            "AND d.objid = r.oid AND d.refclassid = 'pg_class'::regclass "
            "JOIN pg_class t ON t.oid = d.refobjid "
            "LEFT JOIN pg_attribute a ON a.attrelid = t.oid "
            "AND a.attnum = d.refobjsubid "
            "WHERE v.relname = :v AND t.oid <> v.oid"
        ),
        {"v": VIEW},
    ).all()
    columns = {(row.rel, row.col) for row in depends if row.col is not None}

    assert {row.rel for row in depends} == {"hub_public_batch", "batch_listing"}
    assert columns == DIRECT_READS


def test_only_the_reader_may_read_the_view_and_nobody_writes_it(
    restricted_session: Session,
) -> None:
    """The reader SELECTs it; the application role is granted nothing on it.

    The owner's own preview reads its listing row, not this view, so the
    application role has no reason to hold a grant here.

    :param restricted_session: A session as the application role
    :return: None
    """
    privileges = restricted_session.execute(
        sa.text(
            "SELECT has_table_privilege(:r, :v, 'SELECT'), "
            "has_table_privilege(:r, :v, 'INSERT') "
            "OR has_table_privilege(:r, :v, 'UPDATE') "
            "OR has_table_privilege(:r, :v, 'DELETE')"
        ),
        {"r": HUB_READER_ROLE, "v": VIEW},
    ).one()
    app_grants = restricted_session.execute(
        sa.text(
            "SELECT count(*) FROM pg_class c, aclexplode(c.relacl) g "
            "WHERE c.relname = :v AND g.grantee = CAST(:r AS regrole)"
        ),
        {"v": VIEW, "r": APP_ROLE},
    ).scalar_one()

    assert tuple(privileges) == (True, False)
    assert app_grants == 0
