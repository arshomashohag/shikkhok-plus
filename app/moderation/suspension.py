"""Suspending and restoring an owner's public listing.

**Suspension is the only moderation act that changes a listing.** It marks the
owner listing ``suspended``, hides every published batch listing of that owner
so nothing of theirs stays public, tells the people who run the listing, and
logs a closed-vocabulary event.

**Suspending evicts the owner's pages from the edge** in the same transaction,
so a cached page cannot outlive the suspension by its TTL [Review Focus 2].

**Lifting it never republishes.** The owner listing returns to ``hidden`` and
its batch listings stay hidden: the owner chooses to publish again, because a
listing that was removed for cause should not reappear on an administrator's
click alone.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import PlatformAdminLens
from app.db.models import (
    BatchListing,
    HubModerationEvent,
    Owner,
    OwnerListing,
)
from app.errors import ValidationError
from app.hub.listings.evict import evict_owner
from app.hub.listings.shared import managing_accounts
from app.moderation.reports import admin_not_found
from app.moderation.vocab import REASONS
from app.notifications.inbox import HUB_LISTING_SUSPENDED, deliver

__all__ = ["set"]


def set(
    session: Session,
    admin: PlatformAdminLens,
    owner_id: uuid.UUID,
    suspended: bool,
    reason_code: str,
    now: dt.datetime,
    correlation_id: str = "internal",
) -> None:
    """Suspend or restore an owner's listing.

    Named ``set`` because the interface is ``suspension.set``; nothing in this
    module calls the builtin ``set``.

    Repeating the state an owner listing is already in changes and logs
    nothing.

    :param session: The session
    :param admin: The administrator's lens
    :param owner_id: The owner whose listing it is
    :param suspended: True to suspend, False to lift
    :param reason_code: One of the closed reasons
    :param now: The moment of the change
    :param correlation_id: The request that caused it
    :return: None
    :raises ValidationError: The reason is not in the closed set
    :raises AuthorizationError: The owner has no listing, or only a draft
    """
    if reason_code not in REASONS:
        raise ValidationError(
            code="REPORT_REASON_INVALID",
            message_key="hub.report_reason_invalid",
        )
    listing = session.scalar(
        sa.select(OwnerListing)
        .where(OwnerListing.owner_id == owner_id)
        .with_for_update()
    )
    if listing is None or listing.status == "draft":
        raise admin_not_found()
    if suspended:
        if listing.status == "suspended":
            return
        listing.status = "suspended"
        listing.suspended_at = now
        listing.suspension_reason_code = reason_code
        listing.updated_at = now
        session.execute(
            sa.update(BatchListing)
            .where(
                BatchListing.owner_id == owner_id, BatchListing.status == "published"
            )
            .values(status="hidden", updated_at=now)
        )
        evict_owner(session, listing.slug, now)
        owner = session.get_one(Owner, owner_id)
        deliver(
            session,
            account_ids=managing_accounts(session, owner),
            kind=HUB_LISTING_SUSPENDED,
            batch_name=listing.public_name,
            now=now,
            source_id=owner_id,
        )
        event = "listing_suspended"
    else:
        if listing.status != "suspended":
            return
        listing.status = "hidden"
        listing.suspended_at = None
        listing.suspension_reason_code = None
        listing.updated_at = now
        event = "listing_unsuspended"
    session.add(
        HubModerationEvent(
            event=event,
            target_kind="owner_listing",
            target_id=owner_id,
            actor_admin_account_id=admin.account_id,
            decision_code=reason_code,
            correlation_id=correlation_id,
            at=now,
        )
    )
    session.commit()
