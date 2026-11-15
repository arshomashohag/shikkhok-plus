"""Reader reports about hub listings, and the administrator's decision on them.

**Filing a report never changes a listing.** A report is a complaint, so a
stranger cannot take a teacher's page down by filing one; only an
administrator's suspension (see :mod:`app.moderation.suspension`) does.

**Every unreportable target answers identically.** A draft, hidden, suspended
or missing listing, and a target kind R1 has not built, all raise the same
refusal, so a report cannot be used to learn which ids exist or what state
they are in. The per-account daily ceiling is consumed before the lookup, which
also bounds how many probes one account gets.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final, Literal

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.ceilings import CeilingChecker
from app.authz.lenses import PlatformAdminLens
from app.db.models import (
    Batch,
    BatchListing,
    HubModerationEvent,
    HubReport,
    OwnerListing,
)
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.help.identity import requester_ref
from app.hub.listings.shared import refuse_phone_in
from app.moderation.vocab import REASONS

__all__ = ["QueueItem", "decide", "file", "not_found", "queue"]

_SECONDS_PER_HOUR: Final = 3600


@dataclass(frozen=True, slots=True)
class QueueItem:
    """One row of the administrator's queue.

    :ivar kind: ``report`` or ``listing``
    :ivar report_id: The report, for a report row
    :ivar target_kind: What was reported or suspended
    :ivar target_id: The target's id
    :ivar owner_id: The owner a listing belongs to, when known
    :ivar title: The target's public name
    :ivar text: The target's public text
    :ivar reason: The report reason, or the suspension reason code
    :ivar note: The reporter's note, for a report row
    :ivar reporter_ref: The opaque reporter label, for a report row
    :ivar waited_hours: Whole hours since the report or the suspension
    """

    kind: Literal["report", "listing"]
    report_id: uuid.UUID | None
    target_kind: str
    target_id: uuid.UUID
    owner_id: uuid.UUID | None
    title: str | None
    text: str | None
    reason: str | None
    note: str | None
    reporter_ref: str | None
    waited_hours: int


def not_found() -> AuthorizationError:
    """Build the one refusal every unreportable target shares.

    :return: A 404-equivalent authorization error
    """
    return AuthorizationError(
        code="REPORT_TARGET_NOT_FOUND",
        message_key="hub.report_target_not_found",
        status=404,
    )


def _reportable(session: Session, target_kind: str, target_id: uuid.UUID) -> bool:
    """Say whether a target is a published listing.

    An owner listing is tried first by owner id, then a batch listing by batch
    id; the ids are globally unique, so at most one matches.

    :param session: The session
    :param target_kind: The reported kind
    :param target_id: The reported id
    :return: True only for a published owner or batch listing
    """
    if target_kind != "listing":
        return False
    owner_status = session.scalar(
        sa.select(OwnerListing.status).where(OwnerListing.owner_id == target_id)
    )
    if owner_status is not None:
        return owner_status == "published"
    batch_status = session.scalar(
        sa.select(BatchListing.status).where(BatchListing.batch_id == target_id)
    )
    return batch_status == "published"


def file(
    session: Session,
    account_id: uuid.UUID,
    target_kind: str,
    target_id: uuid.UUID,
    reason: str,
    note: str | None,
    now: dt.datetime,
    correlation_id: str = "internal",
) -> None:
    """File one report and log the event; change no listing.

    :param session: The session
    :param account_id: The reporter
    :param target_kind: ``listing``, ``media``, ``review`` or ``reply``
    :param target_id: The target
    :param reason: A closed reason
    :param note: An optional note of up to 500 characters
    :param now: The moment of filing
    :param correlation_id: The request that caused it
    :return: None
    :raises ValidationError: The reason is unknown or the note carries a phone
        number
    :raises CeilingBreach: The account has filed ten reports today
    :raises AuthorizationError: The target is not a published listing
    :raises ConflictError: This account already reported this target
    """
    if reason not in REASONS:
        raise ValidationError(
            code="REPORT_REASON_INVALID", message_key="hub.report_reason_invalid"
        )
    refuse_phone_in([("note", note)])
    CeilingChecker(session).check_and_consume_hub_report(account_id, now)
    if not _reportable(session, target_kind, target_id):
        raise not_found()
    try:
        with session.begin_nested():
            session.add(
                HubReport(
                    target_kind=target_kind,
                    target_id=target_id,
                    reporter_account_id=account_id,
                    reason=reason,
                    note=note,
                    created_at=now,
                )
            )
            session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(
            code="REPORT_ALREADY_FILED", message_key="hub.report_already_filed"
        ) from exc
    session.add(
        HubModerationEvent(
            event="report_filed",
            target_kind=target_kind,
            target_id=target_id,
            decision_code=reason,
            correlation_id=correlation_id,
            at=now,
        )
    )
    session.commit()


def _hours(since: dt.datetime, now: dt.datetime) -> int:
    """Count whole hours waited, never negative.

    :param since: When the wait began
    :param now: The present moment
    :return: Whole hours
    """
    return max(0, int((now - since).total_seconds() // _SECONDS_PER_HOUR))


def _target_texts(
    session: Session, target_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[uuid.UUID, str | None, str | None]]:
    """Look up the public text of listing targets.

    :param session: The session
    :param target_ids: Owner ids and batch ids
    :return: ``{target id: (owner id, title, text)}`` for those that exist
    """
    found: dict[uuid.UUID, tuple[uuid.UUID, str | None, str | None]] = {}
    for owner_listing in session.scalars(
        sa.select(OwnerListing).where(OwnerListing.owner_id.in_(target_ids))
    ):
        found[owner_listing.owner_id] = (
            owner_listing.owner_id,
            owner_listing.public_name,
            owner_listing.headline_en or owner_listing.headline_bn,
        )
    for batch_listing, name in session.execute(
        sa.select(BatchListing, Batch.name)
        .join(Batch, Batch.id == BatchListing.batch_id)
        .where(BatchListing.batch_id.in_(target_ids))
    ):
        found[batch_listing.batch_id] = (
            batch_listing.owner_id,
            name,
            batch_listing.description_en or batch_listing.description_bn,
        )
    return found


def queue(
    session: Session,
    kind: Literal["report", "listing"],
    now: dt.datetime | None = None,
) -> list[QueueItem]:
    """List what an administrator should look at, oldest first.

    ``report`` lists open reports; ``listing`` lists suspended owner listings.
    Neither carries a reporter's phone, name or account id.

    :param session: The session
    :param kind: Which queue
    :param now: The moment waits are measured to, or None for the clock
    :return: The items, oldest first
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    if kind == "listing":
        suspended = session.scalars(
            sa.select(OwnerListing)
            .where(OwnerListing.status == "suspended")
            .order_by(OwnerListing.suspended_at, OwnerListing.owner_id)
        ).all()
        return [
            QueueItem(
                kind="listing",
                report_id=None,
                target_kind="listing",
                target_id=listing.owner_id,
                owner_id=listing.owner_id,
                title=listing.public_name,
                text=listing.headline_en or listing.headline_bn,
                reason=listing.suspension_reason_code,
                note=None,
                reporter_ref=None,
                waited_hours=_hours(listing.suspended_at or moment, moment),
            )
            for listing in suspended
        ]
    open_reports = session.scalars(
        sa.select(HubReport)
        .where(HubReport.status == "open")
        .order_by(HubReport.created_at, HubReport.id)
    ).all()
    texts = _target_texts(session, [r.target_id for r in open_reports])
    items = []
    for report in open_reports:
        owner_id, title, text = texts.get(report.target_id, (None, None, None))
        items.append(
            QueueItem(
                kind="report",
                report_id=report.id,
                target_kind=report.target_kind,
                target_id=report.target_id,
                owner_id=owner_id,
                title=title,
                text=text,
                reason=report.reason,
                note=report.note,
                reporter_ref=requester_ref(report.reporter_account_id),
                waited_hours=_hours(report.created_at, moment),
            )
        )
    return items


