"""Review and reply moderation: decisions, report holds and the admin queue.

Written before :mod:`app.moderation.reviews` existed. Who may take a review
down is an authorization predicate [team: Testing Posture]: a child-safety
or personal-information report holds a published review or reply at once,
**except** one filed by the batch's own owner or managers, who "may report;
never hide or delete" (spec section 6) [F10]. An upheld report removes its
target whatever its status [F9]; a dismissed one restores only a held
target, and only when no other open holding report stands.

Everything is arranged through the table-owner session and exercised
through the restricted one.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
import uuid
from typing import Final, get_args

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from app.authz.admin import PLATFORM_ADMIN_PHONES_ENV
from app.authz.lenses import PlatformAdminLens
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.hub.public.invalidation import owner_paths
from app.hub.public.settings import HUB_REVIEWS_ENV
from app.local_time import bangladesh_today
from app.moderation import reports, reviews
from app.moderation.vocab import (
    REPORT_REJECTION_CODES,
    REVIEW_REJECTION_CODES,
    ReviewRejectionCode,
)
from app.reviews import authoring
from app.reviews.eligibility import Assessment
from app.reviews.identity import review_author_ref
from app.reviews.lens import ReviewerLens
from tests.help.conftest import People, phone_of
from tests.moderation.conftest import admin_headers
from tests.reviews.support import (
    PublicBatch,
    account,
    add_review,
    guardian_seat,
    public_batch,
    public_centre_batch,
)

#: The admin path for one review or reply.
DETAIL: Final = "/v1/admin/hub/reviews/{review_id}"


def _now() -> dt.datetime:
    """Give the present.

    :return: Now, in UTC
    """
    return dt.datetime.now(tz=dt.UTC)


def _month() -> dt.date:
    """Give the first of this month in Bangladesh.

    :return: The date
    """
    return bangladesh_today().replace(day=1)


def _admin(session: Session) -> PlatformAdminLens:
    """Give an administrator's lens over a fresh account.

    :param session: An arranging session
    :return: The lens
    """
    return PlatformAdminLens(account_id=account(session))


def _set_status(session: Session, review_id: uuid.UUID, status: str) -> None:
    """Move a stored review to a status, with the columns that status needs.

    :param session: An arranging session
    :param review_id: The review
    :param status: Any review status
    :return: None
    """
    shown = status in ("published", "held")
    session.execute(
        sa.text(
            "UPDATE review SET status = CAST(:s AS hub_review_status), "
            "published_month = :m, approved_at = :a, rejection_code = :c "
            "WHERE id = :r"
        ),
        {
            "s": status,
            "m": _month() if shown else None,
            "a": _now() if status == "approved" else None,
            "c": "off_topic" if status in ("rejected", "removed") else None,
            "r": review_id,
        },
    )
    session.commit()


def _reviewed(
    session: Session,
    batch_id: uuid.UUID,
    status: str,
    *,
    author: uuid.UUID | None = None,
    rating: int = 4,
) -> uuid.UUID:
    """Add a guardian's review of a batch, in a status.

    :param session: An arranging session
    :param batch_id: The batch
    :param status: The review's status
    :param author: The author; a fresh account by default
    :param rating: 1 to 5
    :return: The review id
    """
    review_id = add_review(session, batch_id, author or account(session), rating=rating)
    _set_status(session, review_id, status)
    return review_id


def _published(session: Session, batch_id: uuid.UUID, n: int = 3) -> list[uuid.UUID]:
    """Publish ``n`` reviews of a batch, enough to clear the threshold.

    :param session: An arranging session
    :param batch_id: The batch
    :param n: How many
    :return: The review ids
    """
    return [_reviewed(session, batch_id, "published") for _ in range(n)]


def _reply(
    session: Session,
    review_id: uuid.UUID,
    *,
    status: str = "published",
    body: str = "Thank you for writing.",
) -> None:
    """Store a reply directly.

    :param session: An arranging session
    :param review_id: The review
    :param status: ``pending``, ``published`` or ``held``
    :param body: The text
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO review_reply (review_id, body, status, published_month) "
            "VALUES (:r, :b, CAST(:s AS hub_reply_status), :m)"
        ),
        {
            "r": review_id,
            "b": body,
            "s": status,
            "m": _month() if status in ("published", "held") else None,
        },
    )
    session.commit()


def _review(session: Session, review_id: uuid.UUID) -> Row[tuple[object, ...]]:
    """Read a stored review fresh.

    :param session: An arranging session
    :param review_id: The review
    :return: The row
    """
    session.rollback()
    return session.execute(
        sa.text("SELECT * FROM review WHERE id = :r"), {"r": review_id}
    ).one()


def _reply_row(session: Session, review_id: uuid.UUID) -> Row[tuple[object, ...]]:
    """Read a stored reply fresh.

    :param session: An arranging session
    :param review_id: The review it answers
    :return: The row
    """
    session.rollback()
    return session.execute(
        sa.text("SELECT * FROM review_reply WHERE review_id = :r"), {"r": review_id}
    ).one()


