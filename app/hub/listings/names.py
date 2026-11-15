"""Which teachers a batch's public page may name.

A solo tutor is named by their public name. A centre names only members who
agreed to it, and falls back to a label that names nobody, so a member who
never opened the hub is never published by being assigned a class.
"""

from __future__ import annotations

import uuid
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

__all__ = ["CENTRE_FACULTY", "teacher_names"]

#: What a centre batch shows when no assigned member has agreed to be named.
CENTRE_FACULTY: Final = "Centre faculty"

_OWNER: Final = sa.text(
    "SELECT o.kind::text AS kind, l.public_name "
    "FROM owner o LEFT JOIN owner_listing l ON l.owner_id = o.id "
    "WHERE o.id = :owner"
)

_MEMBERS: Final = sa.text(
    "SELECT DISTINCT s.batch_id, m.display_name FROM schedule_slot s "
    "JOIN owner_member m ON m.id = s.teacher_member_id "
    "WHERE m.owner_id = :owner AND s.batch_id = ANY(:batches) "
    "AND m.public_name_consent_at IS NOT NULL "
    "AND m.decision = 'accepted' AND m.revoked_at IS NULL "
    "ORDER BY m.display_name"
)


def teacher_names(
    session: Session, owner_id: uuid.UUID, batch_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """Name the teachers of several batches of one owner.

    :param session: The session
    :param owner_id: The owner of every batch listed
    :param batch_ids: The batches
    :return: The names to show, per batch; never empty for a centre
    """
    owner = session.execute(_OWNER, {"owner": owner_id}).one_or_none()
    if owner is not None and owner.kind != "organisation":
        solo = [owner.public_name] if (owner.public_name or "").strip() else []
        return {batch_id: list(solo) for batch_id in batch_ids}
    named: dict[uuid.UUID, list[str]] = {batch_id: [] for batch_id in batch_ids}
    for row in session.execute(_MEMBERS, {"owner": owner_id, "batches": batch_ids}):
        named[row.batch_id].append(row.display_name)
    return {batch_id: names or [CENTRE_FACULTY] for batch_id, names in named.items()}
