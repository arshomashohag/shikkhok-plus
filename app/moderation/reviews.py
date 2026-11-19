"""Review and reply moderation: an administrator's decision, and a report's hold.

**Every review and every reply is seen before it is public** [hub spec D7,
Calls 2 and 3]. An administrator decides what waits in ``pending``
(:func:`decide`): approving a review queues it, as ``approved``, for the
weekly publication; approving a reply publishes it at once, in this month.
A rejection carries one of :data:`~app.moderation.vocab.REVIEW_REJECTION_CODES`.

**A child-safety or personal-information report holds a published review or
reply at once** [H3 deviation 2 applied to reviews]. :func:`hold` runs in
the report's own transaction, so a report that rolls back leaves the item
published. A held item keeps its ``published_month`` and leaves the views;
the owner's pages are evicted. **Except a report by someone who runs the
batch** [F10, I-2] -- its owner, its managers, or a teacher assigned to it,
the very set eligibility refuses as reviewers: spec section 6 lets the owner
"report; never hide or delete", so their report holds nothing and waits in
the queue on the 24-hour child-safety timetable like any other
(:func:`runs_batch`).

**A decision on a report carries to its target** (:func:`settle_report`, in
the decision's transaction). Upheld: the target is removed whatever its
status -- published, held, approved or back in ``pending`` after an edit or
a replacement [F9] -- with the code mapped from the report's reason.
Dismissed: a held target is restored, unless another open holding report,
not filed by someone who runs the batch, still names it.

**A review's author is told when it is rejected or removed** -- by either
path above, in the decision's transaction -- as ``hub_review_outcome`` with
the preview ``rejected`` or ``removed`` and never the code, which only the
author's own ``my-review`` shows (:func:`app.reviews.publication.tell_author`).
An approval tells nobody: the weekly publication does. A reply's outcome
tells nobody in H4.

**Lock order: content, then reports** [T4-c, T5-d]. Every path here locks
the review (and, for a reply, the review then the reply) before it reads or
writes a ``hub_report`` row -- the same order the author's delete and the
owner's ``delete_reply`` take -- so none of them can deadlock with another.
:func:`lock` is the one place the order is written.

**What an administrator sees of the author** [Call 14, TC-14]: a role and
an opaque reference (:func:`app.reviews.identity.review_author_ref`), never
an account id, the evidencing seat, a name, a phone number or any time;
the queue's ``waited_hours`` is the only clock it shows.

**Every act is a closed-vocabulary moderation event** [0046], with
``target_kind`` ``review`` or ``reply``. A held item's hold time is the
latest ``review_held`` or ``reply_held`` event's ``at`` [F11]; ``0045``
stores no hold time of its own.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal, cast

import sqlalchemy as sa
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from app.authz.lenses import PlatformAdminLens
from app.db.models import (
    HubModerationEvent,
    HubReport,
    Review,
    ReviewReply,
)
from app.errors import ConflictError, ValidationError
from app.hub.public import invalidation
from app.hub.public.settings import reviews_enabled
from app.local_time import bangladesh_today
from app.moderation.refusals import admin_not_found
from app.moderation.vocab import (
    HOLD_REASONS,
    REPORT_REJECTION_CODES,
    REVIEW_REJECTION_CODES,
)
from app.reviews.eligibility import runs_batch_sql
from app.reviews.identity import review_author_ref
from app.reviews.publication import tell_author

__all__ = [
    "DECIDABLE",
    "REVIEW_FIELDS",
    "REVIEW_TARGETS",
    "ReviewDetail",
    "ReviewTarget",
    "WaitingReview",
    "decide",
    "describe",
    "detail",
    "hold",
    "is_public",
    "lock",
    "runs_batch",
    "settle_report",
    "waiting",
]

#: What a review moderation decision or report names.
ReviewTarget = Literal["review", "reply"]

#: Both of them, for membership tests on a report's kind.
REVIEW_TARGETS: Final[frozenset[str]] = frozenset({"review", "reply"})

#: The statuses an administrator decides: waiting for review, or held.
DECIDABLE: Final[tuple[str, ...]] = ("pending", "held")

#: The statuses an upheld report has nothing left to remove from.
_SETTLED: Final[tuple[str, ...]] = ("rejected", "removed")

#: The statuses in which an item is, or was until a moment ago, on a page.
_SHOWN: Final[tuple[str, ...]] = ("published", "held")

#: What the queue shows of a review or reply, in order: the review's rating
#: and words, and a reply's words.
REVIEW_FIELDS: Final[tuple[str, ...]] = ("review_rating", "review_body", "reply_body")

#: One submitted field: ``(key, value)``, as the queue shows it.
Fields = tuple[tuple[str, str], ...]

#: Whether the public view shows a review, and its reply's text.
_PUBLIC: Final = sa.text(
    "SELECT reply_body IS NOT NULL AS replied FROM hub_public_review WHERE id = :id"
)

#: The owner slug of the page a review is on.
_OWNER_SLUG: Final = sa.text(
    """
    SELECT ol.slug
    FROM review r
    JOIN batch_listing bl ON bl.batch_id = r.batch_id
    JOIN owner_listing ol ON ol.owner_id = bl.owner_id
    WHERE r.id = :review_id
    """
)

#: Whether an account runs the batch a review is of [F10, I-2].
_RUNS_BATCH: Final = sa.text(
    f"""
    SELECT {runs_batch_sql("r.batch_id", ":account_id")}
    FROM review r
    WHERE r.id = :review_id
    """  # noqa: S608  module constants, never input
)

#: Whether an open holding report, other than one being decided, by someone
#: who does not run the batch, still names a review or reply [T7-c, F10].
_STILL_HELD: Final = sa.text(
    f"""
    SELECT EXISTS (
        SELECT 1
        FROM hub_report h
        JOIN review r ON r.id = h.target_id
        WHERE h.target_kind = CAST(:target_kind AS hub_report_target)
          AND h.target_id = :target_id
          AND h.status = 'open'
          AND h.reason::text = ANY(:reasons)
          AND (CAST(:report_id AS uuid) IS NULL
               OR h.id <> CAST(:report_id AS uuid))
          AND NOT {runs_batch_sql("r.batch_id", "h.reporter_account_id")})
    """  # noqa: S608  module constants, never input
)

#: The latest hold of each held review or reply: when, and the reason [F11].
_LATEST_HOLD: Final = """
    SELECT DISTINCT ON (target_kind, target_id)
           target_kind::text AS kind, target_id, at, decision_code
    FROM hub_moderation_event
    WHERE event IN ('review_held', 'reply_held')
    ORDER BY target_kind, target_id, at DESC
