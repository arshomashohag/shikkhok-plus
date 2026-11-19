"""The guardian's side of a join request: describe, send, read and withdraw.

**Who may send** is :func:`app.hub.enquiries.target.resolve`, one SQL
statement; every target the caller may not ask answers the one
``ENQUIRY_TARGET_NOT_FOUND``.

**Contact travels only through the consent box** (Call 5) [F10]. A student
name or message holding a phone number or a web address is refused with
``ENQUIRY_CONTAINS_CONTACT``, naming only the field, before anything is
read or written. Otherwise a guardian who left "share" unticked could type
their number anyway, and ``share_contact`` would not mean what it says.

**Only a stored request is counted** (Call 9), on the H4 pattern: the insert
comes first, and the daily allowance is consumed by the non-committing
consume only once a request was actually written. A send refused for its
text, its target or an open request spends nothing; a breach rolls the new
request back with the count.

**One open request per owner** is the partial unique index
``uq_listing_enquiry_open``: the send is ``INSERT ... ON CONFLICT DO
NOTHING``, never a check-then-insert, and the call that loses a race
answers ``ENQUIRY_ALREADY_OPEN``.

**The owners hear of it, and nothing the guardian typed travels.** Every
account that runs the listing gets one ``hub_enquiry_received`` item naming
the batch's public title (else the listing's public name), with no preview.

**A send never outlives either party's deletion** [H5 T7 review]. Before
it decides, a send takes the caller's account key -- the first lock an
account deletion takes -- and then the owner listing's row ``FOR SHARE``,
holding both until it commits. The ``owner`` row is retained by a deletion,
so its foreign key would never notice one; the listing is the row that goes,
and a deletion locks it ``FOR UPDATE`` before it collects the owner's
requests. So a send already holding either lock is collected by the
deletion that waits for it, and a send that waits on a deletion finds the
account gone (the 401 a deleted account's token gets) or the listing gone
(the one ``ENQUIRY_TARGET_NOT_FOUND``). The order is key, listing, request,
inbox, as in the deletion; nothing locks a request and then a listing.

**Withdrawal is total and never switch-gated**: :func:`withdraw` locks the
caller's row, then hands it to :func:`app.hub.enquiries.forget.forget`.

``student_name``, ``message`` and the guardian's contact are never logged;
nothing here logs at all.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final, Literal, cast

import sqlalchemy as sa
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from app.accounts.phone import contains_phone
from app.auth.ceilings import CeilingChecker
from app.db.advisory import account_key, lock_keys
from app.db.models import Owner
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.hub.enquiries import forget, target
from app.hub.listings.shared import managing_accounts
from app.local_time import bangladesh_today
from app.notifications.inbox import HUB_ENQUIRY_RECEIVED, deliver
from app.reviews.content import contains_url

__all__ = [
    "MAX_MESSAGE",
    "MAX_STUDENT_NAME",
    "MINE_LIMIT",
    "EnquiryTarget",
    "MyEnquiry",
    "describe",
    "mine",
    "send",
    "withdraw",
]

#: The longest student name, counted after stripping (Call 10).
MAX_STUDENT_NAME: Final = 80

#: The longest message, counted after stripping (Call 10; FR-41).
MAX_MESSAGE: Final = 300

#: How many of their own requests a guardian's list returns, newest first.
MINE_LIMIT: Final = 50

#: Where a request is.
EnquiryStatus = Literal["open", "closed"]

#: How the owner answered it (Call 7).
EnquiryOutcome = Literal["added", "not_now", "call_us"]

#: The caller's contact kind, and whether they already have a request open
#: with the owner.
_CALLER: Final = sa.text(
    """
    SELECT a.phone IS NOT NULL AS has_phone,
           EXISTS (
               SELECT 1 FROM listing_enquiry e
               WHERE e.owner_id = :owner_id
                 AND e.enquirer_account_id = a.id
                 AND e.status = 'open'
           ) AS already_open
    FROM account a
    WHERE a.id = :account_id
    """
)

#: Whether the caller's account still exists, read under its key.
_ACCOUNT_EXISTS: Final = sa.text("SELECT 1 FROM account WHERE id = :account_id")

#: The asked owner's listing, held until the send commits, so a deletion
#: cannot remove it between the decision and the insert.
_HOLD_LISTING: Final = sa.text(
    "SELECT owner_id FROM owner_listing WHERE slug = :slug FOR SHARE"
)

#: A new request; nothing when one is already open with this owner.
_CREATE: Final = sa.text(
    """
    INSERT INTO listing_enquiry (owner_id, batch_id, enquirer_account_id,
                                 student_name, class_level, message,
                                 share_contact, created_at)
    VALUES (:owner_id, :batch_id, :account_id, :student_name, :class_level,
            :message, :share_contact, :now)
    ON CONFLICT (owner_id, enquirer_account_id) WHERE status = 'open'
    DO NOTHING
    RETURNING id
    """
)

#: A guardian's requests as they see them. The owner's published number
#: appears only on a ``call_us`` answer, and only while the owner is public.
_MINE_SELECT: Final = """
    SELECT e.id, ol.public_name AS owner_public_name,
           bl.public_title AS batch_title, e.student_name, e.class_level,
           e.message, e.share_contact, e.status, e.outcome, e.created_at,
           CASE WHEN e.outcome = 'call_us' THEN p.public_contact_phone END
               AS owner_contact_phone
    FROM listing_enquiry e
    LEFT JOIN owner_listing ol ON ol.owner_id = e.owner_id
    LEFT JOIN batch_listing bl ON bl.batch_id = e.batch_id
    LEFT JOIN hub_public_owner p ON p.owner_id = e.owner_id
    WHERE e.enquirer_account_id = :account_id
