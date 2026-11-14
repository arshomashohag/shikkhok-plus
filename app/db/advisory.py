"""The one helper that names advisory keys and takes them in order.

**Why one helper** [U2: NFR4.2]. Several paths serialise on the same
keys: a teacher save and a contact match on a contact [BR2.7], two
contact changes and a deletion on an account [LO-4]. Two transactions
taking overlapping keys in different orders could wait on each other in
a cycle, so every key is computed here and taken by :func:`lock_keys`,
in one total order: by namespace (``student:``, then ``account:``, then
``contact:``), and by ascending 64-bit key within a namespace [LO-1].

Transaction-scoped (``pg_advisory_xact_lock``), so released at commit or
rollback; correct across application instances [NFR8.9]; per contact or
per account, never global [NFR8.11]; and bounded by the engine's
``lock_timeout`` [NFR4.4]. A leaf module, so the roster and the matcher
can both import it without importing each other.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

__all__ = ["account_key", "contact_key", "lock_keys"]

#: The order namespaces are taken in [NFR4.2 LO-1]. The ``student:`` key
#: is the create-replay key ``replayed_student`` takes itself.
_NAMESPACE_ORDER: Final = ("student", "account", "contact")

#: One key's lock. ``hashtextextended`` is the form ``replayed_student``
#: already uses, so every advisory key in the product shares one space.
_LOCK: Final = sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))")

#: The 64-bit value each key locks on, to order several keys by it.
_HASHES: Final = sa.text(
    "SELECT key, hashtextextended(key, 0) AS hashed "
    "FROM unnest(CAST(:keys AS text[])) AS key"
)


def account_key(account_id: uuid.UUID) -> str:
    """Name the key that serialises one account's contact changes.

    :param account_id: The account
    :return: The key
    """
    return f"account:{account_id}"


def contact_key(kind: str, value: str) -> str:
    """Name the key for one canonical contact [BR2.7].

    The kind is part of the key, so a phone and an email can never share
    one by coincidence of spelling.

    :param kind: ``phone`` or ``email``
    :param value: The canonical contact
    :return: The key
    """
    return f"contact:{kind}:{value}"


def lock_keys(session: Session, keys: Iterable[str]) -> None:
    """Take transaction-scoped advisory locks on keys, in the one order.

    A key already held by this transaction is taken again harmlessly:
    advisory locks are re-entrant within a transaction.

    :param session: The session whose transaction takes the locks
    :param keys: The keys, in any order, duplicates allowed
    :return: None
    """
    distinct = sorted(set(keys))
    if len(distinct) > 1:
        hashed: dict[str, int] = {
            str(key): int(value)
            for key, value in session.execute(_HASHES, {"keys": distinct})
        }
        distinct.sort(
            key=lambda key: (_NAMESPACE_ORDER.index(key.split(":", 1)[0]), hashed[key])
        )
    for key in distinct:
        session.execute(_LOCK, {"key": key})
