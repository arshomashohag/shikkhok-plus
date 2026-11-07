"""Teachers and coaching centres, by name, with the apps they use.

**The one list of named people an administrator sees**, and it names
only teachers and centres [TC-14, D-6]. A solo tutor's name is the one
they show their own students (``batch.teacher_display_name``); a centre's
is the name it registered. Neither comes from ``profile``, and no phone
number is selected.

A centre's apps and last-seen time are those of its live members --
the people who actually sign in to run it -- since a centre itself has
no account.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final, Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.accounts.clients import PLATFORMS, Platform
from app.help.identity import requester_ref

__all__ = ["WORKSPACE_LIMIT", "Workspace", "workspaces"]

#: The most rows one list returns.
WORKSPACE_LIMIT: Final = 1000


@dataclass(frozen=True, slots=True)
class Workspace:
    """One teacher or centre.

    :ivar workspace_id: The owner row
    :ivar kind: ``teacher`` for a solo tutor, ``centre`` for a centre
    :ivar name: The teacher's or centre's name, if one has been given
    :ivar platforms: The apps its people use, in a fixed order
    :ivar joined_at: When the workspace was created
    :ivar last_seen_at: The latest sign-in or refresh, if any
    :ivar ref: A solo tutor's help-centre label, to find their tickets
    """

    workspace_id: uuid.UUID
    kind: Literal["teacher", "centre"]
    name: str | None
    platforms: tuple[Platform, ...]
    joined_at: dt.datetime
    last_seen_at: dt.datetime | None
    ref: str | None


_WORKSPACES: Final = sa.text(
    "WITH people AS ("
    "  SELECT o.id AS owner_id, o.account_id FROM owner o "
    "  WHERE o.kind = 'teacher' AND o.account_id IS NOT NULL "
    "  UNION "
    "  SELECT m.owner_id, m.account_id FROM owner_member m "
    "  JOIN owner o ON o.id = m.owner_id "
    "  WHERE o.kind = 'organisation' AND m.decision = 'accepted' "
    "  AND m.revoked_at IS NULL AND m.account_id IS NOT NULL"
    ") "
    "SELECT o.id, o.kind, o.account_id, o.created_at, "
    "CASE WHEN o.kind = 'organisation' THEN o.name ELSE "
    "  (SELECT b.teacher_display_name FROM batch b WHERE b.owner_id = o.id "
    "   AND b.teacher_display_name IS NOT NULL "
    "   AND length(trim(b.teacher_display_name)) > 0 "
    "   ORDER BY b.created_at, b.id LIMIT 1) END AS name, "
    "(SELECT array_agg(DISTINCT c.platform::text) FROM people p "
    "  JOIN account_client c ON c.account_id = p.account_id "
    "  WHERE p.owner_id = o.id) AS platforms, "
    "(SELECT max(c.last_seen_at) FROM people p "
    "  JOIN account_client c ON c.account_id = p.account_id "
    "  WHERE p.owner_id = o.id) AS last_seen_at "
    "FROM owner o "
    "WHERE o.kind = 'organisation' OR o.account_id IS NOT NULL "
    "ORDER BY last_seen_at DESC NULLS LAST, o.created_at DESC, o.id "
    "LIMIT :limit"
)


def workspaces(session: Session) -> list[Workspace]:
    """List teachers and centres, most recently seen first.

    A solo tutor who deleted their account leaves an owner row with no
    account; it is not a teacher any more and is not listed.

    :param session: The session to read through
    :return: The workspaces
    """
    rows = session.execute(_WORKSPACES, {"limit": WORKSPACE_LIMIT})
    found: list[Workspace] = []
    for r in rows:
        used = set(r.platforms or ())
        found.append(
            Workspace(
                workspace_id=r.id,
                kind="centre" if r.kind == "organisation" else "teacher",
                name=r.name,
                platforms=tuple(p for p in PLATFORMS if p in used),
                joined_at=r.created_at,
                last_seen_at=r.last_seen_at,
                ref=requester_ref(r.account_id) if r.account_id else None,
            )
        )
    return found
