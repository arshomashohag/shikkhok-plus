"""A person's own centre invitations: listing, accepting, declining.

**Its own statement, off the hot path**, on the invitation grant's
reasoning [ADR-011]: a person may hold several unanswered offers, so the
grant is a set, and the per-request lens query never pays for it.

**Pending and declined both grant a :class:`MembershipLens`**, so a
decline stays reversible by its holder. A revoked membership grants
nothing here or anywhere: once a centre ends a membership, only the
centre can make a new offer.

**Signing up is not accepting.** :func:`link_memberships` attaches an
invitation to the account that now holds its number and leaves the
decision exactly as it was, the rule a seat follows [BR5.1].
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import MembershipLens
from app.db.models import Owner, OwnerMember

__all__ = [
    "MembershipRow",
    "available_memberships",
    "decide_membership",
    "link_memberships",
    "read_membership",
]


@dataclass(frozen=True, slots=True)
class MembershipRow:
    """One offer, as its holder sees it.

    :ivar member_id: The membership
    :ivar centre_name: The centre's name
    :ivar role: ``manager`` or ``teacher``
    :ivar decision: ``pending`` or ``declined``
    """

    member_id: uuid.UUID
    centre_name: str
    role: str
    decision: str


def available_memberships(
    session: Session, account_id: uuid.UUID
) -> list[MembershipLens]:
    """Resolve every unanswered or declined, unrevoked offer to this account.

    :param session: The session to read through
    :param account_id: The authenticated account
    :return: One lens per offer, oldest first
    """
    ids = session.scalars(
        sa.select(OwnerMember.id)
        .where(
            OwnerMember.account_id == account_id,
            OwnerMember.decision.in_(("pending", "declined")),
            OwnerMember.revoked_at.is_(None),
        )
        .order_by(OwnerMember.created_at, OwnerMember.id)
    )
    return [MembershipLens(account_id=account_id, member_id=i) for i in ids]


def read_membership(session: Session, *, lens: MembershipLens) -> MembershipRow:
    """Read the one offer the lens reaches.

    :param session: The session to read through
    :param lens: The membership lens
    :return: The centre's name, the role and this holder's decision
    """
    member, name = session.execute(
        sa.select(OwnerMember, Owner.name)
        .join(Owner, Owner.id == OwnerMember.owner_id)
        .where(OwnerMember.id == lens.member_id)
    ).one()
    return MembershipRow(
        member_id=member.id,
        centre_name=name or "",
        role=member.role,
        decision=member.decision,
    )


def decide_membership(
    session: Session,
    *,
    lens: MembershipLens,
    accept: bool,
    now: dt.datetime | None = None,
) -> str:
    """Accept or decline the one offer the lens reaches. Commits.

    Accepting a manager offer grants the centre's workspace on the very
    next request, through the lens query; accepting a teacher offer
    grants no teacher lens at all.

    :param session: The session to write through
    :param lens: The membership lens
    :param accept: True to accept, False to decline
    :param now: The moment, or None for the clock
    :return: The decision recorded
    """
    member = session.get(OwnerMember, lens.member_id, with_for_update=True)
    decision = "accepted" if accept else "declined"
    if member is not None:
        member.decision = decision
        member.decided_at = now or dt.datetime.now(tz=dt.UTC)
    session.commit()
    return decision


#: Attaches the invitations a number holds to the account that now owns
#: it. The link and NOT the decision; never a revoked offer.
_LINK = sa.text(
    """
    UPDATE owner_member
    SET account_id = :account_id
    WHERE invited_phone = :phone
      AND account_id IS NULL
      AND revoked_at IS NULL
    """
)


def link_memberships(session: Session, *, account_id: uuid.UUID, phone: str) -> None:
    """Attach this number's live invitations to its new account.

    Adds to the caller's transaction and does not commit.

    :param session: The session to write through
    :param account_id: The account just created
    :param phone: The number it is keyed on
    :return: None
    """
    session.execute(_LINK, {"account_id": account_id, "phone": phone})
