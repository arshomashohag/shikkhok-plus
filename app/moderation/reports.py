"""Reader reports about hub listings and photos, and the administrator's decision.

**Filing a report never changes a listing.** A report is a complaint, so a
stranger cannot take a teacher's page down by filing one; only an
administrator's suspension (see :mod:`app.moderation.suspension`) does.

**A photo, a review and a reply are the exceptions, and only for two
reasons.** A ``child_safety`` or ``personal_info`` report on one holds it at
once, in the report's own transaction (:func:`app.moderation.media.hold`,
:func:`app.moderation.reviews.hold`): a photo of a child, or a child named in
a review, that should not be public comes down before anyone reviews it,
and an administrator restores it if the report was wrong [H3 deviation 2].
A report on a review or reply filed by the batch's own owner or managers
holds nothing [F10]: the owner "may report; never hide or delete".

**A review or reply is locked before its report rows** [T4-c, T5-d], when a
report is filed and when one is decided, in the order the author's delete
takes, so neither can deadlock with it
(:func:`app.moderation.reviews.lock`).

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
from app.errors import ConflictError, ValidationError
from app.help.identity import requester_ref
from app.hub.listings.shared import refuse_phone_in
from app.hub.media.storage import MediaStore
from app.moderation import media, reviews
from app.moderation.refusals import admin_not_found, not_found
from app.moderation.vocab import HOLD_REASONS, REASONS

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

    :ivar kind: ``report``, ``listing``, ``media`` or ``review``
    :ivar report_id: The report, for a report row
    :ivar target_kind: What was reported or suspended
    :ivar target_id: The target's id
    :ivar owner_id: The owner a listing belongs to, when known
    :ivar title: The target's public name: an owner's ``public_name`` or a
        batch's ``public_title``; for a photo, its page's
    :ivar fields: Everything the owner submitted for display on the target,
        as ``(key, value)`` pairs
    :ivar reason: The report reason, the suspension reason code, or the
        reason a held photo was held
    :ivar note: The reporter's note, for a report row
    :ivar reporter_ref: The opaque reporter label, for a report row
    :ivar waited_hours: Whole hours since the report, the suspension, the
        hold, the upload, or a review's or reply's submit or edit
    :ivar author_ref: For a review or reply, the opaque reference of the
        review's author; for a reply, of the review it answers
    :ivar author_role: That author's role
    """

    kind: Literal["report", "listing", "media", "review"]
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
    author_ref: str | None = None
    author_role: str | None = None


