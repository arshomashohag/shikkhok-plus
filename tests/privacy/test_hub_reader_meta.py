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

from app.db.roles import HUB_READER_ROLE
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
    ["profile", "enrollment", "payment_method", "account", "student", "batch"],
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
