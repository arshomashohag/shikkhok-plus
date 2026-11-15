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
    BatchListing,
    HubModerationEvent,
    HubReport,
    OwnerListing,
)
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.help.identity import requester_ref
from app.hub.listings.shared import refuse_phone_in
from app.moderation.vocab import REASONS

__all__ = [
    "BATCH_FIELDS",
    "OWNER_FIELDS",
    "QueueItem",
    "admin_not_found",
    "decide",
    "file",
    "not_found",
    "queue",
]

_SECONDS_PER_HOUR: Final = 3600

#: What an owner submitted for display, in the order the queue shows it.
#: ``area_en`` and ``area_bn`` are the upazila and district names.
OWNER_FIELDS: Final[tuple[str, ...]] = (
    "public_name",
    "headline_en",
    "headline_bn",
    "bio_en",
    "bio_bn",
    "qualifications",
    "street_address",
    "public_contact_phone",
    "area_en",
    "area_bn",
)

#: What an owner submitted for display about one batch, in queue order.
#: ``batch.name`` is the teacher's private label and is never among them.
BATCH_FIELDS: Final[tuple[str, ...]] = (
    "public_title",
    "description_en",
    "description_bn",
    "syllabus_en",
    "syllabus_bn",
    "subject_tags",
)

#: One target's submitted fields: ``(key, value)`` pairs, empty ones left out.
Fields = tuple[tuple[str, str], ...]

_AREA_NAMES: Final = sa.text(
    "SELECT l.owner_id, d.name_en AS d_en, d.name_bn AS d_bn, "
    "u.name_en AS u_en, u.name_bn AS u_bn FROM owner_listing l "
    "LEFT JOIN bd_area d ON d.code = l.district_code "
    "LEFT JOIN bd_area u ON u.code = l.upazila_code "
    "WHERE l.owner_id = ANY(:owners)"
)