def _reportable(session: Session, target_kind: str, target_id: uuid.UUID) -> bool:
    """Say whether a target is public: a listing, a photo, a review or a reply.

    The kind decides the one table looked in: an owner listing by owner id,
    a batch listing by batch id, a photo by media id, a review or reply by
    review id. A batch listing counts only while its owner listing is
    published too; a photo only where the public view shows it -- approved,
    on a published page; a review or reply only where ``hub_public_review``
    shows it, and never while reviews are switched off.

    :param session: The session
    :param target_kind: The reported kind
    :param target_id: The reported id
    :return: True only for a published owner or batch listing, a photo on a
        public page, or a review or reply text the public can read
    """
    if target_kind in reviews.REVIEW_TARGETS:
        return reviews.is_public(session, target_kind, target_id)
    if target_kind == "media":
        return media.is_public(session, target_id)
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

    A ``child_safety`` or ``personal_info`` report on a photo also holds the
    photo, in this same transaction; on a review or a reply, it holds that
    item, unless the reporter runs the reviewed batch [F10].

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
    :raises AuthorizationError: The target is not a published listing, a
        photo on a public page, or a review or reply the public can read
    :raises ConflictError: This account already reported this target
    """
    if reason not in REASONS:
        raise ValidationError(
            code="REPORT_REASON_INVALID", message_key="hub.report_reason_invalid"
        )
    refuse_phone_in([("note", note)])
    CeilingChecker(session).check_and_consume_hub_report(account_id, now)
    if target_kind in reviews.REVIEW_TARGETS:
        # The content row before any report row [T4-c, T5-d].
        reviews.lock(session, target_kind, target_id)
    if not _reportable(session, target_kind, target_id):
        session.rollback()
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
    if target_kind == "media" and reason in HOLD_REASONS:
        media.hold(
            session, target_id, reason=reason, now=now, correlation_id=correlation_id
        )
    elif (
        target_kind in reviews.REVIEW_TARGETS
        and reason in HOLD_REASONS
        and not reviews.runs_batch(session, target_id, account_id)
    ):
        reviews.hold(
            session,
            target_kind,
            target_id,
            reason=reason,
            now=now,
            correlation_id=correlation_id,
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


@dataclass(frozen=True, slots=True)
class _Target:
    """What a report row shows of what was reported.

    :ivar owner_id: The owner it belongs to
    :ivar title: Its public name or title; for a review or reply, the
        batch's public title
    :ivar fields: What was submitted for display on it
    :ivar author_ref: For a review or reply, the review author's reference
    :ivar author_role: That author's role
    """

    owner_id: uuid.UUID | None
    title: str | None
    fields: Fields
    author_ref: str | None = None
    author_role: str | None = None


#: What a report row shows when its target is gone.
_GONE: Final = _Target(owner_id=None, title=None, fields=())


def _targets(
    session: Session, reports: list[HubReport]
) -> dict[tuple[str, uuid.UUID], _Target]:
    """Look up the submitted public text of reported targets.

    Each report's kind names its table, so an owner id is never read as a
    batch id or the reverse. A review or reply is described by its batch's
    public title, its rating and words, and its author's role and opaque
    reference -- never the author.

    :param session: The session
    :param reports: The reports
    :return: ``{(kind, id): target}`` for those that exist
    """
    wanted: dict[str, list[uuid.UUID]] = {}
    for report in reports:
        wanted.setdefault(report.target_kind, []).append(report.target_id)
    found: dict[tuple[str, uuid.UUID], _Target] = {}
    owners = list(
        session.scalars(
            sa.select(OwnerListing).where(
                OwnerListing.owner_id.in_(wanted.get("owner_listing", []))
            )
        )
    )
    for owner_id, fields in _owner_fields(session, owners).items():
        title = next((v for k, v in fields if k == "public_name"), None)
        found["owner_listing", owner_id] = _Target(owner_id, title, fields)
    for batch in session.scalars(
        sa.select(BatchListing).where(
            BatchListing.batch_id.in_(wanted.get("batch_listing", []))
        )
    ):
        found["batch_listing", batch.batch_id] = _Target(
            batch.owner_id, batch.public_title, _batch_fields(batch)
        )
    for media_id, described in media.describe(session, wanted.get("media", [])).items():
        found["media", media_id] = _Target(*described)
    for kind in sorted(reviews.REVIEW_TARGETS):
        for review_id, about in reviews.describe(
            session, kind, wanted.get(kind, [])
        ).items():
            found[kind, review_id] = _Target(*about)
    return found


def _waiting_media(session: Session, moment: dt.datetime) -> list[QueueItem]:
    """List the photos waiting for a decision as queue rows.

    :param session: The session
    :param moment: The moment waits are measured to
    :return: Photos waiting for review or held, oldest upload first
    """
    return [
        QueueItem(
            kind="media",
            report_id=None,
            target_kind="media",
            target_id=w.media_id,
            owner_id=w.owner_id,
            title=w.title,
            fields=w.fields,
            reason=w.held_reason,
            note=None,
            reporter_ref=None,
            waited_hours=_hours(w.since, moment),
        )
        for w in media.waiting(session, moment)
    ]


def _waiting_reviews(session: Session, moment: dt.datetime) -> list[QueueItem]:
    """List the reviews and replies waiting for a decision as queue rows.

    :param session: The session
    :param moment: The moment waits are measured to
    :return: Pending and held reviews and replies, oldest wait first
    """
    return [
        QueueItem(
            kind="review",
            report_id=None,
            target_kind=w.target_kind,
            target_id=w.review_id,
            owner_id=w.owner_id,
            title=w.title,
            fields=w.fields,
            reason=w.held_reason,
            note=None,
            reporter_ref=None,
            waited_hours=_hours(w.since, moment),
            author_ref=w.author_ref,
            author_role=w.author_role,
        )
        for w in reviews.waiting(session)
    ]


def queue(
    session: Session,
    kind: Literal["report", "listing", "media", "review"],
    now: dt.datetime | None = None,
) -> list[QueueItem]:
    """List what an administrator should look at, oldest first.

    ``report`` lists open reports; ``listing`` lists suspended owner
    listings; ``media`` lists photos waiting for review or held after a
    report; ``review`` lists reviews and replies waiting for review or held
    after a report. None carries a reporter's or an author's phone, name or
    account id.

    :param session: The session
    :param kind: Which queue
    :param now: The moment waits are measured to, or None for the clock
    :return: The items, oldest first
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    if kind == "media":
        return _waiting_media(session, moment)
    if kind == "review":
        return _waiting_reviews(session, moment)
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
        target = targets.get((report.target_kind, report.target_id), _GONE)
        items.append(
            QueueItem(
                kind="report",
                report_id=report.id,
                target_kind=report.target_kind,
                target_id=report.target_id,
                owner_id=target.owner_id,
                title=target.title,
                fields=target.fields,
                reason=report.reason,
                note=report.note,
                reporter_ref=requester_ref(report.reporter_account_id),
                waited_hours=_hours(report.created_at, moment),
                author_ref=target.author_ref,
                author_role=target.author_role,
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
    *,
    store: MediaStore | None = None,
) -> None:
    """Record an administrator's decision on a report.

    Upholding a listing report suspends nothing by itself; suspension is its
    own act. A decision on a photo report carries to the photo in the same
    transaction [R11]: upheld removes it, and dismissing the report that
    holds it restores it (:func:`app.moderation.media.settle_report`). A
    decision on a review or reply report carries to that item the same way
    (:func:`app.moderation.reviews.settle_report`); the item is locked
    before the report [T4-c, T5-d].

    :param session: The session
    :param admin: The administrator's lens
    :param report_id: The report
    :param decision: ``upheld`` or ``dismissed``
    :param now: The moment of decision
    :param correlation_id: The request that caused it
    :param store: The photo bucket, which restoring a held photo needs
    :return: None
    :raises AuthorizationError: No such report
    :raises ConflictError: The report was already decided
    :raises TransientError: A held photo could not be restored; nothing
        was decided
    """
    # A report's target never changes, so it is read unlocked to know which
    # content row to lock first; the report is locked after it.
    named = session.execute(
        sa.select(HubReport.target_kind, HubReport.target_id).where(
            HubReport.id == report_id
        )
    ).one_or_none()
    if named is not None and named.target_kind in reviews.REVIEW_TARGETS:
        reviews.lock(session, named.target_kind, named.target_id)
    report = session.scalar(
        sa.select(HubReport)
        .where(HubReport.id == report_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if report is None:
        session.rollback()
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
    fresh = None
    if report.target_kind in reviews.REVIEW_TARGETS:
        reviews.settle_report(
            session,
            admin,
            report.target_kind,
            report.target_id,
            upheld=decision == "upheld",
            reason=report.reason,
            report_id=report.id,
            now=now,
            correlation_id=correlation_id,
        )
    elif report.target_kind == "media":
        fresh = media.settle_report(
            session,
            store,
            admin,
            report.target_id,
            upheld=decision == "upheld",
            reason=report.reason,
            report_id=report.id,
            now=now,
            correlation_id=correlation_id,
        )
    # A restore copied to a fresh key; a failed commit must not orphan it.
    media.commit_releasing(session, fresh, now)
