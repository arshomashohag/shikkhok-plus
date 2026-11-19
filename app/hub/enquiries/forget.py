"""Forget join requests totally: the request and every inbox item about it.

**Deletion is total** (Call 12; Review Focus 4). A guardian may withdraw a
request at any time, and nothing of it may outlive the withdrawal: not the
row, not the owners' ``hub_enquiry_received`` items and not the guardian's
``hub_enquiry_answered`` item. The guardian's withdrawal (Task 3), and
account deletion of the guardian or of a solo owner (Task 7), all come
through :func:`forget`; account deletion collects its requests with
:func:`for_account`. The switch never gates it.

**Callers hold the row locks** [F7]. Each caller first takes ``SELECT ...
FOR UPDATE`` on the requests it forgets, before this touches an inbox item,
because the owner's close locks the request row first and then marks inbox
items read. Locking in the same order means the two serialise; deleting the
items first would deadlock against a close already holding the row.

**One lock statement, in id order** [H4 T10-a]. :func:`for_account` locks
the requests an account sent and the requests its solo owner received in a
single ``ORDER BY id FOR UPDATE``. Two accounts deleted at once, each holding
a request of the other's, then queue on the same first row instead of each
locking its own and waiting on the other's.

Neither function commits.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import Notification
from app.notifications.inbox import HUB_ENQUIRY_ANSWERED, HUB_ENQUIRY_RECEIVED

__all__ = ["for_account", "forget"]

#: Every inbox kind a request produces, for either party.
_KINDS: Final = (HUB_ENQUIRY_RECEIVED, HUB_ENQUIRY_ANSWERED)

#: The requests themselves.
_DELETE: Final = sa.text("DELETE FROM listing_enquiry WHERE id = ANY(:ids)")

#: Every request an account sent, and every request its solo owner
#: received, locked in id order in one statement. A centre's owner row has
#: no account, so a manager's deletion matches none of the centre's; the
#: ``owner`` row is retained, so its cascade would never reach the rest.
_LOCK_FOR_ACCOUNT: Final = sa.text(
    """
    SELECT id FROM listing_enquiry
    WHERE enquirer_account_id = :account_id
       OR owner_id IN (SELECT id FROM owner
                       WHERE account_id = :account_id AND kind = 'teacher')
    ORDER BY id
    FOR UPDATE
    """
)


def forget(session: Session, enquiry_ids: Sequence[uuid.UUID]) -> None:
    """Delete requests and every recipient's inbox items about them.

    :param session: The caller's session, inside its transaction, already
        holding each request's row lock
    :param enquiry_ids: The requests; ids that do not exist are ignored
    :return: None
    """
    ids = list(enquiry_ids)
    if not ids:
        return
    # One statement for both kinds and every request: account deletion
    # forgets many at once.
    session.execute(
        sa.delete(Notification).where(
            Notification.kind.in_(_KINDS), Notification.source_id.in_(ids)
        )
    )
    session.execute(_DELETE, {"ids": ids})


def for_account(session: Session, account_id: uuid.UUID) -> int:
    """Forget every request an account sent or its solo owner received.

    For account deletion (Task 7). Locks the requests first, in id order,
    then hands them to :func:`forget`, in the caller's transaction, so they
    go with the solo owner's listing or not at all. A request deleted by a
    concurrent withdrawal or deletion while this waited is skipped by the
    lock and not counted.

    :param session: The deletion's session, inside its transaction
    :param account_id: The account being deleted
    :return: How many requests were forgotten
    """
    ids = list(session.scalars(_LOCK_FOR_ACCOUNT, {"account_id": account_id}))
    forget(session, ids)
    return len(ids)
