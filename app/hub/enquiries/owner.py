"""The owner's side of a join request: list, read one and close it.

**Owner scoping is the lens** (Task 5 serves this through ``TeacherLens``
routes). Every statement here filters on ``owner_id = lens.owner_id``, the
value :func:`app.api.deps.teacher_lens` resolves for an account that runs
the listing, the same people :func:`app.hub.listings.shared.managing_accounts`
delivers to: a solo tutor, or each of a centre's accepted managers, who
share one inbox. A missing request and another owner's request answer the
one ``ENQUIRY_NOT_FOUND``, so an id never says whether it exists.

**The contact predicate** (Review Focus 1) is computed in the SELECT, read
live from ``account`` and never copied into the request (Call 4): with
``share_contact`` the owner sees the account's phone, or its email only
when it has no phone; without it, neither.

**What the owner may answer** is :data:`OwnerEnquiry.outcomes_allowed`,
and :func:`close` accepts exactly those outcomes, so the clients render
the actions it lists and decide nothing:

* ``not_now`` always;
* ``added`` only with a shared contact, since without one there is nobody
  to seat (the table's CHECK says the same);
* ``call_us`` only while the owner is a row of ``hub_public_owner`` with a
  public number [F11]. That is where the guardian reads the number from,
  so a hidden or suspended owner, whose number the guardian cannot see,
  cannot tell them to call it.

A closed request allows nothing. A suspended listing does not block
closing with the other outcomes.

**Closing** locks the request row first, then writes the guardian's
answer and marks every manager's ``hub_enquiry_received`` copy read, the
same order a withdrawal takes [F7], so the two serialise rather than
deadlock. The answer's preview is the outcome code and nothing else.

``student_name``, ``message`` and the contact are never logged; nothing
here logs at all. No account id appears in an :class:`OwnerEnquiry`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final, cast, get_args

import sqlalchemy as sa
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.hub.enquiries.sending import EnquiryOutcome, EnquiryStatus
from app.notifications.inbox import (
    HUB_ENQUIRY_ANSWERED,
    HUB_ENQUIRY_RECEIVED,
    deliver,
    mark_read_for_source,
)

__all__ = ["LIST_LIMIT", "OUTCOMES", "OwnerEnquiry", "close", "get", "list_for"]

#: How many requests the owner's list returns.
LIST_LIMIT: Final = 100

#: Every outcome, in the order the enum declares them and the list shows
#: the allowed ones. Read off :data:`~app.hub.enquiries.sending.EnquiryOutcome`
#: rather than spelled a third time; ``tests/contract/test_enquiry_contract.py``
#: holds both to the model's ``HUB_ENQUIRY_OUTCOME_VALUES``.
OUTCOMES: Final[tuple[EnquiryOutcome, ...]] = get_args(EnquiryOutcome)

#: The owner's requests as they see them. The contact columns are the
#: contact predicate; ``can_call`` is whether the guardian would be shown
#: a number to call [F11]. Join requests only: interests have their own
#: list and are closed by their own route [0049].
_SELECT: Final = """
    SELECT e.id, e.batch_id, bl.public_title AS batch_title, e.student_name,
           e.class_level, e.message, e.share_contact, e.status, e.outcome,
           e.created_at,
           CASE WHEN e.share_contact THEN a.phone END AS guardian_phone,
           CASE WHEN e.share_contact AND a.phone IS NULL THEN a.email END
               AS guardian_email,
           p.public_contact_phone IS NOT NULL AS can_call
    FROM listing_enquiry e
    JOIN account a ON a.id = e.enquirer_account_id
    LEFT JOIN batch_listing bl ON bl.batch_id = e.batch_id
    LEFT JOIN hub_public_owner p ON p.owner_id = e.owner_id
    WHERE e.owner_id = :owner_id AND e.kind = 'join'
