"""Arrangement helpers for the H5 join-request tests.

Everything here writes through the table-owner session, so the service under
test, handed the restricted session, is the only thing exercising the
application role's grants.

The published owner and batch come from the H4 review builders
(:func:`tests.reviews.support.public_batch` and
:func:`~tests.reviews.support.public_centre_batch`) [F19]; this module only
turns join requests on and states the batch's admissions.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.accounts.phone import canonical_phone
from app.authz.lenses import TeacherLens
from app.db.models import Account
from tests.hub.support import add_member
from tests.reviews.support import public_batch, public_centre_batch

__all__ = [
    "EnquirableWorld",
    "close",
    "enquirable_owner",
    "guardian",
]


@dataclass(frozen=True, slots=True)
class EnquirableWorld:
    """A published owner that accepts join requests, with one listed batch.

    :ivar lens: A teacher lens on the owner, held by one of its managers
    :ivar owner_slug: The owner listing's public slug
    :ivar batch_id: The listed batch
    :ivar batch_title: The batch listing's public title
    :ivar manager_ids: Every account that runs the listing, sorted: a solo
        tutor's own account, or both of a centre's managers
    """

    lens: TeacherLens
    owner_slug: str
    batch_id: uuid.UUID
    batch_title: str
    manager_ids: list[uuid.UUID]


def enquirable_owner(
    session: Session,
    *,
    centre: bool = False,
    accepts: bool = True,
    admissions: str = "open",
) -> EnquirableWorld:
    """Arrange a published owner and batch that a guardian may ask to join.

    A centre gets a second accepted manager, so a delivery to "every
    manager" is told apart from a delivery to the first one.

    :param session: An arranging session
    :param centre: A coaching centre rather than a solo tutor
    :param accepts: The owner listing's ``accepts_enquiries``
    :param admissions: The batch listing's admissions
    :return: The world
    """
    batch = public_centre_batch(session) if centre else public_batch(session)
    managers = [batch.teacher_account_id]
    if centre:
        _, second = add_member(session, batch.owner_id, role="manager", name="Shila")
        managers.append(second)
    session.execute(
        sa.text("UPDATE owner_listing SET accepts_enquiries = :a WHERE owner_id = :o"),
        {"a": accepts, "o": batch.owner_id},
    )
    session.execute(
        sa.text(
            "UPDATE batch_listing SET admissions = CAST(:a AS hub_admissions) "
            "WHERE batch_id = :b"
        ),
        {"a": admissions, "b": batch.batch_id},
    )
    session.commit()
    slug, title = session.execute(
        sa.text(
            "SELECT ol.slug, bl.public_title FROM batch_listing bl "
            "JOIN owner_listing ol ON ol.owner_id = bl.owner_id "
            "WHERE bl.batch_id = :b"
        ),
        {"b": batch.batch_id},
    ).one()
    return EnquirableWorld(
        lens=TeacherLens(account_id=batch.teacher_account_id, owner_id=batch.owner_id),
        owner_slug=str(slug),
        batch_id=batch.batch_id,
        batch_title=str(title),
        manager_ids=sorted(managers),
    )


def guardian(
    session: Session,
    *,
    phone: str | None = "01712345678",
    email: str | None = None,
) -> uuid.UUID:
    """Create a verified account, as sign-up leaves one.

    :param session: An arranging session
    :param phone: The account's number as typed, or None for none
    :param email: The account's email address, or None for none
    :return: The account id
    """
    now = dt.datetime.now(tz=dt.UTC)
    row = Account(
        phone=None if phone is None else canonical_phone(phone),
        email=email,
        created_at=now,
        activated_at=now,
    )
    session.add(row)
    session.commit()
    return row.id


def close(
    session: Session,
    enquiry_id: uuid.UUID,
    outcome: str,
    now: dt.datetime | None = None,
) -> None:
    """Close a request directly, standing in for the owner's close (Task 4).

    :param session: An arranging session
    :param enquiry_id: The request
    :param outcome: ``added``, ``not_now`` or ``call_us``
    :param now: When it was closed; the real clock by default
    :return: None
    """
    session.execute(
        sa.text(
            "UPDATE listing_enquiry SET status = 'closed', "
            "outcome = CAST(:o AS hub_enquiry_outcome), closed_at = :t "
            "WHERE id = :e"
        ),
        {"o": outcome, "t": now or dt.datetime.now(tz=dt.UTC), "e": enquiry_id},
    )
    session.commit()
