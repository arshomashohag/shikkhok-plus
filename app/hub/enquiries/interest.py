"""A family's interest in a listed batch: share, read, withdraw; the owner's list.

An interest is a ``listing_enquiry`` row of kind ``interest`` [0049]: a
signed-in family tells the people who run a batch that they are interested
in it, sharing the phone number on their account, so the owner can call
when a seat opens (owner decision, 2026-11-28). Nothing is typed: no
student name, no class, no message. It is a join request's lighter twin,
and it reuses the request's machinery rather than restating it:

* **Who may share** is :func:`app.hub.enquiries.target.resolve`, the
  request's one SQL statement, with ``closed_ok``: an interest may be
  shared in a batch whose admissions are closed, which is when it matters.
  The owner must accept join requests: being listed and being contacted by
  strangers stay two separate agreements.
* **The locks** are the request's: the caller's account key, then the
  listing ``FOR SHARE`` (:func:`app.hub.enquiries.sending._hold`), so an
  interest never outlives either party's deletion.
* **The phone is read live** from ``account`` and never copied. A family
  with no phone on their account cannot share an interest: a phone number
  is what one shares.
* **One open interest per batch and family** is the partial unique index
  ``uq_listing_enquiry_interest_open``. Sharing again is not an error: it
  stores nothing, counts nothing, tells nobody, and answers the interest
  already shared.
* **Only a stored interest is counted**, against its own daily allowance,
  and only a stored interest is announced: one ``hub_interest_received``
  item to everyone who runs the listing, naming the batch and nobody else.
* **Withdrawal** is the request's own (:func:`app.hub.enquiries.sending.withdraw`),
  which forgets either kind, its inbox items with it.
* **The owner closes** an interest once dealt with. Nothing is sent to the
  family: closing says only that the owner has seen it.

The phone number is never logged; nothing here logs at all. No account id
appears in anything returned.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final, Literal, cast

import sqlalchemy as sa
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from app.auth.ceilings import HUB_INTEREST_ACCOUNT_DAILY, CeilingChecker
from app.authz.lenses import TeacherLens
from app.db.models import Owner
from app.errors import AuthorizationError, ConflictError
from app.governance.dispositions import CLASS_AGE, RETENTION
from app.hub.enquiries import target
from app.hub.enquiries.sending import _hold
from app.hub.listings.shared import managing_accounts
from app.local_time import bangladesh_today
from app.notifications.inbox import HUB_INTEREST_RECEIVED, deliver, mark_read_for_source

__all__ = [
    "MINE_LIMIT",
    "OWNER_LIMIT",
    "InterestStatus",
    "InterestTarget",
    "MyInterest",
    "OwnerInterest",
    "close",
    "describe",
    "list_for",
    "mine",
    "share",
]

#: Every interest a family can hold: the daily allowance for every day of
#: the retention window, plus the day it starts part-way through and the
#: day since the purge last ran, as the request's own list reasons.
MINE_LIMIT: Final = HUB_INTEREST_ACCOUNT_DAILY * (
    CLASS_AGE[RETENTION["listing_enquiry"]].days + 2
)

#: How many open interests the owner's list returns, newest first.
OWNER_LIMIT: Final = 200

#: Where an interest is: shared, or seen and closed by the owner.
InterestStatus = Literal["open", "closed"]

#: The caller's phone, and whether they already hold an open interest in
#: the batch.
_CALLER: Final = sa.text(
    """
    SELECT a.phone,
           EXISTS (
               SELECT 1 FROM listing_enquiry e
               WHERE e.batch_id = :batch_id
                 AND e.enquirer_account_id = a.id
                 AND e.kind = 'interest'
                 AND e.status = 'open'
           ) AS already_shared
    FROM account a
    WHERE a.id = :account_id
    """
)

#: A new interest; nothing when one is already open in this batch.
_CREATE: Final = sa.text(
    """
    INSERT INTO listing_enquiry (owner_id, batch_id, enquirer_account_id,
                                 kind, share_contact, created_at)
    VALUES (:owner_id, :batch_id, :account_id, 'interest', true, :now)
    ON CONFLICT (batch_id, enquirer_account_id)
        WHERE status = 'open' AND kind = 'interest'
    DO NOTHING
    RETURNING id
    """
)

#: The interest already open in a batch, when sharing again stored none.
_OPEN: Final = sa.text(
    """
    SELECT id FROM listing_enquiry
    WHERE batch_id = :batch_id AND enquirer_account_id = :account_id
      AND kind = 'interest' AND status = 'open'
    """
)

#: A family's interests as they see them.
_MINE_SELECT: Final = """
    SELECT e.id, ol.public_name AS owner_public_name,
           bl.public_title AS batch_title, e.status, e.created_at
    FROM listing_enquiry e
    LEFT JOIN owner_listing ol ON ol.owner_id = e.owner_id
    LEFT JOIN batch_listing bl ON bl.batch_id = e.batch_id
    WHERE e.enquirer_account_id = :account_id AND e.kind = 'interest'