"""

#: The owner's list: open first, then newest.
_LIST: Final = sa.text(
    _SELECT + " ORDER BY e.status = 'open' DESC, e.created_at DESC, e.id DESC"
    " LIMIT :limit"
)

#: One of the owner's requests.
_ONE: Final = sa.text(_SELECT + " AND e.id = :enquiry_id")

#: The request to close, locked, with whom to answer and what to call it.
_LOCK: Final = sa.text(
    """
    SELECT e.enquirer_account_id,
           COALESCE(bl.public_title, ol.public_name, '') AS batch_name
    FROM listing_enquiry e
    LEFT JOIN batch_listing bl ON bl.batch_id = e.batch_id
    LEFT JOIN owner_listing ol ON ol.owner_id = e.owner_id
    WHERE e.id = :enquiry_id AND e.owner_id = :owner_id AND e.kind = 'join'
    FOR UPDATE OF e
    """
)

#: Close the locked request.
_CLOSE: Final = sa.text(
    """
    UPDATE listing_enquiry
    SET status = 'closed', outcome = CAST(:outcome AS hub_enquiry_outcome),
        closed_at = :now
    WHERE id = :enquiry_id
    """
)


@dataclass(frozen=True, slots=True)
class OwnerEnquiry:
    """One join request, as the people who run the listing see it.

    :ivar id: The request
    :ivar batch_id: The batch asked about, or None for the owner as a whole
    :ivar batch_title: That batch's public title, or None
    :ivar student_name: As the guardian typed it
    :ivar class_level: One of the hub class levels
    :ivar message: As typed, or None
    :ivar status: ``open`` or ``closed``
    :ivar outcome: How it was answered, or None while open
    :ivar received_at: When it was sent
    :ivar guardian_phone: The guardian's phone, only when they shared their
        contact
    :ivar guardian_email: The guardian's email, only when they shared their
        contact and have no phone
    :ivar outcomes_allowed: What :func:`close` would accept now, in
        :data:`OUTCOMES` order; empty once closed
    """

    id: uuid.UUID
    batch_id: uuid.UUID | None
    batch_title: str | None
    student_name: str
    class_level: str
    message: str | None
    status: EnquiryStatus
    outcome: EnquiryOutcome | None
    received_at: dt.datetime
    guardian_phone: str | None
    guardian_email: str | None
    outcomes_allowed: list[EnquiryOutcome]


def _allowed(
    status: EnquiryStatus, share_contact: bool, can_call: bool
) -> list[EnquiryOutcome]:
    """Say which outcomes a request may be closed with.

    The one rule both :data:`OwnerEnquiry.outcomes_allowed` and
    :func:`close` read.

    :param status: The request's status
    :param share_contact: Whether its guardian shared their contact
    :param can_call: Whether the owner is public with a number
    :return: The allowed outcomes, in :data:`OUTCOMES` order
    """
    if status == "closed":
        return []
    permitted = {"added": share_contact, "not_now": True, "call_us": can_call}
    return [outcome for outcome in OUTCOMES if permitted[outcome]]


def _owner_enquiry(row: Row[tuple[object, ...]]) -> OwnerEnquiry:
    """Map a row of :data:`_LIST` or :data:`_ONE`.

    :param row: The row
    :return: The request
    """
    status = cast("EnquiryStatus", row.status)
    return OwnerEnquiry(
        id=cast("uuid.UUID", row.id),
        batch_id=cast("uuid.UUID | None", row.batch_id),
        batch_title=cast("str | None", row.batch_title),
        student_name=cast("str", row.student_name),
        class_level=cast("str", row.class_level),
        message=cast("str | None", row.message),
        status=status,
        outcome=cast("EnquiryOutcome | None", row.outcome),
        received_at=cast("dt.datetime", row.created_at),
        guardian_phone=cast("str | None", row.guardian_phone),
        guardian_email=cast("str | None", row.guardian_email),
        outcomes_allowed=_allowed(status, bool(row.share_contact), bool(row.can_call)),
    )


def _not_found() -> AuthorizationError:
    """Build the one refusal for a missing or another owner's request.

    :return: ``ENQUIRY_NOT_FOUND`` (404)
    """
    return AuthorizationError(
        code="ENQUIRY_NOT_FOUND",
        message_key="hub.enquiry.not_found",
        status=404,
    )


def list_for(session: Session, lens: TeacherLens) -> list[OwnerEnquiry]:
    """Read the owner's requests, open first, then newest.

    :param session: The session to read through
    :param lens: The teacher lens naming the owner
    :return: At most :data:`LIST_LIMIT` requests
    """
    rows = session.execute(_LIST, {"owner_id": lens.owner_id, "limit": LIST_LIMIT})
    return [_owner_enquiry(row) for row in rows]


def get(session: Session, lens: TeacherLens, enquiry_id: uuid.UUID) -> OwnerEnquiry:
    """Read one of the owner's requests.

    :param session: The session to read through
    :param lens: The teacher lens naming the owner
    :param enquiry_id: The request
    :return: The request
    :raises AuthorizationError: ``ENQUIRY_NOT_FOUND`` (404) for a missing
        request or another owner's
    """
    row = session.execute(
        _ONE, {"owner_id": lens.owner_id, "enquiry_id": enquiry_id}
    ).one_or_none()
    if row is None:
        raise _not_found()
    return _owner_enquiry(row)


def close(
    session: Session,
    lens: TeacherLens,
    enquiry_id: uuid.UUID,
    outcome: EnquiryOutcome,
    now: dt.datetime,
) -> OwnerEnquiry:
    """Answer a request, tell its guardian and settle the owners' inbox.

    Locks the request row before touching any inbox item [F7]. Commits on
    success and rolls back on any failure, so a refusal changes nothing.
    The request returned is read inside the closing transaction, so a
    withdrawal waiting on the row cannot turn a successful close into a
    404.

    :param session: The session to write through
    :param lens: The teacher lens naming the owner
    :param enquiry_id: The request
    :param outcome: ``added``, ``not_now`` or ``call_us``
    :param now: The moment of closing
    :return: The closed request
    :raises AuthorizationError: ``ENQUIRY_NOT_FOUND`` (404) for a missing
        request or another owner's
    :raises ConflictError: ``ENQUIRY_ALREADY_CLOSED`` (409)
    :raises ValidationError: ``ENQUIRY_OUTCOME_INVALID`` (400) for an
        outcome not in the request's ``outcomes_allowed``
    """
    scope = {"owner_id": lens.owner_id, "enquiry_id": enquiry_id}
    try:
        locked = session.execute(_LOCK, scope).one_or_none()
        if locked is None:
            raise _not_found()
        current = _owner_enquiry(session.execute(_ONE, scope).one())
        if current.status == "closed":
            raise ConflictError(
                code="ENQUIRY_ALREADY_CLOSED",
                message_key="hub.enquiry.already_closed",
            )
        if outcome not in current.outcomes_allowed:
            raise ValidationError(
                code="ENQUIRY_OUTCOME_INVALID",
                message_key="hub.enquiry.outcome_invalid",
            )
        session.execute(
            _CLOSE, {"outcome": outcome, "now": now, "enquiry_id": enquiry_id}
        )
        deliver(
            session,
            account_ids=[locked.enquirer_account_id],
            kind=HUB_ENQUIRY_ANSWERED,
            batch_name=locked.batch_name,
            now=now,
            source_id=enquiry_id,
            preview=outcome,
        )
        mark_read_for_source(
            session, kind=HUB_ENQUIRY_RECEIVED, source_id=enquiry_id, now=now
        )
        # Read back under the lock: once committed, a waiting withdrawal
        # may remove the request before a later read could see it.
        closed = _owner_enquiry(session.execute(_ONE, scope).one())
        session.commit()
    except Exception:
        session.rollback()
        raise
    return closed
