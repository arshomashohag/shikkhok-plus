"""Database access for public hub reads.

Public pages read as ``shikkhok_hub_reader``, a role with only the grants
a revision has named, never as the application role that can see every
table.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.roles import HUB_READER_ROLE

__all__ = ["as_hub_reader"]


def as_hub_reader(session: Session) -> None:
    """Drop to the hub reader role for the rest of this transaction.

    ``SET LOCAL`` ends with the transaction, so the role cannot leak to
    the next request on a pooled connection.

    :param session: A session whose transaction is open
    :return: None
    """
    # SET ROLE cannot take a bind parameter; the name is a module constant.
    session.execute(sa.text(f"SET LOCAL ROLE {HUB_READER_ROLE}"))
