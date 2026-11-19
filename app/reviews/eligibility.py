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
close the batch for a newer sibling; among waiting seats, one lacking only
tenure comes first, so its known ``eligible_from`` is never hidden; then
the earliest join date.

**Nobody who runs the batch reviews it** [T3-c]: its owner, its managers
and its assigned teachers are refused as non-members, revealing nothing.

**An author keeps a standing after losing membership** (Call 7): a batch
the account reviewed but is no longer a member of comes back as
``author_only``, so "delete at any time" survives a declined seat or an
unpublished listing.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from dataclasses import dataclass
from typing import Final, Literal, cast

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
    "runs_batch_sql",
]

#: Where an account stands with one batch.
Standing = Literal["eligible", "not_yet", "closed", "author_only"]

#: How long the evidencing seat has been enrolled; frozen at first submit.
Tenure = Literal["lt_6m", "6_12m", "gt_1y"]

#: Which unmet condition a ``not_yet`` member waits on.
WaitingOn = Literal["tenure", "attendance"]

#: What :func:`runs_batch_sql` accepts as an operand: a column, a qualified
#: column or a bound parameter, never anything a caller typed.
_OPERAND: Final = re.compile(r"^:?[a-z_]+(?:\.[a-z_]+)?$")


def runs_batch_sql(batch_id: str, account_id: str) -> str:
    """Write the SQL predicate "this account runs this batch" [T3-c, F10].

    **The one definition of who runs a batch**, shared by eligibility (who
    may not review it) and by moderation (whose report holds nothing, and
    keeps nothing held), so the two sets cannot drift apart [I-2]. Running
    it means being any of:

    * the owner's own account (a solo tutor);
    * an accepted, unrevoked manager of the owner;
    * an accepted, unrevoked member assigned to teach this batch, by a
      weekly slot or by a single class.

    All three set ``joined_on``, mark attendance or control the seat, so
    they could otherwise be a "verified guardian" of their own batch, or
    take its reviews down at once with a report.

    The predicate is an ``EXISTS``, so it is true or false and never NULL,
    and its aliases are prefixed ``rb_`` so it nests inside any statement.

    :param batch_id: A SQL expression naming the batch, e.g. ``e.batch_id``
    :param account_id: A SQL expression naming the account, e.g.
        ``:account_id`` or ``h.reporter_account_id``
    :return: The predicate, to embed in a statement
    :raises ValueError: An operand that is not a plain column or parameter
    """
    for operand in (batch_id, account_id):
        if not _OPERAND.match(operand):
            msg = f"not a column or parameter: {operand!r}"
            raise ValueError(msg)
    return f"""EXISTS (
        SELECT 1
        FROM batch rb_batch
        JOIN owner rb_owner ON rb_owner.id = rb_batch.owner_id
        WHERE rb_batch.id = {batch_id}
          AND (rb_owner.account_id = {account_id}
               OR EXISTS (
                   SELECT 1 FROM owner_member rb_member
                   WHERE rb_member.owner_id = rb_batch.owner_id
                     AND rb_member.account_id = {account_id}
                     AND rb_member.decision = 'accepted'
                     AND rb_member.revoked_at IS NULL
                     AND (rb_member.role = 'manager'
                          OR EXISTS (
                              SELECT 1 FROM schedule_slot rb_slot
                              WHERE rb_slot.batch_id = rb_batch.id
                                AND rb_slot.teacher_member_id = rb_member.id)
                          OR EXISTS (
                              SELECT 1 FROM session rb_class
                              WHERE rb_class.batch_id = rb_batch.id
                                AND rb_class.teacher_member_id = rb_member.id)))))"""  # noqa: S608  module constants, never input


#: ONE statement: every condition, the seat choice and the standing.
#:
#: ``:batch_id`` NULL means every batch, which is how the reviewable list
#: runs it; the cast lets PostgreSQL type a NULL parameter.
#:
#: ``seat`` applies membership (conditions 1-3) as joins and filters, so a
#: seat failing one never reaches the rest. It also refuses membership to
#: anyone who runs the batch [T3-c], as :func:`runs_batch_sql` defines it.
#:
#: ``judged`` computes 4-6 per seat. ``evidence`` keeps one seat per batch:
#: eligible first; then one still inside the recency window; then, among
#: waiting seats, one lacking only tenure [T3-g]; then the earliest join,
#: which among seats lacking only tenure is the earliest ``eligible_from``,
#: so a known date is never hidden [T3-d]. The final ``UNION ALL`` adds the
#: batches the account reviewed without being a member.
#:
#: ``eligible_from`` is set **only when tenure alone is unmet** [FR-c,
#: revising F20]: for a seat still short of classes, day 30 is not a day
#: the family can review on, so no date is given at all.
#:
#: The tenure date is ``created_at`` read in Bangladesh when ``joined_on``
#: is unset: a seat created at 20:00 UTC was created the next day there.
ELIGIBILITY_QUERY = sa.text(
    f"""
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
          AND NOT {runs_batch_sql("e.batch_id", ":account_id")}
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
                 attendance_ok DESC,
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
           CASE WHEN ev.recent AND ev.attendance_ok AND NOT ev.tenure_ok
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
    """  # noqa: S608  module constants, never input
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
    :ivar eligible_from: The day tenure is met, only for a ``not_yet``
        member who lacks tenure alone [FR-c]; None while classes are also
        still needed
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
