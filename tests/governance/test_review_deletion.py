"""Reviews go totally with their author, or with a solo teacher's listing.

**A guardian's deletion forgets every review they wrote**: the review, the
reply to it and every report on either, filed by anyone. **A solo teacher's
deletion forgets every review of their listed classes** the same way,
before the listings go; the ``batch_listing -> review`` cascade would
otherwise remove the reviews behind :func:`app.reviews.forget.forget`'s
back and leave the reports naming them [T7-f]. So every test here ends by
asserting that no ``hub_report`` row names a review or a reply that no
longer exists.

**A coaching centre's reviews and replies outlive a manager**, the reply
no longer saying who wrote it. ``hub_moderation_event`` rows survive as
bare ids and closed codes.

The deletion runs as the application role, with the reviews switch off
(its default): the switch never gates a deletion.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.governance.deletion import delete_account
from app.hub.public.invalidation import owner_paths
from app.local_time import bangladesh_today
from tests.reviews.support import (
    PublicBatch,
    account,
    add_review,
    public_batch,
    public_centre_batch,
    second_batch,
)

#: Reports naming a review or a reply that no longer exists; a reply's
#: id is its review's.
_ORPHAN_REPORTS = sa.text(
    """
    SELECT count(*) FROM hub_report h
    WHERE (h.target_kind = 'review'
           AND NOT EXISTS (SELECT 1 FROM review r WHERE r.id = h.target_id))
       OR (h.target_kind = 'reply'
           AND NOT EXISTS (SELECT 1 FROM review_reply p
                           WHERE p.review_id = h.target_id))
    """
)


def _phone(session: Session, account_id: uuid.UUID) -> str:
    """Read an account's number.

    :param session: A session
    :param account_id: The account
    :return: Its phone number
    """
    return str(
        session.execute(
            sa.text("SELECT phone FROM account WHERE id = :a"), {"a": account_id}
        ).scalar_one()
    )


def _publish(session: Session, review_id: uuid.UUID) -> None:
    """Publish a review this month.

    :param session: An arranging session
    :param review_id: The review
    :return: None
    """
    session.execute(
        sa.text(
            "UPDATE review SET status = 'published', published_month = :m WHERE id = :r"
        ),
        {"m": bangladesh_today().replace(day=1), "r": review_id},
    )
    session.commit()


def _reply(session: Session, review_id: uuid.UUID, writer: uuid.UUID) -> None:
    """Give a review a published reply.

    :param session: An arranging session
    :param review_id: The review
    :param writer: The account that wrote the reply
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO review_reply (review_id, body, status, published_month, "
            "written_by_account_id) VALUES (:r, 'Thank you', 'published', :m, :w)"
        ),
        {"r": review_id, "m": bangladesh_today().replace(day=1), "w": writer},
    )
    session.commit()


