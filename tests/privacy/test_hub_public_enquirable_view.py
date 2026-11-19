"""``hub_public_enquirable``: which owners a guardian may ask to join.

**This view decides who may be messaged at all**, so these tests were
written before the migration. An owner is in it exactly while their listing
is in ``hub_public_owner`` -- published, which already excludes a draft, a
hidden and a suspended listing -- AND the owner has opted in with
``owner_listing.accepts_enquiries`` (Call 3). Being listed and being
messaged by strangers are two separate agreements.

Every case reads the view as the hub reader, against rows arranged as the
table owner. The view exposes an owner id and a slug, both already public
through ``hub_public_owner``, and reads no other private column [F22].
"""

from __future__ import annotations

import re
import uuid
from typing import Final

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.roles import APP_ROLE, HUB_READER_ROLE
from app.hub.public.db import as_hub_reader
from tests.batches.conftest import make_teacher
from tests.privacy.test_hub_public_views import PRIVATE_TABLES, _owner_listing

#: Exactly what ``hub_public_enquirable`` shows, in order.
COLUMNS: Final[tuple[str, ...]] = ("owner_id", "slug")

#: Every column the view itself depends on, by ``(relation, column)``.
#: What it reads through ``hub_public_owner`` is that view's own business,
#: probed in ``test_hub_public_views.py``.
DIRECT_READS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("hub_public_owner", "owner_id"),
        ("hub_public_owner", "slug"),
        ("owner_listing", "owner_id"),
        ("owner_listing", "accepts_enquiries"),
    }
)

#: The public views the application role reads directly (Call 16).
APP_VIEWS: Final[tuple[str, ...]] = (
    "hub_public_owner",
    "hub_public_batch",
    "hub_public_enquirable",
)


def _owner(
    session: Session, slug: str, *, status: str = "published", accepts: bool = True
) -> uuid.UUID:
    """Arrange a solo owner's listing, opted in to requests or not.

    :param session: An arranging session
    :param slug: The listing's slug
    :param status: The listing status
    :param accepts: Whether the owner accepts join requests
    :return: The owner id
    """
    teacher = make_teacher(session)
    _owner_listing(session, teacher.owner_id, slug=slug, status=status)
    session.execute(
        sa.text("UPDATE owner_listing SET accepts_enquiries = :a WHERE owner_id = :o"),
        {"a": accepts, "o": teacher.owner_id},
    )
    session.commit()
    return teacher.owner_id


def _enquirable(session: Session) -> dict[uuid.UUID, str]:
    """Read the view as the hub reader.

    :param session: The application role's session; left as the reader
    :return: Each enquirable owner's slug, by owner id
    """
    as_hub_reader(session)
    rows = session.execute(sa.text("SELECT owner_id, slug FROM hub_public_enquirable"))
    return {row.owner_id: row.slug for row in rows}


@pytest.mark.parametrize(
    ("status", "accepts"),
    [
        ("draft", True),
        ("hidden", True),
        ("suspended", True),
        ("published", False),
    ],
)
def test_enquirable_view_lists_only_published_accepting_owners(
    owner_session: Session, restricted_session: Session, status: str, accepts: bool
) -> None:
    """Only a published owner who opted in may be asked; the others are absent.

    A published, opted-in owner beside it is listed, so the test is not
    vacuous.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :param status: The other owner's listing status
    :param accepts: Whether the other owner opted in
    :return: None
    """
    live = _owner(owner_session, "open-tutor")
    _owner(owner_session, "closed-tutor", status=status, accepts=accepts)

    assert _enquirable(restricted_session) == {live: "open-tutor"}


def test_opting_out_leaves_the_public_page_and_withdraws_the_target(
    owner_session: Session, restricted_session: Session
) -> None:
    """Turning requests off removes the owner here and nowhere else.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    owner_id = _owner(owner_session, "quiet-tutor", accepts=False)

    assert _enquirable(restricted_session) == {}
    owners = restricted_session.execute(
        sa.text("SELECT owner_id FROM hub_public_owner")
    ).scalars()
    assert set(owners) == {owner_id}


def test_enquirable_view_shows_exactly_its_columns(
    owner_session: Session, restricted_session: Session
) -> None:
    """An owner id and a slug, both already public, and nothing else.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    _owner(owner_session, "open-tutor")
    as_hub_reader(restricted_session)
    result = restricted_session.execute(sa.text("SELECT * FROM hub_public_enquirable"))

    assert tuple(result.keys()) == COLUMNS


def test_enquirable_view_never_depends_on_private_columns(
    restricted_session: Session,
) -> None:
    """What PostgreSQL resolved, not what the text says.

    The view itself depends on ``owner_listing.owner_id`` and
    ``owner_listing.accepts_enquiries`` and on nothing else but what it
    reads through ``hub_public_owner``. No private table is named.

    :param restricted_session: A session as the application role
    :return: None
    """
    text = restricted_session.execute(
        sa.text("SELECT definition FROM pg_views WHERE viewname = :v"),
        {"v": "hub_public_enquirable"},
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
            "WHERE v.relname = 'hub_public_enquirable' AND t.oid <> v.oid"
        )
    ).all()
    columns = {(row.rel, row.col) for row in depends if row.col is not None}
    relations = {row.rel for row in depends}

    assert relations == {"hub_public_owner", "owner_listing"}
    assert columns == DIRECT_READS


@pytest.mark.parametrize("view", APP_VIEWS)
def test_app_role_can_select_the_three_public_views(
    restricted_session: Session, view: str
) -> None:
    """The application role holds its own grant on each view (Call 16).

    Checked twice: the ACL names the role itself, a stated and reviewed
    audience; and the role reads the view as itself. Before ``0047`` the
    session was refused ``0040``'s two views unless it first became the
    reader. It is granted nothing but ``SELECT`` on any of them.

    :param restricted_session: A session as the application role
    :param view: The view
    :return: None
    """
    direct = restricted_session.execute(
        sa.text(
            "SELECT array_agg(g.privilege_type::text ORDER BY g.privilege_type) "
            "FROM pg_class c, aclexplode(c.relacl) g "
            "WHERE c.relname = :v AND g.grantee = CAST(:r AS regrole)"
        ),
        {"v": view, "r": APP_ROLE},
    ).scalar_one()
    # And the role reads it as itself, with no ``SET LOCAL ROLE``: a
    # missing grant would raise here rather than count.
    restricted_session.execute(
        sa.text(f"SELECT count(*) FROM {view}")  # noqa: S608  parametrised constants
    ).scalar_one()

    assert direct == ["SELECT"]


def test_reader_may_read_the_view_and_not_write_it(
    restricted_session: Session,
) -> None:
    """The reader SELECTs the view and writes nothing.

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
        {"r": HUB_READER_ROLE, "v": "hub_public_enquirable"},
    ).one()

    assert tuple(privileges) == (True, False)


def test_enquirable_view_is_security_barrier(restricted_session: Session) -> None:
    """A caller's predicate cannot run beneath the view's filter.

    :param restricted_session: A session as the application role
    :return: None
    """
    options = restricted_session.execute(
        sa.text("SELECT reloptions FROM pg_class WHERE relname = :v"),
        {"v": "hub_public_enquirable"},
    ).scalar_one()

    assert "security_barrier=true" in (options or [])