"""

#: Every review and reply waiting for a decision, and since when: an edit or
#: a replacement restarts the wait, a hold starts it at the hold. A reply
#: whose review is rejected or removed is left out: it can never be shown
#: unless its review's author edits it back to ``pending``, which lists it
#: again.
_WAITING: Final = sa.text(
    f"""
    WITH held AS ({_LATEST_HOLD})
    SELECT 'review' AS kind, r.id AS review_id, r.status::text AS status,
           bl.owner_id, bl.public_title, r.author_account_id,
           r.author_role::text AS author_role, r.rating, r.body,
           NULL AS reply_body, h.decision_code AS held_reason,
           CASE WHEN r.status = 'held'
                THEN COALESCE(h.at, r.edited_at, r.submitted_at)
                ELSE COALESCE(r.edited_at, r.submitted_at) END AS since
    FROM review r
    JOIN batch_listing bl ON bl.batch_id = r.batch_id
    LEFT JOIN held h ON h.kind = 'review' AND h.target_id = r.id
                    AND r.status = 'held'
    WHERE r.status IN ('pending', 'held')
    UNION ALL
    SELECT 'reply', r.id, p.status::text, bl.owner_id, bl.public_title,
           r.author_account_id, r.author_role::text, r.rating, r.body,
           p.body, h.decision_code,
           CASE WHEN p.status = 'held'
                THEN COALESCE(h.at, p.edited_at, p.created_at)
                ELSE COALESCE(p.edited_at, p.created_at) END
    FROM review_reply p
    JOIN review r ON r.id = p.review_id
    JOIN batch_listing bl ON bl.batch_id = r.batch_id
    LEFT JOIN held h ON h.kind = 'reply' AND h.target_id = r.id
                    AND p.status = 'held'
    WHERE p.status IN ('pending', 'held')
      AND r.status NOT IN ('rejected', 'removed')
    ORDER BY since, review_id, kind
    """  # noqa: S608  module constants, never input
)

#: One review with its reply, its batch's title and its owner's public name.
_ONE: Final = sa.text(
    f"""
    WITH held AS ({_LATEST_HOLD})
    SELECT r.id AS review_id, r.rating, r.body,
           r.tenure_bucket::text AS tenure, r.author_role::text AS author_role,
           r.author_account_id, r.status::text AS review_status,
           p.status::text AS reply_status, p.body AS reply_body,
           bl.owner_id, bl.public_title, ol.public_name,
           CASE WHEN r.status = 'held'
                THEN COALESCE(hr.at, r.edited_at, r.submitted_at)
                ELSE COALESCE(r.edited_at, r.submitted_at) END AS review_since,
           CASE WHEN p.status = 'held'
                THEN COALESCE(hp.at, p.edited_at, p.created_at)
                ELSE COALESCE(p.edited_at, p.created_at) END AS reply_since
    FROM review r
    JOIN batch_listing bl ON bl.batch_id = r.batch_id
    LEFT JOIN owner_listing ol ON ol.owner_id = bl.owner_id
    LEFT JOIN review_reply p ON p.review_id = r.id
    LEFT JOIN held hr ON hr.kind = 'review' AND hr.target_id = r.id
    LEFT JOIN held hp ON hp.kind = 'reply' AND hp.target_id = r.id
    WHERE r.id = ANY(:ids)
    """  # noqa: S608  module constants, never input
)

_SECONDS_PER_HOUR: Final = 3600


@dataclass(frozen=True, slots=True)
class WaitingReview:
    """One review or reply waiting for an administrator.

    :ivar target_kind: ``review`` or ``reply``
    :ivar review_id: The review; a reply's id is its review's
    :ivar owner_id: The batch's owner
    :ivar title: The batch's public title
    :ivar author_ref: The review author's opaque reference; for a reply,
        the author of the review it answers
    :ivar author_role: That author's role
    :ivar fields: The rating and words, and a reply's words
    :ivar status: ``pending`` or ``held``
    :ivar held_reason: The report reason that held it, when held
    :ivar since: When the wait began: the latest hold, else the latest
        edit or replacement, else the first submit
    """

    target_kind: ReviewTarget
    review_id: uuid.UUID
    owner_id: uuid.UUID
    title: str | None
    author_ref: str
    author_role: str
    fields: Fields
    status: str
    held_reason: str | None
    since: dt.datetime


@dataclass(frozen=True, slots=True)
class ReviewDetail:
    """One review or reply as an administrator moderates it.

    **Never** an account id, the seat, a name or phone number, or a time
    finer than the whole hours waited.

    :ivar target_kind: ``review`` or ``reply``
    :ivar review_id: The review; a reply's id is its review's
    :ivar rating: The review's rating, 1 to 5
    :ivar body: The review's words, or None
    :ivar tenure: The review author's tenure bucket
    :ivar author_role: The review author's role
    :ivar author_ref: The review author's opaque reference
    :ivar status: The target's status
    :ivar batch_title: The batch's public title
    :ivar owner_public_name: The owner listing's public name
    :ivar reply_body: The reply's words, in any status, or None
    :ivar open_reports: Open reports naming the target
    :ivar waited_hours: Whole hours waited, while pending or held
    """

    target_kind: ReviewTarget
    review_id: uuid.UUID
    rating: int
    body: str | None
    tenure: str
    author_role: str
    author_ref: str
    status: str
    batch_title: str | None
    owner_public_name: str | None
    reply_body: str | None
    open_reports: int
    waited_hours: int | None


def _code_invalid() -> ValidationError:
    """Build the refusal for a code that does not fit the decision.

    :return: The error
    """
    return ValidationError(
        code="REVIEW_CODE_INVALID", message_key="hub.review.code_invalid"
    )


def _already_decided() -> ConflictError:
    """Build the refusal for an item that is not waiting for a decision.

    :return: The error
    """
    return ConflictError(
        code="REVIEW_ALREADY_DECIDED", message_key="hub.review.already_decided"
    )


def _report_open() -> ConflictError:
    """Build the refusal for approving an item a report still holds [T7-c].

    :return: The error
    """
    return ConflictError(
        code="REVIEW_REPORT_OPEN", message_key="hub.review.report_open"
    )


def _hours(since: dt.datetime, now: dt.datetime) -> int:
    """Count whole hours waited, never negative.

    :param since: When the wait began
    :param now: The present moment
    :return: Whole hours
    """
    return max(0, int((now - since).total_seconds() // _SECONDS_PER_HOUR))


def _fields(rating: int, body: str | None, reply_body: str | None) -> Fields:
    """List what the queue shows of a review and its reply.

    :param rating: The review's rating
    :param body: The review's words
    :param reply_body: The reply's words, for a reply
    :return: ``(key, value)`` pairs, empty ones left out
    """
    values = (str(rating), body, reply_body)
    return tuple(
        (key, value)
        for key, value in zip(REVIEW_FIELDS, values, strict=True)
        if value and value.strip()
    )


def is_public(session: Session, target_kind: str, target_id: uuid.UUID) -> bool:
    """Say whether the public can see a review, or a reply's text.

    Read from ``hub_public_review``, so the threshold and the batch's
    visibility are the view's and never restated here. False for anything
    while reviews are switched off.

    :param session: The session
    :param target_kind: ``review`` or ``reply``
    :param target_id: The review; a reply's id is its review's
    :return: True for a review in the view, or a reply whose text it shows
    """
    if not reviews_enabled() or target_kind not in REVIEW_TARGETS:
        return False
    row = session.execute(_PUBLIC, {"id": target_id}).one_or_none()
    if row is None:
        return False
    return target_kind == "review" or bool(row.replied)


def _locked_review(
    session: Session, review_id: uuid.UUID, *, share: bool = False
) -> Review | None:
    """Read and lock one review, fresh from the database.

    :param session: The session
    :param review_id: The review
    :param share: Take a share lock rather than an update lock
    :return: The review, or None
    """
    return session.execute(
        sa.select(Review)
        .where(Review.id == review_id)
        .with_for_update(read=share)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def lock(
    session: Session, target_kind: str, target_id: uuid.UUID
) -> Review | ReviewReply | None:
    """Lock a review, or a reply after its review, before any report row.

    A review is locked for update. A reply's review is share-locked first,
    as ``delete_reply`` does, then the reply for update: content before
    reports, review before reply [T4-c, T5-d].

    :param session: The session
    :param target_kind: ``review`` or ``reply``
    :param target_id: The review; a reply's id is its review's
    :return: The locked target, or None when it does not exist
    """
    if target_kind == "review":
        return _locked_review(session, target_id)
    if _locked_review(session, target_id, share=True) is None:
        return None
    return session.execute(
        sa.select(ReviewReply)
        .where(ReviewReply.review_id == target_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def runs_batch(session: Session, review_id: uuid.UUID, account_id: uuid.UUID) -> bool:
    """Say whether an account runs the batch a review is of [F10, I-2].

    Its reports hold nothing: the owner "may report; never hide or delete".
    "Runs" is eligibility's own exclusion, from the one shared predicate
    (:func:`~app.reviews.eligibility.runs_batch_sql`): the owner's account,
    its accepted, unrevoked managers, and any such member assigned to teach
    the batch by slot or by class. Whoever may not review a batch may not
    take its reviews down either.

    :param session: The session
    :param review_id: The review, or the review a reply answers
    :param account_id: The reporter
    :return: True when the account runs the batch; False for anyone else,
        and for a review that does not exist
    """
    return bool(
        session.execute(
            _RUNS_BATCH, {"review_id": review_id, "account_id": account_id}
        ).scalar_one_or_none()
    )


def _event(
    target_kind: str,
    target_id: uuid.UUID,
    act: str,
    *,
    actor: uuid.UUID | None,
    code: str | None,
    correlation_id: str,
    now: dt.datetime,
) -> HubModerationEvent:
    """Build one review or reply moderation event.

    :param target_kind: ``review`` or ``reply``
    :param target_id: The review
    :param act: ``approved``, ``rejected``, ``held``, ``restored`` or
        ``removed``
    :param actor: The administrator, or None for a report's hold
    :param code: The rejection code or the report reason
    :param correlation_id: The request that caused it
    :param now: When it happened
    :return: The event, not yet added
    """
    return HubModerationEvent(
        event=f"{target_kind}_{act}",
        target_kind=target_kind,
        target_id=target_id,
        actor_admin_account_id=actor,
        decision_code=code,
        correlation_id=correlation_id,
        at=now,
    )


def _evict(session: Session, review_id: uuid.UUID, now: dt.datetime) -> None:
    """Enqueue the owner's pages for eviction, in the caller's transaction.

    :param session: The session
    :param review_id: The review whose page changed
    :param now: The moment of the change
    :return: None
    """
    slug = session.execute(_OWNER_SLUG, {"review_id": review_id}).scalar_one_or_none()
    if slug is not None:
        invalidation.enqueue(session, invalidation.owner_paths(slug), now)


def hold(
    session: Session,
    target_kind: str,
    target_id: uuid.UUID,
    *,
    reason: str,
    now: dt.datetime,
    correlation_id: str = "internal",
) -> None:
    """Take a reported review or reply down, in the reporting transaction.

    Commits nothing: the hold stands or falls with the report. An item no
    longer published by the time it is locked -- held by another report a
    moment earlier, or edited back to ``pending`` -- is left as it is. The
    caller has decided the reporter does not run the batch [F10].

    :param session: The report's session
    :param target_kind: ``review`` or ``reply``
    :param target_id: The review; a reply's id is its review's
    :param reason: The report's reason, recorded on the event
    :param now: The moment of the report
    :param correlation_id: The request that caused it
    :return: None
    """
    item = lock(session, target_kind, target_id)
    if item is None or item.status != "published":
        return
    item.status = "held"
    _evict(session, target_id, now)
    session.add(
        _event(
            target_kind,
            target_id,
            "held",
            actor=None,
            code=reason,
            correlation_id=correlation_id,
            now=now,
        )
    )


def _take_down(item: Review | ReviewReply, status: str, code: str) -> None:
    """Mark an item rejected or removed, clearing what only a shown item has.

    :param item: The locked review or reply
    :param status: ``rejected`` or ``removed``
    :param code: Its closed code
    :return: None
    """
    item.status = status
    item.rejection_code = code
    item.published_month = None
    if isinstance(item, Review):
        item.approved_at = None


def _tell(
    session: Session,
    item: Review | ReviewReply,
    outcome: Literal["rejected", "removed"],
    now: dt.datetime,
) -> None:
    """Tell a review's author it was rejected or removed, never why.

    In the decision's transaction, so a decision that rolls back sends
    nothing. The code stays on the review, for the author's own
    ``my-review``. A reply's rejection or removal tells nobody: reply
    notifications are not part of H4.

    :param session: The decision's session
    :param item: The locked review or reply, already taken down
    :param outcome: ``rejected`` or ``removed``
    :param now: The moment of the decision
    :return: None
    """
    if isinstance(item, Review):
        tell_author(
            session,
            author_account_id=item.author_account_id,
            batch_id=item.batch_id,
            outcome=outcome,
            now=now,
        )


def decide(
    session: Session,
    lens: PlatformAdminLens,
    target_kind: ReviewTarget,
    target_id: uuid.UUID,
    *,
    approve: bool,
    code: str | None,
    now: dt.datetime,
    correlation_id: str = "internal",
) -> str:
    """Approve or reject a review or reply waiting or held, and commit.

    ============  =======  ===========================  ====================
    Target        From     Approve                      Reject (with a code)
    ============  =======  ===========================  ====================
    review        pending  ``approved``, ``approved_at``  ``rejected``
    review        held     ``published`` (restored)     ``removed``
    reply         pending  ``published``, this month    ``rejected``
    reply         held     ``published`` (restored)     ``removed``
    ============  =======  ===========================  ====================

    A held item keeps its month on a restore; a rejection or removal clears
    it. A change to what the public sees evicts the owner's pages.

    **Nothing is approved over a standing report** [T7-c, I-1]: while an
    open child-safety or personal-information report names the item,
    approval is refused, as a photo's is (``MEDIA_REPORT_OPEN``) -- whether
    the item is still ``held`` or was moved back to ``pending`` by its
    author's edit or its owner's replacement, which change the words but
    settle no report. Deciding that report is what restores a held item,
    or frees a pending one for approval. A report by someone who runs the
    batch holds nothing [F10, I-2] and so blocks nothing. A rejection is
    never refused for an open report.

    :param session: The session
    :param lens: The administrator's lens
    :param target_kind: ``review`` or ``reply``
    :param target_id: The review; a reply's id is its review's
    :param approve: True to approve, False to reject
    :param code: For a rejection, one of
        :data:`~app.moderation.vocab.REVIEW_REJECTION_CODES`; None to approve
    :param now: The moment of the decision
    :param correlation_id: The request that caused it
    :return: The target's new status
    :raises ValidationError: ``REVIEW_CODE_INVALID``: a code with an
        approval, or a rejection without one of the five codes
    :raises AuthorizationError: No such review, or no reply to it
    :raises ConflictError: ``REVIEW_ALREADY_DECIDED``: the target is neither
        pending nor held; ``REVIEW_REPORT_OPEN``: an approval of a
        target, held or pending, an open holding report still names
    """
    fits = code is None if approve else code in REVIEW_REJECTION_CODES
    if not fits:
        raise _code_invalid()
    try:
        item = lock(session, target_kind, target_id)
        if item is None:
            raise admin_not_found()
        before = item.status
        if before not in DECIDABLE:
            raise _already_decided()
        # Whatever the status: an author's edit or an owner's replacement
        # moves a held item to pending without settling its report [I-1].
        if approve and _still_held(session, target_kind, target_id, None):
            raise _report_open()
        if approve and before == "held":
            act = "restored"
            item.status = "published"
        elif approve and isinstance(item, Review):
            act = "approved"
            item.status = "approved"
            item.approved_at = now
        elif approve:
            act = "approved"
            item.status = "published"
            item.published_month = bangladesh_today(now).replace(day=1)
        else:
            act = "removed" if before == "held" else "rejected"
            _take_down(item, act, cast("str", code))
            _tell(session, item, "removed" if act == "removed" else "rejected", now)
        item.decided_at = now
        item.decided_by_account_id = lens.account_id
        if before == "held" or item.status == "published":
            _evict(session, target_id, now)
        session.add(
            _event(
                target_kind,
                target_id,
                act,
                actor=lens.account_id,
                code=code,
                correlation_id=correlation_id,
                now=now,
            )
        )
        status = item.status
        session.commit()
    except Exception:
        session.rollback()
        raise
    return status


def _still_held(
    session: Session,
    target_kind: str,
    target_id: uuid.UUID,
    report_id: uuid.UUID | None,
) -> bool:
    """Say whether an open report keeps a review or reply held.

    A report by someone who runs the batch holds nothing [F10, I-2], so it
    keeps nothing held either.

    :param session: The session
    :param target_kind: ``review`` or ``reply``
    :param target_id: The review
    :param report_id: The report being dismissed, left out; or None to
        consider every open report
    :return: True when an open child-safety or personal-information report
        (other than ``report_id``), by someone who does not run the batch,
        names the target
    """
    return bool(
        session.execute(
            _STILL_HELD,
            {
                "target_kind": target_kind,
                "target_id": target_id,
                "reasons": sorted(HOLD_REASONS),
                "report_id": report_id,
            },
        ).scalar_one()
    )


def settle_report(
    session: Session,
    lens: PlatformAdminLens,
    target_kind: str,
    target_id: uuid.UUID,
    *,
    upheld: bool,
    reason: str,
    report_id: uuid.UUID,
    now: dt.datetime,
    correlation_id: str = "internal",
) -> None:
    """Carry an administrator's decision on a report to its review or reply.

    In the decision's transaction, committing nothing. The caller locked the
    target before the report (:func:`lock`); it is locked again here, which
    is a no-op, so this cannot be called out of order.

    Upheld: the target is removed whatever its status [F9], unless it is
    already rejected or removed, with the code mapped from the reason.
    Dismissed: a held target is restored once no other open holding report
    names it. Anything else is left alone.

    :param session: The decision's session
    :param lens: The administrator's lens
    :param target_kind: ``review`` or ``reply``
    :param target_id: The review; a reply's id is its review's
    :param upheld: True to uphold, False to dismiss
    :param reason: The report's reason
    :param report_id: The report being decided, already marked
    :param now: The moment of the decision
    :param correlation_id: The request that caused it
    :return: None
    """
    item = lock(session, target_kind, target_id)
    if item is None:
        return
    before = item.status
    code: str | None
    if upheld:
        if before in _SETTLED:
            return
        code = REPORT_REJECTION_CODES.get(reason, "other")
        _take_down(item, "removed", code)
        _tell(session, item, "removed", now)
        act = "removed"
    else:
        if before != "held" or _still_held(session, target_kind, target_id, report_id):
            return
        code = None
        item.status = "published"
        act = "restored"
    item.decided_at = now
    item.decided_by_account_id = lens.account_id
    if before in _SHOWN:
        _evict(session, target_id, now)
    session.add(
        _event(
            target_kind,
            target_id,
            act,
            actor=lens.account_id,
            code=code,
            correlation_id=correlation_id,
            now=now,
        )
    )


def _waiting_review(row: Row[tuple[object, ...]]) -> WaitingReview:
    """Map a row of :data:`_WAITING`.

    :param row: The row
    :return: The waiting item
    """
    return WaitingReview(
        target_kind=cast("ReviewTarget", row.kind),
        review_id=cast("uuid.UUID", row.review_id),
        owner_id=cast("uuid.UUID", row.owner_id),
        title=cast("str | None", row.public_title),
        author_ref=review_author_ref(cast("uuid.UUID", row.author_account_id)),
        author_role=cast("str", row.author_role),
        fields=_fields(
            cast("int", row.rating),
            cast("str | None", row.body),
            cast("str | None", row.reply_body),
        ),
        status=cast("str", row.status),
        held_reason=cast("str | None", row.held_reason),
        since=cast("dt.datetime", row.since),
    )


def waiting(session: Session) -> list[WaitingReview]:
    """List the reviews and replies an administrator should decide.

    Pending and held, oldest wait first: a held item from its latest hold
    [F11], a pending one from its latest edit or replacement, else from its
    first submit.

    :param session: The session
    :return: The items
    """
    return [_waiting_review(row) for row in session.execute(_WAITING)]


def _one(
    session: Session, review_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Row[tuple[object, ...]]]:
    """Read reviews with their replies, batch titles and owner names.

    :param session: The session
    :param review_ids: The reviews
    :return: ``{review id: row}``, one row of :data:`_ONE` per review found
    """
    return {
        row.review_id: row for row in session.execute(_ONE, {"ids": list(review_ids)})
    }


def describe(
    session: Session, target_kind: str, review_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, tuple[uuid.UUID, str | None, Fields, str, str]]:
    """Describe reported reviews or replies for the report queue.

    :param session: The session
    :param target_kind: ``review`` or ``reply``
    :param review_ids: The reviews named by the reports
    :return: ``{review id: (owner id, batch title, fields, author ref,
        author role)}`` for those that exist, and for a reply only where
        the reply does
    """
    found = {}
    for review_id, row in _one(session, review_ids).items():
        reply = target_kind == "reply"
        if reply and row.reply_status is None:
            continue
        found[review_id] = (
            row.owner_id,
            row.public_title,
            _fields(row.rating, row.body, row.reply_body if reply else None),
            review_author_ref(row.author_account_id),
            row.author_role,
        )
    return found


def detail(
    session: Session,
    target_kind: ReviewTarget,
    target_id: uuid.UUID,
    now: dt.datetime | None = None,
) -> ReviewDetail:
    """Read one review or reply as an administrator moderates it.

    :param session: The session
    :param target_kind: ``review`` or ``reply``
    :param target_id: The review; a reply's id is its review's
    :param now: The moment waits are measured to, or None for the clock
    :return: The item, naming its author only by role and reference
    :raises AuthorizationError: No such review, or no reply to it
    """
    row = _one(session, [target_id]).get(target_id)
    reply = target_kind == "reply"
    if row is None or (reply and row.reply_status is None):
        raise admin_not_found()
    status = row.reply_status if reply else row.review_status
    since = row.reply_since if reply else row.review_since
    moment = now or dt.datetime.now(tz=dt.UTC)
    open_reports = session.scalar(
        sa.select(sa.func.count())
        .select_from(HubReport)
        .where(
            HubReport.target_kind == target_kind,
            HubReport.target_id == target_id,
            HubReport.status == "open",
        )
    )
    return ReviewDetail(
        target_kind=target_kind,
        review_id=row.review_id,
        rating=row.rating,
        body=row.body,
        tenure=row.tenure,
        author_role=row.author_role,
        author_ref=review_author_ref(row.author_account_id),
        status=status,
        batch_title=row.public_title,
        owner_public_name=row.public_name,
        reply_body=row.reply_body,
        open_reports=int(open_reports or 0),
        waited_hours=_hours(since, moment) if status in DECIDABLE else None,
    )