def _report(
    session: Session, kind: str, target: uuid.UUID, reporter: uuid.UUID
) -> None:
    """File an open report.

    :param session: An arranging session
    :param kind: ``review`` or ``reply``
    :param target: The review's id, for either kind
    :param reporter: The reporting account
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO hub_report (id, target_kind, target_id, "
            "reporter_account_id, reason) VALUES (gen_random_uuid(), "
            "CAST(:k AS hub_report_target), :t, :a, 'other')"
        ),
        {"k": kind, "t": target, "a": reporter},
    )
    session.commit()


def _reviewed(
    session: Session, batch: PublicBatch, author: uuid.UUID, *, published: bool
) -> uuid.UUID:
    """Arrange a review with a reply and a report on each by someone else.

    :param session: An arranging session
    :param batch: The reviewed batch
    :param author: The review's author
    :param published: Publish the review rather than leave it pending
    :return: The review id
    """
    review_id = add_review(session, batch.batch_id, author)
    if published:
        _publish(session, review_id)
    _reply(session, review_id, batch.teacher_account_id)
    reporter = account(session)
    _report(session, "review", review_id, reporter)
    _report(session, "reply", review_id, reporter)
    return review_id


def _over_threshold(session: Session, batch_id: uuid.UUID) -> list[uuid.UUID]:
    """Publish three reviews by other guardians, so the batch shows reviews.

    :param session: An arranging session
    :param batch_id: The batch
    :return: The three review ids
    """
    ids = [add_review(session, batch_id, account(session)) for _ in range(3)]
    for review_id in ids:
        _publish(session, review_id)
    return ids


def _scalar(session: Session, sql: str, **params: object) -> int:
    """Run a count in a fresh transaction.

    :param session: An arranging session
    :param sql: The count
    :param params: Its parameters
    :return: The count
    """
    session.rollback()
    return int(session.execute(sa.text(sql), params).scalar_one())


def _orphans(session: Session) -> int:
    """Count reports naming a review or reply that is gone.

    :param session: An arranging session
    :return: The count
    """
    session.rollback()
    return int(session.execute(_ORPHAN_REPORTS).scalar_one())


def _reports_on(session: Session, review_ids: list[uuid.UUID]) -> int:
    """Count reports on some reviews or their replies.

    :param session: An arranging session
    :param review_ids: The reviews
    :return: The count
    """
    return _scalar(
        session,
        "SELECT count(*) FROM hub_report WHERE target_kind IN ('review', 'reply') "
        "AND target_id = ANY(:ids)",
        ids=review_ids,
    )


def _slug(session: Session, owner_id: uuid.UUID) -> str:
    """Read an owner listing's slug.

    :param session: An arranging session
    :param owner_id: The owner
    :return: The slug
    """
    return str(
        session.execute(
            sa.text("SELECT slug FROM owner_listing WHERE owner_id = :o"),
            {"o": owner_id},
        ).scalar_one()
    )


def _paths(session: Session) -> set[str]:
    """Read every queued edge-cache path.

    :param session: An arranging session
    :return: The paths
    """
    session.rollback()
    return set(session.scalars(sa.text("SELECT path FROM cdn_invalidation")))


def test_guardian_account_deletion_removes_reviews_replies_and_reports_on_them(
    owner_session: Session, restricted_session: Session
) -> None:
    one, two = public_batch(owner_session), public_batch(owner_session)
    others = _over_threshold(owner_session, one.batch_id)
    _reply(owner_session, others[0], one.teacher_account_id)
    bystander = account(owner_session)
    _report(owner_session, "review", others[0], bystander)
    _report(owner_session, "reply", others[0], bystander)
    guardian = account(owner_session)
    mine = [
        _reviewed(owner_session, one, guardian, published=True),
        _reviewed(owner_session, two, guardian, published=False),
    ]

    delete_account(restricted_session, _phone(owner_session, guardian))

    assert (
        _scalar(owner_session, "SELECT count(*) FROM review WHERE id = ANY(:i)", i=mine)
        == 0
    )
    assert (
        _scalar(
            owner_session,
            "SELECT count(*) FROM review_reply WHERE review_id = ANY(:i)",
            i=mine,
        )
        == 0
    )
    assert _reports_on(owner_session, mine) == 0
    assert _orphans(owner_session) == 0
    # Nobody else's review, reply or report went with them.
    assert (
        _scalar(
            owner_session, "SELECT count(*) FROM review WHERE id = ANY(:i)", i=others
        )
        == 3
    )
    assert (
        _scalar(
            owner_session,
            "SELECT count(*) FROM review_reply WHERE review_id = :r",
            r=others[0],
        )
        == 1
    )
    assert _reports_on(owner_session, others) == 2


def test_guardian_deletion_removes_reports_they_filed(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    target = add_review(owner_session, batch.batch_id, account(owner_session))
    _publish(owner_session, target)
    _reply(owner_session, target, batch.teacher_account_id)
    guardian, other = account(owner_session), account(owner_session)
    for reporter in (guardian, other):
        _report(owner_session, "review", target, reporter)
        _report(owner_session, "reply", target, reporter)

    delete_account(restricted_session, _phone(owner_session, guardian))

    assert (
        _scalar(
            owner_session,
            "SELECT count(*) FROM hub_report WHERE reporter_account_id = :a",
            a=guardian,
        )
        == 0
    )
    assert (
        _scalar(
            owner_session,
            "SELECT count(*) FROM hub_report WHERE reporter_account_id = :a "
            "AND target_id = :t",
            a=other,
            t=target,
        )
        == 2
    )
    assert _orphans(owner_session) == 0


def test_solo_owner_deletion_removes_their_batches_reviews_and_reports_on_them(
    owner_session: Session, restricted_session: Session
) -> None:
    solo = public_batch(owner_session)
    other_batch = second_batch(owner_session, solo.owner_id, title="SSC Chemistry")
    elsewhere = public_batch(owner_session)
    theirs = [
        *_over_threshold(owner_session, solo.batch_id),
        _reviewed(owner_session, solo, account(owner_session), published=True),
        _reviewed(
            owner_session,
            PublicBatch(solo.owner_id, solo.teacher_account_id, other_batch),
            account(owner_session),
            published=False,
        ),
    ]
    kept = _reviewed(owner_session, elsewhere, account(owner_session), published=True)

    delete_account(restricted_session, _phone(owner_session, solo.teacher_account_id))

    assert (
        _scalar(
            owner_session, "SELECT count(*) FROM review WHERE id = ANY(:i)", i=theirs
        )
        == 0
    )
    assert _reports_on(owner_session, theirs) == 0
    assert _orphans(owner_session) == 0
    assert _scalar(owner_session, "SELECT count(*) FROM review_reply") == 1
    assert _reports_on(owner_session, [kept]) == 2


def test_centre_reviews_and_replies_survive_manager_deletion_with_writer_cleared(
    owner_session: Session, restricted_session: Session
) -> None:
    centre = public_centre_batch(owner_session)
    reviews = _over_threshold(owner_session, centre.batch_id)
    _reply(owner_session, reviews[0], centre.teacher_account_id)
    reporter = account(owner_session)
    _report(owner_session, "review", reviews[0], reporter)
    _report(owner_session, "reply", reviews[0], reporter)

    delete_account(restricted_session, _phone(owner_session, centre.teacher_account_id))

    assert (
        _scalar(
            owner_session, "SELECT count(*) FROM review WHERE id = ANY(:i)", i=reviews
        )
        == 3
    )
    writer = owner_session.execute(
        sa.text(
            "SELECT body, status::text, written_by_account_id FROM review_reply "
            "WHERE review_id = :r"
        ),
        {"r": reviews[0]},
    ).one()
    assert tuple(writer) == ("Thank you", "published", None)
    assert _reports_on(owner_session, reviews) == 2
    assert _orphans(owner_session) == 0


def test_visible_review_deletion_enqueues_invalidation(
    owner_session: Session, restricted_session: Session
) -> None:
    shown, unshown = public_batch(owner_session), public_batch(owner_session)
    _over_threshold(owner_session, shown.batch_id)
    guardian = account(owner_session)
    _reviewed(owner_session, shown, guardian, published=True)
    # Below the threshold: published, but on no public page.
    _reviewed(owner_session, unshown, guardian, published=True)
    owner_session.execute(sa.text("DELETE FROM cdn_invalidation"))
    owner_session.commit()

    delete_account(restricted_session, _phone(owner_session, guardian))

    paths = _paths(owner_session)
    assert set(owner_paths(_slug(owner_session, shown.owner_id))) <= paths
    assert not set(owner_paths(_slug(owner_session, unshown.owner_id))) & paths


def test_pending_review_deletion_enqueues_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    _over_threshold(owner_session, batch.batch_id)
    guardian = account(owner_session)
    _reviewed(owner_session, batch, guardian, published=False)
    owner_session.execute(sa.text("DELETE FROM cdn_invalidation"))
    owner_session.commit()

    delete_account(restricted_session, _phone(owner_session, guardian))

    assert _paths(owner_session) == set()


def test_moderation_events_survive_as_bare_ids(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    review_id = _reviewed(owner_session, batch, guardian, published=True)
    for kind in ("review", "reply"):
        owner_session.execute(
            sa.text(
                "INSERT INTO hub_moderation_event (id, event, target_kind, "
                "target_id, correlation_id) VALUES (gen_random_uuid(), "
                "'report_filed', CAST(:k AS hub_report_target), :r, 'c-1')"
            ),
            {"k": kind, "r": review_id},
        )
    owner_session.commit()

    delete_account(restricted_session, _phone(owner_session, guardian))

    owner_session.rollback()
    events = owner_session.execute(
        sa.text(
            "SELECT target_kind::text, event::text, actor_admin_account_id, "
            "decision_code FROM hub_moderation_event WHERE target_id = :r "
            "ORDER BY target_kind"
        ),
        {"r": review_id},
    ).all()
    assert [tuple(e) for e in events] == [
        ("reply", "report_filed", None, None),
        ("review", "report_filed", None, None),
    ]
    assert (
        _scalar(owner_session, "SELECT count(*) FROM review WHERE id = :r", r=review_id)
        == 0
    )
    assert _orphans(owner_session) == 0