def _in_view(session: Session, review_id: uuid.UUID) -> Row[tuple[object, ...]] | None:
    """Read a review as the public view shows it.

    :param session: An arranging session
    :param review_id: The review
    :return: Its view row, or None when the public cannot see it
    """
    session.rollback()
    return session.execute(
        sa.text("SELECT * FROM hub_public_review WHERE id = :r"), {"r": review_id}
    ).one_or_none()


def _events(session: Session) -> list[tuple[str, str, str | None, bool]]:
    """Read the moderation events in order.

    :param session: An arranging session
    :return: ``(event, target kind, code, has an actor)`` per event
    """
    session.rollback()
    return [
        (r.event, r.target_kind, r.decision_code, r.actor_admin_account_id is not None)
        for r in session.execute(
            sa.text(
                "SELECT event::text AS event, target_kind::text AS target_kind, "
                "decision_code, actor_admin_account_id "
                "FROM hub_moderation_event ORDER BY at, event"
            )
        )
    ]


def _invalidated(session: Session) -> set[str]:
    """List the paths in the invalidation outbox.

    :param session: An arranging session
    :return: The paths
    """
    session.rollback()
    return set(session.scalars(sa.text("SELECT path FROM cdn_invalidation")))


def _owner_pages(session: Session, owner_id: uuid.UUID) -> set[str]:
    """Give the paths that evict an owner's pages, with the sitemap.

    :param session: An arranging session
    :param owner_id: The owner
    :return: The paths
    """
    slug = session.execute(
        sa.text("SELECT slug FROM owner_listing WHERE owner_id = :o"), {"o": owner_id}
    ).scalar_one()
    return {*owner_paths(str(slug)), "/hub/sitemap.xml"}


def _reports(session: Session) -> int:
    """Count every report row.

    :param session: An arranging session
    :return: The count
    """
    session.rollback()
    return int(session.execute(sa.text("SELECT count(*) FROM hub_report")).scalar_one())


def _report_id(session: Session, kind: str, target: uuid.UUID) -> list[uuid.UUID]:
    """List the reports on a target, oldest first.

    :param session: An arranging session
    :param kind: ``review`` or ``reply``
    :param target: The target id
    :return: The report ids
    """
    session.rollback()
    return list(
        session.scalars(
            sa.text(
                "SELECT id FROM hub_report WHERE target_id = :t "
                "AND target_kind = CAST(:k AS hub_report_target) "
                "ORDER BY created_at, id"
            ),
            {"t": target, "k": kind},
        )
    )


def _file(
    session: Session,
    kind: str,
    target: uuid.UUID,
    reason: str,
    reporter: uuid.UUID | None = None,
    owner_session: Session | None = None,
) -> uuid.UUID:
    """File a report through the service.

    :param session: The restricted session
    :param kind: ``review`` or ``reply``
    :param target: The target id
    :param reason: The reason
    :param reporter: The reporting account
    :param owner_session: For minting a fresh reporter when none is given
    :return: The reporter
    """
    if reporter is None:
        assert owner_session is not None
        reporter = account(owner_session)
    reports.file(session, reporter, kind, target, reason, None, _now())
    return reporter


# ---------------------------------------------------------------------------
# An administrator's decision
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("reviews_on")
def test_pending_review_approves_to_approved_not_published(
    owner_session: Session, restricted_session: Session
) -> None:
    """Approval queues it for the weekly publication; nothing goes public."""
    batch = public_batch(owner_session)
    _published(owner_session, batch.batch_id)
    target = _reviewed(owner_session, batch.batch_id, "pending")
    admin = _admin(owner_session)
    now = _now()

    status = reviews.decide(
        restricted_session,
        admin,
        "review",
        target,
        approve=True,
        code=None,
        now=now,
        correlation_id="c1",
    )

    assert status == "approved"
    row = _review(owner_session, target)
    assert (row.status, row.published_month) == ("approved", None)
    assert row.approved_at == now
    assert row.decided_by_account_id == admin.account_id
    assert _in_view(owner_session, target) is None
    assert _events(owner_session) == [("review_approved", "review", None, True)]
    assert _invalidated(owner_session) == set()


@pytest.mark.usefixtures("reviews_on")
def test_reject_requires_code_and_records_event(
    owner_session: Session, restricted_session: Session
) -> None:
    """A rejection needs one of the five codes; an approval takes none."""
    batch = public_batch(owner_session)
    target = _reviewed(owner_session, batch.batch_id, "pending")
    admin = _admin(owner_session)

    refusals = []
    for approve, code in ((False, None), (False, "abuse"), (True, "off_topic")):
        with pytest.raises(ValidationError) as caught:
            reviews.decide(
                restricted_session,
                admin,
                "review",
                target,
                approve=approve,
                code=code,
                now=_now(),
                correlation_id="c1",
            )
        restricted_session.rollback()
        refusals.append((caught.value.code, caught.value.message_key))
    assert set(refusals) == {("REVIEW_CODE_INVALID", "hub.review.code_invalid")}
    assert _review(owner_session, target).status == "pending"

    status = reviews.decide(
        restricted_session,
        admin,
        "review",
        target,
        approve=False,
        code="off_topic",
        now=_now(),
        correlation_id="c1",
    )

    assert status == "rejected"
    row = _review(owner_session, target)
    assert (row.status, row.rejection_code, row.published_month) == (
        "rejected",
        "off_topic",
        None,
    )
    assert _events(owner_session) == [("review_rejected", "review", "off_topic", True)]


