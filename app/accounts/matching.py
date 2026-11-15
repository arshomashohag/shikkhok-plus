"""ContactMatching: linking an account to what teachers and centres recorded.

**One matcher, three moments** [BR3.1]: an account created on a contact,
a phone added or replaced, an email added or replaced. Each calls
:func:`match_contact` once for the contact that has just become the
account's, inside the transaction that made it the account's, so a
rollback of that write undoes the links too [NFR4.6].

**It sets links and never decisions** [BR3.4]. The person is offered an
invitation; nothing here grants a lens. The statements that do the work
belong to their tables' owners -- seats to the roster
(:func:`app.students.service.link_seats`), invitations to the centre
(:func:`app.centres.memberships.link_memberships`) -- and each fills only
an EMPTY, unblocked, unrevoked link, so a link already naming somebody is
never moved [BR3.5, BR3.6] and running twice changes nothing [BR3.8].

**Its first act is the contact's advisory key** [BR2.7], so a teacher
save resolving a target from the same contact either committed first
and is seen here, or waits and then sees this match. Keys are named and
ordered by :mod:`app.db.advisory`, the one helper every U2 path uses
[NFR4.2].
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.accounts.identifier import Identifier
from app.centres.memberships import link_memberships
from app.db import advisory
from app.students.service import link_seats

__all__ = ["contact_key", "lock_account", "lock_contact", "match_contact"]


def contact_key(contact: Identifier) -> str:
    """Name the advisory key for one contact [BR2.7].

    :param contact: The canonical contact
    :return: The key
    """
    return advisory.contact_key(contact.column, contact.value)


def lock_contact(session: Session, contact: Identifier) -> None:
    """Take one contact's advisory key [BR2.7, LO-5].

    Account creation calls this before inserting the account row, so a
    sign-up and a contact add of the same contact cannot wait on each
    other, one on the unique index and the other on this key.

    :param session: The session whose transaction takes the lock
    :param contact: The canonical contact
    :return: None
    """
    advisory.lock_keys(session, [contact_key(contact)])


def lock_account(
    session: Session, account_id: uuid.UUID, contacts: Iterable[Identifier] = ()
) -> None:
    """Take an account's key and its contacts' keys, in the one order.

    The account key serialises two contact changes on one account and a
    deletion of it [LO-4], which is what makes "already holds this kind"
    and "is the last contact" reliable without locking the account row
    ahead of seat rows.

    :param session: The session whose transaction takes the locks
    :param account_id: The account
    :param contacts: The contacts the change touches
    :return: None
    """
    advisory.lock_keys(
        session,
        [advisory.account_key(account_id), *(contact_key(c) for c in contacts)],
    )


def match_contact(
    session: Session, *, account_id: uuid.UUID, contact: Identifier
) -> None:
    """Link everything recorded against a newly verified contact.

    Seats first, then centre invitations, after the contact's advisory
    key. A phone links every empty, unblocked link recording it; an email
    links only those recording no phone [BR3.2, BR3.3]. A constant number
    of statements whatever the number of rows [NFR8.4]. Adds to the
    caller's transaction and never commits.

    :param session: The session to write through
    :param account_id: The account that now holds the contact
    :param contact: The contact, verified
    :return: None
    """
    lock_contact(session, contact)
    link_seats(session, account_id=account_id, kind=contact.column, value=contact.value)
    link_memberships(
        session, account_id=account_id, kind=contact.column, value=contact.value
    )
