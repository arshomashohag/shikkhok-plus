"""The public hub's read role: what it is, and what it cannot touch.

The hub serves pages to anonymous visitors, so its database access is a
privilege boundary of its own. ``shikkhok_hub_reader`` is a ``NOLOGIN``
role the application role may become for one transaction. It starts with
**no table grants at all**, so every later grant is a reviewed diff and
anything not granted fails closed.
"""

from __future__ import annotations

import psycopg.errors
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.db.roles import APP_ROLE, HUB_READER_ROLE
from app.hub.public.db import as_hub_reader


def test_hub_reader_is_not_superuser_and_cannot_bypass_rls(
    restricted_session: Session,
) -> None:
    """The role is neither a superuser, an RLS bypasser, nor a login.

    :param restricted_session: A session as the restricted application role
    :return: None
    """
    row = restricted_session.execute(
        sa.text(
            "SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles "
            "WHERE rolname = :name"
        ),
        {"name": HUB_READER_ROLE},
    ).one()

    assert tuple(row) == (False, False, False)


def test_app_role_does_not_inherit_reader_grants(restricted_session: Session) -> None:
    """The application role holds none of the reader's grants as itself.

    ``0001`` creates it ``NOINHERIT``, so a view granted only to the reader
    is read by ``SET LOCAL ROLE`` and never by the role directly. The
    comments in ``0040``, ``0043`` and ``0045`` state this; this test is
    what keeps them true.

    :param restricted_session: A session as the restricted application role
    :return: None
    """
    inherits = restricted_session.execute(
        sa.text("SELECT rolinherit FROM pg_roles WHERE rolname = :r"),
        {"r": APP_ROLE},
    ).scalar_one()
    member = restricted_session.execute(
        sa.text("SELECT pg_has_role(:a, :h, 'MEMBER')"),
        {"a": APP_ROLE, "h": HUB_READER_ROLE},
    ).scalar_one()
    reads_as_itself = restricted_session.execute(
        sa.text("SELECT has_table_privilege(:a, 'hub_public_teacher_name', 'SELECT')"),
        {"a": APP_ROLE},
    ).scalar_one()

    assert (inherits, member, reads_as_itself) == (False, True, False)


def test_app_role_may_become_hub_reader(restricted_session: Session) -> None:
    """``as_hub_reader`` switches the current user inside the transaction.

    :param restricted_session: A session as the restricted application role
    :return: None
    """
    as_hub_reader(restricted_session)

    current = restricted_session.execute(sa.text("SELECT current_user")).scalar_one()
    assert current == HUB_READER_ROLE


@pytest.mark.parametrize(
    "table",
    [
        "profile",
        "enrollment",
        "payment_method",
        "account",
        "student",
        "batch",
        "review",
        "review_reply",
        "listing_enquiry",
    ],
)
def test_hub_reader_cannot_read_private_tables(
    restricted_session: Session, table: str
) -> None:
    """With no table grants, every private table is refused outright.

    :param restricted_session: A session as the restricted application role
    :param table: A table the hub must never read
    :return: None
    """
    as_hub_reader(restricted_session)

    with pytest.raises(ProgrammingError) as caught:
        restricted_session.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1"))  # noqa: S608  parametrised constants

    assert isinstance(caught.value.orig, psycopg.errors.InsufficientPrivilege)