def test_review_rejection_codes_are_the_five() -> None:
    """The closed set the decision and the wire share.

    It holds every code an upheld report maps a reason to.
    """
    assert get_args(ReviewRejectionCode) == REVIEW_REJECTION_CODES
    assert set(REPORT_REJECTION_CODES.values()) <= set(REVIEW_REJECTION_CODES)
    assert REVIEW_REJECTION_CODES == (
        "identifiable_child",
        "personal_info",
        "abusive",
        "off_topic",
        "other",
    )


@pytest.mark.usefixtures("reviews_on")
def test_reply_approval_publishes_immediately(
    owner_session: Session, restricted_session: Session
) -> None:
    """A reply has no weekly batch: approval publishes it, this month."""
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    _reply(owner_session, target, status="pending", body="We are glad.")
    admin = _admin(owner_session)

    status = reviews.decide(
        restricted_session,
        admin,
        "reply",
        target,
        approve=True,
        code=None,
        now=_now(),
        correlation_id="c1",
    )

    assert status == "published"
    reply = _reply_row(owner_session, target)
    assert (reply.status, reply.published_month) == ("published", _month())
    assert reply.decided_by_account_id == admin.account_id
    shown = _in_view(owner_session, target)
    assert shown is not None
    assert shown.reply_body == "We are glad."
    assert _review(owner_session, target).status == "published"
    assert _events(owner_session) == [("reply_approved", "reply", None, True)]
    assert _invalidated(owner_session) == _owner_pages(owner_session, batch.owner_id)


@pytest.mark.usefixtures("reviews_on")
def test_reply_rejection_keeps_the_review(
    owner_session: Session, restricted_session: Session
) -> None:
    """Rejecting a reply leaves the review it answers as it was."""
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    _reply(owner_session, target, status="pending")

    status = reviews.decide(
        restricted_session,
        _admin(owner_session),
        "reply",
        target,
        approve=False,
        code="personal_info",
        now=_now(),
        correlation_id="c1",
    )

    assert status == "rejected"
    reply = _reply_row(owner_session, target)
    assert (reply.status, reply.rejection_code) == ("rejected", "personal_info")
    assert _review(owner_session, target).status == "published"
    assert _events(owner_session) == [
        ("reply_rejected", "reply", "personal_info", True)
    ]


@pytest.mark.usefixtures("reviews_on")
@pytest.mark.parametrize("status", ["approved", "published", "rejected", "removed"])
def test_decision_on_published_is_conflict(
    owner_session: Session, restricted_session: Session, status: str
) -> None:
    """Only pending and held items are decided; anything else is conflict."""
    batch = public_batch(owner_session)
    target = _reviewed(owner_session, batch.batch_id, status)

    for approve, code in ((True, None), (False, "other")):
        with pytest.raises(ConflictError) as caught:
            reviews.decide(
                restricted_session,
                _admin(owner_session),
                "review",
                target,
                approve=approve,
                code=code,
                now=_now(),
                correlation_id="c1",
            )
        restricted_session.rollback()
        assert (caught.value.code, caught.value.message_key) == (
            "REVIEW_ALREADY_DECIDED",
            "hub.review.already_decided",
        )
    assert _review(owner_session, target).status == status
    assert _events(owner_session) == []


@pytest.mark.usefixtures("reviews_on")
@pytest.mark.parametrize("kind", ["review", "reply"])
def test_decision_on_nothing_is_admin_not_found(
    owner_session: Session, restricted_session: Session, kind: str
) -> None:
    """An id never minted, or a review with no reply, is not found."""
    batch = public_batch(owner_session)
    without_reply = _published(owner_session, batch.batch_id)[0]
    targets = [uuid.uuid4()] + ([without_reply] if kind == "reply" else [])

    for target in targets:
        with pytest.raises(AuthorizationError) as caught:
            reviews.decide(
                restricted_session,
                _admin(owner_session),
                kind,  # type: ignore[arg-type]
                target,
                approve=True,
                code=None,
                now=_now(),
                correlation_id="c1",
            )
        restricted_session.rollback()
        assert caught.value.code == "HUB_ADMIN_TARGET_NOT_FOUND"


@pytest.mark.usefixtures("reviews_on")
def test_held_review_approve_restores_and_reject_removes(
    owner_session: Session, restricted_session: Session
) -> None:
    """Held: approve restores it (its month kept); reject removes it."""
    batch = public_batch(owner_session)
    restored, removed, _ = _published(owner_session, batch.batch_id)
    for target in (restored, removed):
        _set_status(owner_session, target, "held")
    admin = _admin(owner_session)

    assert (
        reviews.decide(
            restricted_session,
            admin,
            "review",
            restored,
            approve=True,
            code=None,
            now=_now(),
            correlation_id="c1",
        )
        == "published"
    )
    assert (
        reviews.decide(
            restricted_session,
            admin,
            "review",
            removed,
            approve=False,
            code="abusive",
            now=_now(),
            correlation_id="c1",
        )
        == "removed"
    )

    back = _review(owner_session, restored)
    assert (back.status, back.published_month) == ("published", _month())
    gone = _review(owner_session, removed)
    assert (gone.status, gone.published_month, gone.rejection_code) == (
        "removed",
        None,
        "abusive",
    )
    assert sorted(_events(owner_session)) == [
        ("review_removed", "review", "abusive", True),
        ("review_restored", "review", None, True),
    ]
    assert _invalidated(owner_session) == _owner_pages(owner_session, batch.owner_id)