"""

#: The caller's interests, newest first.
_MINE: Final = sa.text(
    _MINE_SELECT + " ORDER BY e.created_at DESC, e.id DESC LIMIT :limit"
)

#: One of the caller's interests.
_ONE_MINE: Final = sa.text(_MINE_SELECT + " AND e.id = :interest_id")

#: The owner's open interests, newest first. The phone is the account's
#: own, read now: a family who changes or removes their number is seen
#: with the new one, or none.
_OWNER: Final = sa.text(
    """
    SELECT e.id, e.batch_id, bl.public_title AS batch_title,
           a.phone AS guardian_phone, e.created_at
    FROM listing_enquiry e
    JOIN account a ON a.id = e.enquirer_account_id
    LEFT JOIN batch_listing bl ON bl.batch_id = e.batch_id
    WHERE e.owner_id = :owner_id AND e.kind = 'interest' AND e.status = 'open'
    ORDER BY e.created_at DESC, e.id DESC
    LIMIT :limit
    """
)

#: The owner's open interest to close, locked.
_LOCK: Final = sa.text(
    """
    SELECT id FROM listing_enquiry
    WHERE id = :interest_id AND owner_id = :owner_id
      AND kind = 'interest' AND status = 'open'
    FOR UPDATE
    """
)

#: Close the locked interest: the owner has seen it.
_CLOSE: Final = sa.text(
    """
    UPDATE listing_enquiry
    SET status = 'closed', outcome = 'not_now', closed_at = :now
    WHERE id = :interest_id
    """
)


@dataclass(frozen=True, slots=True)
class InterestTarget:
    """What the confirm screen shows before the family shares.

    Informed consent needs whom the number goes to. Like a join request's
    target, it says whether there is a number to share and never the
    number itself: no contact field reaches the family's side.

    :ivar owner_public_name: The listing's public name
    :ivar batch_title: The batch's public title
    :ivar has_phone: Whether the caller's account has a phone number to
        share; without one, sharing would be refused
    :ivar already_shared: The caller already has an open interest here
    """

    owner_public_name: str
    batch_title: str
    has_phone: bool
    already_shared: bool


@dataclass(frozen=True, slots=True)
class MyInterest:
    """One of the caller's own interests.

    :ivar id: The interest
    :ivar owner_public_name: The listing's public name, or None once gone
    :ivar batch_title: The batch's public title, or None once gone
    :ivar status: ``open`` while shared, ``closed`` once the owner saw it
    :ivar shared_on: The day it was shared, in Bangladesh
    """

    id: uuid.UUID
    owner_public_name: str | None
    batch_title: str | None
    status: InterestStatus
    shared_on: dt.date


@dataclass(frozen=True, slots=True)
class OwnerInterest:
    """One open interest, as the people who run the listing see it.

    No name: whatever a family typed about themselves is never shown to a
    teacher. The phone is what they chose to share.

    :ivar id: The interest
    :ivar batch_id: The batch, or None once its listing is gone
    :ivar batch_title: Its public title, or None
    :ivar guardian_phone: The family's phone as their account holds it
        now, or None if they have since removed it; the name the join
        request's contact predicate uses
    :ivar shared_on: The day it was shared, in Bangladesh
    """

    id: uuid.UUID
    batch_id: uuid.UUID | None
    batch_title: str | None
    guardian_phone: str | None
    shared_on: dt.date


def _my_interest(row: Row[tuple[object, ...]]) -> MyInterest:
    """Map a row of :data:`_MINE` or :data:`_ONE_MINE`.

    :param row: The row
    :return: The interest
    """
    return MyInterest(
        id=cast("uuid.UUID", row.id),
        owner_public_name=cast("str | None", row.owner_public_name),
        batch_title=cast("str | None", row.batch_title),
        status=cast("InterestStatus", row.status),
        shared_on=bangladesh_today(cast("dt.datetime", row.created_at)),
    )


def _found_batch(found: target.Target) -> tuple[uuid.UUID, str]:
    """Read the batch a resolved target names.

    :param found: The target, resolved with a batch id
    :return: The batch id and its public title
    """
    # ``resolve`` returns a row only when the named batch matched, so a
    # target resolved with a batch id always carries both.
    return cast("uuid.UUID", found.batch_id), cast("str", found.batch_title)


def describe(
    session: Session, account_id: uuid.UUID, owner_slug: str, batch_id: uuid.UUID
) -> InterestTarget:
    """Say whom an interest would reach and which number it would share.

    :param session: The session to read through
    :param account_id: The authenticated caller
    :param owner_slug: The owner's public slug
    :param batch_id: The batch
    :return: The target as the confirm screen shows it
    :raises AuthorizationError: ``ENQUIRY_TARGET_NOT_FOUND`` (404)
    """
    found = target.resolve(session, account_id, owner_slug, batch_id, closed_ok=True)
    found_batch, title = _found_batch(found)
    caller = session.execute(
        _CALLER, {"batch_id": found_batch, "account_id": account_id}
    ).one()
    return InterestTarget(
        owner_public_name=found.owner_public_name,
        batch_title=title,
        has_phone=caller.phone is not None,
        already_shared=bool(caller.already_shared),
    )


def share(
    session: Session,
    account_id: uuid.UUID,
    owner_slug: str,
    batch_id: uuid.UUID,
    now: dt.datetime,
) -> MyInterest:
    """Share the caller's interest in a batch, and tell who runs it.

    Commits on success and rolls back on any failure. Sharing again while
    an interest is open stores, counts and announces nothing, and answers
    the open one.

    :param session: The session to write through
    :param account_id: The authenticated family
    :param owner_slug: The owner's public slug
    :param batch_id: The batch
    :param now: The moment of sharing
    :return: The interest as the family sees it
    :raises AuthorizationError: ``ENQUIRY_TARGET_NOT_FOUND`` (404), or
        ``NOT_AUTHENTICATED`` (401) when the account was deleted meanwhile
    :raises ConflictError: ``HUB_INTEREST_NEEDS_PHONE`` (409) when the
        caller's account has no phone number to share
    :raises CeilingBreach: ``HUB_INTEREST_CEILING``, the eleventh today
    """
    try:
        held = _hold(session, account_id, owner_slug)
        # Decided after the locks, and run even when nothing is held, as a
        # join request's send is, so no refusal is quicker than another.
        found = target.resolve(
            session, account_id, owner_slug, batch_id, closed_ok=True
        )
        if not held:
            raise target.not_found()
        found_batch, title = _found_batch(found)
        caller = session.execute(
            _CALLER, {"batch_id": found_batch, "account_id": account_id}
        ).one()
        if caller.phone is None:
            raise ConflictError(
                code="HUB_INTEREST_NEEDS_PHONE",
                message_key="hub.interest.needs_phone",
            )
        interest_id = session.execute(
            _CREATE,
            {
                "owner_id": found.owner_id,
                "batch_id": found_batch,
                "account_id": account_id,
                "now": now,
            },
        ).scalar_one_or_none()
        if interest_id is None:
            # Already shared here: answer that one, and count nothing.
            interest_id = session.execute(
                _OPEN, {"batch_id": found_batch, "account_id": account_id}
            ).scalar_one()
        else:
            # Counted only now that one was stored; a breach rolls it back.
            CeilingChecker(session).consume_hub_interest_in_transaction(account_id, now)
            owner = session.execute(
                sa.select(Owner).where(Owner.id == found.owner_id)
            ).scalar_one()
            deliver(
                session,
                account_ids=managing_accounts(session, owner),
                kind=HUB_INTEREST_RECEIVED,
                batch_name=title,
                now=now,
                source_id=interest_id,
                preview=None,
            )
        shared = _my_interest(
            session.execute(
                _ONE_MINE, {"account_id": account_id, "interest_id": interest_id}
            ).one()
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return shared


def mine(session: Session, account_id: uuid.UUID) -> list[MyInterest]:
    """Read the caller's own interests, newest first.

    Never switch-gated: a family can always see what they shared, so they
    can take it back.

    :param session: The session to read through
    :param account_id: The authenticated family
    :return: At most :data:`MINE_LIMIT` interests
    """
    rows = session.execute(_MINE, {"account_id": account_id, "limit": MINE_LIMIT})
    return [_my_interest(row) for row in rows]


def list_for(session: Session, lens: TeacherLens) -> list[OwnerInterest]:
    """Read the owner's open interests, newest first.

    :param session: The session to read through
    :param lens: The teacher lens naming the owner
    :return: At most :data:`OWNER_LIMIT` interests
    """
    rows = session.execute(_OWNER, {"owner_id": lens.owner_id, "limit": OWNER_LIMIT})
    return [
        OwnerInterest(
            id=row.id,
            batch_id=row.batch_id,
            batch_title=row.batch_title,
            guardian_phone=row.guardian_phone,
            shared_on=bangladesh_today(row.created_at),
        )
        for row in rows
    ]


def _not_found() -> AuthorizationError:
    """Build the one refusal for a missing, closed or another owner's interest.

    :return: ``ENQUIRY_NOT_FOUND`` (404), as for a join request
    """
    return AuthorizationError(
        code="ENQUIRY_NOT_FOUND", message_key="hub.enquiry.not_found", status=404
    )


def close(
    session: Session, lens: TeacherLens, interest_id: uuid.UUID, now: dt.datetime
) -> None:
    """Close an open interest the owner has dealt with, and settle their inbox.

    Locks the interest row before touching any inbox item, as closing a
    request does. Sends the family nothing.

    :param session: The session to write through
    :param lens: The teacher lens naming the owner
    :param interest_id: The interest
    :param now: The moment of closing
    :return: None
    :raises AuthorizationError: ``ENQUIRY_NOT_FOUND`` (404) for a missing,
        already closed or another owner's interest
    """
    try:
        locked = session.execute(
            _LOCK, {"owner_id": lens.owner_id, "interest_id": interest_id}
        ).first()
        if locked is None:
            raise _not_found()
        session.execute(_CLOSE, {"interest_id": interest_id, "now": now})
        mark_read_for_source(
            session, kind=HUB_INTEREST_RECEIVED, source_id=interest_id, now=now
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
