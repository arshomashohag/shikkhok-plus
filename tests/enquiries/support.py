"""Arrangement helpers for the H5 join-request tests.

Everything here writes through the table-owner session, so the service under
test, handed the restricted session, is the only thing exercising the
application role's grants.

The published owner and batch come from the H4 review builders
(:func:`tests.reviews.support.public_batch` and
:func:`~tests.reviews.support.public_centre_batch`) [F19]; this module only
turns join requests on and states the batch's admissions.

:data:`CASES` are the targets a guardian may not ask (Review Focus 2),
shared by the service-level identity test in ``test_target.py`` and the
HTTP-level byte test in ``test_enquiry_routes.py``, so both compare the
same cases with a slug that never existed, :data:`NEVER`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.accounts.phone import canonical_phone
from app.authz.lenses import TeacherLens
from app.db.models import Account
from tests.hub.support import add_member
from tests.reviews.support import public_batch, public_centre_batch

__all__ = [
    "CASES",
    "NEVER",
    "Case",
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
    """Close a request directly, as arrangement only.

    Writes the row and nothing else: no answer is delivered and no inbox
    item is marked read. A test about closing uses
    :func:`app.hub.enquiries.owner.close`; this is for tests that only need
    a request to be closed already, such as one carrying an outcome the
    owner could not choose today.

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


#: A slug no listing has ever held.
NEVER = "never-existed-slug"

#: A case: ``(slug, batch id, caller)`` worked out from a fresh world.
Case = Callable[[Session, EnquirableWorld], tuple[str, uuid.UUID | None, uuid.UUID]]


def _set(session: Session, sql: str, **values: object) -> None:
    """Run one arranging statement and commit.

    :param session: An arranging session
    :param sql: The statement
    :param values: Its parameters
    :return: None
    """
    session.execute(sa.text(sql), values)
    session.commit()


def _owner_status(status: str) -> Case:
    """Build a case moving the owner listing to a status.

    :param status: ``draft``, ``hidden`` or ``suspended``
    :return: The case
    """

    def case(
        session: Session, world: EnquirableWorld
    ) -> tuple[str, uuid.UUID | None, uuid.UUID]:
        _set(
            session,
            "UPDATE owner_listing SET status = CAST(:s AS hub_listing_status) "
            "WHERE owner_id = :o",
            s=status,
            o=world.lens.owner_id,
        )
        return world.owner_slug, None, guardian(session)

    return case


def _not_accepting(
    session: Session, world: EnquirableWorld
) -> tuple[str, uuid.UUID | None, uuid.UUID]:
    _set(
        session,
        "UPDATE owner_listing SET accepts_enquiries = false WHERE owner_id = :o",
        o=world.lens.owner_id,
    )
    return world.owner_slug, None, guardian(session)


def _batch_closed(
    session: Session, world: EnquirableWorld
) -> tuple[str, uuid.UUID | None, uuid.UUID]:
    _set(
        session,
        "UPDATE batch_listing SET admissions = 'closed' WHERE batch_id = :b",
        b=world.batch_id,
    )
    return world.owner_slug, world.batch_id, guardian(session)


def _batch_of_another_owner(
    session: Session, world: EnquirableWorld
) -> tuple[str, uuid.UUID | None, uuid.UUID]:
    other = enquirable_owner(session)
    return world.owner_slug, other.batch_id, guardian(session)


def _batch_status(status: str) -> Case:
    """Build a case moving the batch listing to a status.

    :param status: ``draft``, ``hidden`` or ``suspended``
    :return: The case
    """

    def case(
        session: Session, world: EnquirableWorld
    ) -> tuple[str, uuid.UUID | None, uuid.UUID]:
        _set(
            session,
            "UPDATE batch_listing SET status = CAST(:s AS hub_listing_status) "
            "WHERE batch_id = :b",
            s=status,
            b=world.batch_id,
        )
        return world.owner_slug, world.batch_id, guardian(session)

    return case


def _batch_inactive(
    session: Session, world: EnquirableWorld
) -> tuple[str, uuid.UUID | None, uuid.UUID]:
    _set(session, "UPDATE batch SET active = false WHERE id = :b", b=world.batch_id)
    return world.owner_slug, world.batch_id, guardian(session)


def _unknown_batch(
    session: Session, world: EnquirableWorld
) -> tuple[str, uuid.UUID | None, uuid.UUID]:
    return world.owner_slug, uuid.uuid4(), guardian(session)


def _centre_manager(
    session: Session, world: EnquirableWorld
) -> tuple[str, uuid.UUID | None, uuid.UUID]:
    centre = enquirable_owner(session, centre=True)
    return centre.owner_slug, centre.batch_id, centre.manager_ids[-1]


def _solo_owner_self(
    session: Session, world: EnquirableWorld
) -> tuple[str, uuid.UUID | None, uuid.UUID]:
    return world.owner_slug, world.batch_id, world.lens.account_id


CASES: dict[str, Case] = {
    "owner_draft": _owner_status("draft"),
    "owner_hidden": _owner_status("hidden"),
    "owner_suspended": _owner_status("suspended"),
    "not_accepting": _not_accepting,
    "batch_closed": _batch_closed,
    "batch_of_another_owner": _batch_of_another_owner,
    "batch_draft": _batch_status("draft"),
    "batch_hidden": _batch_status("hidden"),
    "batch_suspended": _batch_status("suspended"),
    "batch_inactive": _batch_inactive,
    "batch_unknown": _unknown_batch,
    "caller_centre_manager": _centre_manager,
    "caller_solo_owner": _solo_owner_self,
}
