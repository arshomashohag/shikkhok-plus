"""Forget join requests totally: the request and every inbox item about it.

**Deletion is total** (Call 12; Review Focus 4). A guardian may withdraw a
request at any time, and nothing of it may outlive the withdrawal: not the
row, not the owners' ``hub_enquiry_received`` items and not the guardian's
``hub_enquiry_answered`` item. The guardian's withdrawal (Task 3), and
account deletion of the guardian or of a solo owner (Task 7), all come
through :func:`forget`. The switch never gates it.

**Callers hold the row locks** [F7]. Each caller first takes ``SELECT ...
FOR UPDATE`` on the requests it forgets, before this touches an inbox item,
because the owner's close locks the request row first and then marks inbox
items read. Locking in the same order means the two serialise; deleting the
items first would deadlock against a close already holding the row.

:func:`forget` commits nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.notifications.inbox import (
    HUB_ENQUIRY_ANSWERED,
    HUB_ENQUIRY_RECEIVED,
    remove_for_source,
)

__all__ = ["forget"]

#: Every inbox kind a request produces, for either party.
_KINDS: Final = (HUB_ENQUIRY_RECEIVED, HUB_ENQUIRY_ANSWERED)

#: The requests themselves.
_DELETE: Final = sa.text("DELETE FROM listing_enquiry WHERE id = ANY(:ids)")


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
    for kind in _KINDS:
        for enquiry_id in ids:
            remove_for_source(session, kind=kind, source_id=enquiry_id)
    session.execute(_DELETE, {"ids": ids})