# ---------------------------------------------------------------------------
# A report's hold
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("reviews_on")
@pytest.mark.parametrize("reason", ["child_safety", "personal_info"])
def test_child_safety_report_holds_review_in_same_transaction(
    owner_session: Session,
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    """Rolled back: still published, nothing enqueued. Committed: held."""
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    reporter = account(owner_session)

    real_hold = reviews.hold
    held_in_rolled_back_leg: list[uuid.UUID] = []

    def failing_commit() -> None:
        raise RuntimeError("the report's commit failed")

    with monkeypatch.context() as patch:

        def hold_then_fail_commit(
            session: Session, kind: str, target_id: uuid.UUID, **kwargs: object
        ) -> None:
            real_hold(session, kind, target_id, **kwargs)  # type: ignore[arg-type]
            held_in_rolled_back_leg.append(target_id)
            patch.setattr(session, "commit", failing_commit)

        patch.setattr(reviews, "hold", hold_then_fail_commit)
        with pytest.raises(RuntimeError, match="the report's commit failed"):
            reports.file(
                restricted_session, reporter, "review", target, reason, None, _now()
            )
    restricted_session.rollback()
    assert held_in_rolled_back_leg == [target]

    assert _review(owner_session, target).status == "published"
    assert _in_view(owner_session, target) is not None
    assert _invalidated(owner_session) == set()
    assert _reports(owner_session) == 0

    reports.file(restricted_session, reporter, "review", target, reason, None, _now())

    row = _review(owner_session, target)
    assert (row.status, row.published_month) == ("held", _month())
    # Held leaves two published: the batch drops below the threshold.
    assert _in_view(owner_session, target) is None
    assert _invalidated(owner_session) == _owner_pages(owner_session, batch.owner_id)
    assert sorted(_events(owner_session)) == [
        ("report_filed", "review", reason, False),
        ("review_held", "review", reason, False),
    ]


@pytest.mark.usefixtures("reviews_on")
@pytest.mark.parametrize("reason", ["abusive", "fake", "misleading", "other"])
def test_other_reasons_do_not_hold_a_review(
    owner_session: Session, restricted_session: Session, reason: str
) -> None:
    """Only the two harms hold; the rest wait for a decision."""
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]

    _file(restricted_session, "review", target, reason, owner_session=owner_session)

    assert _review(owner_session, target).status == "published"
    assert _invalidated(owner_session) == set()


@pytest.mark.usefixtures("reviews_on")
def test_reply_report_holds_reply_only(
    owner_session: Session, restricted_session: Session
) -> None:
    """A reported reply comes down; the review it answers stays up."""
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    _reply(owner_session, target)

    _file(
        restricted_session, "reply", target, "child_safety", owner_session=owner_session
    )

    reply = _reply_row(owner_session, target)
    assert (reply.status, reply.published_month) == ("held", _month())
    assert _review(owner_session, target).status == "published"
    shown = _in_view(owner_session, target)
    assert shown is not None
    assert shown.reply_body is None
    assert _invalidated(owner_session) == _owner_pages(owner_session, batch.owner_id)
    assert ("reply_held", "reply", "child_safety", False) in _events(owner_session)


@pytest.mark.usefixtures("reviews_on")
@pytest.mark.parametrize("who", ["owner", "manager"])
def test_owner_report_does_not_hold_review(
    owner_session: Session, restricted_session: Session, who: str
) -> None:
    """F10: the batch's owner or manager may report, never hide [spec 6].

    Their child-safety report goes to the queue and holds nothing; and it
    does not keep a review held once the report that did hold it is
    dismissed.
    """
    batch = (
        public_batch(owner_session)
        if who == "owner"
        else public_centre_batch(owner_session)
    )
    target, other, _ = _published(owner_session, batch.batch_id)
    _reply(owner_session, other)

    for kind, item in (("review", target), ("reply", other)):
        _file(restricted_session, kind, item, "child_safety", batch.teacher_account_id)

    assert _review(owner_session, target).status == "published"
    assert _reply_row(owner_session, other).status == "published"
    assert _invalidated(owner_session) == set()
    queued = [
        (i.target_kind, i.target_id)
        for i in reports.queue(restricted_session, "report")
    ]
    assert queued == [("review", target), ("reply", other)]

    # A stranger's holding report, dismissed: the owner's does not keep it held.
    _file(
        restricted_session,
        "review",
        target,
        "child_safety",
        owner_session=owner_session,
    )
    assert _review(owner_session, target).status == "held"
    stranger_report = _report_id(owner_session, "review", target)[-1]
    reports.decide(
        restricted_session,
        _admin(owner_session),
        stranger_report,
        "dismissed",
        _now(),
    )
    assert _review(owner_session, target).status == "published"


