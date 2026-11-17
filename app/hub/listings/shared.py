"""Rules the owner listing and the batch listings share.

One slug shape, one phone scan, one suspended refusal and one unique-violation
translation, so the two services cannot drift apart; and one answer to "who
runs this listing", which the suspension notice and the demand question both
send to.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from typing import Final, Protocol

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts.phone import contains_phone
from app.db.models import Owner, OwnerMember
from app.errors import ConflictError, ValidationError

__all__ = [
    "SLUG",
    "flush_slug_unique",
    "managing_accounts",
    "refuse_phone_in",
    "refuse_suspended",
    "require_slug_shape",
]

SLUG: Final = re.compile(r"[a-z0-9-]{3,60}")


class _HasStatus(Protocol):
    """Anything carrying a listing status."""

    status: str


def refuse_suspended(listing: _HasStatus) -> None:
    """Refuse any owner action on a suspended listing.

    :param listing: The listing
    :raises ConflictError: It is suspended
    """
    if listing.status == "suspended":
        raise ConflictError(
            code="HUB_LISTING_SUSPENDED", message_key="hub.listing_suspended"
        )


def refuse_phone_in(values: Iterable[tuple[str, str | None]]) -> None:
    """Refuse a free-text value that carries a phone number.

    :param values: ``(field name, value)`` pairs; ``None`` is skipped
    :raises ValidationError: A value contains a phone number
    """
    for name, value in values:
        if value is not None and contains_phone(value):
            raise ValidationError(
                code="HUB_TEXT_CONTAINS_CONTACT",
                message_key="hub.text_contains_contact",
                details={"field": name},
            )


def require_slug_shape(slug: str) -> None:
    """Refuse a slug outside the public pattern.

    :param slug: The wanted slug
    :raises ValidationError: It does not match ``[a-z0-9-]{3,60}``
    """
    if not SLUG.fullmatch(slug):
        raise ValidationError(code="HUB_SLUG_INVALID", message_key="hub.slug_invalid")


def flush_slug_unique(session: Session, constraint: str) -> None:
    """Flush inside a SAVEPOINT, translating a slug collision.

    :param session: The session
    :param constraint: The unique index name that signals a taken slug
    :raises ConflictError: The slug index was violated; the session is rolled
        back
    """
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as error:
        if constraint not in str(error.orig):
            raise
        session.rollback()
        raise ConflictError(
            code="HUB_SLUG_TAKEN", message_key="hub.slug_taken"
        ) from error


def managing_accounts(session: Session, owner: Owner) -> list[uuid.UUID]:
    """Find who runs an owner's listing.

    A solo tutor's own account, and a centre's accepted, unrevoked managers.

    :param session: The session
    :param owner: The owner
    :return: Distinct account ids, in a stable order
    """
    accounts: list[uuid.UUID] = []
    if owner.account_id is not None:
        accounts.append(owner.account_id)
    accounts.extend(
        a
        for a in session.scalars(
            sa.select(OwnerMember.account_id).where(
                OwnerMember.owner_id == owner.id,
                OwnerMember.role == "manager",
                OwnerMember.decision == "accepted",
                OwnerMember.revoked_at.is_(None),
                OwnerMember.account_id.is_not(None),
            )
        )
        if a is not None
    )
    return sorted(dict.fromkeys(accounts))