def decide(
    session: Session,
    admin: PlatformAdminLens,
    report_id: uuid.UUID,
    decision: Literal["upheld", "dismissed"],
    now: dt.datetime,
    correlation_id: str = "internal",
) -> None:
    """Record an administrator's decision on a report.

    Upholding a report suspends nothing by itself; suspension is its own act.

    :param session: The session
    :param admin: The administrator's lens
    :param report_id: The report
    :param decision: ``upheld`` or ``dismissed``
    :param now: The moment of decision
    :param correlation_id: The request that caused it
    :return: None
    :raises AuthorizationError: No such report
    :raises ConflictError: The report was already decided
    """
    report = session.scalar(
        sa.select(HubReport).where(HubReport.id == report_id).with_for_update()
    )
    if report is None:
        raise not_found()
    if report.status != "open":
        raise ConflictError(
            code="REPORT_ALREADY_DECIDED", message_key="hub.report_already_decided"
        )
    report.status = decision
    report.decided_at = now
    report.decided_by_account_id = admin.account_id
    session.add(
        HubModerationEvent(
            event="report_upheld" if decision == "upheld" else "report_dismissed",
            target_kind=report.target_kind,
            target_id=report.target_id,
            actor_admin_account_id=admin.account_id,
            decision_code=report.reason,
            correlation_id=correlation_id,
            at=now,
        )
    )
    session.commit()
