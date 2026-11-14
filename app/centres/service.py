"""Creating a centre, and a manager's control over who belongs to it.

**A centre is an owner with no account** [0022]. Its batches, fees and
expenses hang from it exactly as a solo tutor's hang from theirs, so every
teacher route already serves it: a manager acting on the centre holds a
:class:`~app.authz.lenses.TeacherLens` whose ``owner_id`` is the centre,
granted by an accepted, unrevoked ``manager`` membership inside the lens
query itself.

**Naming a number is not that person's agreement.** An invitation is
``pending`` and grants nothing until its holder accepts it -- the rule a
student's seat follows, for the reason D1 exists: a mistyped digit would
otherwise hand a stranger the centre's whole record the moment they signed
up.

**A centre always keeps a manager.** Revoking the last live manager is
refused, because a centre nobody can manage is a set of families' records
nobody can reach or correct.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts.identifier import resolve_link_target
from app.authz.lenses import TeacherLens
from app.db.advisory import contact_key, lock_keys
from app.db.models import Account, Owner, OwnerMember
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.teaching.unassign import unassign_member

__all__ = [
    "MemberRow",
    "WorkspaceRow",
    "add_invitation",
    "centre_of",
    "create_centre",
    "invite_member",
    "list_members",
    "revoke_member",
    "workspaces_of",
]


@dataclass(frozen=True, slots=True)
class MemberRow:
    """One person's place in a centre, as a manager sees it.

    :ivar member_id: The membership
    :ivar display_name: The name the inviting manager typed
    :ivar phone: The number invited, or None for an invitation by email
        alone; a legacy ``""`` is read as None [U2: BR1.9]
    :ivar invited_email: The address invited, or None
    :ivar role: ``manager`` or ``teacher``
    :ivar decision: ``pending``, ``accepted`` or ``declined``
    :ivar invited_at: When they were invited
    :ivar revoked: Whether a manager ended the membership
    :ivar is_you: Whether this membership is the caller's own
    """

    member_id: uuid.UUID
    display_name: str
    phone: str | None
    invited_email: str | None
    role: str
    decision: str
    invited_at: dt.datetime
    revoked: bool
    is_you: bool


@dataclass(frozen=True, slots=True)
class WorkspaceRow:
    """One workspace an account may act on.

    :ivar owner_id: The owner the workspace is
    :ivar kind: ``solo`` for a tutor's own, ``centre`` for a centre
    :ivar name: The centre's name, or None for a solo workspace
    """

    owner_id: uuid.UUID
    kind: str
    name: str | None


def _now(now: dt.datetime | None) -> dt.datetime:
    """Return the given moment or the clock.

    :param now: A fixed moment, or None
    :return: The moment to record
    """
    return now or dt.datetime.now(tz=dt.UTC)


def _clean(text: str) -> str:
    """Trim a typed name, refusing one that is blank.

    :param text: The name as typed
    :return: The trimmed name
    :raises ValidationError: The name is blank
    """
    cleaned = text.strip()
    if not cleaned:
        raise ValidationError(code="NAME_REQUIRED", message_key="centre.name.required")
    return cleaned


def create_centre(
    session: Session,
    *,
    account_id: uuid.UUID,
    name: str,
    manager_name: str,
    now: dt.datetime | None = None,
) -> uuid.UUID:
    """Create a centre with this account as its first manager.

    The membership is ``accepted`` at once, because the person creating
    the centre is the one agreeing to manage it. **The manager's name is
    the one typed for the centre**, never read from the profile: a
    profile is owner-private, and the member list is read by every other
    manager. Adds to the caller's transaction and does not commit.

    :param session: The session to write through
    :param account_id: The account creating it
    :param name: The centre's name
    :param manager_name: How the centre's members see this person
    :param now: The moment of creation, or None for the clock
    :return: The new centre's owner id
    :raises ValidationError: A name is blank
    """
    moment = _now(now)
    centre = Owner(
        account_id=None, kind="organisation", name=_clean(name), created_at=moment
    )
    session.add(centre)
    session.flush()

    # The manager's own contacts, as recorded: no phone is NULL rather than
    # the ``""`` this row used to carry, and the address is kept so an
    # email-only manager's row says how they were reached [U2: BR1.9].
    phone, email = session.execute(
        sa.select(Account.phone, Account.email).where(Account.id == account_id)
    ).one()
    session.add(
        OwnerMember(
            owner_id=centre.id,
            account_id=account_id,
            invited_phone=phone,
            invited_email=email,
            display_name=_clean(manager_name),
            role="manager",
            decision="accepted",
            invited_by_account_id=account_id,
            created_at=moment,
            decided_at=moment,
        )
    )
    session.flush()
    return centre.id


def centre_of(session: Session, lens: TeacherLens) -> Owner:
    """Return the centre this workspace is, refusing a solo workspace.

    :param session: The session to read through
    :param lens: The teacher lens the request acts on
    :return: The centre's owner row
    :raises ConflictError: The workspace is a solo tutor's, which has no
        members to manage
    """
    owner = session.get(Owner, lens.owner_id)
    if owner is None or owner.kind != "organisation":
        raise ConflictError(code="NOT_A_CENTRE", message_key="centre.not_a_centre")
    return owner


def invite_member(
    session: Session,
    *,
    lens: TeacherLens,
    phone: str | None,
    display_name: str,
    role: str,
    now: dt.datetime | None = None,
    email: str | None = None,
) -> uuid.UUID:
    """Invite a number, an address, or both to the centre.

    **Pending, and linked to an account at once only if one already holds
    the contact that decides** -- the phone when one is given, else the
    address [BR2.1]; otherwise the account that later verifies it is
    linked by the matcher. Either way the membership grants nothing until
    its holder accepts. Commits.

    :param session: The session to write through
    :param lens: The manager's lens on the centre
    :param phone: The canonical number invited, or None
    :param display_name: The name the manager typed
    :param role: ``manager`` or ``teacher``
    :param now: The moment, or None for the clock
    :param email: The canonical address invited, or None [U2: FR6.4]
    :return: The new membership
    :raises ConflictError: Not a centre, or the number or the address
        already holds a live membership here
    """
    centre = centre_of(session, lens)
    member = add_invitation(
        session,
        centre_id=centre.id,
        invited_by=lens.account_id,
        phone=phone,
        email=email,
        display_name=display_name,
        role=role,
        now=now,
    )
    session.commit()
    return member.id


def _already_invited() -> ConflictError:
    """Build the refusal for a contact a live invitation here already has.

    :return: The error
    """
    return ConflictError(
        code="MEMBER_ALREADY_INVITED", message_key="centre.member.already_invited"
    )


def add_invitation(
    session: Session,
    *,
    centre_id: uuid.UUID,
    invited_by: uuid.UUID,
    phone: str | None,
    display_name: str,
    role: str,
    now: dt.datetime | None = None,
    email: str | None = None,
) -> OwnerMember:
    """Add a pending membership, refusing a contact already live here.

    The one writer of an invitation, shared by the member routes and the
    staff console so both apply the same rule [BR1.10]. Adds to the
    caller's transaction, flushes, and does not commit.

    **By phone, by email, or both** [U2: BR1.8]. A live invitation of this
    centre holding the phone, or holding the address, refuses the new one.
    The given contacts' advisory keys are taken before the target is
    resolved, so a match for the same contact running now either
    committed first and is seen, or sees this invitation [BR2.7].

    :param session: The session to write through
    :param centre_id: The centre, already checked to be one
    :param invited_by: The inviting manager's account
    :param phone: The canonical number invited, or None
    :param display_name: The name the manager typed
    :param role: ``manager`` or ``teacher``
    :param now: The moment, or None for the clock
    :param email: The canonical address invited, or None
    :return: The new membership
    :raises ConflictError: The number or the address already holds a live
        membership here, including one written concurrently
    :raises ValueError: Neither a number nor an address was given
    """
    phone = phone or None
    if phone is None and email is None:
        raise ValueError("an invitation needs a phone number or an email address")
    contacts = [
        *([("phone", phone)] if phone is not None else []),
        *([("email", email)] if email is not None else []),
    ]
    lock_keys(session, [contact_key(kind, value) for kind, value in contacts])
    same_contact = [
        *([OwnerMember.invited_phone == phone] if phone is not None else []),
        *([OwnerMember.invited_email == email] if email is not None else []),
    ]
    live = session.scalar(
        sa.select(OwnerMember.id).where(
            OwnerMember.owner_id == centre_id,
            sa.or_(*same_contact),
            OwnerMember.revoked_at.is_(None),
        )
    )
    if live is not None:
        raise _already_invited()
    holder = resolve_link_target(session, phone=phone, email=email)
    member = OwnerMember(
        owner_id=centre_id,
        account_id=holder,
        invited_phone=phone,
        invited_email=email,
        display_name=_clean(display_name),
        role=role,
        decision="pending",
        invited_by_account_id=invited_by,
        created_at=_now(now),
    )
    # In a savepoint: two invitations of one number at once both pass the
    # check above, and the partial unique index refuses the second. The
    # savepoint keeps the caller's transaction usable, and the refusal is
    # the same one a sequential duplicate gets [audit C-47].
    try:
        with session.begin_nested():
            session.add(member)
            session.flush()
    except IntegrityError:
        raise ConflictError(
            code="MEMBER_ALREADY_INVITED", message_key="centre.member.already_invited"
        ) from None
    return member


def list_members(session: Session, *, lens: TeacherLens) -> list[MemberRow]:
    """List the centre's members, live ones first, oldest first within.

    :param session: The session to read through
    :param lens: The manager's lens on the centre
    :return: Every membership the centre has recorded
    :raises ConflictError: The workspace is not a centre
    """
    centre = centre_of(session, lens)
    rows = session.scalars(
        sa.select(OwnerMember)
        .where(OwnerMember.owner_id == centre.id)
        .order_by(
            OwnerMember.revoked_at.is_not(None),
            OwnerMember.created_at,
            OwnerMember.id,
        )
    )
    return [
        MemberRow(
            member_id=row.id,
            display_name=row.display_name,
            # A legacy manager row's "" means no phone [BR1.9].
            phone=row.invited_phone or None,
            invited_email=row.invited_email,
            role=row.role,
            decision=row.decision,
            invited_at=row.created_at,
            revoked=row.revoked_at is not None,
            is_you=row.account_id == lens.account_id,
        )
        for row in rows
    ]


def revoke_member(
    session: Session,
    *,
    lens: TeacherLens,
    member_id: uuid.UUID,
    now: dt.datetime | None = None,
) -> None:
    """End a membership, keeping its record. Commits.

    Takes effect on the member's next request: the lens query reads
    ``revoked_at`` on every request, and nothing caches a grant.

    :param session: The session to write through
    :param lens: The manager's lens on the centre
    :param member_id: The membership to end
    :param now: The moment, or None for the clock
    :raises AuthorizationError: No such membership in this centre
    :raises ConflictError: Not a centre, already ended, or the last live
        manager
    """
    centre = centre_of(session, lens)
    member = session.scalar(
        sa.select(OwnerMember)
        .where(OwnerMember.id == member_id, OwnerMember.owner_id == centre.id)
        .with_for_update()
    )
    if member is None:
        raise AuthorizationError(
            code="NO_TEACHER_LENS", message_key="authz.lens.not_available"
        )
    if member.revoked_at is not None:
        raise ConflictError(
            code="MEMBER_ALREADY_REVOKED", message_key="centre.member.already_revoked"
        )
    if member.role == "manager" and member.decision == "accepted":
        # Locked, so two managers revoking each other at once cannot
        # both pass and leave the centre with none.
        managers = session.scalars(
            sa.select(OwnerMember.id)
            .where(
                OwnerMember.owner_id == centre.id,
                OwnerMember.role == "manager",
                OwnerMember.decision == "accepted",
                OwnerMember.revoked_at.is_(None),
            )
            .with_for_update()
        ).all()
        if len(managers) <= 1:
            raise ConflictError(
                code="LAST_MANAGER", message_key="centre.member.last_manager"
            )
    member.revoked_at = _now(now)
    unassign_member(session, member_id=member.id)
    session.commit()


#: The workspaces an account may act on, in the lens query's order: its
#: own solo workspace first, then each centre it manages. The same
#: predicates as the grant, so the list never offers a workspace the
#: header would then refuse.
_WORKSPACES = sa.text(
    """
    SELECT w.id, w.kind, w.name FROM (
        SELECT o.id, o.kind, o.name, 0 AS solo_last, o.created_at
        FROM owner o WHERE o.account_id = :account_id
        UNION ALL
        SELECT o.id, o.kind, o.name, 1, m.created_at
        FROM owner_member m JOIN owner o ON o.id = m.owner_id
        WHERE m.account_id = :account_id
          AND m.role = 'manager'
          AND m.decision = 'accepted'
          AND m.revoked_at IS NULL
    ) AS w
    ORDER BY w.solo_last, w.created_at, w.id
    """
)


def workspaces_of(session: Session, account_id: uuid.UUID) -> list[WorkspaceRow]:
    """List the workspaces this account may act on, solo first.

    :param session: The session to read through
    :param account_id: The authenticated account
    :return: One row per workspace
    """
    seen: dict[uuid.UUID, WorkspaceRow] = {}
    for row in session.execute(_WORKSPACES, {"account_id": account_id}):
        seen.setdefault(
            row.id,
            WorkspaceRow(
                owner_id=row.id,
                kind="centre" if row.kind == "organisation" else "solo",
                name=row.name,
            ),
        )
    return list(seen.values())
