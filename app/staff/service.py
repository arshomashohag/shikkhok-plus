"""Recording, correcting and ending a centre's staff records [0023].

**A staff record grants nothing.** It is what a manager typed. App access
is an ``owner_member`` row, and a teacher's record links to one through
``member_id``; inviting a teacher writes both in **one transaction**, so a
refused invitation leaves no record behind and a record never claims an
offer that was not made.

**Leaving revokes access in the same step.** A person who has left must
not keep reaching the centre's families because a second action was
forgotten, so :func:`leave` ends the linked membership in the transaction
that records the date.

**Pay terms pair a basis with a rate**, checked here with named codes and
held again by the table's CHECK.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.centres.service import add_invitation, centre_of
from app.db.models import OwnerMember, Staff
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.local_time import bangladesh_today
from app.money import Money

__all__ = [
    "StaffDraft",
    "StaffView",
    "access_of",
    "add_other",
    "invite_teacher",
    "leave",
    "list_staff",
    "read_staff",
    "update_staff",
]

#: The columns a correction may write, and nothing else.
EDITABLE: tuple[str, ...] = (
    "display_name",
    "email",
    "staff_house",
    "staff_road",
    "staff_city",
    "staff_postcode",
    "role_label",
    "pay_basis",
    "pay_rate",
    "joined_on",
)


@dataclass(frozen=True, slots=True)
class StaffDraft:
    """What a manager typed for a new record.

    :ivar display_name: Their name
    :ivar phone: Their number, canonical, or None
    :ivar email: Their email, or None
    :ivar staff_house: House or flat, or None
    :ivar staff_road: Road or area, or None
    :ivar staff_city: City or district, or None
    :ivar staff_postcode: Four digits, or None
    :ivar role_label: What they do, or None
    :ivar pay_basis: How they are paid
    :ivar pay_rate: The salary or rate per class, or None
    :ivar joined_on: When they started, or None for today
    """

    display_name: str
    phone: str | None
    email: str | None
    staff_house: str | None
    staff_road: str | None
    staff_city: str | None
    staff_postcode: str | None
    role_label: str | None
    pay_basis: str
    pay_rate: Money | None
    joined_on: dt.date | None


@dataclass(frozen=True, slots=True)
class StaffView:
    """One record with its access state resolved.

    :ivar staff: The record
    :ivar access: ``none``, ``invited``, ``declined``, ``active`` or
        ``revoked``
    """

    staff: Staff
    access: str


def _check_pay(basis: str, rate: Money | None) -> None:
    """Refuse pay terms that do not pair a basis with a rate.

    :param basis: ``monthly``, ``per_class`` or ``none``
    :param rate: The rate, or None
    :raises ValidationError: A paid basis without a rate above zero, or a
        rate with no basis
    """
    if basis == "none":
        if rate is not None:
            raise ValidationError(
                code="STAFF_PAY_RATE_NOT_ALLOWED",
                message_key="staff.pay.rate_not_allowed",
            )
        return
    if rate is None or not rate.is_positive():
        raise ValidationError(
            code="STAFF_PAY_RATE_REQUIRED", message_key="staff.pay.rate_required"
        )


def access_of(member: OwnerMember | None) -> str:
    """Name where a staff member's app access stands.

    :param member: The linked membership, or None
    :return: The access state
    """
    if member is None:
        return "none"
    if member.revoked_at is not None:
        return "revoked"
    if member.decision == "accepted":
        return "active"
    if member.decision == "declined":
        return "declined"
    return "invited"


def _view(session: Session, staff: Staff) -> StaffView:
    """Resolve a record's access state.

    :param session: The session to read through
    :param staff: The record
    :return: The record and its access
    """
    member = session.get(OwnerMember, staff.member_id) if staff.member_id else None
    return StaffView(staff=staff, access=access_of(member))


def _record(
    session: Session,
    *,
    centre_id: uuid.UUID,
    kind: str,
    draft: StaffDraft,
    created_by: uuid.UUID,
    member_id: uuid.UUID | None,
    now: dt.datetime,
) -> Staff:
    """Add one staff row to the caller's transaction.

    :param session: The session to write through
    :param centre_id: The centre
    :param kind: ``teacher`` or ``other``
    :param draft: What the manager typed
    :param created_by: The manager's account
    :param member_id: The linked membership, or None
    :param now: The moment
    :return: The new row, flushed
    """
    staff = Staff(
        owner_id=centre_id,
        kind=kind,
        display_name=draft.display_name.strip(),
        phone=draft.phone,
        email=draft.email,
        staff_house=draft.staff_house,
        staff_road=draft.staff_road,
        staff_city=draft.staff_city,
        staff_postcode=draft.staff_postcode,
        role_label=draft.role_label if kind == "other" else None,
        member_id=member_id,
        pay_basis=draft.pay_basis,
        pay_rate=draft.pay_rate,
        joined_on=draft.joined_on or bangladesh_today(),
        created_by_account_id=created_by,
        created_at=now,
    )
    session.add(staff)
    session.flush()
    return staff


def invite_teacher(
    session: Session,
    *,
    lens: TeacherLens,
    draft: StaffDraft,
    now: dt.datetime | None = None,
) -> StaffView:
    """Record a teacher and offer them app access, in one transaction.

    :param session: The session to write through
    :param lens: The manager's lens on the centre
    :param draft: What the manager typed; the phone is required
    :param now: The moment, or None for the clock
    :return: The new record, its access ``invited``
    :raises ConflictError: Not a centre, or the number is already live here
    :raises ValidationError: The pay terms do not pair
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    centre = centre_of(session, lens)
    _check_pay(draft.pay_basis, draft.pay_rate)
    member = add_invitation(
        session,
        centre_id=centre.id,
        invited_by=lens.account_id,
        phone=draft.phone or "",
        display_name=draft.display_name,
        role="teacher",
        now=moment,
    )
    staff = _record(
        session,
        centre_id=centre.id,
        kind="teacher",
        draft=draft,
        created_by=lens.account_id,
        member_id=member.id,
        now=moment,
    )
    session.commit()
    return _view(session, staff)