"""

#: The caller's requests, newest first.
_MINE: Final = sa.text(
    _MINE_SELECT + " ORDER BY e.created_at DESC, e.id DESC LIMIT :limit"
)

#: One of the caller's requests.
_ONE: Final = sa.text(_MINE_SELECT + " AND e.id = :enquiry_id")

#: The caller's own request, locked before anything about it is removed.
_LOCK_OWN: Final = sa.text(
    """
    SELECT id FROM listing_enquiry
    WHERE id = :enquiry_id AND enquirer_account_id = :account_id
    FOR UPDATE
    """
)


@dataclass(frozen=True, slots=True)
class EnquiryTarget:
    """What the request form shows before the guardian sends.

    Informed consent needs the name of whoever would receive the number.

    :ivar owner_public_name: The listing's public name
    :ivar batch_title: The batch's public title, or None for the owner
    :ivar contact_kind: What "share" would share: the account's phone when
        it has one, else its email address
    :ivar already_open: The caller already has a request open with this
        owner, so a send would answer ``ENQUIRY_ALREADY_OPEN``
    """

    owner_public_name: str
    batch_title: str | None
    contact_kind: Literal["phone", "email"]
    already_open: bool


@dataclass(frozen=True, slots=True)
class MyEnquiry:
    """One of the caller's own requests, as they may see it.

    Carries no account id of anyone, and never the guardian's own contact.

    :ivar id: The request
    :ivar owner_public_name: The listing's public name, or None once the
        listing itself is gone
    :ivar batch_title: The batch's public title, or None
    :ivar student_name: As the guardian typed it
    :ivar class_level: One of the hub class levels
    :ivar message: As typed, or None
    :ivar share_contact: Whether they chose to share their contact
    :ivar status: ``open`` or ``closed``
    :ivar outcome: How the owner answered, or None while open
    :ivar sent_on: The day it was sent, in Bangladesh
    :ivar owner_contact_phone: The owner's published number, only on a
        ``call_us`` answer and only while the owner's listing is public
    """

    id: uuid.UUID
    owner_public_name: str | None
    batch_title: str | None
    student_name: str
    class_level: str
    message: str | None
    share_contact: bool
    status: EnquiryStatus
    outcome: EnquiryOutcome | None
    sent_on: dt.date
    owner_contact_phone: str | None


def _my_enquiry(row: Row[tuple[object, ...]]) -> MyEnquiry:
    """Map a row of :data:`_MINE` or :data:`_ONE`.

    :param row: The row
    :return: The request
    """
    return MyEnquiry(
        id=cast("uuid.UUID", row.id),
        owner_public_name=cast("str | None", row.owner_public_name),
        batch_title=cast("str | None", row.batch_title),
        student_name=cast("str", row.student_name),
        class_level=cast("str", row.class_level),
        message=cast("str | None", row.message),
        share_contact=cast("bool", row.share_contact),
        status=cast("EnquiryStatus", row.status),
        outcome=cast("EnquiryOutcome | None", row.outcome),
        sent_on=bangladesh_today(cast("dt.datetime", row.created_at)),
        owner_contact_phone=cast("str | None", row.owner_contact_phone),
    )


def describe(
    session: Session,
    account_id: uuid.UUID,
    owner_slug: str,
    batch_id: uuid.UUID | None,
) -> EnquiryTarget:
    """Say who a request would reach and what "share" would share.

    :param session: The session to read through
    :param account_id: The authenticated caller
    :param owner_slug: The owner's public slug
    :param batch_id: The batch asked about, or None
    :return: The target as the form shows it
    :raises AuthorizationError: ``ENQUIRY_TARGET_NOT_FOUND`` (404)
    """
    found = target.resolve(session, account_id, owner_slug, batch_id)
    caller = session.execute(
        _CALLER, {"owner_id": found.owner_id, "account_id": account_id}
    ).one()
    return EnquiryTarget(
        owner_public_name=found.owner_public_name,
        batch_title=found.batch_title,
        contact_kind="phone" if caller.has_phone else "email",
        already_open=bool(caller.already_open),
    )


def _within(field: str, text: str, longest: int) -> None:
    """Refuse text that is empty or too long after stripping.

    :param field: The field's name, returned to the client
    :param text: The stripped text
    :param longest: Its longest allowed length
    :return: None
    :raises ValidationError: ``REQUEST_INVALID`` naming the field
    """
    if not 1 <= len(text) <= longest:
        raise ValidationError(
            code="REQUEST_INVALID",
            message_key="error.unexpected",
            details={"fields": field},
        )


def _refuse_contact(field: str, text: str | None) -> None:
    """Refuse text carrying a phone number or a web address [F10].

    :param field: The field's name, returned to the client
    :param text: The stripped text, or None for none
    :return: None
    :raises ValidationError: ``ENQUIRY_CONTAINS_CONTACT`` (400)
    """
    if text is None:
        return
    if contains_phone(text) or contains_url(text):
        raise ValidationError(
            code="ENQUIRY_CONTAINS_CONTACT",
            message_key="hub.enquiry.contains_contact",
            details={"field": field},
        )


def _hold(session: Session, account_id: uuid.UUID, owner_slug: str) -> None:
    """Take the send's locks, before anything is decided.

    The caller's account key first, then the listing ``FOR SHARE``: the
    order an account deletion takes its own key and then a solo owner's
    listing, so the two never wait on each other in a cycle.

    :param session: The send's session, inside its transaction
    :param account_id: The authenticated guardian
    :param owner_slug: The owner's public slug
    :return: None
    :raises AuthorizationError: ``NOT_AUTHENTICATED`` (401) when the account
        was deleted after authentication; ``ENQUIRY_TARGET_NOT_FOUND`` (404)
        when no listing has the slug, or it was deleted while this waited
    """
    lock_keys(session, [account_key(account_id)])
    if session.execute(_ACCOUNT_EXISTS, {"account_id": account_id}).first() is None:
        # Deleted between authentication and here: the next request is a
        # 401 anyway, so this one answers as that one will.
        raise AuthorizationError(
            code="NOT_AUTHENTICATED", message_key="auth.token.not_valid", status=401
        )
    if session.execute(_HOLD_LISTING, {"slug": owner_slug}).first() is None:
        raise target.not_found()


def _notify_owners(
    session: Session,
    found: target.Target,
    enquiry_id: uuid.UUID,
    now: dt.datetime,
) -> None:
    """Tell everyone who runs the listing that a request arrived.

    :param session: The send's session
    :param found: The request's target
    :param enquiry_id: The new request
    :param now: When it was sent
    :return: None
    """
    owner = session.execute(
        sa.select(Owner).where(Owner.id == found.owner_id)
    ).scalar_one()
    deliver(
        session,
        account_ids=managing_accounts(session, owner),
        kind=HUB_ENQUIRY_RECEIVED,
        batch_name=found.batch_title or found.owner_public_name,
        now=now,
        source_id=enquiry_id,
        preview=None,
    )


def send(
    session: Session,
    account_id: uuid.UUID,
    owner_slug: str,
    *,
    student_name: str,
    class_level: str,
    message: str | None,
    batch_id: uuid.UUID | None,
    share_contact: bool,
    now: dt.datetime,
) -> MyEnquiry:
    """Send a join request, and tell the people who run the listing.

    Commits on success and rolls back on any failure, so a refusal stores
    and counts nothing.

    :param session: The session to write through
    :param account_id: The authenticated guardian
    :param owner_slug: The owner's public slug
    :param student_name: The student's name; stripped
    :param class_level: One of the hub class levels
    :param message: An optional message; stripped, and None when blank
    :param batch_id: The batch asked about, or None for the owner
    :param share_contact: Whether the owner may see the guardian's contact
    :param now: The moment of sending
    :return: The request as the guardian sees it
    :raises ValidationError: ``ENQUIRY_CONTAINS_CONTACT`` for a number or
        address in the text, ``REQUEST_INVALID`` for a length out of range
    :raises AuthorizationError: ``ENQUIRY_TARGET_NOT_FOUND`` (404), or
        ``NOT_AUTHENTICATED`` (401) when the account was deleted meanwhile
    :raises ConflictError: ``ENQUIRY_ALREADY_OPEN`` while a request to this
        owner is open
    :raises CeilingBreach: ``HUB_ENQUIRY_CEILING``, the sixth request today
    """
    name = student_name.strip()
    text = None if message is None else message.strip() or None
    _within("student_name", name, MAX_STUDENT_NAME)
    if text is not None:
        _within("message", text, MAX_MESSAGE)
    _refuse_contact("student_name", name)
    _refuse_contact("message", text)
    try:
        _hold(session, account_id, owner_slug)
        # Decided after the locks, so a listing deleted while this waited is
        # refused rather than trusted from an earlier read. The slug is
        # unique and cannot change while held, so `resolve` reads the row
        # held above.
        found = target.resolve(session, account_id, owner_slug, batch_id)
        enquiry_id = session.execute(
            _CREATE,
            {
                "owner_id": found.owner_id,
                "batch_id": found.batch_id,
                "account_id": account_id,
                "student_name": name,
                "class_level": class_level,
                "message": text,
                "share_contact": share_contact,
                "now": now,
            },
        ).scalar_one_or_none()
        if enquiry_id is None:
            # An open request already holds the index; raising rolls this
            # transaction back, so nothing is counted.
            raise ConflictError(
                code="ENQUIRY_ALREADY_OPEN", message_key="hub.enquiry.already_open"
            )
        # Counted only now that a request was written; a breach rolls the
        # insert back with the count.
        CeilingChecker(session).consume_hub_enquiry_in_transaction(account_id, now)
        _notify_owners(session, found, enquiry_id, now)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return _my_enquiry(
        session.execute(
            _ONE, {"account_id": account_id, "enquiry_id": enquiry_id}
        ).one()
    )


def mine(session: Session, account_id: uuid.UUID) -> list[MyEnquiry]:
    """Read the caller's own requests, newest first.

    Never switch-gated: a guardian can always see what they sent, so they
    can withdraw it.

    :param session: The session to read through
    :param account_id: The authenticated guardian
    :return: At most :data:`MINE_LIMIT` requests
    """
    rows = session.execute(_MINE, {"account_id": account_id, "limit": MINE_LIMIT})
    return [_my_enquiry(row) for row in rows]


def withdraw(session: Session, account_id: uuid.UUID, enquiry_id: uuid.UUID) -> None:
    """Withdraw one of the caller's requests, totally.

    Locks the caller's row first [F7], then forgets it. Another account's
    request, or one that does not exist, changes nothing and is not an
    error. Never switch-gated.

    :param session: The session to write through
    :param account_id: The authenticated guardian
    :param enquiry_id: The request
    :return: None
    """
    try:
        owned = list(
            session.scalars(
                _LOCK_OWN, {"enquiry_id": enquiry_id, "account_id": account_id}
            )
        )
        forget.forget(session, owned)
        session.commit()
    except Exception:
        session.rollback()
        raise
