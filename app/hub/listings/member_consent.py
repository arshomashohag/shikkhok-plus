"""A centre member's own consent to be named on the centre's public page.

**Withdrawing evicts the centre's whole prefix** [Review Focus 5], through
:func:`~app.hub.listings.evict.evict_named_member`, in the withdrawal's own
transaction. Agreeing takes nothing down and evicts nothing: the name appears
when the cached page expires.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import CentreMemberLens
from app.hub.listings.evict import evict_named_member

__all__ = ["list_own_memberships", "set_public_name_consent"]


def set_public_name_consent(
    session: Session, lens: CentreMemberLens, consent: bool, now: dt.datetime
) -> None:
    """Record or withdraw the member's consent to be named publicly.

    The row is the lens's own membership; nothing here takes an id from the
    request body.

    :param session: The session
    :param lens: The caller's lens on their own membership
    :param consent: True to agree, False to withdraw
    :param now: The moment of agreement, or of the withdrawal
    :return: None
    """
    held = session.execute(
        sa.text(
            "SELECT public_name_consent_at IS NOT NULL FROM owner_member "
            "WHERE id = :id FOR UPDATE"
        ),
        {"id": lens.member_id},
    ).scalar_one()
    session.execute(
        sa.text("UPDATE owner_member SET public_name_consent_at = :at WHERE id = :id"),
        {"at": now if consent else None, "id": lens.member_id},
    )
    evict_named_member(session, lens.owner_id, held and not consent, now)
    session.commit()


def list_own_memberships(
    session: Session, account_id: uuid.UUID
) -> list[dict[str, object]]:
    """List the account's own accepted, unrevoked centre memberships.

    :param session: The session
    :param account_id: The authenticated account; no other id is accepted
    :return: One mapping per membership, oldest first, each carrying
        ``name_shown``: the name the centre's page publishes once the member
        agrees, exactly as :func:`app.hub.listings.names.teacher_names`
        reads it
    """
    rows = session.execute(
        sa.text(
            "SELECT m.id AS member_id, m.owner_id AS centre_id, "
            "o.name AS centre_name, m.role::text AS role, "
            "(m.public_name_consent_at IS NOT NULL) AS public_name_consent, "
            "m.display_name AS name_shown "
            "FROM owner_member m JOIN owner o ON o.id = m.owner_id "
            "WHERE m.account_id = :a AND m.decision = 'accepted' "
            "AND m.revoked_at IS NULL ORDER BY m.created_at, m.id"
        ),
        {"a": account_id},
    )
    return [
        {
            "member_id": r.member_id,
            "centre_id": r.centre_id,
            "centre_name": r.centre_name or "",
            "role": r.role,
            "public_name_consent": r.public_name_consent,
            "name_shown": r.name_shown,
        }
        for r in rows
    ]