def add_other(
    session: Session,
    *,
    lens: TeacherLens,
    draft: StaffDraft,
    now: dt.datetime | None = None,
) -> StaffView:
    """Record someone who works at the centre and never gets app access.

    :param session: The session to write through
    :param lens: The manager's lens on the centre
    :param draft: What the manager typed
    :param now: The moment, or None for the clock
    :return: The new record, its access ``none``
    :raises ConflictError: Not a centre
    :raises ValidationError: The pay terms do not pair
    """
    centre = centre_of(session, lens)
    _check_pay(draft.pay_basis, draft.pay_rate)
    staff = _record(
        session,
        centre_id=centre.id,
        kind="other",
        draft=draft,
        created_by=lens.account_id,
        member_id=None,
        now=now or dt.datetime.now(tz=dt.UTC),
    )
    session.commit()
    return _view(session, staff)


def _owned(
    session: Session, lens: TeacherLens, staff_id: uuid.UUID, *, lock: bool = False
) -> Staff:
    """Return this centre's record, refusing any other id alike.

    :param session: The session to read through
    :param lens: The manager's lens on the centre
    :param staff_id: The record
    :param lock: Whether to lock the row for a write
    :return: The record
    :raises ConflictError: The workspace is not a centre
    :raises AuthorizationError: No such record in this centre
    """
    centre = centre_of(session, lens)
    query = sa.select(Staff).where(Staff.id == staff_id, Staff.owner_id == centre.id)
    staff = session.scalar(query.with_for_update() if lock else query)
    if staff is None:
        raise AuthorizationError(
            code="NO_TEACHER_LENS", message_key="authz.lens.not_available"
        )
    return staff


def list_staff(session: Session, *, lens: TeacherLens) -> list[StaffView]:
    """List the centre's records: active first, then those who left.

    :param session: The session to read through
    :param lens: The manager's lens on the centre
    :return: Every record, oldest first within each group
    :raises ConflictError: The workspace is not a centre
    """
    centre = centre_of(session, lens)
    rows = session.execute(
        sa.select(Staff, OwnerMember)
        .outerjoin(OwnerMember, OwnerMember.id == Staff.member_id)
        .where(Staff.owner_id == centre.id)
        .order_by(Staff.left_on.is_not(None), Staff.created_at, Staff.id)
    ).all()
    return [StaffView(staff=staff, access=access_of(member)) for staff, member in rows]


def read_staff(
    session: Session, *, lens: TeacherLens, staff_id: uuid.UUID
) -> StaffView:
    """Read one of the centre's records.

    :param session: The session to read through
    :param lens: The manager's lens on the centre
    :param staff_id: The record
    :return: The record and its access
    """
    return _view(session, _owned(session, lens, staff_id))


def update_staff(
    session: Session,
    *,
    lens: TeacherLens,
    staff_id: uuid.UUID,
    changes: dict[str, object],
) -> StaffView:
    """Correct a record's typed facts. Commits.

    :param session: The session to write through
    :param lens: The manager's lens on the centre
    :param staff_id: The record
    :param changes: Column to new value, only for the fields sent
    :return: The corrected record
    :raises ValidationError: The resulting pay terms do not pair, or the
        joining date falls after the leaving date
    """
    staff = _owned(session, lens, staff_id, lock=True)
    for column, value in changes.items():
        # Only the editable columns are ever written; the request schema
        # forbids any other field, so nothing is dropped in practice.
        if column not in EDITABLE:
            continue
        if column == "role_label" and staff.kind != "other":
            continue
        if column == "display_name" and value is None:
            continue
        setattr(staff, column, value)
    _check_pay(staff.pay_basis, staff.pay_rate)
    if staff.left_on is not None and staff.joined_on > staff.left_on:
        raise ValidationError(
            code="STAFF_LEFT_BEFORE_JOINED", message_key="staff.left_before_joined"
        )
    session.commit()
    return _view(session, staff)


def leave(
    session: Session,
    *,
    lens: TeacherLens,
    staff_id: uuid.UUID,
    left_on: dt.date | None = None,
    now: dt.datetime | None = None,
) -> StaffView:
    """Record that someone left, ending their app access in the same step.

    :param session: The session to write through
    :param lens: The manager's lens on the centre
    :param staff_id: The record
    :param left_on: Their last day, or None for today
    :param now: The moment access ends, or None for the clock
    :return: The record, marked left
    :raises ConflictError: They have already left
    :raises ValidationError: The date is before they joined
    """
    staff = _owned(session, lens, staff_id, lock=True)
    if staff.left_on is not None:
        raise ConflictError(code="STAFF_ALREADY_LEFT", message_key="staff.already_left")
    day = left_on or bangladesh_today()
    if day < staff.joined_on:
        raise ValidationError(
            code="STAFF_LEFT_BEFORE_JOINED", message_key="staff.left_before_joined"
        )
    staff.left_on = day
    if staff.member_id is not None:
        member = session.get(OwnerMember, staff.member_id, with_for_update=True)
        if member is not None and member.revoked_at is None:
            member.revoked_at = now or dt.datetime.now(tz=dt.UTC)
    session.commit()
    return _view(session, staff)