@dataclass(frozen=True, slots=True)
class QueueItem:
    """One row of the administrator's queue.

    :ivar kind: ``report`` or ``listing``
    :ivar report_id: The report, for a report row
    :ivar target_kind: What was reported or suspended
    :ivar target_id: The target's id
    :ivar owner_id: The owner a listing belongs to, when known
    :ivar title: The target's public name: an owner's ``public_name`` or a
        batch's ``public_title``
    :ivar fields: Everything the owner submitted for display on the target,
        as ``(key, value)`` pairs
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
    fields: Fields
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


def admin_not_found() -> AuthorizationError:
    """Build the refusal an administrator gets for nothing to act on.

    :return: A 404-equivalent authorization error
    """
    return AuthorizationError(
        code="HUB_ADMIN_TARGET_NOT_FOUND",
        message_key="hub.admin_target_not_found",
        status=404,
    )


def _reportable(session: Session, target_kind: str, target_id: uuid.UUID) -> bool:
    """Say whether a target is a published listing of the kind named.

    The kind decides the one table looked in: an owner listing by owner id,
    a batch listing by batch id. A batch listing counts only while its owner
    listing is published too.

    :param session: The session
    :param target_kind: The reported kind
    :param target_id: The reported id
    :return: True only for a published owner or batch listing
    """
    if target_kind == "owner_listing":
        status = session.scalar(
            sa.select(OwnerListing.status).where(OwnerListing.owner_id == target_id)
        )
        return status == "published"
    if target_kind != "batch_listing":
        return False
    batch = session.execute(
        sa.select(BatchListing.status, BatchListing.owner_id).where(
            BatchListing.batch_id == target_id
        )
    ).one_or_none()
    if batch is None or batch.status != "published":
        return False
    parent = session.scalar(
        sa.select(OwnerListing.status).where(OwnerListing.owner_id == batch.owner_id)
    )
    return parent == "published"


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
    :param target_kind: ``owner_listing``, ``batch_listing``, ``media``,
        ``review`` or ``reply``
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
        if "uq_hub_report_target_reporter" not in str(exc.orig):
            raise
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


def _present(pairs: list[tuple[str, str | None]]) -> Fields:
    """Keep the pairs that hold something.

    :param pairs: ``(key, value)`` pairs
    :return: The pairs with a non-blank value
    """
    return tuple((key, value) for key, value in pairs if value and value.strip())


def _area(upazila: str | None, district: str | None) -> str | None:
    """Join an upazila and a district name, either of which may be absent.

    :param upazila: The upazila's name
    :param district: The district's name
    :return: ``"upazila, district"``, one of them, or None
    """
    return ", ".join(n for n in (upazila, district) if n) or None


def _owner_fields(
    session: Session, listings: list[OwnerListing]
) -> dict[uuid.UUID, Fields]:
    """Read every submitted public field of some owner listings.

    :param session: The session
    :param listings: The listings
    :return: ``{owner id: fields}``
    """
    areas = {
        row.owner_id: row
        for row in session.execute(
            _AREA_NAMES, {"owners": [listing.owner_id for listing in listings]}
        )
    }
    found: dict[uuid.UUID, Fields] = {}
    for listing in listings:
        area = areas.get(listing.owner_id)
        values: dict[str, str | None] = {
            name: getattr(listing, name) for name in OWNER_FIELDS[:-2]
        }
        values["area_en"] = _area(area.u_en, area.d_en) if area else None
        values["area_bn"] = _area(area.u_bn, area.d_bn) if area else None
        found[listing.owner_id] = _present([(k, values[k]) for k in OWNER_FIELDS])
    return found


def _batch_fields(listing: BatchListing) -> Fields:
    """Read every submitted public field of one batch listing.

    :param listing: The batch listing
    :return: Its fields
    """
    values: dict[str, str | None] = {
        name: getattr(listing, name) for name in BATCH_FIELDS[:-1]
    }
    values["subject_tags"] = ", ".join(listing.subject_tags)
    return _present([(k, values[k]) for k in BATCH_FIELDS])


def _targets(
    session: Session, reports: list[HubReport]
) -> dict[tuple[str, uuid.UUID], tuple[uuid.UUID, str | None, Fields]]:
    """Look up the submitted public text of reported listings.

    Each report's kind names its table, so an owner id is never read as a
    batch id or the reverse.

    :param session: The session
    :param reports: The reports
    :return: ``{(kind, id): (owner id, title, fields)}`` for those that exist
    """
    wanted: dict[str, list[uuid.UUID]] = {}
    for report in reports:
        wanted.setdefault(report.target_kind, []).append(report.target_id)
    found: dict[tuple[str, uuid.UUID], tuple[uuid.UUID, str | None, Fields]] = {}
    owners = list(
        session.scalars(
            sa.select(OwnerListing).where(
                OwnerListing.owner_id.in_(wanted.get("owner_listing", []))
            )
        )
    )
    for owner_id, fields in _owner_fields(session, owners).items():
        title = next((v for k, v in fields if k == "public_name"), None)
        found["owner_listing", owner_id] = (owner_id, title, fields)
    for batch in session.scalars(
        sa.select(BatchListing).where(
            BatchListing.batch_id.in_(wanted.get("batch_listing", []))
        )
    ):
        found["batch_listing", batch.batch_id] = (
            batch.owner_id,
            batch.public_title,
            _batch_fields(batch),
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
        suspended = list(
            session.scalars(
                sa.select(OwnerListing)
                .where(OwnerListing.status == "suspended")
                .order_by(OwnerListing.suspended_at, OwnerListing.owner_id)
            )
        )
        submitted = _owner_fields(session, suspended)
        return [
            QueueItem(
                kind="listing",
                report_id=None,
                target_kind="owner_listing",
                target_id=listing.owner_id,
                owner_id=listing.owner_id,
                title=listing.public_name,
                fields=submitted[listing.owner_id],
                reason=listing.suspension_reason_code,
                note=None,
                reporter_ref=None,
                waited_hours=_hours(listing.suspended_at or moment, moment),
            )
            for listing in suspended
        ]
    open_reports = list(
        session.scalars(
            sa.select(HubReport)
            .where(HubReport.status == "open")
            .order_by(HubReport.created_at, HubReport.id)
        )
    )
    targets = _targets(session, open_reports)
    items = []
    for report in open_reports:
        owner_id, title, fields = targets.get(
            (report.target_kind, report.target_id), (None, None, ())
        )
        items.append(
            QueueItem(
                kind="report",
                report_id=report.id,
                target_kind=report.target_kind,
                target_id=report.target_id,
                owner_id=owner_id,
                title=title,
                fields=fields,
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
        raise admin_not_found()
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