# ---------------------------------------------------------------------------
# A decision on a report reaches the review or reply
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("reviews_on")
def test_upheld_report_removes_and_dismissed_restores_unless_another_hold(
    owner_session: Session, restricted_session: Session
) -> None:
    """Two holding reports: one dismissed keeps it held, both restore it.

    A held review cannot be reported again, so the two arise as they would:
    held, restored by an administrator with its report still open, then
    held again by a second report.
    """
    batch = public_batch(owner_session)
    target, second, _ = _published(owner_session, batch.batch_id)
    admin = _admin(owner_session)
    _file(
        restricted_session,
        "review",
        target,
        "child_safety",
        owner_session=owner_session,
    )
    reviews.decide(
        restricted_session,
        admin,
        "review",
        target,
        approve=True,
        code=None,
        now=_now(),
        correlation_id="c1",
    )
    _file(
        restricted_session,
        "review",
        target,
        "personal_info",
        owner_session=owner_session,
    )
    first_report, second_report = _report_id(owner_session, "review", target)

    reports.decide(restricted_session, admin, first_report, "dismissed", _now())
    assert _review(owner_session, target).status == "held"

    reports.decide(restricted_session, admin, second_report, "dismissed", _now())
    row = _review(owner_session, target)
    assert (row.status, row.published_month) == ("published", _month())
    assert ("review_restored", "review", None, True) in _events(owner_session)

    _file(
        restricted_session,
        "review",
        second,
        "child_safety",
        owner_session=owner_session,
    )
    (upheld,) = _report_id(owner_session, "review", second)
    reports.decide(restricted_session, admin, upheld, "upheld", _now())
    gone = _review(owner_session, second)
    assert (gone.status, gone.rejection_code, gone.published_month) == (
        "removed",
        "identifiable_child",
        None,
    )
    assert ("review_removed", "review", "identifiable_child", True) in _events(
        owner_session
    )
    assert _invalidated(owner_session) == _owner_pages(owner_session, batch.owner_id)


@pytest.mark.usefixtures("reviews_on")
@pytest.mark.parametrize("now_status", ["published", "pending", "approved", "held"])
def test_upheld_report_removes_a_review_whatever_its_status(
    owner_session: Session, restricted_session: Session, now_status: str
) -> None:
    """F9: an edit back to pending does not escape an upheld report."""
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    _file(restricted_session, "review", target, "abusive", owner_session=owner_session)
    _set_status(owner_session, target, now_status)
    (report_id,) = _report_id(owner_session, "review", target)

    reports.decide(
        restricted_session, _admin(owner_session), report_id, "upheld", _now()
    )

    row = _review(owner_session, target)
    assert (row.status, row.rejection_code, row.approved_at) == (
        "removed",
        "other",
        None,
    )


@pytest.mark.usefixtures("reviews_on")
@pytest.mark.parametrize("now_status", ["published", "pending", "held"])
def test_upheld_reply_report_removes_the_reply_whatever_its_status(
    owner_session: Session, restricted_session: Session, now_status: str
) -> None:
    """F9 for replies: a replacement back to pending does not escape."""
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    _reply(owner_session, target)
    _file(restricted_session, "reply", target, "abusive", owner_session=owner_session)
    owner_session.execute(
        sa.text(
            "UPDATE review_reply SET status = CAST(:s AS hub_reply_status), "
            "published_month = :m WHERE review_id = :r"
        ),
        {
            "s": now_status,
            "m": None if now_status == "pending" else _month(),
            "r": target,
        },
    )
    owner_session.commit()
    (report_id,) = _report_id(owner_session, "reply", target)

    reports.decide(
        restricted_session, _admin(owner_session), report_id, "upheld", _now()
    )

    reply = _reply_row(owner_session, target)
    assert (reply.status, reply.rejection_code, reply.published_month) == (
        "removed",
        "other",
        None,
    )
    assert _review(owner_session, target).status == "published"


@pytest.mark.usefixtures("reviews_on")
def test_dismissing_a_report_on_a_published_review_changes_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    """Dismissal restores only a held target."""
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    _file(restricted_session, "review", target, "abusive", owner_session=owner_session)
    (report_id,) = _report_id(owner_session, "review", target)

    reports.decide(
        restricted_session, _admin(owner_session), report_id, "dismissed", _now()
    )

    assert _review(owner_session, target).status == "published"
    assert sorted(e[0] for e in _events(owner_session)) == [
        "report_dismissed",
        "report_filed",
    ]


# ---------------------------------------------------------------------------
# What is reportable
# ---------------------------------------------------------------------------


def _refusal(
    session: Session, reporter: uuid.UUID, kind: str, target: uuid.UUID
) -> tuple[str, str, int]:
    """File a report expected to be refused and return the refusal.

    :param session: The restricted session
    :param reporter: The reporting account
    :param kind: The target kind
    :param target: The target id
    :return: ``(code, message key, status)``
    """
    with pytest.raises(AuthorizationError) as caught:
        reports.file(session, reporter, kind, target, "child_safety", None, _now())
    session.rollback()
    return caught.value.code, caught.value.message_key, caught.value.status


