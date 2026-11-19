"""How many photos an owner may hold: 12 on their own page, 8 per batch.

**Every status counts but the two terminal ones** [H3 global constraints]:
an upload still in flight, a photo awaiting review, an approved one and a
held one all occupy a slot; a rejected or withdrawn photo frees it.

**The owner row is the lock** [Review Focus 4]. Two uploads racing at the
quota would each count the same rows under READ COMMITTED and each insert,
leaving 13. :func:`lock_owner` takes ``owner`` ``FOR UPDATE`` before the
count, so the second waits until the first has committed its row and then
counts it. The daily ceiling is consumed in the same transaction, without
committing (:meth:`~app.auth.ceilings.CeilingChecker.consume_hub_media`),
so nothing releases the lock early.

**The lock is also where a departed owner is noticed** [R13]. Account
deletion keeps a solo teacher's ``owner`` row and clears its
``account_id``, under the same lock. A photo write that passed its lens
check and then waited for the lock would otherwise create or publish a photo
nobody owns, which no later deletion would ever reach. :func:`lock_owner`
re-reads the row under the lock and reports whether a solo owner still has
its account; every caller refuses, writing nothing, when it does not. A
centre's owner row has no account by design and is always live.
"""

from __future__ import annotations

import uuid
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import ListingMedia, Owner
from app.errors import AuthorizationError, ConflictError

__all__ = [
    "BATCH_LIMIT",
    "OWNER_LIMIT",
    "UNCOUNTED",
    "counted",
    "limit_reached",
    "lock_owner",
    "owner_departed",
    "require_room",
]

#: Photos on the owner's own page.
OWNER_LIMIT: Final[int] = 12

#: Photos on one batch's page.
BATCH_LIMIT: Final[int] = 8

#: The statuses that free a slot.
UNCOUNTED: Final[tuple[str, ...]] = ("rejected", "withdrawn")


def limit_reached() -> ConflictError:
    """Build the refusal every photo quota shares.

    :return: The error
    """
    return ConflictError(
        code="MEDIA_LIMIT_REACHED", message_key="hub.media.limit_reached"
    )


def lock_owner(session: Session, owner_id: uuid.UUID) -> bool:
    """Lock the owner row until the caller's transaction ends, and check it.

    The result is the check, read under the lock: a caller that ignores it
    can write a photo for an owner whose account was deleted while it waited.

    :param session: The caller's session
    :param owner_id: The owner
    :return: True when the owner may still have photos written for it: a
        centre, or a solo teacher whose account still exists. False when the
        row is gone or is a solo teacher's whose account was deleted.
    """
    row = session.execute(
        sa.select(Owner.kind, Owner.account_id)
        .where(Owner.id == owner_id)
        .with_for_update()
    ).one_or_none()
    return row is not None and (row.kind != "teacher" or row.account_id is not None)


def owner_departed() -> AuthorizationError:
    """Build the refusal a teacher gets when its owner's account is gone.

    The same answer a request without a teacher lens gets, because that is
    what the request now is.

    :return: The error
    """
    return AuthorizationError(
        code="NO_TEACHER_LENS", message_key="authz.lens.not_available"
    )


def counted(session: Session, owner_id: uuid.UUID, batch_id: uuid.UUID | None) -> int:
    """Count the photos occupying one gallery's slots.

    :param session: The session
    :param owner_id: The owner
    :param batch_id: The batch, or None for the owner's own gallery
    :return: The count
    """
    gallery = (
        ListingMedia.batch_id.is_(None)
        if batch_id is None
        else ListingMedia.batch_id == batch_id
    )
    return int(
        session.execute(
            sa.select(sa.func.count()).where(
                ListingMedia.owner_id == owner_id,
                gallery,
                ListingMedia.status.not_in(UNCOUNTED),
            )
        ).scalar_one()
    )


def require_room(
    session: Session, owner_id: uuid.UUID, batch_id: uuid.UUID | None
) -> None:
    """Refuse an upload to a full gallery.

    Call after :func:`lock_owner`, in the same transaction.

    :param session: The upload's session
    :param owner_id: The owner
    :param batch_id: The batch, or None for the owner's own gallery
    :return: None
    :raises ConflictError: The gallery is full
    """
    limit = OWNER_LIMIT if batch_id is None else BATCH_LIMIT
    if counted(session, owner_id, batch_id) >= limit:
        raise limit_reached()
