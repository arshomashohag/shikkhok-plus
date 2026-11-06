"""The class-teacher grant: one class, by assignment [C4].

**Its own statement, off the hot path**, on the invitation grant's
reasoning [ADR-011]: a centre teacher's reach is a set of classes, it
changes whenever a manager reassigns one, and it is needed only on the
handful of routes written for it.

**Two refusals, deliberately different.** A caller with no live
membership in the class's centre is refused exactly as for a class that
does not exist, so the routes cannot test which classes exist. A caller
who is a member there, but to whom the class is not (or no longer)
assigned, is told ``CLASS_REASSIGNED``: they were shown that class, and a
write queued before a manager moved it must say why it was not applied.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import ClassTeacherLens
from app.db.models import Batch, OwnerMember, Session
from app.errors import AuthorizationError, ConflictError

__all__ = ["resolve_class_lens"]


def resolve_class_lens(
    session: DbSession, *, account_id: uuid.UUID, session_id: uuid.UUID
) -> ClassTeacherLens:
    """Grant the lens for one class, or refuse.

    :param session: The session to read through
    :param account_id: The authenticated account
    :param session_id: The class, from the route path
    :return: The lens for that one class
    :raises AuthorizationError: No such class, or no live membership in
        its centre
    :raises ConflictError: A member there, but the class is not assigned
        to them
    """
    row = session.execute(
        sa.select(Session.teacher_member_id, Batch.owner_id, OwnerMember.id)
        .join(Batch, Batch.id == Session.batch_id)
        .join(
            OwnerMember,
            sa.and_(
                OwnerMember.owner_id == Batch.owner_id,
                OwnerMember.account_id == account_id,
                OwnerMember.decision == "accepted",
                OwnerMember.revoked_at.is_(None),
            ),
        )
        .where(Session.id == session_id)
    ).first()
    if row is None:
        raise AuthorizationError(
            code="NO_CLASS_LENS", message_key="authz.lens.not_available"
        )
    assigned, owner_id, member_id = row
    if assigned != member_id:
        raise ConflictError(code="CLASS_REASSIGNED", message_key="class.reassigned")
    return ClassTeacherLens(
        account_id=account_id,
        owner_id=owner_id,
        member_id=member_id,
        session_id=session_id,
    )