def test_reports_on_reviews_refused_when_switch_off(
    owner_session: Session,
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Off: a published review or reply answers the shared refusal."""
    monkeypatch.delenv(HUB_REVIEWS_ENV, raising=False)
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    _reply(owner_session, target)
    reporter = account(owner_session)

    refusals = {
        _refusal(restricted_session, reporter, kind, item)
        for kind, item in (
            ("review", target),
            ("reply", target),
            ("review", uuid.uuid4()),
        )
    }

    assert refusals == {("REPORT_TARGET_NOT_FOUND", "hub.report_target_not_found", 404)}
    assert _review(owner_session, target).status == "published"
    assert _reports(owner_session) == 0


@pytest.mark.usefixtures("reviews_on")
def test_report_on_below_threshold_review_refused(
    owner_session: Session, restricted_session: Session
) -> None:
    """Two published reviews are not public, so neither is reportable."""
    batch = public_batch(owner_session)
    target, _ = _published(owner_session, batch.batch_id, n=2)
    pending = _published(owner_session, batch.batch_id, n=1)[0]
    _set_status(owner_session, pending, "pending")
    reporter = account(owner_session)

    refusals = {
        _refusal(restricted_session, reporter, kind, item)
        for kind, item in (("review", target), ("reply", target), ("review", pending))
    }

    assert refusals == {("REPORT_TARGET_NOT_FOUND", "hub.report_target_not_found", 404)}
    assert _review(owner_session, target).status == "published"


@pytest.mark.usefixtures("reviews_on")
def test_a_pending_reply_is_not_reportable(
    owner_session: Session, restricted_session: Session
) -> None:
    """A reply counts only while the view shows its text."""
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    _reply(owner_session, target, status="pending")

    assert reviews.is_public(restricted_session, "review", target)
    assert not reviews.is_public(restricted_session, "reply", target)
    assert _refusal(restricted_session, account(owner_session), "reply", target) == (
        "REPORT_TARGET_NOT_FOUND",
        "hub.report_target_not_found",
        404,
    )


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("reviews_on")
def test_review_queue_lists_pending_and_held_oldest_first(
    owner_session: Session, restricted_session: Session
) -> None:
    """F11: a held item waits from its latest hold event, not its submit."""
    batch = public_batch(owner_session)
    now = _now()
    held, replied, _ = _published(owner_session, batch.batch_id)
    pending = _reviewed(owner_session, batch.batch_id, "pending")
    _reply(owner_session, replied, status="pending", body="Thanks.")
    owner_session.execute(
        sa.text("UPDATE review SET submitted_at = :t WHERE id = :r"),
        {"t": now - dt.timedelta(hours=10), "r": pending},
    )
    owner_session.execute(
        sa.text("UPDATE review_reply SET created_at = :t WHERE review_id = :r"),
        {"t": now - dt.timedelta(hours=20), "r": replied},
    )
    owner_session.commit()
    _file(
        restricted_session, "review", held, "child_safety", owner_session=owner_session
    )
    owner_session.execute(
        sa.text("UPDATE review SET submitted_at = :t WHERE id = :r"),
        {"t": now - dt.timedelta(days=60), "r": held},
    )
    owner_session.execute(
        sa.text("UPDATE hub_moderation_event SET at = :t WHERE event = 'review_held'"),
        {"t": now - dt.timedelta(hours=30)},
    )
    owner_session.commit()

    items = reports.queue(restricted_session, "review", now)

    assert [(i.target_kind, i.target_id, i.waited_hours) for i in items] == [
        ("review", held, 30),
        ("reply", replied, 20),
        ("review", pending, 10),
    ]
    assert all(i.kind == "review" and i.report_id is None for i in items)
    assert items[0].reason == "child_safety"
    assert items[1].reason is None
    assert items[0].title == "HSC Physics"
    assert items[0].owner_id == batch.owner_id
    author = _review(owner_session, pending).author_account_id
    assert items[2].author_ref == review_author_ref(author)
    assert items[2].author_role == "guardian"
    assert ("reply_body", "Thanks.") in items[1].fields


@pytest.mark.usefixtures("reviews_on")
def test_report_rows_on_reviews_name_the_batch_and_the_author_ref(
    owner_session: Session, restricted_session: Session
) -> None:
    """A report row for a review carries its words, never its author."""
    batch = public_batch(owner_session)
    author = account(owner_session)
    target = _reviewed(owner_session, batch.batch_id, "published", author=author)
    _published(owner_session, batch.batch_id, n=2)
    owner_session.execute(
        sa.text("UPDATE review SET body = 'Kind teacher.' WHERE id = :r"), {"r": target}
    )
    owner_session.commit()
    _file(restricted_session, "review", target, "abusive", owner_session=owner_session)

    (item,) = reports.queue(restricted_session, "report")

    assert (item.target_kind, item.title, item.owner_id) == (
        "review",
        "HSC Physics",
        batch.owner_id,
    )
    assert dict(item.fields) == {"review_rating": "4", "review_body": "Kind teacher."}
    assert (item.author_ref, item.author_role) == (
        review_author_ref(author),
        "guardian",
    )
    assert str(author) not in repr(item)


@pytest.mark.usefixtures("reviews_on")
@pytest.mark.parametrize("status", ["pending", "held"])
def test_deleted_review_leaves_every_queue(
    owner_session: Session, restricted_session: Session, status: str
) -> None:
    """F21: the author's delete takes it out of every queue, reports and all."""
    batch = public_batch(owner_session)
    author = account(owner_session)
    target = _reviewed(owner_session, batch.batch_id, "published", author=author)
    _published(owner_session, batch.batch_id)
    _reply(owner_session, target)
    _file(restricted_session, "reply", target, "abusive", owner_session=owner_session)
    _file(
        restricted_session,
        "review",
        target,
        "child_safety",
        owner_session=owner_session,
    )
    if status == "pending":
        _set_status(owner_session, target, "pending")
    assert _review(owner_session, target).status == status
    assert target in {i.target_id for i in reports.queue(restricted_session, "review")}
    assert len(reports.queue(restricted_session, "report")) == 2
    owner_session.rollback()

    authoring.delete(restricted_session, _author_lens(batch, author), _now())

    assert [
        i for i in reports.queue(restricted_session, "review") if i.target_id == target
    ] == []
    assert reports.queue(restricted_session, "report") == []
    assert _reports(owner_session) == 0


def _author_lens(batch: PublicBatch, author: uuid.UUID) -> ReviewerLens:
    """Build the author's reviewer lens for a batch.

    :param batch: The batch
    :param author: The author
    :return: The lens
    """
    return ReviewerLens(
        account_id=author,
        batch_id=batch.batch_id,
        assessment=Assessment(
            batch_id=batch.batch_id,
            batch_title="HSC Physics",
            owner_public_name="Rahim Sir",
            enrollment_id=None,
            review_id=None,
            standing="author_only",
            waiting_on=None,
            eligible_from=None,
            tenure=None,
        ),
    )


# ---------------------------------------------------------------------------
# Lock order [T4-c, T5-d]
# ---------------------------------------------------------------------------


def _wait_for_a_lock_waiter(session: Session) -> None:
    """Block until some backend waits on a lock.

    :param session: The session holding the lock
    :return: None
    :raises AssertionError: Nobody waited within ten seconds
    """
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        waiting = session.execute(
            sa.text("SELECT count(*) FROM pg_locks WHERE NOT granted")
        ).scalar_one()
        if waiting:
            return
        time.sleep(0.05)
    session.rollback()
    raise AssertionError("the decision never waited on the author's delete")


@pytest.mark.usefixtures("reviews_on")
@pytest.mark.parametrize("kind", ["review", "reply"])
def test_a_report_decision_waits_on_the_content_lock_not_the_report(
    owner_session: Session, restricted_session: Session, kind: str
) -> None:
    """The decision locks the review first, as the author's delete does.

    The author's delete is held after it locked the review and deleted the
    reports; the decision waits on the review, and once the delete commits
    it finds no report. Locking the report first would deadlock instead.
    """
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    _reply(owner_session, target)
    _file(restricted_session, kind, target, "abusive", owner_session=owner_session)
    (report_id,) = _report_id(owner_session, kind, target)
    admin = _admin(owner_session)
    owner_session.execute(
        sa.text("SELECT id FROM review WHERE id = :r FOR UPDATE"), {"r": target}
    )
    owner_session.execute(
        sa.text("DELETE FROM hub_report WHERE target_id = :r"), {"r": target}
    )
    owner_session.execute(sa.text("DELETE FROM review WHERE id = :r"), {"r": target})
    outcome: list[object] = []

    def settle() -> None:
        try:
            reports.decide(restricted_session, admin, report_id, "upheld", _now())
            outcome.append("decided")
        except Exception as error:  # noqa: BLE001 -- asserted below
            outcome.append(error)

    thread = threading.Thread(target=settle)
    thread.start()
    _wait_for_a_lock_waiter(owner_session)
    owner_session.commit()
    thread.join(timeout=30)

    assert len(outcome) == 1
    refused = outcome[0]
    assert isinstance(refused, AuthorizationError), outcome
    assert refused.code == "HUB_ADMIN_TARGET_NOT_FOUND"


# ---------------------------------------------------------------------------
# The admin routes
# ---------------------------------------------------------------------------


def _admin_headers(
    session: Session, people: People, monkeypatch: pytest.MonkeyPatch
) -> dict[str, str]:
    """Make the stranger an administrator and return their headers.

    :param session: An arranging session
    :param people: The arranged accounts
    :param monkeypatch: The patcher
    :return: The headers
    """
    monkeypatch.setenv(PLATFORM_ADMIN_PHONES_ENV, phone_of(session, people.stranger))
    return admin_headers(session, people.stranger)


@pytest.mark.usefixtures("reviews_on")
def test_admin_detail_carries_author_ref_and_no_identity(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The author is a reference and a role; no account, seat, name or time."""
    batch = public_batch(owner_session, title="HSC Physics", owner_name="Rahim Sir")
    author = account(owner_session)
    seat = guardian_seat(owner_session, batch.batch_id, author, joined_on=None)
    target = add_review(
        owner_session, batch.batch_id, author, enrollment_id=seat, rating=5
    )
    owner_session.execute(
        sa.text("UPDATE review SET body = 'Patient with every child.' WHERE id = :r"),
        {"r": target},
    )
    owner_session.commit()
    _reply(owner_session, target, status="pending", body="Thank you.")
    headers = _admin_headers(owner_session, people, monkeypatch)

    review = api_client.get(
        DETAIL.format(review_id=target), params={"target": "review"}, headers=headers
    )
    reply = api_client.get(
        DETAIL.format(review_id=target), params={"target": "reply"}, headers=headers
    )

    assert review.status_code == 200, review.text
    body = review.json()
    assert set(body) == {
        "target_kind",
        "review_id",
        "rating",
        "body",
        "tenure",
        "author_role",
        "author_ref",
        "status",
        "batch_title",
        "owner_public_name",
        "reply_body",
        "open_reports",
        "waited_hours",
    }
    assert body["author_ref"] == review_author_ref(author)
    assert (body["target_kind"], body["status"], body["rating"]) == (
        "review",
        "pending",
        5,
    )
    assert (body["batch_title"], body["owner_public_name"]) == (
        "HSC Physics",
        "Rahim Sir",
    )
    assert body["body"] == "Patient with every child."
    assert reply.status_code == 200, reply.text
    assert (reply.json()["target_kind"], reply.json()["status"]) == ("reply", "pending")
    assert reply.json()["reply_body"] == "Thank you."
    assert reply.json()["body"] == "Patient with every child."
    phone = phone_of(owner_session, author)
    for text in (review.text, reply.text):
        for secret in (str(author), str(seat), phone, "submitted_at", "display_name"):
            assert secret not in text


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/v1/admin/hub/queue?kind=review", None),
        ("GET", DETAIL + "?target=review", None),
        ("POST", DETAIL + "/decision", {"target": "review", "decision": "approve"}),
    ],
)
def test_queue_review_kind_off_answers_reviews_off(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    """Off: the review queue, the detail and the decision all answer off."""
    monkeypatch.delenv(HUB_REVIEWS_ENV, raising=False)
    batch = public_batch(owner_session)
    target = _reviewed(owner_session, batch.batch_id, "pending")
    headers = _admin_headers(owner_session, people, monkeypatch)

    response = api_client.request(
        method, path.format(review_id=target), json=payload, headers=headers
    )

    assert response.status_code == 404, response.text
    error = response.json()["error"]
    assert (error["code"], error["message_key"]) == (
        "HUB_REVIEWS_OFF",
        "hub.review.off",
    )
    assert _review(owner_session, target).status == "pending"


@pytest.mark.usefixtures("reviews_on")
def test_admin_decision_route_approves_a_review_and_a_reply(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The route answers the target and its new status."""
    batch = public_batch(owner_session)
    target = _published(owner_session, batch.batch_id)[0]
    pending = _reviewed(owner_session, batch.batch_id, "pending")
    _reply(owner_session, target, status="pending")
    headers = _admin_headers(owner_session, people, monkeypatch)

    reply = api_client.post(
        DETAIL.format(review_id=target) + "/decision",
        json={"target": "reply", "decision": "approve"},
        headers=headers,
    )
    review = api_client.post(
        DETAIL.format(review_id=pending) + "/decision",
        json={"target": "review", "decision": "reject", "code": "identifiable_child"},
        headers=headers,
    )
    queue = api_client.get("/v1/admin/hub/queue?kind=review", headers=headers)

    assert reply.status_code == 200, reply.text
    assert reply.json() == {
        "review_id": str(target),
        "target": "reply",
        "status": "published",
    }
    assert review.json() == {
        "review_id": str(pending),
        "target": "review",
        "status": "rejected",
    }
    assert queue.status_code == 200, queue.text
    assert queue.json() == {"kind": "review", "items": []}


@pytest.mark.usefixtures("reviews_on")
def test_error_envelopes(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T6-b: the two new codes, through the admin decision route."""
    batch = public_batch(owner_session)
    published = _published(owner_session, batch.batch_id)[0]
    pending = _reviewed(owner_session, batch.batch_id, "pending")
    headers = _admin_headers(owner_session, people, monkeypatch)
    decide = DETAIL + "/decision"

    decided = api_client.post(
        decide.format(review_id=published),
        json={"target": "review", "decision": "approve"},
        headers=headers,
    )
    no_code = api_client.post(
        decide.format(review_id=pending),
        json={"target": "review", "decision": "reject"},
        headers=headers,
    )
    code_on_approval = api_client.post(
        decide.format(review_id=pending),
        json={"target": "review", "decision": "approve", "code": "other"},
        headers=headers,
    )

    cases = [(decided, 409, "REVIEW_ALREADY_DECIDED", "hub.review.already_decided")]
    cases += [
        (r, 400, "REVIEW_CODE_INVALID", "hub.review.code_invalid")
        for r in (no_code, code_on_approval)
    ]
    for response, status, code, key in cases:
        assert response.status_code == status, response.text
        error = response.json()["error"]
        assert (error["code"], error["message_key"]) == (code, key)
    assert _review(owner_session, pending).status == "pending"
