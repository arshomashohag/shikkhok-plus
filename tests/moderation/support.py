"""Arrangement helpers for the moderation tests.

Everything writes through the table-owner session so the service under test,
handed the restricted session, is what exercises the application role's grants.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import BatchListing, OwnerListing

__all__ = ["publish_batch", "publish_owner", "status_of"]


def publish_owner(
    session: Session,
    owner_id: uuid.UUID,
    *,
    name: str = "Rahim Sir",
    status: str = "published",
) -> None:
    """Insert an owner listing in a given status.

    :param session: An arranging session
    :param owner_id: The owner
    :param name: The public name
    :param status: The listing status
    :return: None
    """
    session.add(
        OwnerListing(
            owner_id=owner_id,
            slug=f"s-{uuid.uuid4().hex[:12]}",
            status=status,
            public_name=name,
            headline_en="Maths for SSC",
            published_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    session.commit()


def publish_batch(
    session: Session,
    owner_id: uuid.UUID,
    batch_id: uuid.UUID,
    *,
    status: str = "published",
) -> None:
    """Insert a batch listing in a given status.

    :param session: An arranging session
    :param owner_id: The batch's owner
    :param batch_id: The batch
    :param status: The listing status
    :return: None
    """
    session.add(
        BatchListing(
            batch_id=batch_id,
            owner_id=owner_id,
            slug=f"b-{uuid.uuid4().hex[:12]}",
            status=status,
            description_en="Weekend batch",
            show_fee=False,
            show_schedule=False,
            published_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    session.commit()


def status_of(session: Session, table: str, key: str, value: uuid.UUID) -> str:
    """Read a listing's status fresh from the database.

    :param session: Any session
    :param table: ``owner_listing`` or ``batch_listing``
    :param key: The key column
    :param value: The key value
    :return: The status
    """
    session.rollback()
    return str(
        session.execute(
            sa.text(f"SELECT status FROM {table} WHERE {key} = :v"),  # noqa: S608
            {"v": value},
        ).scalar_one()
    )
