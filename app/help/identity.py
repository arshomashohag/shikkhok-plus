"""What a platform administrator may know about who someone is.

**The administrator boundary is decided here, once** [TC-14, D-6]. An
administrator may see a teacher's name -- the name a teacher shows their
own students, or the name a centre gave its member -- and a centre's
name. For a student or a guardian, an administrator sees the role and an
opaque label and nothing else: never a name, a phone number, a profile
field or anything a teacher wrote about them.

**Names come from teacher-facing columns, never from ``profile``.**
``Profile.self_name`` is owner-private and row-level security admits only
its owner, so reading it here would either fail or, worse, need the
policy bypassed. The teacher's name instead comes from
``batch.teacher_display_name`` (what the teacher chose to show students)
and a centre member's from ``owner_member.display_name`` (what the
centre typed), both of which already appear in front of other people.

**The opaque label is derived, not stored apart from the account.** It
is a truncated SHA-256 of the account id under a fixed prefix: stable,
so one person's tickets group together, and not reversible, since an
account id is a random UUID the administrator never sees.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

__all__ = ["RequesterIdentity", "Role", "identities", "requester_ref"]

Role = Literal["teacher", "centre_member", "student", "guardian"]

#: Domain-separates this hash from any other use of the account id.
_REF_PREFIX: Final = b"shikkhokplus/help-requester/v1:"

#: Ten hex characters: 40 bits, collision-free in practice at any
#: realistic number of people asking for help, and short enough to read.
_REF_LENGTH: Final = 10


@dataclass(frozen=True, slots=True)
class RequesterIdentity:
    """Who asked, as far as an administrator may know.

    :ivar ref: The opaque, stable label
    :ivar roles: The roles the account holds now, in a fixed order
    :ivar name: The teacher's name, set only for a teacher or centre member
    :ivar centre: The centre's name, set only for a centre member
    """

    ref: str
    roles: tuple[Role, ...]
    name: str | None
    centre: str | None


def requester_ref(account_id: uuid.UUID) -> str:
    """Derive the opaque label for an account.

    :param account_id: The account
    :return: Ten upper-case hex characters
    """
    digest = hashlib.sha256(_REF_PREFIX + account_id.bytes).hexdigest()
    return digest[:_REF_LENGTH].upper()


_ROLES: Final = sa.text(
    "SELECT a.id, "
    "EXISTS (SELECT 1 FROM owner o WHERE o.account_id = a.id "
    "        AND o.kind = 'teacher') AS teacher, "
    "(SELECT b.teacher_display_name FROM batch b JOIN owner o "
    "   ON o.id = b.owner_id "
    "  WHERE o.account_id = a.id AND o.kind = 'teacher' "
    "    AND b.teacher_display_name IS NOT NULL "
    "    AND length(trim(b.teacher_display_name)) > 0 "
    "  ORDER BY b.created_at, b.id LIMIT 1) AS teacher_name, "
    "(SELECT m.display_name FROM owner_member m "
    "  WHERE m.account_id = a.id AND m.decision = 'accepted' "
    "    AND m.revoked_at IS NULL "
    "  ORDER BY m.created_at, m.id LIMIT 1) AS member_name, "
    "(SELECT o.name FROM owner_member m JOIN owner o ON o.id = m.owner_id "
    "  WHERE m.account_id = a.id AND m.decision = 'accepted' "
    "    AND m.revoked_at IS NULL "
    "  ORDER BY m.created_at, m.id LIMIT 1) AS centre_name, "
    "EXISTS (SELECT 1 FROM enrollment e WHERE e.student_account_id = a.id "
    "        AND e.student_decision = 'accepted') AS student, "
    "EXISTS (SELECT 1 FROM enrollment e WHERE e.guardian_account_id = a.id "
    "        AND e.guardian_decision = 'accepted') AS guardian "
    "FROM account a WHERE a.id = ANY(:ids)"
)


def identities(
    session: Session, account_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, RequesterIdentity]:
    """Label each account as an administrator may see it.

    One statement for the whole set, so a page of tickets costs one round
    trip however many people asked.

    **A name is returned only alongside a teacher role.** An account that
    is a teacher in one place and a guardian in another is shown by its
    teacher name, because that name is already public to its students;
    an account that is only a student or a guardian gets no name at all.

    :param session: The session to read through
    :param account_ids: The accounts to label
    :return: One identity per account that still exists
    """
    ids = list(set(account_ids))
    if not ids:
        return {}
    found: dict[uuid.UUID, RequesterIdentity] = {}
    for row in session.execute(_ROLES, {"ids": ids}):
        roles: list[Role] = []
        if row.teacher:
            roles.append("teacher")
        if row.member_name is not None:
            roles.append("centre_member")
        if row.student:
            roles.append("student")
        if row.guardian:
            roles.append("guardian")
        name: str | None = None
        if row.teacher:
            name = row.teacher_name
        if name is None and row.member_name is not None:
            name = row.member_name
        found[row.id] = RequesterIdentity(
            ref=requester_ref(row.id),
            roles=tuple(roles),
            name=name,
            centre=row.centre_name if row.member_name is not None else None,
        )
    return found
