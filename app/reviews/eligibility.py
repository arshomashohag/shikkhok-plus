"""Who may review a batch: one statement, read as the application role.

**Eligibility is decided in SQL and nowhere else** [spec §6]. The six
conditions are computed per seat inside :data:`ELIGIBILITY_QUERY`, the seat
that stands for the account is chosen there, and the standing is a ``CASE``
there; Python only maps a row to an :class:`Assessment`. A second place that
decided would be a second place to get the predicate wrong.

Conditions 1-3 are **membership**. A caller failing any of them is not told
which, and is not told whether the batch exists: :func:`assess` returns None
for both, and the lens turns None into one ``NOT_AVAILABLE``.

1. the account is the seat's guardian, and accepted the link;
2. the guardian link is not relink-blocked;
3. the batch is public: its listing and its owner's listing published, and
   the batch itself active.

Conditions 4-6 apply to a member, and decide the **standing**:

4. tenure: joined at least 30 days ago, in Bangladesh's calendar;
5. attendance: present at 4 or more distinct, non-cancelled classes of
   this batch;
6. recency: not inactive for more than 180 days.

**Siblings are one reviewer.** A guardian with several children in one
batch is assessed once. The seat standing for them is the eligible one with
the earliest join date; when none is eligible, a seat still inside the
recency window comes before a closed one, so a long-gone child does not
close the batch for a newer sibling; then the earliest join date.

**An author keeps a standing after losing membership** (Call 7): a batch
the account reviewed but is no longer a member of comes back as
``author_only``, so "delete at any time" survives a declined seat or an
unpublished listing.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Literal, cast

import sqlalchemy as sa
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

__all__ = [
    "ELIGIBILITY_QUERY",
    "Assessment",
    "Standing",
    "Tenure",
    "assess",
    "reviewable",
]

#: Where an account stands with one batch.
Standing = Literal["eligible", "not_yet", "closed", "author_only"]

#: How long the evidencing seat has been enrolled; frozen at first submit.
Tenure = Literal["lt_6m", "6_12m", "gt_1y"]

#: Which unmet condition a ``not_yet`` member waits on.
WaitingOn = Literal["tenure", "attendance"]

#: ONE statement: every condition, the seat choice and the standing.
#:
#: ``:batch_id`` NULL means every batch, which is how the reviewable list
#: runs it; the cast lets PostgreSQL type a NULL parameter.
#:
#: ``seat`` applies membership (conditions 1-3) as joins and filters, so a
#: seat failing one never reaches the rest. ``judged`` computes 4-6 per
#: seat. ``evidence`` keeps one seat per batch. The final ``UNION ALL``
#: adds the batches the account reviewed without being a member.
#:
#: The tenure date is ``created_at`` read in Bangladesh when ``joined_on``
#: is unset: a seat created at 20:00 UTC was created the next day there.
ELIGIBILITY_QUERY = sa.text(
    """
    WITH seat AS (
        SELECT e.id AS enrollment_id,
               e.batch_id,
               e.inactive_from,
               COALESCE(e.joined_on,
                        (e.created_at AT TIME ZONE 'Asia/Dhaka')::date) AS joined,
               bl.public_title,
               ol.public_name
        FROM enrollment e
        JOIN batch b ON b.id = e.batch_id AND b.active
        JOIN batch_listing bl
          ON bl.batch_id = e.batch_id AND bl.status = 'published'
        JOIN owner_listing ol
          ON ol.owner_id = b.owner_id AND ol.status = 'published'
        WHERE e.guardian_account_id = :account_id
          AND e.guardian_decision = 'accepted'
          AND e.guardian_relink_blocked_at IS NULL
          AND (CAST(:batch_id AS uuid) IS NULL
               OR e.batch_id = CAST(:batch_id AS uuid))
    ),
    judged AS (
        SELECT seat.*,
               seat.joined <= CAST(:today AS date) - 30 AS tenure_ok,
               (SELECT count(DISTINCT s.id)
                FROM attendance a
                JOIN session s ON s.id = a.session_id
                WHERE a.enrollment_id = seat.enrollment_id
                  AND a.present
                  AND s.batch_id = seat.batch_id
                  AND s.status <> 'cancelled') >= 4 AS attendance_ok,
               (seat.inactive_from IS NULL
                OR seat.inactive_from >= CAST(:today AS date) - 180) AS recent
        FROM seat
    ),
    evidence AS (
        SELECT DISTINCT ON (batch_id) *,
               tenure_ok AND attendance_ok AND recent AS eligible
        FROM judged
        ORDER BY batch_id,
                 (tenure_ok AND attendance_ok AND recent) DESC,
                 recent DESC,
                 joined,
                 enrollment_id
    )
    SELECT ev.batch_id,
           COALESCE(ev.public_title, '') AS batch_title,
           ev.public_name AS owner_public_name,
           ev.enrollment_id,
           r.id AS review_id,
           CASE WHEN ev.eligible THEN 'eligible'
                WHEN NOT ev.recent THEN 'closed'
                ELSE 'not_yet' END AS standing,
           CASE WHEN ev.eligible OR NOT ev.recent THEN NULL
                WHEN NOT ev.attendance_ok THEN 'attendance'
                ELSE 'tenure' END AS waiting_on,
           CASE WHEN ev.recent AND NOT ev.tenure_ok
                THEN ev.joined + 30 END AS eligible_from,
           CASE WHEN ev.joined + interval '6 months' > CAST(:today AS date)
                THEN 'lt_6m'
                WHEN ev.joined + interval '12 months' > CAST(:today AS date)
                THEN '6_12m'
                ELSE 'gt_1y' END AS tenure
    FROM evidence ev
    LEFT JOIN review r
      ON r.batch_id = ev.batch_id AND r.author_account_id = :account_id
    UNION ALL
    SELECT r.batch_id,
           COALESCE(bl.public_title, '') AS batch_title,
           COALESCE(ol.public_name, '') AS owner_public_name,
           NULL AS enrollment_id,
           r.id AS review_id,
           'author_only' AS standing,
           NULL AS waiting_on,
           NULL AS eligible_from,
           NULL AS tenure
    FROM review r
    JOIN batch_listing bl ON bl.batch_id = r.batch_id
    LEFT JOIN owner_listing ol ON ol.owner_id = bl.owner_id
    WHERE r.author_account_id = :account_id
      AND (CAST(:batch_id AS uuid) IS NULL
           OR r.batch_id = CAST(:batch_id AS uuid))
      AND NOT EXISTS (SELECT 1 FROM seat WHERE seat.batch_id = r.batch_id)
    ORDER BY batch_title, batch_id
    """
)


@dataclass(frozen=True, slots=True)
class Assessment:
    """Where one account stands with one batch.

    :ivar batch_id: The batch
    :ivar batch_title: Its public title (``batch_listing.public_title``),
        never the teacher's own ``batch.name``
    :ivar owner_public_name: The owner listing's public name
    :ivar enrollment_id: The seat standing for the account, or None for an
        author who is no longer a member
    :ivar review_id: The account's review of the batch, if it wrote one
    :ivar standing: ``eligible``, ``not_yet``, ``closed`` or ``author_only``
    :ivar waiting_on: For ``not_yet``, the unmet condition the refusal
        names; attendance when both tenure and attendance are unmet
    :ivar eligible_from: The day tenure is met, whenever a ``not_yet``
        member has not met it yet [F20]
    :ivar tenure: The evidencing seat's tenure bucket, for a member
    """

    batch_id: uuid.UUID
    batch_title: str
    owner_public_name: str
    enrollment_id: uuid.UUID | None
    review_id: uuid.UUID | None
    standing: Standing
    waiting_on: WaitingOn | None
    eligible_from: dt.date | None
    tenure: Tenure | None


def _assessment(row: Row[tuple[object, ...]]) -> Assessment:
    """Map one statement row to an assessment.

    :param row: A row of :data:`ELIGIBILITY_QUERY`
    :return: The assessment
    """
    return Assessment(
        batch_id=cast("uuid.UUID", row.batch_id),
        batch_title=cast("str", row.batch_title),
        owner_public_name=cast("str", row.owner_public_name),
        enrollment_id=cast("uuid.UUID | None", row.enrollment_id),
        review_id=cast("uuid.UUID | None", row.review_id),
        standing=cast("Standing", row.standing),
        waiting_on=cast("WaitingOn | None", row.waiting_on),
        eligible_from=cast("dt.date | None", row.eligible_from),
        tenure=cast("Tenure | None", row.tenure),
    )


def _run(
    session: Session,
    account_id: uuid.UUID,
    batch_id: uuid.UUID | None,
    today: dt.date,
) -> list[Assessment]:
    """Run the statement once.

    :param session: The session to query through
    :param account_id: The account being assessed
    :param batch_id: One batch, or None for all
    :param today: Bangladesh's date
    :return: One assessment per batch, ordered by title
    """
    rows = session.execute(
        ELIGIBILITY_QUERY,
        {"account_id": account_id, "batch_id": batch_id, "today": today},
    ).all()
    return [_assessment(row) for row in rows]


def assess(
    session: Session,
    account_id: uuid.UUID,
    batch_id: uuid.UUID,
    today: dt.date,
) -> Assessment | None:
    """Assess one account against one batch.

    :param session: The session to query through
    :param account_id: The account being assessed
    :param batch_id: The batch
    :param today: Bangladesh's date, from ``bangladesh_today()``
    :return: The assessment, or None for a non-member who wrote no review
        of the batch -- including when the batch does not exist
    """
    found = _run(session, account_id, batch_id, today)
    return found[0] if found else None


def reviewable(
    session: Session,
    account_id: uuid.UUID,
    today: dt.date,
    *,
    include_open: bool,
) -> list[Assessment]:
    """List the batches an account may review or has reviewed.

    The standing is already decided by the statement; this only chooses
    which rows a list shows.

    :param session: The session to query through
    :param account_id: The account
    :param today: Bangladesh's date
    :param include_open: Whether to list batches the account could review
        or is waiting to (``eligible`` and ``not_yet``); False while the
        reviews switch is off, leaving only batches it already reviewed
    :return: The rows, ordered by batch title; a ``closed`` batch the
        account never reviewed is never listed
    """
    open_standings = ("eligible", "not_yet") if include_open else ()
    return [
        row
        for row in _run(session, account_id, None, today)
        if row.review_id is not None or row.standing in open_standings
    ]
